import re
with open('simulation/static/mockup-dashboard.html', 'r') as f:
    text = f.read()

style_start = text.find('<style>') + 7
style_end = text.find('</style>')
css = text[style_start:style_end]

print("DASHBOARD CSS:")
for line in css.split('\n'):
    if not line.strip().startswith(':root') and not line.strip().startswith('* {') and not line.strip().startswith('body {') and not line.strip() == '}':
        print(line)
