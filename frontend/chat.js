// =================================================================
// CHAT MESSAGES
// =================================================================
function addMsg(type, content, isHtml) {
  const container = document.getElementById('messages');
  const welcome = document.getElementById('welcome');
  if (welcome) welcome.remove();

  // Only auto-scroll if user is already near bottom
  const shouldScroll = _isNearBottom(container);

  const div = document.createElement('div');
  div.className = 'msg ' + type;
  if (isHtml) {
    div.innerHTML = content;
  } else {
    div.textContent = content;
  }
  container.appendChild(div);
  if (shouldScroll) container.scrollTop = container.scrollHeight;
}

// =================================================================
// SEND MESSAGE / SSE
// =================================================================
async function sendMessage() {
  const input = document.getElementById('chat-input');
  const btn = document.getElementById('send-btn');
  const message = input.value.trim();
  if (!message || state.running) return;

  state.running = true;
  btn.disabled = true;
  input.value = '';

  addMsg('user', message);
  showSpinner('Agent is thinking...');

  try {
    const body = { message };
    if (state.projectDir) {
      body.project_dir = state.projectDir;
    } else if (state.pendingProjectName) {
      body.project_name = state.pendingProjectName;
      state.pendingProjectName = null;
    }

    const resp = await fetch('/api/direct/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const startData = await resp.json();

    if (startData.error) {
      addMsg('error', startData.error);
      state.running = false;
      btn.disabled = false;
      removeSpinner();
      return;
    }

    // Update project info
    state.projectDir = startData.project_dir;
    state.projectName = startData.project_name || startData.project_dir;

    const bar = document.getElementById('project-bar');
    bar.style.display = 'flex';
    document.getElementById('project-bar-name').textContent = state.projectName;
    document.getElementById('project-bar-dir').textContent = '(' + state.projectDir + '/)';

    // Refresh sidebar projects (may be a new project)
    loadProjects();

    // Connect to SSE stream
    const evtSource = new EventSource(startData.stream_url);

    evtSource.addEventListener('turn', function(e) {
      const d = JSON.parse(e.data);
      const info = d.action_turns !== undefined
        ? 'Action ' + d.action_turns + '/' + d.max
        : 'Turn ' + d.turn + '/' + d.max;
      document.getElementById('turn-counter').textContent = info;
    });

    evtSource.addEventListener('thinking', function(e) {
      const d = JSON.parse(e.data);
      addMsg('system', '<span style="color:#26a1ff;">Agent:</span> ' + escHtml(d.content), true);
      showSpinner('Agent is reasoning...');
    });

    evtSource.addEventListener('tool_call', function(e) {
      const d = JSON.parse(e.data);
      const argsStr = typeof d.args === 'object' ? JSON.stringify(d.args) : d.args;
      const shortArgs = argsStr.length > 100 ? argsStr.substring(0, 100) + '...' : argsStr;
      addMsg('tool', d.name + '(' + shortArgs + ')');
      showSpinner('Executing ' + d.name + '...');
    });

    evtSource.addEventListener('tool_result', function(e) {
      const d = JSON.parse(e.data);
      const result = d.result.length > 300 ? d.result.substring(0, 300) + '...' : d.result;
      addMsg('system',
        '<span style="color:#5fe88a;">' + escHtml(d.name) + ' &rarr;</span> ' +
        '<span style="color:#aaa;">' + escHtml(result) + '</span>', true);
    });

    evtSource.addEventListener('pod_url', function(e) {
      const d = JSON.parse(e.data);
      document.getElementById('pod-url').textContent = d.url;
      document.getElementById('pod-bar').style.display = 'flex';
    });

    evtSource.addEventListener('response', function(e) {
      const d = JSON.parse(e.data);
      addMsg('system',
        '<div style="border:1px solid #26a1ff; border-radius:8px; padding:12px; margin:4px 0; background:#0a1a2e;">' +
        '<div style="white-space:pre-wrap; color:#ddd; line-height:1.5;">' + escHtml(d.content) + '</div>' +
        '</div>', true);
    });

    evtSource.addEventListener('plan', function(e) {
      const d = JSON.parse(e.data);
      var html = '<div style="border:1px solid #ffa50066; border-radius:8px; margin:4px 0; background:#1a1a0a;">';
      html += '<div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'" ' +
        'style="padding:10px 12px; cursor:pointer; display:flex; justify-content:space-between; align-items:center;">';
      html += '<span style="color:#ffa500; font-weight:bold;">Plan</span>';
      html += '<span style="color:#ffa500; font-size:0.8em;">click to view steps</span></div>';
      html += '<div style="display:none; padding:0 12px 12px 12px; border-top:1px solid #ffa50022;">';
      html += '<div style="white-space:pre-wrap; color:#ccc; line-height:1.6; font-size:0.9em; margin-top:8px;">' + escHtml(d.content) + '</div>';
      html += '</div></div>';
      addMsg('system', html, true);
    });

    evtSource.addEventListener('phase', function(e) {
      const d = JSON.parse(e.data);
      const labels = {planning: 'Planning', coding: 'Coding', testing: 'Testing', post_test: 'Post-Test'};
      const colors = {planning: '#ffa500', coding: '#26a1ff', testing: '#00e5ff', post_test: '#b388ff'};
      const label = labels[d.phase] || d.phase;
      const color = colors[d.phase] || '#888';
      addMsg('system',
        '<div style="border-bottom:1px solid ' + color + '33; padding:4px 0; margin:8px 0 4px 0;">' +
        '<span style="color:' + color + '; font-weight:bold; font-size:0.85em; text-transform:uppercase; letter-spacing:1px;">' +
        label + '</span></div>', true);
      // Update turn counter with phase
      var tc = document.getElementById('turn-counter');
      if (tc) tc.textContent = label + '...';
    });

    evtSource.addEventListener('test_phase', function(e) {
      const d = JSON.parse(e.data);
      const tag = '<span style="color:#00e5ff; font-weight:bold;">Test Agent:</span> ';
      if (d.status === 'deploying_branch') {
        showSpinner('Test Agent: restarting branch...');
        addMsg('system',
          '<div style="border-left:3px solid #00e5ff; padding:6px 12px; margin:4px 0; background:#0a1a2a;">' +
          tag + 'Restarting branch server before testing...</div>', true);
      } else if (d.status === 'planning') {
        showSpinner('Test Agent: planning (iter ' + d.iteration + ')...');
        addMsg('system',
          '<div style="border-left:3px solid #00e5ff; padding:6px 12px; margin:4px 0; background:#0a1a2a;">' +
          tag + 'Planning tests (iteration ' + d.iteration + ')</div>', true);
      } else if (d.status === 'running') {
        showSpinner('Test Agent: running ' + d.test_count + ' tests...');
        // Collapsible test plan
        var planHtml = '<div style="border:1px solid #00e5ff44; border-radius:8px; margin:4px 0; background:#0a1a2a;">';
        planHtml += '<div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'" ' +
          'style="padding:10px 12px; cursor:pointer; display:flex; justify-content:space-between; align-items:center;">';
        planHtml += '<span>' + tag + 'Running ' + d.test_count + ' tests (iter ' + d.iteration + ')</span>';
        planHtml += '<span style="color:#00e5ff; font-size:0.8em;">click to expand</span></div>';
        planHtml += '<div style="display:none; padding:0 12px 10px 12px; border-top:1px solid #00e5ff22;">';
        if (d.plan_summary) planHtml += '<div style="color:#aaa; font-size:0.85em; margin:8px 0;">' + escHtml(d.plan_summary) + '</div>';
        if (d.tests && d.tests.length > 0) {
          planHtml += '<div style="font-size:0.85em;">';
          d.tests.forEach(function(t) {
            planHtml += '<div style="color:#ccc; padding:2px 0;">- <span style="color:#00e5ff;">[' + escHtml(t.type) + ']</span> ' +
              '<span style="color:#fff;">' + escHtml(t.id) + '</span>: ' + escHtml(t.name) + '</div>';
          });
          planHtml += '</div>';
        }
        planHtml += '</div></div>';
        addMsg('system', planHtml, true);
      } else if (d.status === 'all_passed') {
        // Collapsible results
        var html = '<div style="border:1px solid #5fe88a; border-radius:8px; margin:4px 0; background:#0a2a1a;">';
        html += '<div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'" ' +
          'style="padding:10px 12px; cursor:pointer; display:flex; justify-content:space-between; align-items:center;">';
        html += '<span>' + tag + '<span style="color:#5fe88a; font-weight:bold;">All ' + d.passed + ' tests passed</span></span>';
        html += '<span style="color:#5fe88a; font-size:0.8em;">click for details</span></div>';
        html += '<div style="display:none; padding:0 12px 10px 12px; border-top:1px solid #5fe88a22; font-size:0.85em;">';
        if (d.results) {
          d.results.forEach(function(r) {
            html += '<div style="color:#5fe88a; padding:2px 0;">PASS ' + escHtml(r.id) + ': ' + escHtml(r.name) + '</div>';
          });
        }
        html += '</div></div>';
        addMsg('system', html, true);
      } else if (d.status === 'error') {
        addMsg('system',
          '<div style="border-left:3px solid #ff5555; padding:6px 12px; margin:4px 0; background:#2a0a0a;">' +
          tag + '<span style="color:#ff5555;"> Error: ' + escHtml(d.error || '') + '</span></div>', true);
      }
    });

    evtSource.addEventListener('test_feedback', function(e) {
      const d = JSON.parse(e.data);
      // Collapsible failure details
      var html = '<div style="border:1px solid #ff5555; border-radius:8px; margin:4px 0; background:#2a0a0a;">';
      html += '<div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'" ' +
        'style="padding:10px 12px; cursor:pointer; display:flex; justify-content:space-between; align-items:center;">';
      html += '<span><span style="color:#00e5ff; font-weight:bold;">Test Agent:</span>' +
        '<span style="color:#ff5555; font-weight:bold;"> ' + d.failed + ' failed</span>, ' +
        '<span style="color:#5fe88a;">' + d.passed + ' passed</span>' +
        ' &mdash; feeding back to coder (iter ' + d.iteration + ')</span>';
      html += '<span style="color:#ff5555; font-size:0.8em;">click for details</span></div>';
      html += '<div style="display:none; padding:0 12px 10px 12px; border-top:1px solid #ff555522; font-size:0.85em;">';
      if (d.results) {
        d.results.forEach(function(r) {
          if (r.status === 'pass') {
            html += '<div style="color:#5fe88a; padding:2px 0;">PASS ' + escHtml(r.id) + ': ' + escHtml(r.name) + '</div>';
          } else {
            html += '<div style="color:#ff5555; padding:3px 0; font-weight:bold;">FAIL ' + escHtml(r.id) + ': ' + escHtml(r.name) + '</div>';
            if (r.errors) {
              r.errors.forEach(function(err) {
                html += '<div style="color:#ff8888; padding:1px 0 1px 16px; font-size:0.9em;">' + escHtml(err) + '</div>';
              });
            }
          }
        });
      }
      html += '</div></div>';
      addMsg('system', html, true);
      showSpinner('Test Agent: feeding failures to coder (iter ' + d.iteration + ')...');
    });

    evtSource.addEventListener('td_review', function(e) {
      const d = JSON.parse(e.data);
      if (d.status === 'running') {
        showSpinner('TD Analysis running...');
      } else if (d.status === 'complete' && d.review) {
        // Collapsible TD review
        var html = '<div style="border:1px solid #b388ff; border-radius:8px; margin:4px 0; background:#1a0a2a;">';
        html += '<div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'" ' +
          'style="padding:10px 12px; cursor:pointer; display:flex; justify-content:space-between; align-items:center;">';
        html += '<span style="color:#b388ff; font-weight:bold;">TD Analysis</span>';
        html += '<span style="color:#b388ff; font-size:0.8em;">click to expand</span></div>';
        html += '<div style="display:none; padding:0 12px 12px 12px; border-top:1px solid #b388ff22;">';
        html += '<div style="white-space:pre-wrap; color:#ccc; line-height:1.5; font-size:0.9em; margin-top:8px;">' + escHtml(d.review) + '</div>';
        html += '</div></div>';
        addMsg('system', html, true);
      } else if (d.status === 'error') {
        addMsg('system',
          '<div style="border-left:3px solid #ff5555; padding:6px 12px; margin:4px 0; background:#2a0a0a;">' +
          '<span style="color:#b388ff; font-weight:bold;">TD Analysis:</span>' +
          '<span style="color:#ff5555;"> Error: ' + escHtml(d.error || '') + '</span></div>', true);
      }
    });

    evtSource.addEventListener('done', function(e) {
      const d = JSON.parse(e.data);
      removeSpinner();
      const info = d.action_turns !== undefined
        ? ' (' + d.action_turns + ' action, ' + d.turns + ' total)'
        : ' (' + d.turns + ' turns)';
      document.getElementById('turn-counter').textContent = 'Done' + info;
      evtSource.close();
      state.running = false;
      btn.disabled = false;
      // Refresh todos and branch status after completion
      loadTodos();
      checkBranchStatus();
    });

    evtSource.addEventListener('error', function(e) {
      try {
        const d = JSON.parse(e.data);
        addMsg('error', 'Error: ' + d.message);
      } catch (_) {
        // Connection dropped with no parseable data
      }
      evtSource.close();
      removeSpinner();
      state.running = false;
      btn.disabled = false;
      _showReconnect(message);
    });

    evtSource.onerror = function() {
      if (evtSource.readyState === EventSource.CLOSED) return;
      evtSource.close();
      removeSpinner();
      if (state.running) {
        state.running = false;
        btn.disabled = false;
        _showReconnect(message);
      }
    };

  } catch (e) {
    removeSpinner();
    addMsg('error', 'Failed: ' + e.message);
    state.running = false;
    btn.disabled = false;
  }
}

function _showReconnect(lastMessage) {
  const safeMsg = escHtml(lastMessage).replace(/'/g, "\\'");
  addMsg('error',
    '<div style="display:flex; align-items:center; gap:12px;">' +
    '<span>Connection lost (server may have restarted).</span>' +
    '<button onclick="this.parentElement.parentElement.remove(); _retryMessage(\'' + safeMsg + '\')" ' +
    'style="background:#1a3a1a; color:#5fe88a; border:1px solid #2fbf5e; padding:6px 14px; border-radius:6px; cursor:pointer; white-space:nowrap;">' +
    'Retry</button>' +
    '</div>', true);
}

function _retryMessage(msg) {
  document.getElementById('chat-input').value = msg;
  sendMessage();
}

// =================================================================
// SPINNER
// =================================================================
function showSpinner(text) {
  const spinner = document.getElementById('spinner-bar');
  if (!spinner) return;

  if (!_spinnerStart) {
    _spinnerStart = Date.now();
    _spinnerTimer = setInterval(function() {
      const el = document.getElementById('spinner-elapsed');
      if (el && _spinnerStart) {
        const secs = Math.floor((Date.now() - _spinnerStart) / 1000);
        const mins = Math.floor(secs / 60);
        el.textContent = mins > 0 ? mins + 'm ' + (secs % 60) + 's' : secs + 's';
      }
    }, 1000);
  }

  spinner.innerHTML =
    '<div class="pulse-dot"></div>' +
    '<span class="spinner-label">' + escHtml(text) + '</span>' +
    '<span class="spinner-elapsed" id="spinner-elapsed">0s</span>';
  spinner.style.display = 'flex';
}

function removeSpinner() {
  const spinner = document.getElementById('spinner-bar');
  if (spinner) spinner.style.display = 'none';
  if (_spinnerTimer) {
    clearInterval(_spinnerTimer);
    _spinnerTimer = null;
  }
  _spinnerStart = null;
}

// =================================================================
// CHAT HISTORY
// =================================================================
async function loadHistory(dirName) {
  try {
    const resp = await fetch('/api/direct/history/' + encodeURIComponent(dirName));
    const data = await resp.json();
    if (!data.conversations || data.conversations.length === 0) return;

    addMsg('phase', '-- Previous conversations (' + data.conversations.length + ') --');

    for (const conv of data.conversations) {
      const ts = (conv.timestamp || '').replace('T', ' ').replace(/-/g, ':').slice(0, 16);

      if (conv.user_message) {
        const container = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = 'msg user';
        div.style.opacity = '0.6';
        div.innerHTML = '<span style="color:#555;font-size:0.75em;">' + escHtml(ts) + '</span> ' + escHtml(conv.user_message);
        container.appendChild(div);
      }

      if (conv.response) {
        const container = document.getElementById('messages');
        const div = document.createElement('div');
        div.className = 'msg assistant';
        div.style.opacity = '0.6';
        let html = escHtml(conv.response).replace(/\n/g, '<br>');
        if (conv.tools_used && conv.tools_used.length > 0) {
          const toolNames = conv.tools_used.map(t => escHtml(t.split('(')[0]));
          const unique = [...new Set(toolNames)];
          html += '<br><span style="color:#555;font-size:0.8em;">Tools: ' + unique.join(', ') + '</span>';
        }
        div.innerHTML = html;
        container.appendChild(div);
      }
    }

    addMsg('phase', '-- Current session --');

    const container = document.getElementById('messages');
    container.scrollTop = container.scrollHeight;
  } catch (e) {
    console.error('Failed to load history:', e);
  }
}

async function eraseHistory() {
  if (!state.projectDir) return;
  if (!confirm('Erase all conversation history for ' + state.projectDir + '? This cannot be undone.')) return;
  try {
    const resp = await fetch('/api/direct/history/' + encodeURIComponent(state.projectDir), {method: 'DELETE'});
    const data = await resp.json();
    if (data.ok) {
      document.getElementById('messages').innerHTML =
        '<div style="color:#5fe88a; padding:12px;">History erased (' + data.deleted + ' conversations). Fresh start.</div>';
    }
  } catch (e) {
    alert('Failed to erase history: ' + e.message);
  }
}
