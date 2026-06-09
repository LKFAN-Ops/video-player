const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const path = require('path')
const fs = require('fs')
const crypto = require('crypto')
const { spawn } = require('child_process')
const os = require('os')
let ffmpegPath = null
try {
  ffmpegPath = require('ffmpeg-static')
  // 打包后 ffmpeg-static 的二进制位于 app.asar.unpacked 中，
  // 而 require() 返回的路径仍指向 app.asar，需要替换。
  if (ffmpegPath && ffmpegPath.includes('app.asar') && !ffmpegPath.includes('app.asar.unpacked')) {
    ffmpegPath = ffmpegPath.replace('app.asar', 'app.asar.unpacked')
  }
  if (ffmpegPath && !fs.existsSync(ffmpegPath)) {
    console.error('[ffmpeg] 路径不存在:', ffmpegPath)
    ffmpegPath = null
  } else {
    console.log('[ffmpeg] 路径:', ffmpegPath)
  }
} catch (e) { ffmpegPath = null }

let whisperCmdCache = null
async function detectWhisper() {
  if (whisperCmdCache) return whisperCmdCache
  const tryCmd = (cmd, args) =>
    new Promise((resolve) => {
      const p = spawn(cmd, args, { stdio: 'ignore', env: noProxyEnv() })
      p.on('exit', (code) => resolve(code === 0))
      p.on('error', () => resolve(false))
      setTimeout(() => resolve(false), 15000)
    })
  const fixedPy = 'D:\\Python\\python.exe'
  if (await tryCmd(fixedPy, ['-m', 'whisper', '--help'])) {
    whisperCmdCache = { cmd: fixedPy, prefix: ['-m', 'whisper'] }
    return whisperCmdCache
  }
  if (await tryCmd('whisper', ['--help'])) {
    whisperCmdCache = { cmd: 'whisper', prefix: [] }
    return whisperCmdCache
  }
  if (await tryCmd('python', ['-m', 'whisper', '--help'])) {
    whisperCmdCache = { cmd: 'python', prefix: ['-m', 'whisper'] }
    return whisperCmdCache
  }
  if (await tryCmd('py', ['-3', '-m', 'whisper', '--help'])) {
    whisperCmdCache = { cmd: 'py', prefix: ['-3', '-m', 'whisper'] }
    return whisperCmdCache
  }
  try {
    const out = await new Promise((resolve) => {
      const p = spawn('where', ['python'], { stdio: ['ignore', 'pipe', 'ignore'] })
      let buf = ''
      p.stdout.on('data', (d) => (buf += d.toString()))
      p.on('exit', () => resolve(buf))
      p.on('error', () => resolve(''))
      setTimeout(() => resolve(''), 5000)
    })
    const pathLine = (out || '').split(/\r?\n/).find((l) => l.toLowerCase().endsWith('python.exe'))
    if (pathLine) {
      const pyPath = pathLine.trim()
      if (await tryCmd(pyPath, ['-m', 'whisper', '--help'])) {
        whisperCmdCache = { cmd: pyPath, prefix: ['-m', 'whisper'] }
        return whisperCmdCache
      }
    }
  } catch {}
  return null
}

let fwCmdCache = null
async function detectFasterWhisper() {
  if (fwCmdCache) return fwCmdCache
  const tryPy = (cmd, args) =>
    new Promise((resolve) => {
      const p = spawn(cmd, args, { stdio: 'ignore', env: noProxyEnv() })
      p.on('exit', (code) => resolve(code === 0))
      p.on('error', () => resolve(false))
      setTimeout(() => resolve(false), 15000)
    })
  const fixedPy = 'D:\\Python\\python.exe'
  if (await tryPy(fixedPy, ['-c', 'import faster_whisper'])) {
    fwCmdCache = { cmd: fixedPy }
    return fwCmdCache
  }
  if (await tryPy('python', ['-c', 'import faster_whisper'])) {
    fwCmdCache = { cmd: 'python' }
    return fwCmdCache
  }
  if (await tryPy('py', ['-3', '-c', 'import faster_whisper'])) {
    fwCmdCache = { cmd: 'py', prefix: ['-3'] }
    return fwCmdCache
  }
  try {
    const out = await new Promise((resolve) => {
      const p = spawn('where', ['python'], { stdio: ['ignore', 'pipe', 'ignore'] })
      let buf = ''
      p.stdout.on('data', (d) => (buf += d.toString()))
      p.on('exit', () => resolve(buf))
      p.on('error', () => resolve(''))
      setTimeout(() => resolve(''), 5000)
    })
    const pathLine = (out || '').split(/\r?\n/).find((l) => l.toLowerCase().endsWith('python.exe'))
    if (pathLine) {
      const pyPath = pathLine.trim()
      if (await tryPy(pyPath, ['-c', 'import faster_whisper'])) {
        fwCmdCache = { cmd: pyPath }
        return fwCmdCache
      }
    }
  } catch {}
  return null
}

app.commandLine.appendSwitch('high-dpi-support', '1')
app.commandLine.appendSwitch('force-device-scale-factor', '1')
// 禁用硬件加速：修复 Windows 上某些 GPU 驱动导致的音画不同步问题
app.disableHardwareAcceleration()



const createWindow = () => {
  const win = new BrowserWindow({
    width: 1024,
    height: 700,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js')
    }
  })
  win.webContents.setZoomFactor(1)
  win.webContents.setVisualZoomLevelLimits(1, 1)
  win.loadFile(path.join(__dirname, 'renderer', 'index.html'))
}

app.whenReady().then(() => {
  createWindow()
  // 提前预热翻译 / Whisper 服务，让模型在后台加载，用户勾选实时字幕时已就绪
  startTranslationService().catch(() => {})
  startTranscribeService().catch(() => {})
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

ipcMain.handle('openVideo', async () => {
  const res = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'Video', extensions: ['mp4', 'mkv', 'mov', 'webm', 'avi', 'mpg', 'mpeg', 'wmv', 'flv', 'm4v', 'ts'] }]
  })
  if (res.canceled || !res.filePaths[0]) return null
  return res.filePaths[0]
})

ipcMain.handle('openSubtitle', async () => {
  const res = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'Subtitle', extensions: ['srt', 'vtt'] }]
  })
  if (res.canceled || !res.filePaths[0]) return null
  return res.filePaths[0]
})

ipcMain.handle('saveTextFile', async (evt, { defaultPath, data }) => {
  const res = await dialog.showSaveDialog({ defaultPath })
  if (res.canceled || !res.filePath) return null
  await fs.promises.writeFile(res.filePath, data, 'utf-8')
  return res.filePath
})

ipcMain.handle('readTextFile', async (evt, filePath) => {
  const data = await fs.promises.readFile(filePath, 'utf-8')
  return data
})

// =============== 字幕缓存（整片预转写结果落盘，二次打开零延迟） ===============
function subCacheDir() {
  const dir = path.join(app.getPath('userData'), 'subcache')
  try { fs.mkdirSync(dir, { recursive: true }) } catch (_) {}
  return dir
}
function subCacheFile(videoPath) {
  const h = crypto.createHash('md5').update(String(videoPath)).digest('hex')
  return path.join(subCacheDir(), h + '.json')
}
ipcMain.handle('loadSubCache', async (evt, videoPath) => {
  try {
    const raw = await fs.promises.readFile(subCacheFile(videoPath), 'utf-8')
    const obj = JSON.parse(raw)
    // 用文件大小校验：视频被替换/重新编码后缓存自动失效
    const st = await fs.promises.stat(videoPath)
    if (obj.meta && Number(obj.meta.size) !== Number(st.size)) return null
    return obj
  } catch (_) { return null }
})
ipcMain.handle('saveSubCache', async (evt, { videoPath, data }) => {
  try {
    const st = await fs.promises.stat(videoPath)
    const obj = { meta: { size: st.size, mtimeMs: st.mtimeMs, savedAt: Date.now() }, ...data }
    await fs.promises.writeFile(subCacheFile(videoPath), JSON.stringify(obj), 'utf-8')
    return true
  } catch (_) { return false }
})

ipcMain.handle('exportVideo', async (evt, { inputPath, subtitlePath, outputPath, removeRegion }) => {
  try {
    // 检查FFmpeg是否可用
    const ffCmd = ffmpegPath || 'ffmpeg'
    const hasFfmpeg = await new Promise((resolve) => {
      const p = spawn(ffCmd, ['-version'], { stdio: 'ignore' })
      p.on('exit', (code) => resolve(code === 0))
      p.on('error', () => resolve(false))
      setTimeout(() => resolve(false), 5000)
    })
    
    if (!hasFfmpeg) {
      return { success: false, error: 'ffmpeg_not_found' }
    }
    
    // 构建 -vf 滤镜链：先用 delogo 去除原片硬字幕（像素插值，真去除），再烧录双语字幕
    const filters = []

    // 去原片硬字幕：removeRegion 为视频原始帧的整数像素矩形 {x,y,w,h}
    if (removeRegion && [removeRegion.x, removeRegion.y, removeRegion.w, removeRegion.h].every(n => Number.isFinite(n) && n >= 0)) {
      const x = Math.max(1, Math.round(removeRegion.x))
      const y = Math.max(1, Math.round(removeRegion.y))
      const w = Math.max(1, Math.round(removeRegion.w))
      const h = Math.max(1, Math.round(removeRegion.h))
      filters.push(`delogo=x=${x}:y=${y}:w=${w}:h=${h}`)
    }

    // 烧录字幕（可选）。Windows 下字幕滤镜需把反斜杠 / 冒号转义，否则会被解析器吃掉
    if (subtitlePath) {
      const escSub = String(subtitlePath)
        .replace(/\\/g, '/')
        .replace(/:/g, '\\:')
        .replace(/'/g, "\\'")
      filters.push(`subtitles='${escSub}':force_style='FontName=Arial,FontSize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=20'`)
    }

    const args = ['-i', inputPath]
    if (filters.length) args.push('-vf', filters.join(','))
    args.push(
      '-c:v', 'libx264',        // 视频编码器
      '-crf', '23',             // 视频质量，范围0-51，23为默认
      '-preset', 'medium',      // 编码速度预设
      '-c:a', 'aac',            // 音频编码器，确保兼容性
      '-b:a', '128k',           // 音频比特率
      '-y',                     // 覆盖输出文件
      outputPath                // 输出文件路径
    )
    
    console.log('FFmpeg命令:', ffCmd, args)
    
    // 执行FFmpeg命令
    const result = await new Promise((resolve) => {
      const p = spawn(ffCmd, args, {
        stdio: ['ignore', 'pipe', 'pipe'],
        shell: true  // 在Windows上需要使用shell来处理路径中的空格
      })
      
      let stdout = ''
      let stderr = ''
      
      p.stdout.on('data', (data) => {
        stdout += data.toString()
        console.log('FFmpeg输出:', data.toString())
      })
      
      p.stderr.on('data', (data) => {
        stderr += data.toString()
        console.log('FFmpeg错误:', data.toString())
      })
      
      p.on('exit', (code) => {
        console.log('FFmpeg退出代码:', code)
        resolve({ 
          success: code === 0, 
          stdout, 
          stderr, 
          exitCode: code 
        })
      })
      
      p.on('error', (err) => {
        console.error('FFmpeg执行错误:', err)
        resolve({ success: false, error: 'execution_error', details: err.message })
      })
      
      // 设置超时（最多2小时）
      setTimeout(() => {
        p.kill()
        resolve({ success: false, error: 'timeout' })
      }, 2 * 60 * 60 * 1000)
    })
    
    if (result.success) {
      return { success: true, outputPath }
    } else {
      return { success: false, error: 'ffmpeg_failed', details: result.stderr }
    }
    
  } catch (error) {
    console.error('导出视频错误:', error)
    return { success: false, error: 'unknown', details: error.message }
  }
})

ipcMain.handle('generateSubtitles', async (evt, { inputPath, lang }) => {
  const tmpDir = os.tmpdir()
  const outDir = tmpDir
  const run = async () => {
    const fw = await detectFasterWhisper()
    if (!fw) return { path: null, need: 'whisper' }
    // 整片转写：模型可用 WHISPER_MODEL 覆盖（small/medium 更准）；transcribe.py 内部用批量推理加速、且会按 small→base→tiny 回退
    const fullModel = process.env.WHISPER_MODEL || 'base'
    const args = [path.join(resolveScriptsDir(), 'transcribe.py'), '--input', inputPath, '--output_dir', outDir, '--model', fullModel, '--device', 'cpu', '--compute_type', 'int8']
    if (lang && lang !== 'auto') args.push('--language', lang)
    const ok = await new Promise((resolve) => {
      const pyArgs = args
      const p = spawn(fw.cmd, pyArgs, { stdio: 'ignore', env: pythonEnv() })
      p.on('exit', (code) => resolve(code === 0))
      p.on('error', () => resolve(false))
      setTimeout(() => resolve(false), 600000)
    })
    if (!ok) return { path: null, error: 'whisper_failed' }
    const base = path.basename(inputPath)
    const name = base.replace(path.extname(base), '')
    const srt = path.join(outDir, `${name}.srt`)
    try {
      await fs.promises.access(srt, fs.constants.F_OK)
      return { path: srt }
    } catch {
      return { path: null, error: 'srt_missing' }
    }
  }
  const promise = run()
  const result = await promise
  return result
})

// 商业级硬字幕去除（STTN，GPU）：调用 scripts/desub_sttn.py，进度经 'desubProgress' 推给渲染层
ipcMain.handle('removeHardSubs', async (evt, { inputPath, outputPath, region, maskMode, device }) => {
  const fw = await detectFasterWhisper()
  if (!fw) return { success: false, error: 'no_python' }
  const ffCmd = ffmpegPath || 'ffmpeg'
  const scriptsDir = resolveScriptsDir()
  const modelPath = path.join(resolveHfHome(), 'sttn', 'sttn.pth')

  const args = [
    ...(fw.prefix || []),
    path.join(scriptsDir, 'desub_sttn.py'),
    '--input', inputPath,
    '--output', outputPath,
    '--model', modelPath,
    '--region', `${region.x},${region.y},${region.w},${region.h}`,
    '--mask_mode', maskMode || 'auto',
    '--device', device || 'cuda',
    '--ffmpeg', ffCmd
  ]

  console.log('[desub] 启动:', fw.cmd, args.join(' '))
  return await new Promise((resolve) => {
    const p = spawn(fw.cmd, args, { env: pythonEnv() })
    let stderrTail = ''
    let lastErr = null
    const onLine = (line) => {
      const m = line.match(/^PROGRESS\s+(\d+)\s+(\d+)/)
      if (m) {
        try { evt.sender.send('desubProgress', { done: +m[1], total: +m[2] }) } catch {}
      }
    }
    let outBuf = ''
    p.stdout.on('data', (d) => {
      outBuf += d.toString()
      let i
      while ((i = outBuf.indexOf('\n')) >= 0) {
        onLine(outBuf.slice(0, i).trim())
        outBuf = outBuf.slice(i + 1)
      }
    })
    p.stderr.on('data', (d) => {
      const s = d.toString()
      stderrTail = (stderrTail + s).slice(-2000)
      if (s.includes('ERR:')) lastErr = s.trim()
      console.error('[desub-err]:', s.trim())
    })
    p.on('error', () => resolve({ success: false, error: 'spawn_failed' }))
    p.on('exit', (code) => {
      if (code === 0) resolve({ success: true, outputPath })
      else resolve({ success: false, error: lastErr || 'desub_failed', details: stderrTail })
    })
    // 长视频可能很久，给 4 小时上限
    setTimeout(() => { try { p.kill() } catch {}; resolve({ success: false, error: 'timeout' }) }, 4 * 60 * 60 * 1000)
  })
})

ipcMain.handle('diagnoseEnv', async () => {
  const info = { ffmpeg: false, whisper: false, python: false, tmpWritable: false }
  try {
    const ffCmd = ffmpegPath || 'ffmpeg'
    info.ffmpeg = await new Promise((resolve) => {
      const p = spawn(ffCmd, ['-version'], { stdio: 'ignore' })
      p.on('exit', (code) => resolve(code === 0))
      p.on('error', () => resolve(false))
      setTimeout(() => resolve(false), 5000)
    })
  } catch {}
  try {
    info.python = await new Promise((resolve) => {
      const p = spawn('python', ['-V'], { stdio: 'ignore' })
      p.on('exit', (code) => resolve(code === 0))
      p.on('error', () => resolve(false))
      setTimeout(() => resolve(false), 5000)
    })
  } catch {}
  try {
    const w = await detectWhisper()
    info.whisper = !!w
  } catch {}
  try {
    const fp = path.join(os.tmpdir(), `w_${Date.now()}.txt`)
    await fs.promises.writeFile(fp, 'ok', 'utf-8')
    await fs.promises.unlink(fp)
    info.tmpWritable = true
  } catch {}
  return info
})

// 全局变量
let mtServerProc = null
let port = 8000

// 解析模型缓存目录：优先使用 __dirname/models_cache（开发态或打包带模型时），
// 否则回退到该用户机器上已有的固定位置 E:\bofangqi\models_cache，
// 最后兜底到 userData 目录（首次运行时由 HuggingFace 自动下载）。
function resolveHfHome() {
  const candidates = [
    process.env.HF_HOME,
    path.join(__dirname, 'models_cache'),
    path.join(__dirname, '..', 'models_cache'),
    'E:\\bofangqi\\models_cache',
    path.join(app.getPath('userData'), 'models_cache')
  ].filter(Boolean)
  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return c
    } catch (_) {}
  }
  const fallback = path.join(app.getPath('userData'), 'models_cache')
  try { fs.mkdirSync(fallback, { recursive: true }) } catch (_) {}
  return fallback
}

// 解析 scripts 目录：开发态 __dirname/scripts；打包后由 extraResources 拷贝到 resources/scripts
function resolveScriptsDir() {
  const candidates = [
    path.join(__dirname, 'scripts'),
    path.join(process.resourcesPath || '', 'scripts')
  ]
  for (const c of candidates) {
    try {
      if (fs.existsSync(c)) return c
    } catch (_) {}
  }
  return path.join(__dirname, 'scripts')
}

// 给所有子进程使用：清掉系统代理变量，强制直连，避免 Clash/V2Ray 关闭后被 SSL 重置
function noProxyEnv(extra = {}) {
  const base = { ...process.env }
  for (const k of ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'ALL_PROXY', 'all_proxy']) {
    delete base[k]
  }
  base.NO_PROXY = '*'
  base.no_proxy = '*'
  return Object.assign(base, extra)
}

// Python 子进程：在无代理基础上锁定 HuggingFace 缓存目录与镜像
function pythonEnv(extra = {}) {
  const hf = resolveHfHome()
  return noProxyEnv({
    PYTHONUNBUFFERED: '1',
    HF_ENDPOINT: 'https://hf-mirror.com',
    HF_HUB_ENABLE_HF_TRANSFER: '0',
    HF_HUB_DISABLE_TELEMETRY: '1',
    HF_HOME: hf,
    HF_HUB_CACHE: path.join(hf, 'hub'),
    TRANSFORMERS_CACHE: hf,
    ...extra
  })
}

// 启动翻译服务的函数
async function startTranslationService() {
  // 检查是否已经有服务在运行
  if (mtServerProc) {
    return { ok: true, port }
  }
  
  // 检查是否有Python环境
  const pythonPath = process.env.PYTHON_PATH || 'python'
  try {
    const pythonVersion = await new Promise((resolve, reject) => {
      const p = spawn(pythonPath, ['--version'], { stdio: ['ignore', 'pipe', 'ignore'] })
      let output = ''
      p.stdout.on('data', (data) => output += data.toString())
      p.on('exit', (code) => {
        if (code === 0) {
          resolve(output.trim())
        } else {
          reject(new Error('Python未找到或版本不兼容'))
        }
      })
      p.on('error', reject)
    })
    
    console.log('Python环境检测成功:', pythonVersion)
    
    // 启动翻译服务
    const scriptsDir = resolveScriptsDir()
    const hfHome = resolveHfHome()
    const pyCmd = pythonPath
    const pyArgs = [path.join(scriptsDir, 'mt_server.py'), '--port', String(port)]
    const mtProc = spawn(pyCmd, pyArgs, { env: pythonEnv() })

    console.log('模型缓存目录设置为:', hfHome)
    console.log('翻译脚本目录:', scriptsDir)
    
    mtProc.stdout.on('data', (data) => {
      const line = data.toString().trim()
      if (line) {
        console.log('[翻译服务]:', line)
      }
    })
    
    mtProc.stderr.on('data', (data) => {
      const line = data.toString().trim()
      if (line) {
        console.error('[翻译服务错误]:', line)
      }
    })
    
    mtProc.on('exit', (code) => {
      mtServerProc = null
      console.log('[翻译服务]已退出，代码:', code)
    })
    
    // 等待 Python 进程启动
    await new Promise(resolve => setTimeout(resolve, 3000))

    // 保存进程引用
    mtServerProc = mtProc

    // 发送一条空白预热请求，触发 HuggingFace 模型加载进内存
    // 在后台异步执行，不阻塞服务标记为就绪
    ;(async () => {
      try {
        await fetch(`http://localhost:${port}/translate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: [{ start: '00:00:00,000', end: '00:00:01,000', text: 'hello' }], target: 'zh' })
        })
        console.log('[翻译服务] 模型预热完成')
      } catch (e) {
        console.log('[翻译服务] 预热请求失败（不影响后续使用）:', e.message)
      }
    })()

    return { ok: true, port }
    
  } catch (e) {
    console.error('Python环境检测失败或本地翻译服务启动失败:', e)
    return { ok: false, error: e.message }
  }
}

ipcMain.handle('translateText', async (evt, { texts, target }) => {
  console.log('=== 收到翻译文本请求 ===')
  console.log('目标语言:', target)
  console.log('文本数量:', texts.length)
  if (texts.length > 0) {
    console.log('第一个文本内容:', texts[0])
  }
  
  // 确保翻译服务已经启动
  const startResult = await startTranslationService()
  if (!startResult.ok) {
    console.error('翻译服务启动失败:', startResult.error)
    return { ok: false, error: startResult.error }
  }
  
  // 使用本地翻译服务翻译文本
  try {
    const translateItems = texts.map(text => ({ text }))
    
    // 构建API请求
    const response = await fetch(`http://localhost:${port}/translate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        items: translateItems,
        target: target
      })
    })
    
    if (!response.ok) {
      throw new Error(`HTTP错误! 状态: ${response.status}`)
    }
    
    const result = await response.json()
    console.log('翻译服务返回结果:', result)
    
    return result
    
  } catch (e) {
    console.error('翻译服务调用失败:', e)
    return { ok: false, error: e.message }
  }
})

ipcMain.handle('translateItems', async (evt, { items, target }) => {
  console.log('=== 收到翻译字幕请求 ===')
  console.log('目标语言:', target)
  console.log('字幕项数量:', items.length)
  if (items.length > 0) {
    console.log('第一个字幕项内容:', items[0].text)
  }
  
  // 确保翻译服务已经启动
  const startResult = await startTranslationService()
  if (!startResult.ok) {
    console.error('翻译服务启动失败:', startResult.error)
    return { ok: false, items: [] }
  }
  
  // 使用本地翻译服务翻译字幕项
  try {
    // 构建API请求
    const response = await fetch(`http://localhost:${port}/translate`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        items: items,
        target: target
      })
    })
    
    if (!response.ok) {
      throw new Error(`HTTP错误! 状态: ${response.status}`)
    }
    
    const result = await response.json()
    console.log('翻译服务返回结果:', result)
    
    return result
    
  } catch (e) {
    console.error('翻译服务调用失败:', e)
    return { ok: false, items: [] }
  }
})

// =============== 常驻 Whisper 服务（实时识别加速） ===============
let whisperProc = null
let whisperPort = 8001
let whisperReady = false

async function startTranscribeService() {
  if (whisperProc) return { ok: true, port: whisperPort }

  const fw = await detectFasterWhisper()
  if (!fw) {
    console.warn('[whisper] 未检测到 faster_whisper，实时识别不可用')
    return { ok: false, error: 'no_faster_whisper' }
  }

  const scriptsDir = resolveScriptsDir()
  const hfHome = resolveHfHome()
  const py = fw.cmd
  const args = [
    path.join(scriptsDir, 'whisper_server.py'),
    '--port', String(whisperPort),
    '--model', process.env.WHISPER_MODEL || 'small',  // 精度优先；可用 WHISPER_MODEL 覆盖；缺失时服务自动回退到 base/tiny
    '--device', 'cpu',
    '--compute_type', 'int8'
  ]
  console.log('[whisper] 启动:', py, args.join(' '))
  whisperProc = spawn(py, args, { env: pythonEnv() })
  whisperProc.stdout.on('data', d => {
    const line = d.toString().trim()
    if (line) {
      console.log('[whisper]:', line)
      if (line.includes('监听') || line.includes('listening')) whisperReady = true
    }
  })
  whisperProc.stderr.on('data', d => {
    const line = d.toString().trim()
    if (line) console.error('[whisper-err]:', line)
  })
  whisperProc.on('exit', (code) => {
    console.log('[whisper] 进程退出，code=', code)
    whisperProc = null
    whisperReady = false
  })

  // 健康检查：等待端口可达 + 模型就绪（最多 90 秒）
  const deadline = Date.now() + 90000
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`http://127.0.0.1:${whisperPort}/health`)
      if (r.ok) {
        const j = await r.json()
        if (j && j.ready) { whisperReady = true; break }
      }
    } catch {}
    await new Promise(r => setTimeout(r, 500))
  }
  return { ok: whisperReady, port: whisperPort }
}

ipcMain.handle('transcribeSegment', async (evt, { inputPath, startSec, durationSec, lang }) => {
  // 1) ffmpeg 抽 WAV 片段
  const ffCmd = ffmpegPath || 'ffmpeg'
  const tmpDir = os.tmpdir()
  const segWav = path.join(tmpDir, `seg_${Date.now()}_${Math.floor(Math.random()*1e6)}.wav`)
  const ffArgs = [
    '-ss', String(startSec), '-t', String(durationSec),
    '-i', inputPath,
    '-vn', '-ac', '1', '-ar', '16000', '-f', 'wav',
    '-y', segWav
  ]
  const ffOk = await new Promise((resolve) => {
    const p = spawn(ffCmd, ffArgs, { stdio: 'ignore' })
    p.on('exit', (code) => resolve(code === 0))
    p.on('error', () => resolve(false))
    setTimeout(() => { try { p.kill() } catch {}; resolve(false) }, 30000)
  })
  if (!ffOk) {
    try { await fs.promises.unlink(segWav) } catch {}
    return { srt: null, need: 'ffmpeg' }
  }

  // 2) 调用常驻 Whisper 服务（必要时启动）
  if (!whisperReady) {
    const r = await startTranscribeService()
    if (!r.ok) {
      try { await fs.promises.unlink(segWav) } catch {}
      return { srt: null, need: 'whisper' }
    }
  }

  try {
    const resp = await fetch(`http://127.0.0.1:${whisperPort}/transcribe`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: segWav, language: lang })
    })
    try { await fs.promises.unlink(segWav) } catch {}
    if (!resp.ok) return { srt: null, need: 'whisper' }
    const data = await resp.json()
    if (!data || !data.ok) return { srt: null, need: 'whisper' }
    return { srt: data.srt || '' }
  } catch (e) {
    console.error('[whisper] 请求失败:', e)
    try { await fs.promises.unlink(segWav) } catch {}
    return { srt: null, need: 'whisper' }
  }
})
