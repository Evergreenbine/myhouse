const fs = require('fs');
const cp = require('child_process');
const result = cp.spawnSync('node', ['--check', 'D:\\code\\manbo\\_tmp_check.js'], {encoding: 'utf8', shell: true});
const err = result.stderr || '';
const out = result.stdout || '';
fs.writeFileSync('D:\\code\\manbo\\check_result.txt', 'STDERR:\n' + err + '\n\nSTDOUT:\n' + out, 'utf8');

// Also try to find the error with more detail
const lines = err.split('\n');
for (const line of lines) {
  console.log('ERR:', line);
  const m = line.match(/_tmp_check\.js:(\d+)/);
  if (m) {
    console.log('Line number:', parseInt(m[1]) - 1);
  }
}
