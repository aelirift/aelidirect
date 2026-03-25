// =================================================================
// STATE
// =================================================================
const state = {
  projectDir: null,
  projectName: null,
  running: false,
  configData: null,
  projects: [],
};

let _spinnerStart = null;
let _spinnerTimer = null;

// Shared globals used across files
var _branchIsBranch = false;
var _hbProgressActive = false;
var _hbProgressTimer = null;
var _hbProgressLastFinished = '';

// =================================================================
// UTILS
// =================================================================
function escHtml(s) {
  if (s === null || s === undefined) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _isNearBottom(el) {
  // User is "near bottom" if within 150px of the end
  return (el.scrollHeight - el.scrollTop - el.clientHeight) < 150;
}

function renderMarkdown(md) {
  var html = escHtml(md);
  // Code blocks
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // Inline code
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  // Headers
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Horizontal rules
  html = html.replace(/^---$/gm, '<hr style="border:none;border-top:1px solid #2a2a4a;margin:16px 0;">');
  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // Tables
  html = html.replace(/^\|(.+)\|$/gm, function(match, content) {
    var cells = content.split('|').map(function(c) { return c.trim(); });
    if (cells.every(function(c) { return /^[-:]+$/.test(c); })) return '';
    return '<tr>' + cells.map(function(c) { return '<td>' + c + '</td>'; }).join('') + '</tr>';
  });
  html = html.replace(/(<tr>.*<\/tr>\n?)+/g, '<table>$&</table>');
  // Paragraphs
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  // Clean up
  html = html.replace(/<p>\s*<\/p>/g, '');
  html = html.replace(/<p>(<h[123]>)/g, '$1');
  html = html.replace(/(<\/h[123]>)<\/p>/g, '$1');
  html = html.replace(/<p>(<ul>)/g, '$1');
  html = html.replace(/(<\/ul>)<\/p>/g, '$1');
  html = html.replace(/<p>(<table>)/g, '$1');
  html = html.replace(/(<\/table>)<\/p>/g, '$1');
  html = html.replace(/<p>(<pre>)/g, '$1');
  html = html.replace(/(<\/pre>)<\/p>/g, '$1');
  html = html.replace(/<p>(<hr)/g, '$1');
  html = html.replace(/(margin:16px 0;">)<\/p>/g, '$1');
  return html;
}

function renderMarkdownSimple(md) {
  let html = escHtml(md);
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  html = html.replace(/<p>\s*<\/p>/g, '');
  html = html.replace(/<p>(<h[123]>)/g, '$1');
  html = html.replace(/(<\/h[123]>)<\/p>/g, '$1');
  html = html.replace(/<p>(<ul>)/g, '$1');
  html = html.replace(/(<\/ul>)<\/p>/g, '$1');
  html = html.replace(/<p>(<pre>)/g, '$1');
  html = html.replace(/(<\/pre>)<\/p>/g, '$1');
  return html;
}

// =================================================================
// VIEW SWITCHING
// =================================================================
function showView(viewId) {
  document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
  document.getElementById(viewId).classList.add('active');

  const configBtn = document.getElementById('sidebar-config-btn');
  if (viewId === 'view-config') {
    configBtn.classList.add('active');
    loadConfigPage();
  } else {
    configBtn.classList.remove('active');
  }
}

function toggleConfig() {
  const configView = document.getElementById('view-config');
  if (configView.classList.contains('active')) {
    showView('view-chat');
  } else {
    showView('view-config');
  }
}

function toggleTDView() {
  const tdView = document.getElementById('view-td');
  if (tdView.classList.contains('active')) {
    showView('view-chat');
  } else {
    showView('view-td');
    loadTDHistory();
    loadLatestTDReport();
  }
}

// =================================================================
// SIDEBAR: PROJECT LIST
// =================================================================
async function loadProjects() {
  try {
    const resp = await fetch('/api/projects');
    const data = await resp.json();
    state.projects = data.projects || [];
    renderProjectList();
  } catch (e) {
    console.error('Failed to load projects:', e);
  }
}

function renderProjectList() {
  const container = document.getElementById('sidebar-projects');
  container.innerHTML = '';

  if (state.projects.length === 0) {
    container.innerHTML = '<div style="color:#444; font-size:0.8em; padding:10px 16px;">No projects yet.</div>';
    return;
  }

  for (const p of state.projects) {
    const item = document.createElement('button');
    item.className = 'sidebar-project-item';
    if (state.projectDir === p.dir_name) item.classList.add('active');
    item.innerHTML = `<div class="proj-icon"></div><span class="proj-label">${escHtml(p.project_name)}</span>`;
    item.onclick = () => loadProject(p.dir_name, p.project_name);
    container.appendChild(item);
  }
}

// =================================================================
// PROJECT LOADING
// =================================================================
function loadProject(dirName, projectName) {
  state.projectDir = dirName;
  state.projectName = projectName;

  // Update project bar
  const bar = document.getElementById('project-bar');
  bar.style.display = 'flex';
  document.getElementById('project-bar-name').textContent = projectName;
  document.getElementById('project-bar-dir').textContent = '(' + dirName + '/)';
  document.getElementById('turn-counter').textContent = '';

  // Clear messages
  const container = document.getElementById('messages');
  container.innerHTML = '';

  // Reset pod bar
  document.getElementById('pod-bar').style.display = 'none';

  // Switch to chat view
  showView('view-chat');
  renderProjectList();

  // Add system message
  addMsg('system', 'Loaded project: ' + projectName + '. Ask me anything.');

  // Load history, todos, heartbeat
  loadHistory(dirName);
  loadTodos();
  loadHeartbeat();
  checkBranchStatus();

  document.getElementById('chat-input').focus();
}

async function createNewProject() {
  const name = prompt('New project name:');
  if (!name || !name.trim()) return;

  // Set up the project bar with the name, let user type what to build
  state.pendingProjectName = name.trim();
  state.projectDir = '';
  document.getElementById('project-bar').style.display = 'flex';
  document.getElementById('project-bar-name').textContent = name.trim();
  document.getElementById('project-bar-dir').textContent = '';

  // Clear welcome
  const container = document.getElementById('messages');
  const welcome = document.getElementById('welcome');
  if (welcome) welcome.remove();

  addMsg('phase', 'New project: ' + name.trim() + ' — type what you want to build.');
  document.getElementById('chat-input').focus();
}

// =================================================================
// CONFIG PAGE
// =================================================================
async function loadConfigPage() {
  try {
    const resp = await fetch('/api/config');
    state.configData = await resp.json();
    renderConfigProviders(state.configData);
    document.getElementById('config-pod-host').value = state.configData.pod_host || '';
  } catch (e) {
    document.getElementById('config-providers-list').innerHTML =
      '<div style="color:#f66;padding:20px;">Failed to load config: ' + escHtml(e.message) + '</div>';
  }
}

function renderConfigProviders(data) {
  const container = document.getElementById('config-providers-list');
  let html = '';
  const providers = data.providers || {};

  for (const pid of Object.keys(providers)) {
    const p = providers[pid];
    const isActive = pid === data.selected;

    html += '<div class="config-section ' + (isActive ? 'active-provider' : '') + '" id="config-provider-' + escHtml(pid) + '">' +
      '<div class="config-section-header">' +
        '<span class="config-section-title">' + escHtml(p.name) + '</span>' +
        (isActive ? '<span class="config-active-badge">Active</span>' : '') +
      '</div>' +
      '<div class="config-row">' +
        '<label>ID</label>' +
        '<input type="text" value="' + escHtml(pid) + '" disabled style="opacity:0.5; cursor:not-allowed;">' +
      '</div>' +
      '<div class="config-row">' +
        '<label>Name</label>' +
        '<input type="text" id="cfg-name-' + escHtml(pid) + '" value="' + escHtml(p.name) + '">' +
      '</div>' +
      '<div class="config-row">' +
        '<label>Model</label>' +
        '<input type="text" id="cfg-model-' + escHtml(pid) + '" value="' + escHtml(p.model) + '">' +
      '</div>' +
      '<div class="config-row">' +
        '<label>Base URL</label>' +
        '<input type="text" id="cfg-url-' + escHtml(pid) + '" value="' + escHtml(p.base_url) + '">' +
      '</div>' +
      '<div class="config-row">' +
        '<label>API Key</label>' +
        '<input type="text" id="cfg-key-' + escHtml(pid) + '" placeholder="' + (p.has_key ? escHtml(p.api_key_masked) : 'Enter API key...') + '"' +
        ' class="' + (p.has_key ? 'key-masked' : '') + '">' +
      '</div>' +
      '<div class="config-actions">' +
        (!isActive ? '<button class="config-btn config-btn-active" onclick="setActiveProvider(\'' + escHtml(pid) + '\')">Set Active</button>' : '<button class="config-btn config-btn-active is-active" disabled>Active</button>') +
        (!isActive ? '<button class="config-btn config-btn-delete" onclick="deleteProvider(\'' + escHtml(pid) + '\')">Delete</button>' : '') +
        '<button class="config-btn config-btn-save" onclick="saveProvider(\'' + escHtml(pid) + '\')">Save</button>' +
      '</div>' +
      '<div class="config-status" id="config-status-' + escHtml(pid) + '"></div>' +
    '</div>';
  }

  container.innerHTML = html;
}

async function saveProvider(pid) {
  const name = document.getElementById('cfg-name-' + pid).value.trim();
  const model = document.getElementById('cfg-model-' + pid).value.trim();
  const baseUrl = document.getElementById('cfg-url-' + pid).value.trim();
  const apiKey = document.getElementById('cfg-key-' + pid).value.trim();

  const payload = { id: pid, name: name, model: model, base_url: baseUrl };
  if (apiKey && apiKey.indexOf('...') === -1) {
    payload.api_key = apiKey;
  }

  const resp = await fetch('/api/config/provider', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const result = await resp.json();
  const status = document.getElementById('config-status-' + pid);
  if (result.ok) {
    status.textContent = 'Saved!';
    status.className = 'config-status success';
    setTimeout(function() { status.className = 'config-status'; }, 2000);
    loadConfigPage();
  } else {
    status.textContent = result.error || 'Save failed';
    status.className = 'config-status error';
  }
}

async function setActiveProvider(pid) {
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selected: pid }),
  });
  loadConfigPage();
}

async function deleteProvider(pid) {
  if (!confirm('Delete provider "' + pid + '"?')) return;
  const resp = await fetch('/api/config/provider/' + encodeURIComponent(pid), { method: 'DELETE' });
  const result = await resp.json();
  if (result.ok) {
    loadConfigPage();
  } else {
    alert(result.error || 'Delete failed');
  }
}

async function saveGlobalConfig() {
  const podHost = document.getElementById('config-pod-host').value.trim();
  await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pod_host: podHost || 'localhost' }),
  });
  const status = document.getElementById('config-global-status');
  status.textContent = 'Saved!';
  status.className = 'config-status success';
  setTimeout(function() { status.className = 'config-status'; }, 2000);
}

function addNewProvider() {
  const id = prompt('Provider ID (lowercase, no spaces, e.g. "anthropic", "groq"):');
  if (!id || !id.trim()) return;
  const pid = id.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '');
  if (state.configData && state.configData.providers && state.configData.providers[pid]) {
    alert('Provider "' + pid + '" already exists.');
    return;
  }

  const container = document.getElementById('config-providers-list');
  const html =
    '<div class="config-section" id="config-provider-' + escHtml(pid) + '">' +
      '<div class="config-section-header">' +
        '<span class="config-section-title">New Provider</span>' +
      '</div>' +
      '<div class="config-row">' +
        '<label>ID</label>' +
        '<input type="text" value="' + escHtml(pid) + '" disabled style="opacity:0.5; cursor:not-allowed;">' +
      '</div>' +
      '<div class="config-row">' +
        '<label>Name</label>' +
        '<input type="text" id="cfg-name-' + escHtml(pid) + '" placeholder="Display name...">' +
      '</div>' +
      '<div class="config-row">' +
        '<label>Model</label>' +
        '<input type="text" id="cfg-model-' + escHtml(pid) + '" placeholder="model-name">' +
      '</div>' +
      '<div class="config-row">' +
        '<label>Base URL</label>' +
        '<input type="text" id="cfg-url-' + escHtml(pid) + '" placeholder="https://api.example.com/v1">' +
      '</div>' +
      '<div class="config-row">' +
        '<label>API Key</label>' +
        '<input type="text" id="cfg-key-' + escHtml(pid) + '" placeholder="Enter API key...">' +
      '</div>' +
      '<div class="config-actions">' +
        '<button class="config-btn config-btn-save" onclick="saveProvider(\'' + escHtml(pid) + '\')">Save</button>' +
      '</div>' +
      '<div class="config-status" id="config-status-' + escHtml(pid) + '"></div>' +
    '</div>';
  container.insertAdjacentHTML('beforeend', html);
  document.getElementById('cfg-name-' + pid).focus();
}

// =================================================================
// SPEC MODAL
// =================================================================
async function showSpec(dirName) {
  if (!dirName) return;
  try {
    const resp = await fetch('/api/projects/' + encodeURIComponent(dirName) + '/docs');
    const docs = await resp.json();
    const spec = docs['SPEC.md'] || 'No spec generated yet.';

    const backdrop = document.createElement('div');
    backdrop.className = 'ctx-modal-backdrop';
    backdrop.onclick = function(e) { if (e.target === backdrop) backdrop.remove(); };
    backdrop.innerHTML =
      '<div class="ctx-modal">' +
        '<div class="ctx-modal-header">' +
          '<h3>Spec &mdash; ' + escHtml(dirName) + '</h3>' +
          '<button class="ctx-modal-close" onclick="this.closest(\x27.ctx-modal-backdrop\x27).remove()">\&times;</button>' +
        '</div>' +
        '<div class="ctx-modal-body">' +
          '<pre>' + escHtml(spec) + '</pre>' +
        '</div>' +
      '</div>';
    document.body.appendChild(backdrop);
  } catch (e) {
    alert('Failed to load spec: ' + e.message);
  }
}

// =================================================================
// CONTEXT MAP MODAL
// =================================================================
async function showContextMap(dirName) {
  if (!dirName) return;
  try {
    const resp = await fetch('/api/projects/' + encodeURIComponent(dirName) + '/docs');
    const docs = await resp.json();
    const contextMap = docs['CONTEXT_MAP.md'] || 'No context map generated yet.';

    const backdrop = document.createElement('div');
    backdrop.className = 'ctx-modal-backdrop';
    backdrop.onclick = function(e) { if (e.target === backdrop) backdrop.remove(); };
    backdrop.innerHTML =
      '<div class="ctx-modal">' +
        '<div class="ctx-modal-header">' +
          '<h3>Context Map &mdash; ' + escHtml(dirName) + '</h3>' +
          '<button class="ctx-modal-close" onclick="this.closest(\'.ctx-modal-backdrop\').remove()">&times;</button>' +
        '</div>' +
        '<div class="ctx-modal-body">' +
          '<pre>' + escHtml(contextMap) + '</pre>' +
        '</div>' +
      '</div>';
    document.body.appendChild(backdrop);
  } catch (e) {
    alert('Failed to load context map: ' + e.message);
  }
}

// =================================================================
// INIT
// =================================================================
loadProjects();
checkBranchStatus();
pollHeartbeatProgress();
// Poll branch status every 30s, heartbeat progress every 5s (faster when active)
setInterval(checkBranchStatus, 30000);
setInterval(pollHeartbeatProgress, 5000);
