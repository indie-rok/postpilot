const fs = require('fs');
let content = fs.readFileSync('simulation/static/index.html', 'utf8');

const dashboardCss = `
  .product-bar { background: var(--card); border-bottom: 1px solid var(--border); padding: 16px 32px; display: flex; justify-content: space-between; align-items: center; }
  .product-info { display: flex; align-items: center; gap: 12px; }
  .product-icon { width: 36px; height: 36px; background: var(--brand); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 18px; font-weight: bold; color: #fff; }
  .product-name { font-size: 16px; font-weight: 700; color: #fff; }
  .product-tagline { font-size: 13px; color: var(--muted); }
  .settings-btn { background: transparent; border: 1px solid var(--border); color: var(--muted); padding: 8px 16px; border-radius: 6px; cursor: pointer; font-size: 13px; width: auto; font-weight: normal; }
  .settings-btn:hover { border-color: var(--text); color: var(--text); background: transparent; }

  .main { max-width: 960px; margin: 0 auto; padding: 32px 24px; }
  .section-title { font-size: 13px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 16px; }

  .community-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 16px; margin-bottom: 40px; }
  .community-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; transition: border-color 0.15s; }
  .community-card:hover { border-color: var(--brand); }
  .community-card.add-new { border-style: dashed; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; min-height: 180px; }
  .community-card.add-new:hover { border-color: var(--brand); background: rgba(255,69,0,0.05); }
  .add-icon { font-size: 28px; color: var(--muted); margin-bottom: 8px; }
  .add-label { font-size: 13px; color: var(--muted); }

  .community-name { font-size: 16px; font-weight: 700; margin-bottom: 4px; color: #fff; }
  .community-meta { font-size: 12px; color: var(--muted); margin-bottom: 16px; line-height: 1.6; }
  .community-meta span { display: block; }
  .archetype-pills { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 16px; }
  .archetype-pill { font-size: 10px; padding: 2px 8px; border-radius: 10px; background: rgba(255,255,255,0.08); color: var(--muted); }
  .simulate-btn { width: 100%; padding: 10px; background: var(--brand); color: #fff; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .simulate-btn:hover { background: #ff5414; }

  .runs-table { width: 100%; border-collapse: collapse; }
  .runs-table th { text-align: left; font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 12px; border-bottom: 1px solid var(--border); }
  .runs-table td { padding: 12px; font-size: 13px; border-bottom: 1px solid var(--border); cursor: pointer; }
  .runs-table tr:hover td { background: rgba(255,255,255,0.03); }
  .grade-badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; font-weight: 700; }
  .grade-badge.green { background: rgba(76,175,80,0.2); color: var(--success); }
  .grade-badge.yellow { background: rgba(249,168,37,0.2); color: #f9a825; }
  .grade-badge.red { background: rgba(244,67,54,0.2); color: #f44336; }
  .status-dot { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 6px; }
  .status-dot.complete { background: var(--success); }
  .status-dot.running { background: var(--brand); }
  .tag-text { font-family: monospace; font-size: 12px; }
  .time-ago { color: var(--muted); }
  .subreddit-label { font-size: 11px; padding: 2px 8px; background: rgba(255,255,255,0.06); border-radius: 4px; color: var(--muted); }

  .empty-state { text-align: center; padding: 40px; color: var(--muted); font-size: 14px; }

  .settings-panel { position: fixed; top: 0; right: -400px; width: 400px; height: 100vh; background: var(--bg); border-left: 1px solid var(--border); transition: right 0.3s; z-index: 1000; padding: 24px; overflow-y: auto; box-shadow: -4px 0 24px rgba(0,0,0,0.5); }
  .settings-panel.open { right: 0; }
  .settings-close { background: transparent; border: none; color: var(--muted); font-size: 24px; cursor: pointer; position: absolute; top: 16px; right: 16px; width: auto; padding: 0; }
  .settings-close:hover { color: var(--text); background: transparent; }
`;
content = content.replace('</style>', dashboardCss + '\n  </style>');

const dashboardHtml = `
<div id="dashboard-content"></div>

<div id="settings-panel" class="settings-panel">
  <button class="settings-close" onclick="document.getElementById('settings-panel').classList.remove('open')">&times;</button>
  <h2 style="margin-top:0;">Settings</h2>
  
  <div class="form-group" style="margin-top:24px;">
    <div class="small-label">Product Name</div>
    <input type="text" id="dash-setup-name">
  </div>
  <div class="form-group">
    <div class="small-label">Tagline</div>
    <input type="text" id="dash-setup-tagline">
  </div>
  <div class="form-group">
    <div class="small-label">Description</div>
    <textarea id="dash-setup-description" style="height:100px;"></textarea>
  </div>
  <div class="form-group">
    <div class="small-label">Key Features</div>
    <textarea id="dash-setup-features" style="height:80px;"></textarea>
  </div>
  <div class="form-group">
    <div class="small-label">Pricing</div>
    <input type="text" id="dash-setup-pricing">
  </div>
  <div class="form-group">
    <div class="small-label">Target Audience</div>
    <input type="text" id="dash-setup-target">
  </div>
  
  <h2 style="margin-top:24px;">Simulation Settings</h2>
  <div class="form-group">
    <div class="small-label">LLM Model</div>
    <input type="text" id="dash-setup-llm-model">
  </div>
  <div class="form-group">
    <div class="small-label">LLM Endpoint</div>
    <input type="text" id="dash-setup-llm-url">
  </div>
  <div class="form-group">
    <div class="small-label">LLM API Key</div>
    <input type="password" id="dash-setup-llm-key">
  </div>
  
  <button type="button" id="dash-save-btn" style="margin-top:16px;">Save Settings</button>
</div>
`;
content = content.replace('<div id="view-dashboard" class="view"></div>', '<div id="view-dashboard" class="view">\n' + dashboardHtml + '\n</div>');

const dashboardJs = `
async function initDashboard() {
  const [productResp, commResp, runsResp] = await Promise.all([
    fetch('/api/product'),
    fetch('/api/communities'),
    fetch('/api/runs'),
  ]);
  if (!productResp.ok) { navigateTo('/setup'); return; }
  
  const product = await productResp.json();
  const communities = await commResp.json();
  const runs = await runsResp.json();
  
  renderDashboard(product, communities, runs);
  setupSettingsPanel(product);
}

function renderDashboard(product, communities, runs) {
  const container = document.getElementById('dashboard-content');
  const initial = product.name ? product.name.charAt(0).toUpperCase() : 'P';
  
  let html = \`
    <div class="product-bar">
      <div class="product-info">
        <div class="product-icon">\${initial}</div>
        <div>
          <div class="product-name">\${escapeHTML(product.name || 'Your Product')}</div>
          <div class="product-tagline">\${escapeHTML(product.tagline || '')}</div>
        </div>
      </div>
      <button class="settings-btn" onclick="document.getElementById('settings-panel').classList.add('open')">Settings</button>
    </div>
    <div class="main">
      <div class="section-title">Communities</div>
      <div class="community-grid">
  \`;
  
  communities.forEach(c => {
    const cRuns = runs.filter(r => r.community_id === c.id);
    const lastRun = cRuns.length > 0 ? cRuns[0].created_at : null;
    const timeAgo = lastRun ? new Date(lastRun).toLocaleDateString() : 'Never';
    
    html += \`
      <div class="community-card">
        <div class="community-name">\${escapeHTML(c.subreddit)}</div>
        <div class="community-meta">
          <span>\${c.profile_count} personas &middot; \${cRuns.length} runs</span>
          <span>Last run: \${timeAgo}</span>
        </div>
        <button class="simulate-btn" onclick="navigateTo('/simulate/' + \${c.id})">Simulate</button>
      </div>
    \`;
  });
  
  html += \`
        <div class="community-card add-new" onclick="navigateTo('/communities/new')">
          <div class="add-icon">+</div>
          <div class="add-label">Add community</div>
        </div>
      </div>
      
      <div class="section-title">Recent Runs</div>
  \`;
  
  if (runs.length === 0) {
    html += '<div class="empty-state">No runs yet. Simulate a community to get started.</div>';
  } else {
    html += \`
      <table class="runs-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Community</th>
            <th>Grade</th>
            <th>Comments</th>
            <th>Agents</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
    \`;
    
    runs.forEach(r => {
      const c = communities.find(comm => comm.id === r.community_id);
      const cName = c ? c.subreddit : 'Unknown';
      const score = r.score || 0;
      let gradeStr = 'D', gradeClass = 'red';
      if (score >= 8) { gradeStr = 'A'; gradeClass = 'green'; }
      else if (score >= 6) { gradeStr = 'B'; gradeClass = 'green'; }
      else if (score >= 4) { gradeStr = 'C'; gradeClass = 'yellow'; }
      const date = new Date(r.created_at).toLocaleDateString();
      
      html += \`
        <tr onclick="navigateTo('/simulate/' + \${r.community_id} + '?run=' + '\${r.tag}')">
          <td><span class="status-dot complete"></span><span class="tag-text">\${r.tag}</span></td>
          <td><span class="subreddit-label">\${escapeHTML(cName)}</span></td>
          <td><span class="grade-badge \${gradeClass}">\${gradeStr}</span></td>
          <td>\${r.comments_count || 0}</td>
          <td>\${r.agent_count || 0}</td>
          <td class="time-ago">\${date}</td>
        </tr>
      \`;
    });
    
    html += \`
        </tbody>
      </table>
    \`;
  }
  
  html += '</div>';
  container.innerHTML = html;
}

function setupSettingsPanel(product) {
  document.getElementById('dash-setup-name').value = product.name || '';
  document.getElementById('dash-setup-tagline').value = product.tagline || '';
  document.getElementById('dash-setup-description').value = product.description || '';
  document.getElementById('dash-setup-features').value = product.features || '';
  document.getElementById('dash-setup-pricing').value = product.pricing || '';
  document.getElementById('dash-setup-target').value = product.target_audience || '';
  document.getElementById('dash-setup-llm-model').value = product.llm_model || 'gpt-5-mini';
  document.getElementById('dash-setup-llm-url').value = product.llm_base_url || '';
  document.getElementById('dash-setup-llm-key').value = product.llm_api_key || '';
}

document.getElementById('dash-save-btn').addEventListener('click', async () => {
  const name = document.getElementById('dash-setup-name').value.trim();
  if (!name) { alert('Product name is required'); return; }
  
  const btn = document.getElementById('dash-save-btn');
  btn.disabled = true;
  btn.textContent = 'Saving...';
  
  try {
    const resp = await fetch('/api/product', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        name,
        tagline: document.getElementById('dash-setup-tagline').value.trim() || null,
        description: document.getElementById('dash-setup-description').value.trim() || null,
        features: document.getElementById('dash-setup-features').value.trim() || null,
        pricing: document.getElementById('dash-setup-pricing').value.trim() || null,
        target_audience: document.getElementById('dash-setup-target').value.trim() || null,
        llm_model: document.getElementById('dash-setup-llm-model').value.trim() || null,
        llm_base_url: document.getElementById('dash-setup-llm-url').value.trim() || null,
        llm_api_key: document.getElementById('dash-setup-llm-key').value.trim() || null,
      }),
    });
    if (!resp.ok) throw new Error('Failed to save');
    document.getElementById('settings-panel').classList.remove('open');
    initDashboard(); // refresh
  } catch (err) {
    alert('Error: ' + err.message);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save Settings';
  }
});
`;

content = content.replace('function initDashboard() {}', dashboardJs);

fs.writeFileSync('simulation/static/index.html', content);
