const { app, BrowserWindow, ipcMain, screen } = require('electron');
const path = require('path');

let mainWindow;
let petWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 1000,
    minHeight: 700,
    title: '租房管理系统',
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      webSecurity: false,
      preload: path.join(__dirname, 'preload.js'),
    },
    icon: path.join(__dirname, 'icon.png'),
  });

  mainWindow.loadURL('http://localhost:5173');
  mainWindow.setMenuBarVisibility(false);

  // 最小化时显示桌面萌宠
  mainWindow.on('minimize', () => {
    showPet();
  });
  mainWindow.on('restore', () => {
    hidePet();
  });
  mainWindow.on('show', () => {
    hidePet();
  });
}

function showPet() {
  if (petWindow && !petWindow.isDestroyed()) return;
  
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  
  petWindow = new BrowserWindow({
    width: 160,
    height: 180,
    x: width - 180,
    y: height - 200,
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    skipTaskbar: true,
    resizable: false,
    hasShadow: false,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  petWindow.loadFile('renderer/pet.html');
  petWindow.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  
  petWindow.on('closed', () => { petWindow = null; });
}

function hidePet() {
  if (petWindow && !petWindow.isDestroyed()) {
    petWindow.close();
    petWindow = null;
  }
}

// 点击宠物恢复主窗口
ipcMain.on('pet-restore', () => {
  if (mainWindow) {
    mainWindow.restore();
    mainWindow.focus();
  }
});

app.whenReady().then(() => {
  // 打包后自动启动 Python 后端
  const isPackaged = !process.defaultApp;
  if (isPackaged) {
    const pythonDir = path.join(process.resourcesPath, 'overtime-app');
    const pythonExe = path.join(pythonDir, 'python', 'python.exe');
    const apiScript = path.join(pythonDir, 'api_server.py');
    if (require('fs').existsSync(apiScript)) {
      const pyProcess = require('child_process').spawn(
        require('fs').existsSync(pythonExe) ? pythonExe : 'python',
        [apiScript],
        { cwd: pythonDir, env: { ...process.env, PYTHONUNBUFFERED: '1' }, stdio: 'ignore' }
      );
      pyProcess.unref();
    }
  }
  createWindow();
});

app.on('window-all-closed', () => {
  hidePet();
  app.quit();
});

app.on('before-quit', () => {
  hidePet();
});
