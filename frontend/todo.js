// =================================================================
// TODO PANEL
// =================================================================
function switchTab(tab) {
  document.getElementById('todo-panel').style.display = tab === 'todo' ? 'block' : 'none';
  document.getElementById('heartbeat-panel').style.display = tab === 'heartbeat' ? 'block' : 'none';

  document.getElementById('tab-todo').className = tab === 'todo' ? 'active' : '';
  document.getElementById('tab-heartbeat').className = tab === 'heartbeat' ? 'active' : '';

  if (tab === 'todo') loadTodos();
  if (tab === 'heartbeat') loadHeartbeat();
}

async function addTodo() {
  if (!state.projectDir) { alert('Load a project first'); return; }
  const input = document.getElementById('todo-input');
  const task = input.value.trim();
  if (!task) return;
  input.value = '';
  await fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task }),
  });
  loadTodos();
}

async function loadTodos() {
  if (!state.projectDir) return;
  try {
    const resp = await fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir));
    const data = await resp.json();
    const list = document.getElementById('todo-list');

    if (!data.todos || data.todos.length === 0) {
      list.innerHTML = '<div class="todo-empty">No todos yet.</div>';
      return;
    }

    const statusColors = { pending: '#ffa500', attempted: '#ff6b6b', done: '#5fe88a' };
    const statusIcons = { pending: '\u25CB', attempted: '\u21BB', done: '\u2713' };

    list.innerHTML = data.todos.slice().reverse().map(function(t) {
      const color = statusColors[t.status] || '#888';
      const icon = statusIcons[t.status] || '?';
      const safeTask = escHtml(t.task).replace(/'/g, "\\'");
      const runBtn = t.status !== 'done'
        ? '<button class="todo-btn-run" onclick="event.stopPropagation();sendTodoTask(\'' + safeTask + '\', \'' + t.id + '\')">Run</button>'
        : '';
      const resultHtml = t.last_result
        ? '<div class="todo-result">' + escHtml(t.last_result).substring(0, 150) + '</div>'
        : '';
      var statusBadgeColor = {success:'#5fe88a', failure:'#f66', partial:'#ffa500', incomplete:'#888'}[t.result_status] || '#555';
      var statusBadgeLabel = {success:'PASS', failure:'FAIL', partial:'PARTIAL', incomplete:'INCOMPLETE'}[t.result_status] || '';
      const reviewBadge = t.td_review
        ? ' <span style="color:' + statusBadgeColor + ';font-size:0.75em;font-weight:600;">' + statusBadgeLabel + '</span>'
        : '';

      return '<div class="todo-item" onclick="showTodoDetail(\'' + t.id + '\')">' +
        '<span class="status-icon" style="color:' + color + ';">#' + escHtml(t.id) + ' ' + icon + '</span>' +
        '<div class="todo-content">' +
          '<div class="todo-task">' + escHtml(t.task) + reviewBadge + '</div>' +
          '<div class="todo-meta">' + t.status + (t.attempts > 0 ? ' &middot; ' + t.attempts + ' attempts' : '') + '</div>' +
          resultHtml +
        '</div>' +
        '<div class="todo-actions">' +
          runBtn +
          '<button class="todo-btn-del" onclick="event.stopPropagation();deleteTodo(\'' + t.id + '\')">&times;</button>' +
        '</div>' +
      '</div>';
    }).join('');
  } catch (e) {
    console.error('Failed to load todos:', e);
  }
}

function sendTodoTask(task, todoId) {
  document.getElementById('chat-input').value = task;
  sendMessage();
  // Mark as attempted
  fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir) + '/' + todoId, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'attempted' }),
  });
}

async function deleteTodo(todoId) {
  await fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir) + '/' + todoId, { method: 'DELETE' });
  loadTodos();
}

// =================================================================
// TODO DETAIL MODAL
// =================================================================
async function showTodoDetail(todoId) {
  if (!state.projectDir || !todoId) return;

  // Create overlay
  const overlay = document.createElement('div');
  overlay.className = 'todo-detail-overlay';
  overlay.onclick = function(e) { if (e.target === overlay) overlay.remove(); };

  const modal = document.createElement('div');
  modal.className = 'todo-detail-modal';
  modal.innerHTML = '<button class="todo-detail-close" onclick="this.closest(\'.todo-detail-overlay\').remove()">&times;</button>' +
    '<div class="todo-detail-loading">Loading...</div>';
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  try {
    const resp = await fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir) + '/' + encodeURIComponent(todoId));
    const data = await resp.json();
    if (!data.ok || !data.todo) {
      modal.innerHTML = '<button class="todo-detail-close" onclick="this.closest(\'.todo-detail-overlay\').remove()">&times;</button>' +
        '<div style="color:#f66;padding:20px;">Todo not found.</div>';
      return;
    }
    renderTodoDetailModal(modal, data.todo, data.schedule || {});
  } catch (e) {
    modal.innerHTML = '<button class="todo-detail-close" onclick="this.closest(\'.todo-detail-overlay\').remove()">&times;</button>' +
      '<div style="color:#f66;padding:20px;">Failed to load: ' + escHtml(e.message) + '</div>';
  }
}

function _fmtDuration(secs) {
  if (!secs && secs !== 0) return null;
  if (secs < 60) return secs + 's';
  var m = Math.floor(secs / 60);
  var s = secs % 60;
  if (m < 60) return m + 'm ' + s + 's';
  var h = Math.floor(m / 60);
  m = m % 60;
  return h + 'h ' + m + 'm';
}

function _fmtTs(ts) {
  if (!ts) return '';
  return ts.replace('T', ' ');
}

function _extractIssues(result) {
  // Pull out lines that look like errors/warnings/issues
  var lines = result.split('\n');
  var issues = [];
  var keywords = ['error', 'fail', 'issue', 'warning', 'cannot', 'unable', 'crash',
                   'traceback', 'exception', 'not found', 'missing', 'broken'];
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i].trim();
    if (!line || line.length < 10) continue;
    var lower = line.toLowerCase();
    for (var k = 0; k < keywords.length; k++) {
      if (lower.indexOf(keywords[k]) !== -1) {
        issues.push(line.length > 200 ? line.substring(0, 200) + '...' : line);
        break;
      }
    }
    if (issues.length >= 10) break;
  }
  return issues;
}

function renderTodoDetailModal(modal, t, schedule) {
  const statusColors = { pending: '#ffa500', attempted: '#ff6b6b', done: '#5fe88a' };
  const statusLabels = { pending: 'PENDING', attempted: 'IN PROGRESS', done: 'DONE' };
  const resultStatusColors = { success: '#5fe88a', failure: '#f66', partial: '#ffa500', incomplete: '#888' };
  const resultStatusLabels = { success: 'SUCCESS', failure: 'FAILED', partial: 'SUCCESS WITH ISSUES', incomplete: 'INCOMPLETE' };
  const color = statusColors[t.status] || '#888';

  var html = '<button class="todo-detail-close" onclick="this.closest(\'.todo-detail-overlay\').remove()">&times;</button>';

  // ── Header ──
  html += '<div class="todo-detail-id">#' + escHtml(t.id) + '</div>';
  html += '<div class="todo-detail-task">' + escHtml(t.task) + '</div>';

  // ── Status + Result badge row ──
  html += '<div class="todo-detail-meta">';
  html += '<span style="color:' + color + ';font-weight:600;">' + (statusLabels[t.status] || t.status) + '</span>';
  if (t.result_status) {
    var rc = resultStatusColors[t.result_status] || '#888';
    var rl = resultStatusLabels[t.result_status] || t.result_status.toUpperCase();
    html += '<span class="todo-detail-result-badge ' + t.result_status + '">' + rl + '</span>';
  }
  if (t.attempts > 0) html += '<span>' + t.attempts + ' attempt' + (t.attempts > 1 ? 's' : '') + '</span>';
  if (t.category) html += '<span>' + escHtml(t.category) + '</span>';
  if (t.duration_secs !== null && t.duration_secs !== undefined) {
    html += '<span class="todo-detail-duration">' + _fmtDuration(t.duration_secs) + '</span>';
  }
  html += '</div>';

  // ── Timeline ──
  html += '<div class="todo-detail-timeline">';
  // Created
  html += '<div class="tl-item active">' +
    '<span class="tl-label">Added</span>' +
    '<span class="tl-value">' + _fmtTs(t.created_at) + '</span>' +
  '</div>';
  // Started
  if (t.started_at) {
    html += '<div class="tl-item active">' +
      '<span class="tl-label">Started</span>' +
      '<span class="tl-value">' + _fmtTs(t.started_at) + '</span>' +
    '</div>';
  }
  // Completed
  if (t.completed_at) {
    var tlCls = t.result_status === 'failure' ? 'error' : 'done';
    html += '<div class="tl-item ' + tlCls + '">' +
      '<span class="tl-label">Completed</span>' +
      '<span class="tl-value">' + _fmtTs(t.completed_at) +
      (t.duration_secs !== null && t.duration_secs !== undefined ? ' (' + _fmtDuration(t.duration_secs) + ')' : '') +
      '</span>' +
    '</div>';
  }
  // Scheduled (for pending items)
  if (t.status !== 'done' && schedule) {
    if (schedule.est_run_at) {
      var estLabel = _fmtDuration(schedule.est_run_secs);
      html += '<div class="tl-item pending">' +
        '<span class="tl-label">Scheduled</span>' +
        '<span class="tl-value">' + _fmtTs(schedule.est_run_at) +
        (estLabel ? ' (in ~' + estLabel + ')' : '') +
        '</span>' +
      '</div>';
    } else if (!schedule.heartbeat_enabled) {
      html += '<div class="tl-item">' +
        '<span class="tl-label">Scheduled</span>' +
        '<span class="tl-value" style="color:#555;">Heartbeat off — not scheduled</span>' +
      '</div>';
    }
  }
  html += '</div>';

  // ── Schedule info (for pending items) ──
  if (t.status !== 'done' && schedule && schedule.heartbeat_enabled) {
    html += '<div class="todo-detail-schedule">';
    html += '<div class="sched-row"><span>Queue position</span><span class="sched-value">#' + (schedule.queue_position || '?') + '</span></div>';
    html += '<div class="sched-row"><span>Heartbeat interval</span><span class="sched-value">' + (schedule.heartbeat_interval || '?') + ' min</span></div>';
    if (schedule.est_run_secs !== undefined) {
      html += '<div class="sched-row"><span>Estimated run in</span><span class="sched-value">' + _fmtDuration(schedule.est_run_secs) + '</span></div>';
    }
    html += '</div>';
  }

  // ── Result ──
  if (t.last_result) {
    html += '<div class="todo-detail-section">';
    html += '<h4>Agent Result</h4>';
    html += '<div class="todo-detail-result">' + escHtml(t.last_result) + '</div>';
    html += '</div>';
  }

  // ── Issues summary (extract from result if partial/failure) ──
  if (t.last_result && t.result_status && t.result_status !== 'success') {
    var issues = _extractIssues(t.last_result);
    if (issues.length > 0) {
      html += '<div class="todo-detail-section">';
      html += '<h4>Issues Summary</h4>';
      html += '<div style="background:#1a0a0a;border:1px solid #3a1a1a;border-radius:8px;padding:12px;">';
      html += '<ul style="margin:0 0 0 16px;padding:0;">';
      for (var i = 0; i < issues.length; i++) {
        html += '<li style="color:#ffa500;margin:4px 0;font-size:0.88em;">' + escHtml(issues[i]) + '</li>';
      }
      html += '</ul></div></div>';
    }
  }

  // ── TD Review ──
  if (t.td_review) {
    html += '<div class="todo-detail-section">';
    html += '<h4>TD Review</h4>';
    html += '<div class="todo-detail-review">' + renderMarkdownSimple(t.td_review) + '</div>';
    html += '</div>';
  } else if (t.status === 'done') {
    html += '<div class="todo-detail-section">';
    html += '<h4>TD Review</h4>';
    html += '<div class="todo-detail-loading">Review pending or not yet generated...</div>';
    html += '</div>';
  }

  modal.innerHTML = html;
}
