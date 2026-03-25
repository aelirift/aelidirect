// =================================================================
// BRANCH TESTING BAR
// =================================================================
async function checkBranchStatus() {
  try {
    var resp = await fetch('/api/platform/branch-status');
    var data = await resp.json();
    var bar = document.getElementById('branch-bar');
    if (data.is_branch) {
      _branchIsBranch = true;
      bar.style.display = 'flex';
      document.getElementById('branch-dot').style.display = 'none';
      document.getElementById('branch-label').style.display = '';
      document.getElementById('branch-label').textContent = 'You are on the branch server';
      document.getElementById('branch-label').style.color = '#26a1ff';
      document.getElementById('branch-files').style.display = 'none';
      document.getElementById('branch-test-btn').style.display = 'none';
      document.getElementById('branch-deploy-btn').style.display = 'none';
      document.getElementById('branch-wipe-btn').style.display = 'none';
      return;
    }
    bar.style.display = 'flex';
    // Don't override if heartbeat progress is actively showing
    if (!_hbProgressActive) {
      var branchNewer = data.has_changes && data.changes && data.changes.some(function(c) { return c.branch_newer; });
      _showBranchIdle(branchNewer, data);
    }
  } catch (e) {}
}

function _showBranchIdle(branchNewer, data) {
  document.getElementById('branch-dot').style.display = 'none';
  document.getElementById('branch-label').style.display = branchNewer ? '' : 'none';
  document.getElementById('branch-label').textContent = 'Ready to test';
  document.getElementById('branch-label').style.color = '#5fe88a';
  document.getElementById('branch-files').style.display = branchNewer ? '' : 'none';
  document.getElementById('branch-test-btn').style.display = branchNewer ? '' : 'none';
  document.getElementById('branch-deploy-btn').style.display = branchNewer ? '' : 'none';
  document.getElementById('branch-wipe-btn').style.display = '';
  if (branchNewer && data && data.changes) {
    var fileList = data.changes.filter(function(c) { return c.branch_newer; }).map(function(c) {
      return c.file.split('/').pop();
    }).join(', ');
    document.getElementById('branch-files').textContent = fileList;
  }
}

async function wipeBranch() {
  if (!confirm('Reset branch to match prod? This will overwrite all branch changes including data.')) return;
  try {
    const resp = await fetch('/api/platform/branch-wipe', { method: 'POST' });
    if (!resp.ok) {
      addMsg('error', 'Branch wipe failed: server returned ' + resp.status + '. You may need to restart the server to pick up new endpoints.');
      return;
    }
    const data = await resp.json();
    if (data.ok) {
      document.getElementById('branch-label').style.display = 'none';
      document.getElementById('branch-files').style.display = 'none';
      document.getElementById('branch-test-btn').style.display = 'none';
      addMsg('system', 'Branch wiped — ' + (data.wiped || []).length + ' items synced from prod.');
    } else {
      var errDetail = (data.errors && data.errors.length > 0)
        ? data.errors.join('; ')
        : (data.error || 'unknown');
      addMsg('error', 'Branch wipe partial: ' + errDetail);
    }
  } catch (e) {
    addMsg('error', 'Branch wipe failed: ' + e.message);
  }
}

async function deployBranch() {
  if (!confirm('Deploy branch to prod? This will overwrite prod source files and restart the server.')) return;
  try {
    // Always call branch server (10101) to deploy — prod can't restart itself
    const resp = await fetch('http://127.0.0.1:10101/api/platform/branch-deploy', { method: 'POST' });
    if (!resp.ok) {
      addMsg('error', 'Deploy failed: server returned ' + resp.status);
      return;
    }
    const data = await resp.json();
    if (data.ok) {
      addMsg('system', 'Deployed to prod — ' + (data.deployed || []).join(', ') + '. Restarting prod...');
      // Prod is restarting — poll until it's back, then refresh
      var _retries = 0;
      var _pollReload = setInterval(function() {
        _retries++;
        fetch('/api/config').then(function(r) {
          if (r.ok) { clearInterval(_pollReload); location.reload(); }
        }).catch(function() {});
        if (_retries > 20) { clearInterval(_pollReload); location.reload(); }
      }, 1500);
    } else {
      var errDetail = (data.errors && data.errors.length > 0)
        ? data.errors.join('; ')
        : (data.error || 'unknown');
      addMsg('error', 'Deploy failed: ' + errDetail);
    }
  } catch (e) {
    addMsg('error', 'Deploy failed: ' + e.message);
  }
}
