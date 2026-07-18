const { contextBridge, ipcRenderer } = require("electron")

contextBridge.exposeInMainWorld("electronClipboard", {
  writeImage: (dataUrl) => ipcRenderer.invoke("clipboard:write-image", dataUrl),
})
