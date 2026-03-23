import re

with open("simulation/static/index.html", "r") as f:
    content = f.read()

# Step 1: CSS
css_addition = """
    .progress-strip {
      display: flex;
      align-items: center;
      gap: 12px;
      font-size: 13px;
      padding: 12px;
      background: var(--bg);
      border-radius: 4px;
      margin-bottom: 12px;
    }
    .progress-pill {
      padding: 2px 8px;
      border-radius: 12px;
      font-size: 11px;
      font-weight: 600;
      color: #fff;
      white-space: nowrap;
      text-transform: uppercase;
    }
    .progress-bar-bg {
      flex: 1;
      height: 4px;
      border-radius: 2px;
      background: var(--border);
      overflow: hidden;
    }
    .progress-bar-fill {
      height: 100%;
      border-radius: 2px;
      transition: width 0.3s ease;
    }
    .progress-step { color: var(--text); white-space: nowrap; }
    .progress-calls { color: var(--muted); white-space: nowrap; }
"""
content = content.replace("  </style>", css_addition + "  </style>")

# Step 2: HTML
html_addition = """
        <div class="progress-strip hidden" id="progress-strip">
          <span class="progress-pill" id="progress-pill">SETUP</span>
          <div class="progress-bar-bg">
            <div class="progress-bar-fill" id="progress-fill" style="width: 0%;"></div>
          </div>
          <span class="progress-step" id="progress-step">Preparing...</span>
          <span class="progress-calls" id="progress-calls"></span>
        </div>
"""
content = content.replace(
    '<h2 id="progress-title"><span class="spinner" id="progress-spinner"></span>Running Simulation...</h2>\n        <div class="log-container" id="log-container"></div>',
    '<h2 id="progress-title"><span class="spinner" id="progress-spinner"></span>Running Simulation...</h2>\n' + html_addition + '        <div class="log-container" id="log-container"></div>'
)

# Step 3: JS elements
js_elements_addition = """
    const progressStrip = document.getElementById('progress-strip');
    const progressPill = document.getElementById('progress-pill');
    const progressFill = document.getElementById('progress-fill');
    const progressStep = document.getElementById('progress-step');
    const progressCalls = document.getElementById('progress-calls');
"""
content = content.replace(
    "const progressSpinner = document.getElementById('progress-spinner');",
    "const progressSpinner = document.getElementById('progress-spinner');\n" + js_elements_addition.strip()
)

# Step 3: updateProgress function
js_function_addition = """
    function updateProgress(data) {
      progressStrip.classList.remove('hidden');

      const colors = {
        setup: 'var(--border)',
        simulation: 'var(--brand)',
        interview: 'var(--success)',
        complete: 'var(--success)',
      };
      const labels = {
        setup: 'SETUP',
        simulation: 'SIMULATING',
        interview: 'INTERVIEWING',
        complete: 'COMPLETE',
      };

      const color = colors[data.phase] || 'var(--border)';
      progressPill.textContent = labels[data.phase] || data.phase;
      progressPill.style.backgroundColor = color;
      progressFill.style.backgroundColor = color;

      let pct = 0;
      let step = '';

      if (data.phase === 'setup') {
        pct = 0;
        step = 'Preparing...';
      } else if (data.phase === 'simulation') {
        pct = (data.round / data.total_rounds) * 100;
        step = 'Round ' + data.round + '/' + data.total_rounds;
        if (data.hour) step += ' \\u00b7 ' + data.hour;
        if (data.active_agents != null) step += ' \\u00b7 ' + data.active_agents + ' agents';
      } else if (data.phase === 'interview') {
        pct = data.total > 0 ? (data.current / data.total) * 100 : 100;
        step = data.current + '/' + data.total;
        if (data.agent) step += ' \\u00b7 ' + data.agent;
      } else if (data.phase === 'complete') {
        pct = 100;
        step = 'Done';
      }

      progressFill.style.width = pct + '%';
      progressStep.textContent = step;

      if (data.llm_calls != null) {
        progressCalls.textContent = '\\u00b7 ' + data.llm_calls + ' calls';
      }
    }
"""
content = content.replace(
    "function connectWebSocket() {",
    js_function_addition + "\n    function connectWebSocket() {"
)

# Step 4: WS onmessage
content = content.replace(
    """          if (data.type === 'log') {
            appendLog(data.message);
          } else if (data.type === 'done') {""",
    """          if (data.type === 'log') {
            appendLog(data.message);
          } else if (data.type === 'progress') {
            updateProgress(data);
          } else if (data.type === 'done') {"""
)

# Step 5: Reset progress on launch
reset_addition = """
      progressStrip.classList.add('hidden');
      progressFill.style.width = '0%';
      progressCalls.textContent = '';
"""
content = content.replace(
    "logContainer.innerHTML = '';",
    "logContainer.innerHTML = '';" + reset_addition
)

with open("simulation/static/index.html", "w") as f:
    f.write(content)

