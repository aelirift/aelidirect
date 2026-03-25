// =================================================================
// HEARTBEAT PANEL
// =================================================================
let _hbPollTimer = null;

async function loadHeartbeat() {
  if (!state.projectDir) return;
  try {
    const resp = await fetch('/api/direct/heartbeat/' + encodeURIComponent(state.projectDir));
    const hb = await resp.json();

    const toggle = document.getElementById('hb-toggle');
    const label = document.getElementById('hb-label');

    if (hb.enabled) {
      toggle.classList.add('on');
      label.textContent = 'ON';
      label.classList.add('on');
    } else {
      toggle.classList.remove('on');
      label.textContent = 'OFF';
      label.classList.remove('on');
    }

    // Only set interval if the field hasn't been touched by the user this session
    // Always reflect the server value — the server is the source of truth
    document.getElementById('hb-interval').value = hb.interval_minutes;

    // Running indicator
    const statusArea = document.getElementById('hb-status');
    if (statusArea) statusArea.remove();
    const panel = document.getElementById('heartbeat-panel');
    const statusDiv = document.createElement('div');
    statusDiv.id = 'hb-status';
    statusDiv.style.cssText = 'margin-bottom:12px; padding:10px; border-radius:8px; font-size:0.9em;';

    if (hb.running) {
      statusDiv.style.background = '#1a2a3a';
      statusDiv.style.border = '1px solid #26a1ff44';
      statusDiv.style.color = '#26a1ff';
      statusDiv.innerHTML = '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#26a1ff;animation:pulse-dot 1.2s infinite;margin-right:8px;"></span>' +
        'Running: ' + escHtml(hb.next_todo || 'a task') + '...';
      // Auto-refresh while running
      if (!_hbPollTimer) {
        _hbPollTimer = setInterval(function() { loadHeartbeat(); }, 5000);
      }
    } else if (hb.enabled && hb.next_run_secs !== undefined) {
      const mins = Math.floor(hb.next_run_secs / 60);
      const secs = hb.next_run_secs % 60;
      statusDiv.style.background = '#1a2a1a';
      statusDiv.style.border = '1px solid #2fbf5e44';
      statusDiv.style.color = '#5fe88a';
      const nextTodo = hb.next_todo ? escHtml(hb.next_todo) : 'no pending todos';
      statusDiv.innerHTML = 'Next run in ' + mins + 'm ' + secs + 's' +
        ' &middot; ' + hb.pending_count + ' pending' +
        '<br><span style="color:#888;font-size:0.85em;">Next: ' + nextTodo + '</span>';
      // Clear poll timer if not running
      if (_hbPollTimer) { clearInterval(_hbPollTimer); _hbPollTimer = null; }
    } else if (hb.enabled) {
      statusDiv.style.background = '#1a2a1a';
      statusDiv.style.border = '1px solid #2fbf5e44';
      statusDiv.style.color = '#5fe88a';
      statusDiv.textContent = 'Enabled — ' + (hb.pending_count || 0) + ' pending todos. Waiting for first run...';
      if (_hbPollTimer) { clearInterval(_hbPollTimer); _hbPollTimer = null; }
    } else {
      statusDiv.style.color = '#555';
      statusDiv.textContent = 'Heartbeat is off.';
      if (_hbPollTimer) { clearInterval(_hbPollTimer); _hbPollTimer = null; }
    }

    const runBtn = panel.querySelector('.hb-run-btn');
    if (runBtn) runBtn.parentNode.insertBefore(statusDiv, runBtn);

    // Queue — show pending todos with countdown
    const queue = document.getElementById('hb-queue');
    try {
      const todoResp = await fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir));
      const todoData = await todoResp.json();
      const pendingTodos = (todoData.todos || []).filter(function(t) { return t.status !== 'done'; });

      if (pendingTodos.length === 0) {
        queue.innerHTML = '<div class="hb-queue-empty">No tasks in queue.</div>';
      } else {
        const nextRunSecs = hb.next_run_secs || 0;
        queue.innerHTML = pendingTodos.map(function(t, idx) {
          const isFirst = idx === 0;
          const isRunning = hb.running && isFirst;
          const cls = isRunning ? 'running' : '';
          const numCls = isRunning ? 'running' : 'waiting';
          let countdown = '';
          if (isRunning) {
            countdown = '<span class="q-countdown running">RUNNING</span>';
          } else if (isFirst && hb.enabled && nextRunSecs > 0) {
            const m = Math.floor(nextRunSecs / 60);
            const s = nextRunSecs % 60;
            countdown = '<span class="q-countdown waiting">' + m + 'm ' + s + 's</span>';
          } else if (isFirst && hb.enabled) {
            countdown = '<span class="q-countdown waiting">NEXT</span>';
          } else {
            countdown = '<span class="q-countdown" style="color:#555;">QUEUED</span>';
          }
          return '<div class="hb-queue-item ' + cls + '">' +
            '<div class="q-header">' +
              '<span class="q-num ' + numCls + '">#' + escHtml(t.id) + (isRunning ? ' Running' : ' Waiting') + '</span>' +
              countdown +
            '</div>' +
            '<div class="q-task">' + escHtml(t.task) + '</div>' +
          '</div>';
        }).join('');
      }
    } catch (e) {
      queue.innerHTML = '<div class="hb-queue-empty">Failed to load queue.</div>';
    }

    // History — completed runs with color coding
    const hist = document.getElementById('hb-history');
    if (hb.history && hb.history.length > 0) {
      hist.innerHTML = hb.history.slice(-15).reverse().map(function(h) {
        const result = h.result || '';
        const isError = result.startsWith('ERROR') || result.includes('failed') || result.includes('FAILED');
        const isPartial = result.includes('cannot access') || result.includes('partially') || result.includes('issue');
        const cls = isError ? 'error' : (isPartial ? 'partial' : 'success');
        const resultColor = isError ? '#f66' : (isPartial ? '#ffa500' : '#5fe88a');
        const statusLabel = isError ? 'FAILED' : (isPartial ? 'PARTIAL' : 'DONE');
        const todoId = h.todo_id || '';
        const clickAttr = todoId ? ' onclick="showTodoDetail(\'' + escHtml(todoId) + '\')"' : '';
        return '<div class="hb-history-item ' + cls + '"' + clickAttr + '>' +
          '<div class="hb-ts">' +
            '<span style="color:#26a1ff;font-weight:bold;">#' + escHtml(todoId || '?') + '</span> ' +
            '<span style="color:' + resultColor + ';font-weight:600;font-size:0.85em;">' + statusLabel + '</span> ' +
            escHtml(h.timestamp) +
          '</div>' +
          '<div class="hb-task">' + escHtml(h.task) + '</div>' +
          '<div class="hb-result" style="color:' + resultColor + ';">' + escHtml(result).substring(0, 250) + '...</div>' +
        '</div>';
      }).join('');
    } else {
      hist.innerHTML = '<div style="color:#555;">No runs yet.</div>';
    }
  } catch (e) {
    console.error('Failed to load heartbeat:', e);
  }
}

async function saveHeartbeatInterval() {
  if (!state.projectDir) return;
  const interval = parseInt(document.getElementById('hb-interval').value) || 1;
  try {
    await fetch('/api/direct/heartbeat/' + encodeURIComponent(state.projectDir), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ interval_minutes: interval }),
    });
  } catch (e) {
    console.error('Failed to save interval:', e);
  }
}

async function toggleHeartbeat() {
  if (!state.projectDir) return;
  try {
    const resp = await fetch('/api/direct/heartbeat/' + encodeURIComponent(state.projectDir));
    const hb = await resp.json();
    const interval = parseInt(document.getElementById('hb-interval').value) || 1;
    await fetch('/api/direct/heartbeat/' + encodeURIComponent(state.projectDir), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled: !hb.enabled, interval_minutes: interval }),
    });
    loadHeartbeat();
  } catch (e) {
    console.error('Failed to toggle heartbeat:', e);
  }
}

async function runHeartbeatNow() {
  if (!state.projectDir || state.running) return;

  // Fetch next pending todo
  let nextTask;
  try {
    const todosResp = await fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir));
    const todosData = await todosResp.json();
    const pending = (todosData.todos || []).filter(function(t) {
      return t.status === 'pending' || t.status === 'attempted';
    });
    if (pending.length === 0) {
      addMsg('system', 'No pending todos to execute.');
      return;
    }
    nextTask = pending[0];
  } catch (_) {
    addMsg('error', 'Failed to load todos.');
    return;
  }

  // Mark as attempted
  fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir) + '/' + nextTask.id, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: 'attempted' }),
  });

  addMsg('phase', '--- Heartbeat: executing "' + escHtml(nextTask.task) + '" ---');
  document.getElementById('chat-input').value = nextTask.task;
  sendMessage();

  // After completion, mark as done
  const checkDone = setInterval(function() {
    if (!state.running) {
      clearInterval(checkDone);
      fetch('/api/direct/todos/' + encodeURIComponent(state.projectDir) + '/' + nextTask.id, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'done', result: 'Executed via heartbeat' }),
      }).then(function() {
        loadTodos();
        loadHeartbeat();
      });
    }
  }, 2000);
}

// =================================================================
// HEARTBEAT PROGRESS (merged into branch bar)
// =================================================================
async function pollHeartbeatProgress() {
  if (_branchIsBranch) return;
  try {
    var resp = await fetch('/api/platform/heartbeat-progress');
    var p = await resp.json();
    var bar = document.getElementById('branch-bar');
    var dot = document.getElementById('branch-dot');
    var label = document.getElementById('branch-label');
    var files = document.getElementById('branch-files');

    if (p.active) {
      _hbProgressActive = true;
      bar.style.display = 'flex';
      bar.style.borderColor = '#26a1ff33';
      dot.style.display = '';
      dot.style.background = '#26a1ff';
      dot.style.animation = 'pulse-dot 1.2s infinite';
      label.style.display = '';
      label.style.color = '#26a1ff';
      label.textContent = '#' + p.todo_id + ' ' + (p.step || 'working...');
      files.style.display = '';
      var elapsed = '';
      if (p.started_at) {
        var secs = Math.floor((Date.now() / 1000) - (new Date(p.started_at + 'Z').getTime() / 1000));
        var m = Math.floor(secs / 60);
        var s = secs % 60;
        elapsed = ' · ' + (m > 0 ? m + 'm ' : '') + s + 's';
      }
      files.textContent = 'step ' + (p.total_steps || 0) + ' · write ' + p.turn + '/' + p.max_turns + elapsed;
      // Hide action buttons while running
      document.getElementById('branch-test-btn').style.display = 'none';
      document.getElementById('branch-deploy-btn').style.display = 'none';
      document.getElementById('branch-wipe-btn').style.display = '';
      // Poll faster while active
      if (!_hbProgressTimer) {
        _hbProgressTimer = setInterval(pollHeartbeatProgress, 1500);
      }
    } else if (p.finished_at && p.finished_at !== _hbProgressLastFinished) {
      _hbProgressActive = false;
      _hbProgressLastFinished = p.finished_at;
      var statusColor = p.result_status === 'failure' ? '#f66' : (p.result_status === 'partial' ? '#ffa500' : '#5fe88a');
      var statusLabel = p.result_status === 'failure' ? 'FAILED' : (p.result_status === 'partial' ? 'COMPLETED WITH ISSUES' : 'COMPLETED');
      bar.style.display = 'flex';
      bar.style.borderColor = statusColor + '44';
      dot.style.display = '';
      dot.style.background = statusColor;
      dot.style.animation = 'none';
      label.style.display = '';
      label.style.color = statusColor;
      label.textContent = '#' + p.todo_id + ' ' + statusLabel;
      files.style.display = '';
      files.textContent = (p.result_message || '').substring(0, 100);
      // Refresh data
      loadTodos();
      loadHeartbeat();
      // After 8s, switch to branch status view
      setTimeout(function() { checkBranchStatus(); }, 8000);
      // Stop fast polling
      if (_hbProgressTimer) { clearInterval(_hbProgressTimer); _hbProgressTimer = null; }
    } else {
      _hbProgressActive = false;
      if (_hbProgressTimer) { clearInterval(_hbProgressTimer); _hbProgressTimer = null; }
    }
  } catch (e) {}
}
