const { app, BrowserWindow, ipcMain, clipboard, nativeImage } = require("electron")
const path = require("path")

const DEFAULT_SERVER_URL = "http://39.106.55.190"

function getAppUrl() {
  if (process.env.ELECTRON_DEV === "1") return "http://127.0.0.1:5173"
  return process.env.MYHOUSE_APP_URL || DEFAULT_SERVER_URL
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 980,
    minHeight: 680,
    title: "FU的小家",
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  })

  win.loadURL(getAppUrl())
}

ipcMain.handle("clipboard:write-image", async (_event, dataUrl) => {
  const image = nativeImage.createFromDataURL(String(dataUrl || ""))
  if (image.isEmpty()) return { success: false, message: "图片数据为空" }
  clipboard.writeImage(image)
  return { success: true }
})

app.whenReady().then(createWindow)

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit()
})

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow()
})
