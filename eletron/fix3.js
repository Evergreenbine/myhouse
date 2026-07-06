const fs = require('fs');
let h = fs.readFileSync('renderer/index.html', 'utf8');

// 删除 // ========== 车辆出入 ========== 到 // ========== 喝水记录 ========== 之间的所有内容
const marker1 = '// ========== 车辆出入 ==========';
const marker2 = '// ========== 喝水记录 ==========';
const idx1 = h.indexOf(marker1);
const idx2 = h.indexOf(marker2);
if (idx1 >= 0 && idx2 > idx1) {
  h = h.substring(0, idx1) + marker1 + '\n\n' + h.substring(idx2);
}
fs.writeFileSync('renderer/index.html', h);
console.log('Cleaned up inline car functions');

// Verify
const h2 = fs.readFileSync('renderer/index.html', 'utf8');
const s2 = h2.indexOf('<script>') + 8;
const e2 = h2.lastIndexOf('</script>');
try {
  const js2 = h2.slice(s2, e2);
  // Write to temp and check
  fs.writeFileSync('D:\\code\\manbo\\_tmp2.js', 'async function _w(){\n' + js2 + '\n}');
  const cp = require('child_process');
  const r = cp.spawnSync('node', ['--check', 'D:\\code\\manbo\\_tmp2.js'], {encoding:'utf8'});
  if (r.stderr) {
    console.log('SYNTAX ERROR (line in _tmp2.js):');
    const lines = r.stderr.split('\n');
    for (const l of lines) {
      const m = l.match(/_tmp2\.js:(\d+)/);
      if (m) {
        const ln = parseInt(m[1]) - 1;
        console.log('Line', ln, ':', js2.split('\n')[ln]?.substring(0, 150));
      }
    }
    console.log(r.stderr);
  } else {
    console.log('JS SYNTAX OK!');
  }
} catch(ex) {
  console.log('ERROR:', ex.message);
}
