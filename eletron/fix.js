const fs = require('fs');
let h = fs.readFileSync('renderer/index.html', 'utf8');
const s = h.indexOf('<script>') + 8;
const e = h.lastIndexOf('</script>');
let js = h.slice(s, e);

// Fix: add missing } after loadCar function
const loadCarStart = js.indexOf('async function loadCar');
let depth = 0;
let inTemplate = false;
for (let i = loadCarStart; i < js.length; i++) {
  if (js[i] === '`') inTemplate = !inTemplate;
  if (inTemplate) continue;
  if (js[i] === '{') depth++;
  if (js[i] === '}') depth--;
  if (depth < 0) {
    console.log('loadCar has extra } at', i);
    break;
  }
  if (depth === 0 && i > loadCarStart + 100) {
    // Check if this is the right closing
    const nextNonWS = js.substring(i + 1, i + 50).trim();
    if (nextNonWS.startsWith('//') || nextNonWS.startsWith('async function') || nextNonWS.startsWith('function ')) {
      console.log('loadCar ends at', i, 'next:', nextNonWS.substring(0, 20));
      // Correct!
      break;
    }
  }
}

// Add missing } before next function
const waterFunc = js.indexOf('// ========== 喝水记录');
const before = js.lastIndexOf('}\n', waterFunc);
console.log('Last } before water:', before, 'context:', JSON.stringify(js.substring(before - 20, before + 20)));

// The loadCar function needs one more closing } at the end
// Let's find where the template ends
let tStart = js.lastIndexOf('`}', waterFunc);
console.log('Last `} before water:', tStart, JSON.stringify(js.substring(Math.max(0,tStart-20), tStart+5)));

// Simply add a } before // ========== 喝水记录
const insertPos = h.indexOf('// ========== 喝水记录');
h = h.substring(0, insertPos) + '}\n\n' + h.substring(insertPos);
fs.writeFileSync('renderer/index.html', h);
console.log('Fixed - added } before water function');

// Verify
const ns = h.indexOf('<script>') + 8;
const njs = h.slice(ns, h.lastIndexOf('</script>'));
try {
  new Function(njs);
  console.log('JS OK');
} catch(ex) {
  console.log('Still error:', ex.message);
}
