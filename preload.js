const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('api', {
  openVideo: () => ipcRenderer.invoke('openVideo'),
  openSubtitle: () => ipcRenderer.invoke('openSubtitle'),
  readTextFile: (p) => ipcRenderer.invoke('readTextFile', p),
  saveTextFile: (opts) => ipcRenderer.invoke('saveTextFile', opts),
  loadSubCache: (videoPath) => ipcRenderer.invoke('loadSubCache', videoPath),
  saveSubCache: (videoPath, data) => ipcRenderer.invoke('saveSubCache', { videoPath, data }),
  generateSubtitles: (opts) => ipcRenderer.invoke('generateSubtitles', opts),
  transcribeSegment: (opts) => ipcRenderer.invoke('transcribeSegment', opts),
  diagnoseEnv: () => ipcRenderer.invoke('diagnoseEnv'),
  translateItems: (items, target) => ipcRenderer.invoke('translateItems', { items, target }),
  exportVideo: (opts) => ipcRenderer.invoke('exportVideo', opts),
  removeHardSubs: (opts) => ipcRenderer.invoke('removeHardSubs', opts),
  onDesubProgress: (cb) => {
    const h = (_e, d) => cb(d)
    ipcRenderer.on('desubProgress', h)
    return () => ipcRenderer.removeListener('desubProgress', h)
  }
})
