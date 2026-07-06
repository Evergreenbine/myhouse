const fs = require('fs');
let h = fs.readFileSync('renderer/index.html', 'utf8');

// 1. 删除损坏的 loadCar 函数和多余空行（从 loadCar 到喝水记录之间）
const s = h.indexOf('<script>') + 8;
const js = h.slice(s, h.lastIndexOf('</script>'));
const loadCarStart = js.indexOf('async function loadCar(){');
const nextSection = js.indexOf('// ========== 喝水记录', loadCarStart);
if (loadCarStart >= 0 && nextSection >= 0) {
  h = h.substring(0, s + loadCarStart) + h.substring(s + nextSection);
}
console.log('Removed broken loadCar');

// 2. 在 </body> 前加 <script src="car.js">
h = h.replace('</body>', '<script src="car.js"></script>\n</body>');

// 3. 验证
fs.writeFileSync('renderer/index.html', h);

// 单独验证 car.js
try {
  const carJs = fs.readFileSync('renderer/car.js', 'utf8');
  new Function(carJs);
  console.log('car.js SYNTAX OK');
} catch(ex) {
  console.log('car.js ERROR:', ex.message);
}

// 验证 index.html 内联 JS
const h2 = fs.readFileSync('renderer/index.html', 'utf8');
const s2 = h2.indexOf('<script>') + 8;
const e2 = h2.lastIndexOf('</script>');
const js2 = h2.slice(s2, e2);
try {
  new Function(js2);
  console.log('index.html inline JS SYNTAX OK');
} catch(ex) {
  console.log('index.html inline JS ERROR:', ex.message);
}
