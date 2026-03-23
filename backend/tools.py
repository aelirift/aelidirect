"""
Tools — functions the LLM can ask to call.

Each tool has:
  1. A DEFINITION (JSON schema) — sent to the LLM so it knows the tool exists
  2. An EXECUTOR (Python function) — runs on YOUR machine when the LLM asks for it

The LLM NEVER runs these functions. It just says "please call list_files with path=."
and YOUR code executes it and sends the result back.
"""

import os
from pathlib import Path
from constants import (
    PROJECTS_ROOT, BRANCH_ROOT, PLATFORM_PROJECT_NAME, PROD_ROOT,
    READ_PROJECT_BUDGET, READ_FILE_TRUNCATE, FILE_TAIL_LINES,
    CODE_EXTENSIONS, SKIP_DIRS, SAFE_NAME_MAX_LENGTH,
)

# ─── Project directories ────────────────────────────────────────────
# PROJECTS_ROOT imported from constants
_SAFE_ROOTS = [
    PROD_ROOT.resolve(),  # aelidirect/
]

_active_project_dir = {"path": None}

# ─── Dual file cache (main + branch) ──────────────────────────────────
# Two caches for platform editing:
#   main_cache: reflects prod files (source of truth)
#   branch_cache: reflects what the agent has edited (diverges from prod)
# Non-platform projects use main_cache only.
_file_cache_main = {}      # (resolved_project, rel_path) -> content
_file_cache_branch = {}    # same key format, for branch edits
_file_cache_mtime = {}     # tracks disk mtime for cache invalidation

# BRANCH_ROOT and PLATFORM_PROJECT_NAME imported from constants


def _cache_key(project: Path, path: str) -> tuple:
    return (str(project.resolve()), path)


def _is_platform_project(project: Path) -> bool:
    """Check if this project dir is the platform self-editing project."""
    return project.name == PLATFORM_PROJECT_NAME or project.resolve() == BRANCH_ROOT.resolve()


def file_cache_get(project: Path, path: str) -> str | None:
    """Get cached file content. Uses branch cache for platform project."""
    key = _cache_key(project, path)
    if _is_platform_project(project):
        return _file_cache_branch.get(key)
    return _file_cache_main.get(key)


def file_cache_set(project: Path, path: str, content: str):
    """Set cached file content. Updates branch cache for platform project."""
    key = _cache_key(project, path)
    if _is_platform_project(project):
        _file_cache_branch[key] = content
    else:
        _file_cache_main[key] = content


def file_cache_set_main(project: Path, path: str, content: str):
    """Directly set main cache (used during init/wipe)."""
    _file_cache_main[_cache_key(project, path)] = content


def file_cache_wipe_branch():
    """Copy main cache → branch cache (called on branch wipe)."""
    _file_cache_branch.clear()
    _file_cache_branch.update(_file_cache_main)


def file_cache_deploy_to_main():
    """Copy branch cache → main cache (called on successful deploy)."""
    # Only copy platform-related entries
    for key, content in _file_cache_branch.items():
        _file_cache_main[key] = content


def file_cache_clear(project: Path = None):
    """Clear both caches for a project, or all if None."""
    if project is None:
        _file_cache_main.clear()
        _file_cache_branch.clear()
        _file_cache_mtime.clear()
    else:
        prefix = str(project.resolve())
        for cache in (_file_cache_main, _file_cache_branch, _file_cache_mtime):
            keys = [k for k in cache if k[0] == prefix]
            for k in keys:
                del cache[k]


def _is_safe_path(target: Path, project: Path) -> bool:
    """Check if target is within the project dir OR a known safe symlink root."""
    resolved = target.resolve()
    # Check project dir (without resolving symlinks on the project side)
    try:
        resolved.relative_to(project.resolve())
        return True
    except ValueError:
        pass
    # Check safe roots (for symlinked projects like aelidirect_platform)
    for safe_root in _SAFE_ROOTS:
        try:
            resolved.relative_to(safe_root)
            return True
        except ValueError:
            pass
    return False


def set_active_project(project_dir: Path):
    _active_project_dir["path"] = project_dir


def get_active_project() -> Path:
    return _active_project_dir["path"] or PROJECTS_ROOT


def init_project_dir(project_dir: Path):
    """Initialize a new project directory with starter files and project_env.md."""
    project_dir.mkdir(parents=True, exist_ok=True)
    readme = project_dir / "README.md"
    if not readme.exists():
        readme.write_text(f"# {project_dir.name}\n\nGenerated project.\n")
    main_py = project_dir / "main.py"
    if not main_py.exists():
        main_py.write_text(
            'from fastapi import FastAPI\n\napp = FastAPI()\n\n'
            '@app.get("/")\ndef root():\n    return {"message": "Hello World"}\n\n'
            '@app.get("/health")\ndef health():\n    return {"status": "ok"}\n'
        )


def write_project_env(project_dir: Path, project_name: str, tech_stack: str = "auto", extra: dict | None = None):
    """Write project_env.md with project metadata."""
    import platform
    env_path = project_dir / "project_env.md"

    lines = [
        "# Project Environment",
        "",
        "## Project Identity",
        f"| Property | Value |",
        f"|----------|-------|",
        f"| Project Name | {project_name} |",
        f"| Project Dir | {project_dir.name} |",
        f"| Tech Stack | {tech_stack} |",
        f"| OS | {platform.system()} {platform.release()} |",
        f"| Python | {platform.python_version()} |",
        "",
    ]

    if extra:
        lines.append("## Additional Context")
        for k, v in extra.items():
            lines.append(f"| {k} | {v} |")
        lines.append("")

    env_path.write_text("\n".join(lines))


def read_project_env(project_dir: Path) -> dict:
    """Read project_env.md and return parsed metadata."""
    env_path = project_dir / "project_env.md"
    result = {}
    if not env_path.exists():
        return result
    for line in env_path.read_text().splitlines():
        if line.startswith("|") and "|" in line[1:]:
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if len(parts) == 2 and parts[0] not in ("Property", "--------"):
                key = parts[0].lower().replace(" ", "_")
                result[key] = parts[1]
    return result


def rename_project(project_dir: Path, new_name: str):
    """Update the project name in project_env.md."""
    env = read_project_env(project_dir)
    tech_stack = env.get("tech_stack", "auto")
    extra = {k: v for k, v in env.items() if k not in ("project_name", "project_dir", "tech_stack", "os", "python")}
    write_project_env(project_dir, new_name, tech_stack, extra if extra else None)


# ═══════════════════════════════════════════════════════════════════════
# TOOL DEFINITIONS — these get sent to the LLM as JSON schemas
# The LLM reads these to know what tools are available.
# ═══════════════════════════════════════════════════════════════════════

# READ_PROJECT_BUDGET, CODE_EXTENSIONS, SKIP_DIRS imported from constants


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List all files in the project directory. Returns file names and sizes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Subdirectory to list (relative to project root). Use '.' for root.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root (e.g. 'main.py')",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit_file",
            "description": (
                "Create a NEW file or FULLY REWRITE a file. Use ONLY for creating new files. "
                "For modifying existing files, use patch_file instead — it's safer and faster."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root",
                    },
                    "content": {
                        "type": "string",
                        "description": "The complete new content for the file",
                    },
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "patch_file",
            "description": (
                "Make a targeted edit to an existing file. Finds old_text and replaces it with "
                "new_text. Only sends the changed part — much safer than rewriting the whole file. "
                "Use this for ALL modifications to existing files. The old_text must be an exact "
                "match of text currently in the file (copy it from read_file output)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root",
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Exact text to find in the file (must match exactly)",
                    },
                    "new_text": {
                        "type": "string",
                        "description": "Text to replace it with",
                    },
                },
                "required": ["path", "old_text", "new_text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file_tail",
            "description": (
                "Read the LAST N lines of a file. Use this when read_file shows a file is truncated "
                "and you need to see the end — e.g., to check if a file ends abruptly (missing closing tags, "
                "truncated code). Default: last 50 lines."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root",
                    },
                    "lines": {
                        "type": "integer",
                        "description": "Number of lines from the end (default: 50)",
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_lines",
            "description": (
                "Read a specific range of lines from a file. More efficient than read_file for "
                "large files — read only the section you need. Lines are 1-indexed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path relative to project root",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Starting line number (1-indexed, inclusive)",
                    },
                    "end": {
                        "type": "integer",
                        "description": "Ending line number (inclusive)",
                    },
                },
                "required": ["path", "start", "end"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep_code",
            "description": (
                "Search all project files for a pattern (case-insensitive). Returns matching lines "
                "with file path and line number. Use to verify code patterns exist, find function "
                "definitions, or confirm fixes were applied."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Text or pattern to search for (case-insensitive)",
                    },
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_project",
            "description": (
                "Read ALL source code files in the project at once. Returns every file concatenated "
                "with headers. For small projects this gives you complete context in one call. "
                "For large projects (over budget), returns a file listing with sizes instead — "
                "you then use read_file/read_lines on specific files. "
                "Skips: venv, node_modules, __pycache__, .git, .td_reports, binary files."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════════════
# TOOL EXECUTORS — these run on YOUR machine (never on the LLM server)
# ═══════════════════════════════════════════════════════════════════════

def execute_tool(name: str, arguments: dict, project_dir: Path = None) -> str:
    """Execute a tool by name and return the result as a string.

    project_dir: explicit project directory. If None, falls back to legacy global.
    All pipeline/direct calls MUST pass project_dir explicitly.
    """
    pd = project_dir or get_active_project()
    if name == "list_files":
        return _tool_list_files(pd, arguments.get("path", "."))
    elif name == "read_file":
        return _tool_read_file(pd, arguments.get("path", ""))
    elif name == "edit_file":
        return _tool_edit_file(pd, arguments.get("path", ""), arguments.get("content", ""))
    elif name == "patch_file":
        return _tool_patch_file(
            pd,
            arguments.get("path", ""),
            arguments.get("old_text", ""),
            arguments.get("new_text", ""),
        )
    elif name == "read_file_tail":
        return _tool_read_file_tail(pd, arguments.get("path", ""), arguments.get("lines", 50))
    elif name == "read_lines":
        return _tool_read_lines(pd, arguments.get("path", ""), arguments.get("start", 1), arguments.get("end", 50))
    elif name == "grep_code":
        return _tool_grep_code(pd, arguments.get("pattern", ""))
    elif name == "read_project":
        return _tool_read_project(pd)
    else:
        return f"Unknown tool: {name}"


def _tool_list_files(project: Path, path: str) -> str:
    """List files in the project."""
    target = project / path
    if not target.exists():
        return f"Directory not found: {path}"

    if not _is_safe_path(target, project):
        return "Access denied: path outside project"

    files = []
    for item in sorted(target.iterdir()):
        if item.name.startswith("."):
            continue
        size = item.stat().st_size if item.is_file() else 0
        kind = "file" if item.is_file() else "dir"
        files.append(f"  {item.name} ({kind}, {size} bytes)")

    return f"Files in {path}/:\n" + "\n".join(files) if files else f"Empty directory: {path}/"


def _tool_read_file(project: Path, path: str) -> str:
    """Read a file from the project. Returns from cache if available."""
    target = project / path
    if not _is_safe_path(target, project):
        return "Access denied: path outside project"

    if not target.exists():
        return f"File not found: {path}"
    if not target.is_file():
        return f"Not a file: {path}"

    # Check cache — if file hasn't changed on disk, return cached
    cached = file_cache_get(project, path)
    disk_mtime = target.stat().st_mtime
    cache_key = _cache_key(project, path)
    if cached is not None and _file_cache_mtime.get(cache_key) == disk_mtime:
        content = cached
    else:
        content = target.read_text()
        file_cache_set(project, path, content)
        _file_cache_mtime[cache_key] = disk_mtime

    if len(content) > READ_FILE_TRUNCATE:
        lines = content.splitlines()
        total_lines = len(lines)
        last_lines = "\n".join(lines[-FILE_TAIL_LINES:])
        content = (
            content[:READ_FILE_TRUNCATE] +
            f"\n\n... TRUNCATED (showing first {READ_FILE_TRUNCATE} of {len(content)} chars, {total_lines} total lines)\n"
            f"Use read_file_tail to see the end of this file.\n\n"
            f"=== LAST 20 LINES ===\n{last_lines}"
        )
    return content


def _tool_edit_file(project: Path, path: str, content: str) -> str:
    """Create or overwrite a file in the project."""
    target = project / path
    if not _is_safe_path(target, project):
        return "Access denied: path outside project"

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    # Update cache with new content
    file_cache_set(project, path, content)
    _file_cache_mtime[_cache_key(project, path)] = target.stat().st_mtime
    return f"File written: {path} ({len(content)} chars)"


def _tool_patch_file(project: Path, path: str, old_text: str, new_text: str) -> str:
    """Make a targeted edit to an existing file — find old_text, replace with new_text."""
    target = project / path
    if not _is_safe_path(target, project):
        return "Access denied: path outside project"

    if not target.exists():
        return f"File not found: {path}. Use edit_file to create new files."
    if not target.is_file():
        return f"Not a file: {path}"

    if not old_text:
        return "Error: old_text is empty. Provide the exact text to replace."
    if old_text == new_text:
        return "Error: old_text and new_text are identical. No change needed."

    content = target.read_text()

    # Exact match
    count = content.count(old_text)
    if count == 1:
        new_content = content.replace(old_text, new_text, 1)
        target.write_text(new_content)
        # Update cache with patched content
        file_cache_set(project, path, new_content)
        _file_cache_mtime[_cache_key(project, path)] = target.stat().st_mtime
        old_lines = old_text.count('\n') + 1
        new_lines = new_text.count('\n') + 1
        return f"Patched {path}: replaced {old_lines} lines with {new_lines} lines ({len(new_content)} chars total)"

    if count == 0:
        # No exact match — try to help the LLM fix it
        # Show nearby text for context
        # Try stripped match (whitespace differences)
        stripped_old = old_text.strip()
        if stripped_old and stripped_old in content:
            # Found with different whitespace
            return (
                f"Error: exact match not found in {path}, but a whitespace-trimmed match exists. "
                f"Copy the text exactly as shown by read_file, including indentation."
            )

        # Show the first 200 chars around where it might be
        # Search for first line of old_text
        first_line = old_text.strip().split('\n')[0].strip()
        if first_line and first_line in content:
            idx = content.index(first_line)
            context_start = max(0, idx - 50)
            context_end = min(len(content), idx + len(first_line) + 100)
            nearby = content[context_start:context_end]
            return (
                f"Error: exact match not found in {path}. "
                f"Found the first line '{first_line[:60]}' near position {idx}. "
                f"Nearby text:\n---\n{nearby}\n---\n"
                f"Copy the text exactly from read_file output."
            )

        return (
            f"Error: old_text not found in {path}. "
            f"The text you're trying to replace doesn't exist. "
            f"Use read_file to see the current content and try again."
        )

    # Multiple matches
    return (
        f"Error: old_text matches {count} locations in {path}. "
        f"Include more surrounding context to make it unique (add lines before/after)."
    )


def _tool_read_file_tail(project: Path, path: str, lines = 50) -> str:
    """Read the last N lines of a file."""
    try:
        lines = int(lines)
    except (ValueError, TypeError):
        lines = 50
    target = project / path
    if not _is_safe_path(target, project):
        return "Access denied: path outside project"

    if not target.exists():
        return f"File not found: {path}"
    if not target.is_file():
        return f"Not a file: {path}"

    all_lines = target.read_text().splitlines()
    total = len(all_lines)
    tail = all_lines[-lines:] if lines < total else all_lines
    start_line = max(1, total - lines + 1)

    header = f"=== {path} — last {len(tail)} of {total} lines (starting at line {start_line}) ===\n"
    numbered = "\n".join(f"{start_line + i:4d} | {line}" for i, line in enumerate(tail))

    # Check for signs of truncation
    last_line = all_lines[-1] if all_lines else ""
    warnings = []
    if not last_line.strip():
        pass  # Empty last line is normal
    elif "</html>" not in last_line and "</script>" not in last_line and path.endswith((".html", ".htm")):
        warnings.append("WARNING: HTML file does not end with closing tag — possible truncation")
    if last_line.rstrip().endswith(("(", "{", ",", "=", ".")):
        warnings.append(f"WARNING: File ends mid-statement on line {total} — possible truncation")

    warning_text = "\n".join(warnings) + "\n" if warnings else ""
    return header + numbered + "\n" + warning_text


def _tool_grep_code(project: Path, pattern: str) -> str:
    """Search all project files for a pattern (case-insensitive)."""
    if not pattern:
        return "Error: pattern is empty."
    results = []
    pattern_lower = pattern.lower()
    for f in sorted(project.rglob("*")):
        if not f.is_file() or f.name.startswith("."):
            continue
        try:
            for line_num, line in enumerate(f.read_text().splitlines(), 1):
                if pattern_lower in line.lower():
                    rel = str(f.relative_to(project))
                    results.append(f"  {rel}:{line_num}: {line.strip()[:200]}")
        except Exception:
            continue
    if not results:
        return f"No matches for '{pattern}'"
    if len(results) > 30:
        results = results[:30] + [f"  ... ({len(results)} total matches)"]
    return f"Matches for '{pattern}':\n" + "\n".join(results)


_READ_LINES_PADDING = 20  # Extra lines above/below to reduce follow-up reads

def _tool_read_lines(project: Path, path: str, start = 1, end = 50) -> str:
    """Read a specific range of lines from a file (1-indexed, inclusive).
    Adds padding (±20 lines) to reduce follow-up read calls."""
    try:
        start = int(start)
        end = int(end)
    except (ValueError, TypeError):
        start, end = 1, 50
    target = project / path
    if not _is_safe_path(target, project):
        return "Access denied: path outside project"

    if not target.exists():
        return f"File not found: {path}"
    if not target.is_file():
        return f"Not a file: {path}"

    all_lines = target.read_text().splitlines()
    total = len(all_lines)

    # Add padding to reduce "let me read a bit more" follow-ups
    padded_start = max(1, start - _READ_LINES_PADDING)
    padded_end = min(total, end + _READ_LINES_PADDING)

    if padded_start > total:
        return f"File {path} has only {total} lines. Requested start={start}."

    selected = all_lines[padded_start - 1:padded_end]
    header = f"=== {path} — lines {padded_start}-{padded_end} of {total} (requested {start}-{end}, padded ±{_READ_LINES_PADDING}) ===\n"
    numbered = "\n".join(f"{padded_start + i:4d} | {line}" for i, line in enumerate(selected))
    return header + numbered


def _tool_read_project(project: Path) -> str:
    """Read all source code files in the project.

    If total size fits within READ_PROJECT_BUDGET, returns all file contents concatenated.
    If too large, returns a file listing with sizes so the agent can choose what to read.
    """
    # Collect all readable source files
    files = []
    for f in sorted(project.rglob("*")):
        if not f.is_file():
            continue
        # Skip hidden files and excluded directories
        parts = f.relative_to(project).parts
        if any(p.startswith(".") or p in SKIP_DIRS for p in parts):
            continue
        # Skip non-code files
        if f.suffix.lower() not in CODE_EXTENSIONS:
            continue
        try:
            size = f.stat().st_size
            files.append((f, str(f.relative_to(project)), size))
        except OSError:
            continue

    if not files:
        return "No source files found in project."

    total_size = sum(s for _, _, s in files)

    # If within budget, return everything
    if total_size <= READ_PROJECT_BUDGET:
        parts = [f"=== PROJECT SOURCE ({len(files)} files, {total_size:,} chars) ===\n"]
        for fpath, rel, size in files:
            try:
                content = fpath.read_text()
                parts.append(f"\n{'='*60}\n=== {rel} ({size:,} chars, {len(content.splitlines())} lines) ===\n{'='*60}\n")
                parts.append(content)
            except Exception:
                parts.append(f"\n=== {rel} (read error) ===\n")
        return "\n".join(parts)

    # Over budget — return context map + file listing so agent can choose
    parts = [
        f"=== PROJECT TOO LARGE FOR FULL READ ===\n"
        f"Total: {total_size:,} chars (~{total_size // 4:,} tokens) across {len(files)} files.\n"
        f"Budget: {READ_PROJECT_BUDGET:,} chars (~{READ_PROJECT_BUDGET // 4:,} tokens).\n\n"
        f"Use read_file on specific files, or grep_code to find relevant sections.\n\n"
    ]

    # Auto-include CONTEXT_MAP.md and SPEC.md if they exist (small, high-value)
    for doc_name in ("CONTEXT_MAP.md", "SPEC.md"):
        doc_path = project / doc_name
        if doc_path.exists():
            doc_content = doc_path.read_text()
            parts.append(f"{'='*60}\n=== {doc_name} (auto-included) ===\n{'='*60}\n{doc_content}\n")

    parts.append(f"\nFiles by size (largest first):\n")
    for fpath, rel, size in sorted(files, key=lambda x: x[2], reverse=True):
        lines = 0
        try:
            lines = len(fpath.read_text().splitlines())
        except Exception:
            pass
        parts.append(f"  {rel:50s} {size:>8,} chars  {lines:>5} lines")

    return "\n".join(parts)
