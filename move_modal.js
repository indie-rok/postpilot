const fs = require('fs');
let content = fs.readFileSync('simulation/static/index.html', 'utf8');

const modalStart = content.indexOf('<div class="modal-overlay hidden" id="edit-modal">');
if (modalStart !== -1) {
  // Let's find the closing tag. The modal ends with "    </div>\n  </div>"
  // Let's use regex or just indexOf.
  const modalStrEnd = content.indexOf('  </div>\n  </div>\n\n  <script>', modalStart);
  if (modalStrEnd !== -1) {
    const endStr = '  </div>\n  </div>';
    const endIndex = content.indexOf(endStr, modalStart) + endStr.length;
    const modalHtml = content.substring(modalStart, endIndex);
    
    // Remove it from current position
    content = content.replace(modalHtml, '');
    
    // Insert it before the closing of #app
    // Wait, let's see how #app closes
    content = content.replace('</div>\n\n  <script>', '</div>\n' + modalHtml + '\n</div>\n\n  <script>');
    fs.writeFileSync('simulation/static/index.html', content);
  }
}
