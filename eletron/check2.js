const fs = require('fs');
const h = fs.readFileSync('renderer/index.html', 'utf8');
const s = h.indexOf('<script>') + 8;
const e = h.lastIndexOf('</script>');
const js = h.slice(s, e);

const wrapper = 'async function _wrapper(){\n' + js + '\n}';
const tmp = 'D:\\code\\manbo\\_tmp_check.js';
fs.writeFileSync(tmp, wrapper, 'utf8');

const cp = require('child_process');
const r = cp.spawnSync('node', ['--check', tmp], { encoding: 'utf8' });
const out = 'STATUS:' + r.status + '\nSTDERR:' + (r.stderr||'') + '\nSTDOUT:' + (r.stdout||'');
fs.writeFileSync('D:\\code\\manbo\\check_output.txt', out, 'utf8');
fs.unlinkSync(tmp);
console.log('Check done, status=' + r.status);
