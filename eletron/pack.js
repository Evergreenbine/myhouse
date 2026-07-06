// 简易打包脚本 — 复制 Electron 文件到输出目录
const fs = require('fs'), path = require('path');

const root = __dirname;
const dist = path.join(root, 'dist', 'manbo');

// 清理
fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });

// 保存图标（如果有）
const iconSrc = path.join(root, 'icon.ico');
const hasIcon = fs.existsSync(iconSrc);

// 复制应用文件
['main.js','preload.js'].forEach(f => fs.copyFileSync(path.join(root,f), path.join(dist,f)));
copyDir(path.join(root,'renderer'), path.join(dist,'renderer'));
fs.writeFileSync(path.join(dist,'package.json'), JSON.stringify({
  name: "manbo", main: "main.js", type: "commonjs"
}, null, 2));

// 复制 Electron
const electronDir = fs.realpathSync(path.join(root,'node_modules','electron','dist'));
copyDir(electronDir, dist);

// 创建启动脚本
const exe = path.join(dist, 'electron.exe');
// 复制 electron.exe 为 manbo.exe
const electronExe = path.join(dist, 'electron.exe');
const manboExe = path.join(dist, 'manbo.exe');
if (fs.existsSync(electronExe)) {
  fs.copyFileSync(electronExe, manboExe);
}

// 创建桌面快捷方式 .bat
const desktop = path.join(process.env.USERPROFILE, 'Desktop', 'manbo.bat');
fs.writeFileSync(desktop, `@echo off\r\ncd /d "${dist}"\r\nstart "" "manbo.exe" "${dist}"\r\n`);
console.log('✅ 打包完成: ' + dist);
console.log('桌面快捷方式: ' + desktop);
if (!hasIcon) console.log('💡 将图标保存为 D:\\code\\manbo\\icon.ico 后重新运行本脚本即可设置图标');

function copyDir(src, dest) {
  fs.mkdirSync(dest, { recursive: true });
  fs.readdirSync(src).forEach(f => {
    const s = path.join(src, f), d = path.join(dest, f);
    if (fs.lstatSync(s).isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  });
}
