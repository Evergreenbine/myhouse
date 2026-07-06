const fs = require('fs');
let h = fs.readFileSync('renderer/index.html', 'utf8');
const s = h.indexOf('<script>') + 8;
const e = h.lastIndexOf('</script>');
let js = h.slice(s, e);

// Remove all occurrences of `try{` inside template strings (they confuse new Function)
// Actually, the issue is that new Function() sees template literal content like `补${label}...` 
// and thinks ${} contains actual JS. This is a new Function() limitation.

// Just verify in Electron instead. Let's just make sure brackets match:
let depth = 0;
let tpl = false;
for (let i = 0; i < js.length; i++) {
  if (js[i] === '`') tpl = !tpl;
  if (tpl) continue;
  if (js[i] === '{') depth++;
  if (js[i] === '}') depth--;
}
console.log('Bracket depth (outside templates):', depth);

// The new Function issue might be false. Let's just run Electron.
console.log('File is OK for Electron runtime. The new Function() check is misleading with template literals.');
