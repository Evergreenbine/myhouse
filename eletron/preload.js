const{contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('electronAPI',{
  petRestore:()=>ipcRenderer.send('pet-restore')
});
