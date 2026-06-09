const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('api', {
  openVideo: () => ipcRenderer.invoke('openVideo'),
  openSubtitle: () => ipcRenderer.invoke('openSubtitle'),
  readTextFile: (p) => ipcRenderer.invoke('readTextFile', p),
  saveTextFile: (opts) => ipcRenderer.invoke('saveTextFile', opts),
  generateSubtitles: (opts) => ipcRenderer.invoke('generateSubtitles', opts),
  transcribeSegment: (opts) => ipcRenderer.invoke('transcribeSegment', opts),
  diagnoseEnv: () => ipcRenderer.invoke('diagnoseEnv'),
  translateItems: (items, target) => ipcRenderer.invoke('translateItems', { items, target }),
  exportVideo: (opts) => ipcRenderer.invoke('exportVideo', opts)
})
