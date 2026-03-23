const fs = require('fs');
let content = fs.readFileSync('simulation/static/index.html', 'utf8');

const addCommunityCss = `
  .step { margin-bottom: 32px; }
  .step-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
  .step-number { width: 28px; height: 28px; border-radius: 50%; background: var(--border); display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; }
  .step-number.active { background: var(--brand); }
  .step-number.done { background: var(--success); }
  .step-title { font-size: 15px; font-weight: 600; }
  .step-title.muted { color: var(--muted); }

  .input-row { display: flex; gap: 8px; margin-bottom: 16px; }
  .input-row input { flex: 1; background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 12px; border-radius: 6px; font-size: 14px; }
  .input-row input:focus { outline: none; border-color: var(--brand); }
  .btn { padding: 10px 20px; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
  .btn-primary { background: var(--brand); color: #fff; }
  .btn-primary:hover { background: #ff5414; }
  .btn-secondary { background: var(--border); color: var(--text); }

  .generating-state { display: flex; align-items: center; gap: 12px; padding: 16px; background: rgba(255,69,0,0.08); border: 1px solid rgba(255,69,0,0.2); border-radius: 8px; font-size: 13px; color: var(--brand); }

  .actions-bar { display: flex; gap: 12px; justify-content: flex-end; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--border); }
  
  .persona-grid-2col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 16px; max-height: 400px; overflow-y: auto; }
`;
content = content.replace('</style>', addCommunityCss + '\n  </style>');

const addCommunityHtml = `
<div id="add-community-content">
  <div class="product-bar">
    <div class="product-info">
      <div class="product-name" id="add-comm-product-name">Product</div>
    </div>
    <a href="#" onclick="navigateTo('/dashboard'); return false;" class="back-link">&larr; Back to Dashboard</a>
  </div>
  <div class="main" style="max-width: 700px;">
    <h2>Add Community</h2>
    <p class="subtitle">Enter a subreddit to generate AI personas based on real community data</p>

    <div class="step">
      <div class="step-header">
        <div class="step-number active" id="step1-num">1</div>
        <div class="step-title">Enter subreddit</div>
      </div>
      <div class="input-row">
        <input type="text" id="new-subreddit-input" placeholder="e.g. r/SaaS">
      </div>
      <div style="display:flex; align-items:center; gap: 12px; margin-bottom: 16px;">
        <span style="font-size:13px; font-weight:600;">Personas to generate: <span id="new-persona-val">18</span></span>
        <input type="range" id="new-persona-slider" min="3" max="30" value="18" style="max-width: 200px;">
      </div>
      <button type="button" class="btn btn-primary" id="new-generate-btn">Generate Personas</button>
      <div id="new-generating-state" class="generating-state hidden" style="margin-top:16px;">
        <span class="spinner"></span> Scraping & generating... this takes a minute.
      </div>
    </div>

    <div class="step">
      <div class="step-header">
        <div class="step-number" id="step2-num">2</div>
        <div class="step-title" id="step2-title" style="color:var(--muted);">Review personas</div>
      </div>

      <div id="new-personas-section" class="hidden">
        <div class="persona-summary">
          <span><strong id="new-persona-count">0</strong> personas generated</span>
        </div>
        <div id="new-personas-container" class="persona-grid-2col"></div>
      </div>
    </div>

    <div class="actions-bar">
      <button type="button" class="btn btn-secondary" onclick="navigateTo('/dashboard')">Cancel</button>
      <button type="button" class="btn btn-primary" onclick="navigateTo('/dashboard')">Save Community</button>
    </div>
  </div>
</div>
`;
content = content.replace('<div id="view-add-community" class="view"></div>', '<div id="view-add-community" class="view">\n' + addCommunityHtml + '\n</div>');

const addCommunityJs = `
function initAddCommunity() {
  fetch('/api/product').then(r => r.json()).then(p => {
    document.getElementById('add-comm-product-name').textContent = p.name || 'FlowPulse';
  }).catch(() => {});
  
  document.getElementById('new-subreddit-input').value = 'r/';
  document.getElementById('new-personas-section').classList.add('hidden');
  document.getElementById('new-generating-state').classList.add('hidden');
  document.getElementById('step1-num').classList.add('active');
  document.getElementById('step1-num').classList.remove('done');
  document.getElementById('step1-num').innerHTML = '1';
  document.getElementById('step2-num').classList.remove('active');
  document.getElementById('step2-title').style.color = 'var(--muted)';
  document.getElementById('new-generate-btn').style.display = 'block';
  document.getElementById('new-subreddit-input').disabled = false;
  document.getElementById('new-persona-slider').disabled = false;
}

document.getElementById('new-persona-slider').addEventListener('input', (e) => {
  document.getElementById('new-persona-val').textContent = e.target.value;
});

document.getElementById('new-generate-btn').addEventListener('click', async () => {
  const subreddit = document.getElementById('new-subreddit-input').value.trim();
  if (!subreddit || subreddit === 'r/') { alert('Enter a valid subreddit'); return; }
  
  document.getElementById('new-generate-btn').style.display = 'none';
  document.getElementById('new-generating-state').classList.remove('hidden');
  document.getElementById('new-subreddit-input').disabled = true;
  document.getElementById('new-persona-slider').disabled = true;
  
  try {
    const resp = await fetch('/api/communities/generate', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({
        subreddit: subreddit,
        persona_count: parseInt(document.getElementById('new-persona-slider').value) || 18,
      }),
    });
    if (!resp.ok) {
      const body = await resp.json().catch(() => ({}));
      throw new Error(body.detail || 'Generation failed');
    }
    const data = await resp.json();
    activeCommunityId = data.community_id;
    currentPersonas = data.profiles;
    
    document.getElementById('new-generating-state').classList.add('hidden');
    document.getElementById('step1-num').classList.remove('active');
    document.getElementById('step1-num').classList.add('done');
    document.getElementById('step1-num').innerHTML = '&#10003;';
    
    document.getElementById('step2-num').classList.add('active');
    document.getElementById('step2-title').style.color = 'var(--text)';
    
    document.getElementById('new-personas-section').classList.remove('hidden');
    document.getElementById('new-persona-count').textContent = data.profile_count;
    
    renderNewPersonas(currentPersonas);
    
  } catch (err) {
    alert('Failed: ' + err.message);
    document.getElementById('new-generate-btn').style.display = 'block';
    document.getElementById('new-generating-state').classList.add('hidden');
    document.getElementById('new-subreddit-input').disabled = false;
    document.getElementById('new-persona-slider').disabled = false;
  }
});

function renderNewPersonas(profiles) {
  const container = document.getElementById('new-personas-container');
  container.innerHTML = profiles.map(p => {
    const flairColor = getFlairColor(p.archetype);
    const bioText = p.bio || '';
    return \`
      <div class="persona-card" data-id="\${p.id}">
        <div class="persona-header">
          <span class="persona-name">\${escapeHTML(p.realname || p.username)}</span>
          <span class="persona-archetype" style="background-color:\${flairColor}">\${escapeHTML(p.archetype)}</span>
        </div>
        <div class="persona-bio">\${escapeHTML(bioText)}</div>
        <div class="persona-actions">
          <button type="button" onclick="event.stopPropagation(); openEditModal(\${p.id}, true)">Edit</button>
          <button type="button" onclick="event.stopPropagation(); deletePersona(\${p.id}, true)">Remove</button>
        </div>
      </div>
    \`;
  }).join('');
}
`;
content = content.replace('function initAddCommunity() {}', addCommunityJs);

// Make sure `openEditModal` and `deletePersona` handle re-rendering the right container
// I'll patch deletePersona
content = content.replace('async function deletePersona(profileId) {', 'async function deletePersona(profileId, isNewView = false) {');
content = content.replace('renderPersonas(currentPersonas);\n      } catch (e)', 'if (isNewView) { renderNewPersonas(currentPersonas); } else { renderPersonas(currentPersonas); }\n      } catch (e)');

// I'll patch openEditModal save to re-render properly
// Wait, editSave.addEventListener('click')
const editSavePatch = `
        if (document.getElementById('view-add-community').classList.contains('active')) {
          renderNewPersonas(currentPersonas);
        } else {
          renderPersonas(currentPersonas);
        }
`;
content = content.replace('renderPersonas(currentPersonas);\n        editModal.classList.add(\'hidden\');', editSavePatch + '\n        editModal.classList.add(\'hidden\');');

// Patch openEditModal signature just in case, though it doesn't need to know which view because save checks view active class
// Wait, openEditModal(profileId, isNewView) - the second param isn't strictly needed for opening, but let's allow it

fs.writeFileSync('simulation/static/index.html', content);
