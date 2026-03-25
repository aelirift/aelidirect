// =================================================================
// TD ANALYSIS
// =================================================================
async function runTDAnalysis() {
  const btn = document.getElementById('td-run-btn');
  const status = document.getElementById('td-status');
  btn.disabled = true;
  btn.textContent = 'Analyzing...';
  status.style.display = 'block';
  status.style.background = '#1a1a3a';
  status.style.color = '#26a1ff';
  status.textContent = 'Running TD analysis across all conversations... This may take a minute.';

  try {
    const resp = await fetch('/api/td-analysis', { method: 'POST' });
    const data = await resp.json();
    if (data.error) {
      status.style.background = '#3a1a1a';
      status.style.color = '#f66';
      status.textContent = 'Error: ' + data.error;
    } else {
      status.style.background = '#1a3a1a';
      status.style.color = '#5fe88a';
      status.textContent = 'Analysis complete! ' + data.conversations_analyzed + ' conversations analyzed.';
      renderTDReport(data.report);
      loadTDHistory();
    }
  } catch (e) {
    status.style.background = '#3a1a1a';
    status.style.color = '#f66';
    status.textContent = 'Failed: ' + e.message;
  }
  btn.disabled = false;
  btn.textContent = 'Run Analysis';
}

function renderTDReport(markdown) {
  const container = document.getElementById('td-report-content');
  // Simple markdown to HTML (headings, bold, code, lists, tables)
  let html = escHtml(markdown);
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
  // Italic
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');
  // Unordered lists
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>');
  html = html.replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>');
  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, '<li>$1</li>');
  // Tables (basic)
  html = html.replace(/^\|(.+)\|$/gm, function(match, content) {
    const cells = content.split('|').map(c => c.trim());
    if (cells.every(c => /^-+$/.test(c))) return ''; // separator row
    const tag = 'td';
    return '<tr>' + cells.map(c => '<' + tag + '>' + c + '</' + tag + '>').join('') + '</tr>';
  });
  html = html.replace(/(<tr>.*<\/tr>\n?)+/g, '<table>$&</table>');
  // Paragraphs (double newlines)
  html = html.replace(/\n\n/g, '</p><p>');
  html = '<p>' + html + '</p>';
  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, '');
  html = html.replace(/<p>(<h[123]>)/g, '$1');
  html = html.replace(/(<\/h[123]>)<\/p>/g, '$1');
  html = html.replace(/<p>(<ul>)/g, '$1');
  html = html.replace(/(<\/ul>)<\/p>/g, '$1');
  html = html.replace(/<p>(<table>)/g, '$1');
  html = html.replace(/(<\/table>)<\/p>/g, '$1');
  html = html.replace(/<p>(<pre>)/g, '$1');
  html = html.replace(/(<\/pre>)<\/p>/g, '$1');

  container.innerHTML = html;
}

async function loadLatestTDReport() {
  try {
    const resp = await fetch('/api/td-analysis');
    const data = await resp.json();
    if (data.report) {
      renderTDReport(data.report);
    }
  } catch (e) {
    console.error('Failed to load TD report:', e);
  }
}

async function loadTDHistory() {
  try {
    const resp = await fetch('/api/td-reports');
    const data = await resp.json();
    const list = document.getElementById('td-history-list');
    if (!data.reports || data.reports.length === 0) {
      list.innerHTML = '<div style="color:#555;">No reports yet.</div>';
      return;
    }
    list.innerHTML = data.reports.map(r =>
      '<div class="td-history-item" onclick="loadTDReport(\'' + escHtml(r.timestamp) + '\')">' +
      '<div class="td-ts">' + escHtml(r.timestamp.replace('T', ' ').replace(/-/g, ':')) + '</div>' +
      '<div class="td-preview">' + escHtml(r.preview.substring(0, 150)) + '...</div>' +
      '</div>'
    ).join('');
  } catch (e) {
    document.getElementById('td-history-list').innerHTML = '<div style="color:#f66;">Failed to load.</div>';
  }
}

async function loadTDReport(timestamp) {
  try {
    const resp = await fetch('/api/td-reports/' + encodeURIComponent(timestamp));
    const data = await resp.json();
    if (data.report) renderTDReport(data.report);
  } catch (e) {
    console.error('Failed to load report:', e);
  }
}
