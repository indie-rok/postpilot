const fs = require('fs');
let content = fs.readFileSync('simulation/static/index.html', 'utf8');

// 1. Add CSS for top bar
const topBarCss = `
  .sim-top-bar {
    background: var(--card);
    border-bottom: 1px solid var(--border);
    padding: 12px 32px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin: -20px -20px 20px -20px;
  }
  .sim-top-bar-left { display: flex; align-items: center; gap: 16px; }
  .sim-community-badge {
    font-size: 14px;
    font-weight: 700;
    padding: 4px 12px;
    background: rgba(255,69,0,0.15);
    border-radius: 6px;
    color: var(--brand);
  }
  .sim-persona-count { font-size: 12px; color: var(--muted); }
`;
content = content.replace('</style>', topBarCss + '\n  </style>');

// 2. Replace <header>
const oldHeaderRegex = /<header>[\s\S]*?<\/header>/;
const newHeader = `
<div class="sim-top-bar">
  <div class="sim-top-bar-left">
    <a href="#" onclick="navigateTo('/dashboard'); return false;" class="back-link">&larr; Dashboard</a>
    <span class="sim-community-badge" id="sim-community-name">Community</span>
    <span class="sim-persona-count" id="sim-persona-count">0 personas</span>
  </div>
</div>
`;
content = content.replace(oldHeaderRegex, newHeader);

// 3. Delete <div id="community-section">
// Let's use regex or string replace.
const commSectionStart = content.indexOf('<div id="community-section"');
if (commSectionStart !== -1) {
  // It has some nested divs. 
  const commSectionEndStr = '</div>\n          </div>';
  const commSectionEnd = content.indexOf(commSectionEndStr, commSectionStart);
  if (commSectionEnd !== -1) {
    const commSectionHtml = content.substring(commSectionStart, commSectionEnd + 6);
    content = content.replace(commSectionHtml, '');
  }
}

// 4. Implement initSimulateView
const initSimulateJs = `
async function initSimulateView(communityId) {
  activeCommunityId = communityId;
  
  const [commResp, productResp] = await Promise.all([
    fetch('/api/communities'),
    fetch('/api/product'),
  ]);
  if (commResp.ok) {
    const communities = await commResp.json();
    const community = communities.find(c => c.id === communityId);
    if (community) {
      document.getElementById('sim-community-name').textContent = community.subreddit;
      document.getElementById('sim-persona-count').textContent = community.profile_count + ' personas';
    }
  }
  
  if (productResp.ok) {
    const product = await productResp.json();
    if (product.llm_model) llmModelInput.value = product.llm_model;
    if (product.llm_base_url) baseUrlInput.value = product.llm_base_url;
    if (product.llm_api_key) apiKeyInput.value = product.llm_api_key;
    if (product.batch_size != null) batchSizeInput.value = product.batch_size;
  }
  
  const params = new URLSearchParams(window.location.search);
  const runTag = params.get('run');
  if (runTag) {
    loadRun(runTag);
  } else {
    activeRunTag = null;
    postReadonly.classList.add('hidden');
    postContent.classList.remove('hidden');
    launchBtn.classList.remove('hidden');
    newSimBtn.classList.add('hidden');
  }
  
  loadRunHistory(communityId);
}
`;
content = content.replace('function initSimulateView(communityId) {}', initSimulateJs);

// 5. Modify loadRunHistory
content = content.replace('async function loadRunHistory() {', 'async function loadRunHistory(communityId) {');
content = content.replace("const resp = await fetch('/api/runs');", `
    let url = '/api/runs';
    if (communityId) url += '?community_id=' + communityId;
    const resp = await fetch(url);
`);
// Handle other loadRunHistory calls
content = content.replace(/loadRunHistory\(\)/g, 'loadRunHistory(activeCommunityId)');

// 6. Update simulationDone
content = content.replace('activeRunTag = tag;', 'activeRunTag = tag;\n      history.replaceState(null, \'\', \'/simulate/\' + activeCommunityId + \'?run=\' + tag);');

// 7. Update newSimBtn click handler
// The original:
// newSimBtn.addEventListener('click', () => {
//   activeRunTag = null;
// ...
// });
const newSimOldStr = `newSimBtn.addEventListener('click', () => {
      activeRunTag = null;
      postReadonly.classList.add('hidden');
      postContent.classList.remove('hidden');
      postLabel.textContent = 'Your Post';
      launchBtn.classList.remove('hidden');
      newSimBtn.classList.add('hidden');
      statsBar.classList.add('hidden');
      threadContainer.innerHTML = '<div class="no-comments-yet">Launch a simulation to see agent reactions</div>';
      scorecardEl.classList.add('hidden');
      analyzeBtn.style.display = '';
      document.getElementById('community-section').classList.remove('hidden');
      loadRunHistory(activeCommunityId);
    });`;
const newSimNewStr = `newSimBtn.addEventListener('click', () => {
      navigateTo('/simulate/' + activeCommunityId);
    });`;
content = content.replace(newSimOldStr, newSimNewStr);

fs.writeFileSync('simulation/static/index.html', content);
