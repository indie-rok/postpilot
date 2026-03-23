import re

with open('simulation/static/index.html', 'r') as f:
    content = f.read()

# 1. Add CSS
css_addition = """
    .view { display: none; }
    .view.active { display: block; }
"""
content = content.replace('</style>', css_addition + '  </style>')

# 2. Wrap body content
body_start = content.find('<body>') + len('<body>\n')
# Find the start of the script tag
script_start = content.find('<script>')
body_content = content[body_start:script_start]

new_body_content = """
<div id="app">
  <div id="view-setup" class="view"></div>
  <div id="view-dashboard" class="view"></div>
  <div id="view-add-community" class="view"></div>
  <div id="view-simulate" class="view">
""" + body_content + """
  </div>
</div>
"""
content = content[:body_start] + new_body_content + content[script_start:]

# 3. Add router JS at top of script block
router_js = """
    const routes = {
      '/setup': 'view-setup',
      '/dashboard': 'view-dashboard',
      '/communities/new': 'view-add-community',
    };

    function navigateTo(url) {
      history.pushState(null, '', url);
      routeToView();
    }

    function routeToView() {
      const path = window.location.pathname;
      document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));

      if (path.startsWith('/simulate/')) {
        document.getElementById('view-simulate').classList.add('active');
        const communityId = parseInt(path.split('/')[2]);
        if (communityId) initSimulateView(communityId);
        return;
      }

      const viewId = routes[path];
      if (viewId) {
        document.getElementById(viewId).classList.add('active');
        if (viewId === 'view-dashboard') initDashboard();
        if (viewId === 'view-setup') initSetup();
        if (viewId === 'view-add-community') initAddCommunity();
        return;
      }

      checkProductAndRoute();
    }

    async function checkProductAndRoute() {
      try {
        const resp = await fetch('/api/product');
        if (resp.ok) { navigateTo('/dashboard'); }
        else { navigateTo('/setup'); }
      } catch (e) { navigateTo('/setup'); }
    }

    window.addEventListener('popstate', routeToView);

    function initSetup() {}
    function initDashboard() {}
    function initAddCommunity() {}
    function initSimulateView(communityId) {}

"""
content = content.replace('<script>\n', '<script>\n' + router_js)

# 4. Replace initialization code
# checkRedditStatus();
# ...
# loadRunHistory();
content = content.replace('checkRedditStatus();\n', '')
content = content.replace('loadRunHistory();\n  </script>', 'routeToView();\n  </script>')

with open('simulation/static/index.html', 'w') as f:
    f.write(content)
