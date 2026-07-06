const { app, BrowserWindow } = require('electron');
const path = require('path');

app.whenReady().then(() => {
  const win = new BrowserWindow({
    width: 1200,
    height: 800,
    webPreferences: {
      devTools: true,
      nodeIntegration: false,
      contextIsolation: true,
    },
  });
  win.loadFile('renderer/index.html');
  win.webContents.openDevTools({ mode: 'bottom' });
});
