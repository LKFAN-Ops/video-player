// =============== 视频字幕播放器 主控 ===============
// 设计要点：
// 1. 字幕一律由 #overlay 渲染，不再使用 <track>，避免双轨道竞争。
// 2. 状态由 player 对象集中管理：
//    src / zh / ru 三组数据，render 时根据 displayLang 选择拼接。
// 3. 加载/生成完原文后立即显示原文，翻译异步完成后再升级为译文，
//    避免翻译期间"什么都看不到"的问题。

(() => {
  // ---------- DOM ----------
  const $ = id => document.getElementById(id)
  const videoEl       = $('video')
  const playerEl      = document.querySelector('.player')
  const overlayEl     = $('overlay')
  const statusEl      = $('status')
  const openVideoBtn  = $('openVideo')
  const openSubBtn    = $('openSubtitle')
  const genLangSel    = $('genLang')
  const generateBtn   = $('generate')
  const realtimeChk   = $('realtimeToggle')
  const displayLangSel= $('displayLang')
  const rawModeChk    = $('rawModeToggle')
  const deSubChk      = $('deSubToggle')
  const subMaskEl     = $('subMask')
  const maskHandleEl  = subMaskEl ? subMaskEl.querySelector('.mask-handle') : null
  const toZhBtn       = $('toZh')
  const toRuBtn       = $('toRu')
  const saveSrtBtn    = $('saveSrt')
  const exportVideoBtn= $('exportVideo')
  const removeHardSubBtn = $('removeHardSub')

  if (!videoEl || !overlayEl) {
    console.error('缺少关键 DOM 元素，脚本中止')
    return
  }

  // ---------- State ----------
  const state = {
    videoPath: null,
    src: [],            // 原文字幕
    zh: [],             // 中文译文
    ru: [],             // 俄文译文
    realtime: false,
    realtimeTimer: null,
    realtimeSegSec: 5,                // 单段时长（秒）：太短会切碎单词导致识别错
    realtimeOverlapSec: 0.5,          // 段间重叠，缓解边界截断
    realtimeLookaheadSegs: 3,         // 提前预拉取的段数
    realtimeProcessed: new Set(),
    realtimeInflight: 0,
    realtimeMaxParallel: 2,           // 并发上限：Whisper base 单线程跑得动 2 路
    translateInflight: false,
    lastTranslateAt: 0,
    // 去原片硬字幕：on 开关 + 归一化矩形（相对视频画面内容区，0~1）
    deSub: false,
    maskRect: { x: 0.06, y: 0.80, w: 0.88, h: 0.16 }  // 默认底部字幕条
  }

  // 默认双语显示
  if (displayLangSel) displayLangSel.value = 'zh-ru'

  // ---------- 工具 ----------
  const setStatus = t => { statusEl.textContent = t || '' }

  const toFileUrl = p => {
    if (!p) return ''
    const norm = String(p).trim().replace(/\\/g, '/')
    return encodeURI('file:///' + norm.replace(/^\/+/, ''))
  }

  // ---------- 显示模式 ----------
  function applyFitMode() {
    videoEl.classList.add('fit')
    videoEl.classList.remove('raw')
    videoEl.style.width = ''
    videoEl.style.height = ''
  }
  function applyRawMode() {
    videoEl.classList.add('raw')
    videoEl.classList.remove('fit')
    if (videoEl.videoWidth && videoEl.videoHeight) {
      videoEl.style.width  = videoEl.videoWidth + 'px'
      videoEl.style.height = videoEl.videoHeight + 'px'
    }
  }

  // ---------- 去原片硬字幕：遮罩 ----------
  // 计算视频画面在播放器内实际显示的内容矩形（处理黑边/letterbox），坐标相对 .player
  function videoContentRect() {
    const pr = playerEl.getBoundingClientRect()
    const vr = videoEl.getBoundingClientRect()
    const vw = videoEl.videoWidth, vh = videoEl.videoHeight
    // 元素相对 player 的位置
    let left = vr.left - pr.left, top = vr.top - pr.top
    let width = vr.width, height = vr.height
    if (vw && vh && width && height) {
      const scale = Math.min(width / vw, height / vh)
      const cw = vw * scale, ch = vh * scale
      left += (width - cw) / 2
      top  += (height - ch) / 2
      width = cw; height = ch
    }
    return { left, top, width, height }
  }

  function positionMask() {
    if (!subMaskEl || !state.deSub) return
    const c = videoContentRect()
    const r = state.maskRect
    subMaskEl.style.left   = (c.left + r.x * c.width) + 'px'
    subMaskEl.style.top    = (c.top  + r.y * c.height) + 'px'
    subMaskEl.style.width  = Math.max(8, r.w * c.width) + 'px'
    subMaskEl.style.height = Math.max(8, r.h * c.height) + 'px'
  }

  function showMask(on) {
    state.deSub = !!on
    if (!subMaskEl) return
    subMaskEl.style.display = on ? 'block' : 'none'
    if (on) positionMask()
  }

  // 拖动 / 缩放遮罩框，结果写回归一化 maskRect
  function initMaskInteractions() {
    if (!subMaskEl) return
    let mode = null            // 'move' | 'resize'
    let startX = 0, startY = 0
    let orig = null            // 起始像素矩形

    const onMove = (e) => {
      if (!mode) return
      const c = videoContentRect()
      const dx = e.clientX - startX
      const dy = e.clientY - startY
      let left = orig.left, top = orig.top, w = orig.width, h = orig.height
      if (mode === 'move') { left += dx; top += dy }
      else { w = Math.max(12, orig.width + dx); h = Math.max(12, orig.height + dy) }
      // 限制在内容区内
      left = Math.min(Math.max(left, c.left), c.left + c.width - w)
      top  = Math.min(Math.max(top,  c.top),  c.top  + c.height - h)
      w = Math.min(w, c.left + c.width - left)
      h = Math.min(h, c.top  + c.height - top)
      state.maskRect = {
        x: (left - c.left) / c.width,
        y: (top  - c.top)  / c.height,
        w: w / c.width,
        h: h / c.height
      }
      positionMask()
      e.preventDefault()
    }
    const onUp = () => {
      mode = null
      subMaskEl.classList.remove('editing')
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    const begin = (m, e) => {
      mode = m
      startX = e.clientX; startY = e.clientY
      const r = subMaskEl.getBoundingClientRect()
      const pr = playerEl.getBoundingClientRect()
      orig = { left: r.left - pr.left, top: r.top - pr.top, width: r.width, height: r.height }
      subMaskEl.classList.add('editing')
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
      e.preventDefault(); e.stopPropagation()
    }
    subMaskEl.addEventListener('mousedown', (e) => begin('move', e))
    if (maskHandleEl) maskHandleEl.addEventListener('mousedown', (e) => begin('resize', e))
  }

  // 供导出使用：把归一化矩形换算为视频原始帧的整数像素矩形
  function maskPixelRegion() {
    if (!state.deSub) return null
    const vw = videoEl.videoWidth, vh = videoEl.videoHeight
    if (!vw || !vh) return null
    const r = state.maskRect
    let x = Math.round(r.x * vw)
    let y = Math.round(r.y * vh)
    let w = Math.round(r.w * vw)
    let h = Math.round(r.h * vh)
    // delogo 要求矩形完全在帧内且与边缘留 1px
    x = Math.min(Math.max(1, x), vw - 2)
    y = Math.min(Math.max(1, y), vh - 2)
    w = Math.max(1, Math.min(w, vw - x - 1))
    h = Math.max(1, Math.min(h, vh - y - 1))
    return { x, y, w, h }
  }

  // ---------- 字幕渲染 ----------
  function pickLine(items, sec) {
    return window.SRT.findAt(items, sec)
  }

  function getRenderText(sec) {
    const mode = displayLangSel ? displayLangSel.value : 'src'
    const src = pickLine(state.src, sec)
    const zh  = pickLine(state.zh,  sec)
    const ru  = pickLine(state.ru,  sec)
    const textOf = it => (it && it.text) ? it.text : ''

    // 选择译文模式时，只显示译文；译文未到就保持空白，绝不回退到原文
    if (mode === 'src') return textOf(src)
    if (mode === 'zh')  return textOf(zh)
    if (mode === 'ru')  return textOf(ru)
    if (mode === 'zh-ru') {
      const lines = []
      if (textOf(zh)) lines.push(textOf(zh))
      if (textOf(ru)) lines.push(textOf(ru))
      return lines.join('\n')
    }
    return ''
  }

  function renderOverlay() {
    const sec = videoEl.currentTime || 0
    const text = getRenderText(sec)
    overlayEl.textContent = text || ''
  }

  // ---------- 翻译协调 ----------
  async function ensureTranslations(items, langs) {
    if (!items || !items.length) return
    // 先把两路翻译都跑完，结果一次性写入 state，再渲染——保证中俄同时出现
    const tasks = []
    if (langs.includes('zh')) tasks.push(window.Translate.translateSrtItems(items, 'zh').catch(() => null))
    else                      tasks.push(Promise.resolve(null))
    if (langs.includes('ru')) tasks.push(window.Translate.translateSrtItems(items, 'ru').catch(() => null))
    else                      tasks.push(Promise.resolve(null))

    const [zhOut, ruOut] = await Promise.all(tasks)
    if (zhOut && zhOut.length) state.zh = window.SRT.sortAndDedupe(state.zh.concat(zhOut))
    if (ruOut && ruOut.length) state.ru = window.SRT.sortAndDedupe(state.ru.concat(ruOut))
    renderOverlay()
  }

  // 在视频播放过程中，对当前位置附近尚未翻译的原文进行补翻
  async function ensureNearby(sec) {
    const mode = displayLangSel.value
    if (mode === 'src') return
    if (state.translateInflight) return
    const now = Date.now()
    if (now - state.lastTranslateAt < 400) return
    state.lastTranslateAt = now

    const winS = Math.max(0, sec - 8)
    const winE = sec + 25
    const need = []
    for (const it of state.src) {
      const s = window.SRT.toSeconds(it.start)
      const e = window.SRT.toSeconds(it.end)
      if (e < winS || s > winE) continue
      const needZh = (mode === 'zh' || mode === 'zh-ru') && !findExact(state.zh, it)
      const needRu = (mode === 'ru' || mode === 'zh-ru') && !findExact(state.ru, it)
      if (needZh || needRu) need.push(it)
    }
    if (!need.length) return

    const langs = []
    if (mode === 'zh' || mode === 'zh-ru') langs.push('zh')
    if (mode === 'ru' || mode === 'zh-ru') langs.push('ru')

    state.translateInflight = true
    setStatus('翻译中…')
    try { await ensureTranslations(need, langs) } finally {
      state.translateInflight = false
      setStatus('')
    }
  }

  function findExact(items, target) {
    for (const it of items) {
      if (it.start === target.start && it.end === target.end) {
        return (it.text && it.text.trim()) ? it : null
      }
    }
    return null
  }

  // ---------- 实时字幕 ----------
  function startRealtime() {
    if (!state.videoPath) {
      setStatus('请先打开视频')
      realtimeChk.checked = false
      return
    }
    state.realtime = true
    state.realtimeProcessed.clear()
    state.realtimeInflight = 0
    setStatus('实时识别已开启')

    if (state.realtimeTimer) clearInterval(state.realtimeTimer)
    // 200ms 一拍，比之前的 1s 灵敏 5 倍
    state.realtimeTimer = setInterval(realtimeTick, 200)
    realtimeTick()
  }

  function stopRealtime() {
    state.realtime = false
    if (state.realtimeTimer) clearInterval(state.realtimeTimer)
    state.realtimeTimer = null
    state.realtimeProcessed.clear()
    state.realtimeInflight = 0
    setStatus('')
  }

  function realtimeTick() {
    if (!state.realtime || !state.videoPath) return
    const cur = videoEl.currentTime || 0
    const segIdx = Math.floor(cur / state.realtimeSegSec)
    // 当前段 + 未来 N 段，尽量预拉取
    for (let i = 0; i <= state.realtimeLookaheadSegs; i++) {
      if (state.realtimeInflight >= state.realtimeMaxParallel) return
      const idx = segIdx + i
      if (idx < 0) continue
      if (state.realtimeProcessed.has(idx)) continue
      state.realtimeProcessed.add(idx)
      state.realtimeInflight++
      transcribeAndAppend(idx).catch(e => {
        console.error('实时字幕段失败：', e)
        state.realtimeProcessed.delete(idx)   // 允许下轮重试
      }).finally(() => {
        state.realtimeInflight = Math.max(0, state.realtimeInflight - 1)
      })
    }
  }

  async function transcribeAndAppend(idx) {
    const startSec = Math.max(0, idx * state.realtimeSegSec - (idx > 0 ? state.realtimeOverlapSec : 0))
    const dur = state.realtimeSegSec + (idx > 0 ? state.realtimeOverlapSec : 0)
    const seg = await window.api.transcribeSegment({
      inputPath: state.videoPath,
      startSec,
      durationSec: dur,
      lang: 'auto'
    })
    if (!seg || !seg.srt) {
      if (seg && seg.need === 'ffmpeg') setStatus('需要安装 ffmpeg 才能实时识别')
      else if (seg && seg.need === 'whisper') setStatus('Whisper 服务未就绪，请稍候')
      return
    }
    const items = window.SRT.parse(seg.srt)
    if (!items.length) return
    const offsetItems = window.SRT.offset(items, startSec)
    state.src = window.SRT.sortAndDedupe(state.src.concat(offsetItems))
    renderOverlay()
    // 翻译（异步，不阻塞下一段拉取）
    ensureTranslations(offsetItems, ['zh', 'ru']).catch(() => {})
  }

  // ---------- 视频事件 ----------
  videoEl.addEventListener('loadedmetadata', () => {
    if (rawModeChk.checked) applyRawMode()
    else applyFitMode()
    positionMask()
    setStatus('')
  })
  window.addEventListener('resize', () => { if (state.deSub) positionMask() })
  videoEl.addEventListener('error', () => {
    const code = videoEl.error ? videoEl.error.code : '?'
    setStatus(`视频加载失败 (code ${code})`)
  })
  videoEl.addEventListener('timeupdate', () => {
    renderOverlay()
    ensureNearby(videoEl.currentTime || 0).catch(() => {})
  })
  videoEl.addEventListener('seeked', renderOverlay)
  videoEl.addEventListener('play',   renderOverlay)
  videoEl.addEventListener('pause',  renderOverlay)

  // ---------- 视频加载 ----------
  function loadVideoFromPath(p) {
    state.videoPath = p
    state.src = []; state.zh = []; state.ru = []
    overlayEl.textContent = ''
    stopRealtime()
    realtimeChk.checked = false
    videoEl.pause()
    videoEl.src = toFileUrl(p)
    videoEl.load()
  }

  openVideoBtn.addEventListener('click', async () => {
    setStatus('正在选择视频…')
    const p = await window.api.openVideo()
    if (!p) { setStatus('未选择视频'); return }
    loadVideoFromPath(p)
  })

  // 拖拽打开
  playerEl.addEventListener('dragover', e => e.preventDefault())
  playerEl.addEventListener('drop', e => {
    e.preventDefault()
    const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]
    if (!f || !f.path) return
    loadVideoFromPath(f.path)
  })

  // ---------- 加载已有字幕 ----------
  openSubBtn.addEventListener('click', async () => {
    setStatus('正在选择字幕…')
    const p = await window.api.openSubtitle()
    if (!p) { setStatus('未选择字幕'); return }
    setStatus('读取字幕中…')
    const text = await window.api.readTextFile(p)
    let items = []
    if (p.toLowerCase().endsWith('.vtt')) items = window.SRT.parseVTT(text)
    else                                  items = window.SRT.parse(text)
    if (!items.length) { setStatus('字幕解析失败'); return }

    state.src = window.SRT.sortAndDedupe(items)
    state.zh = []; state.ru = []
    renderOverlay()                // 先把原文显示出来
    setStatus('已加载字幕，正在翻译…')
    await ensureTranslations(state.src, ['zh', 'ru'])
    setStatus('字幕就绪')
  })

  // ---------- 生成字幕（Whisper） ----------
  generateBtn.addEventListener('click', async () => {
    if (!state.videoPath) { setStatus('请先打开视频'); return }
    setStatus('正在转写整段视频，请耐心等待…')
    const lang = genLangSel.value
    const res = await window.api.generateSubtitles({ inputPath: state.videoPath, lang })
    if (!res || !res.path) {
      if (res && res.need === 'whisper') setStatus('需要安装 Whisper')
      else if (res && res.error === 'whisper_failed') setStatus('Whisper 执行失败')
      else setStatus('生成失败：环境异常')
      return
    }
    const text = await window.api.readTextFile(res.path)
    const items = window.SRT.parse(text)
    if (!items.length) { setStatus('生成的字幕为空'); return }
    state.src = window.SRT.sortAndDedupe(items)
    state.zh = []; state.ru = []
    renderOverlay()                // 即刻显示原文
    setStatus('字幕已生成，正在翻译…')
    await ensureTranslations(state.src, ['zh', 'ru'])
    setStatus('双语字幕就绪')
  })

  // ---------- 一键翻译按钮（保留兼容） ----------
  toZhBtn.addEventListener('click', async () => {
    if (!state.src.length) { setStatus('请先加载或生成字幕'); return }
    setStatus('翻译为中文…')
    await ensureTranslations(state.src, ['zh'])
    displayLangSel.value = 'zh'
    renderOverlay()
    setStatus('已翻译为中文')
  })
  toRuBtn.addEventListener('click', async () => {
    if (!state.src.length) { setStatus('请先加载或生成字幕'); return }
    setStatus('翻译为俄语…')
    await ensureTranslations(state.src, ['ru'])
    displayLangSel.value = 'ru'
    renderOverlay()
    setStatus('已翻译为俄语')
  })

  // ---------- 保存当前显示模式的字幕 ----------
  saveSrtBtn.addEventListener('click', async () => {
    if (!state.src.length) { setStatus('请先加载或生成字幕'); return }
    const mode = displayLangSel.value
    let items = state.src
    let defaultName = 'subtitles.srt'

    if (mode === 'zh' && state.zh.length) {
      items = state.zh
      defaultName = 'subtitles_zh.srt'
    } else if (mode === 'ru' && state.ru.length) {
      items = state.ru
      defaultName = 'subtitles_ru.srt'
    } else if (mode === 'zh-ru') {
      items = mergeBilingual()
      defaultName = 'subtitles_zh_ru.srt'
    }

    const data = window.SRT.stringify(items)
    const saved = await window.api.saveTextFile({ defaultPath: defaultName, data })
    if (saved) setStatus('已保存：' + saved)
    else       setStatus('已取消保存')
  })

  function mergeBilingual() {
    // 以 src 的时间轴为锚，分别取 zh / ru 中相同 start/end 的译文
    const out = []
    for (const it of state.src) {
      const zh = findExact(state.zh, it)
      const ru = findExact(state.ru, it)
      const lines = []
      if (zh && zh.text) lines.push(zh.text)
      if (ru && ru.text) lines.push(ru.text)
      out.push({
        start: it.start,
        end:   it.end,
        text:  lines.length ? lines.join('\n') : it.text
      })
    }
    return out
  }

  // ---------- 导出带字幕视频 ----------
  exportVideoBtn.addEventListener('click', async () => {
    if (!state.videoPath) { setStatus('请先打开视频'); return }
    const removeRegion = maskPixelRegion()   // 去原片字幕开启时返回像素矩形，否则 null
    // 没有字幕时，只有在「去原片字幕」开启时才允许导出（纯去字幕）
    if (!state.src.length && !removeRegion) { setStatus('请先加载或生成字幕'); return }

    let tempPath = null
    if (state.src.length) {
      if (!state.zh.length || !state.ru.length) {
        setStatus('正在补全双语翻译…')
        const need = []
        if (!state.zh.length) need.push('zh')
        if (!state.ru.length) need.push('ru')
        await ensureTranslations(state.src, need)
      }
      const merged = mergeBilingual()
      if (merged.length) {
        const tempName = 'bilingual_subtitles.srt'
        const tempData = window.SRT.stringify(merged)
        tempPath = await window.api.saveTextFile({ defaultPath: tempName, data: tempData })
        if (!tempPath) { setStatus('已取消'); return }
      }
    }

    const baseName = state.videoPath.split(/[\\/]/).pop().replace(/\.[^.]+$/, '')
    const suffix = removeRegion ? (tempPath ? '_clean_bilingual' : '_clean') : '_bilingual'
    const outPath  = await window.api.saveTextFile({
      defaultPath: `${baseName}${suffix}.mp4`, data: ''
    })
    if (!outPath) { setStatus('已取消'); return }

    setStatus(removeRegion ? '正在去除原片字幕并导出，耗时较长…' : '正在导出视频，可能耗时较长…')
    const r = await window.api.exportVideo({
      inputPath: state.videoPath,
      subtitlePath: tempPath,
      outputPath: outPath,
      removeRegion
    })
    if (r && r.success) setStatus('视频导出成功：' + outPath)
    else if (r && r.error === 'ffmpeg_not_found') setStatus('需要安装 ffmpeg')
    else setStatus('视频导出失败：' + (r && r.error || '未知错误'))
  })

  // ---------- 商业级去字幕（GPU·STTN） ----------
  if (removeHardSubBtn) removeHardSubBtn.addEventListener('click', async () => {
    if (!state.videoPath) { setStatus('请先打开视频'); return }
    // 必须先开启「去原片字幕」并把遮罩框对准字幕条，以此确定去除区域
    if (!state.deSub) {
      deSubChk.checked = true
      showMask(true)
      setStatus('请先拖动蓝框对准原片字幕条，再点「去字幕(GPU)」')
      return
    }
    const region = maskPixelRegion()
    if (!region) { setStatus('无法确定字幕区域，请重试'); return }

    const baseName = state.videoPath.split(/[\\/]/).pop().replace(/\.[^.]+$/, '')
    const outPath = await window.api.saveTextFile({ defaultPath: `${baseName}_nosub.mp4`, data: '' })
    if (!outPath) { setStatus('已取消'); return }

    removeHardSubBtn.disabled = true
    const off = window.api.onDesubProgress(({ done, total }) => {
      const pct = total ? Math.floor(done * 100 / total) : 0
      setStatus(`GPU 去字幕中… ${done}/${total} (${pct}%)`)
    })
    setStatus('GPU 去字幕中…（首次会自动下载约 66MB 模型）')
    try {
      const r = await window.api.removeHardSubs({
        inputPath: state.videoPath,
        outputPath: outPath,
        region,
        maskMode: 'auto',
        device: 'cuda'
      })
      if (r && r.success) {
        setStatus('去字幕完成：' + outPath + '（已载入，可叠加实时翻译）')
        deSubChk.checked = false; showMask(false)   // 干净视频无需再遮挡
        loadVideoFromPath(outPath)
      } else if (r && r.error === 'no_python') {
        setStatus('未检测到可用的 Python（需 torch + opencv）')
      } else {
        const detail = (r && r.details ? String(r.details).split(/\r?\n/).filter(Boolean).pop() : '') || ''
        const msg = (r && r.error) ? String(r.error).replace(/^ERR:\s*/, '') : '未知错误'
        console.error('[desub] 失败详情:', r && r.details)
        setStatus('去字幕失败：' + msg + (detail && detail !== msg ? ' · ' + detail.slice(0, 160) : ''))
      }
    } finally {
      if (typeof off === 'function') off()
      removeHardSubBtn.disabled = false
    }
  })

  // ---------- 控件事件 ----------
  realtimeChk.addEventListener('change', () => {
    if (realtimeChk.checked) startRealtime()
    else stopRealtime()
  })
  rawModeChk.addEventListener('change', () => {
    if (rawModeChk.checked) applyRawMode()
    else applyFitMode()
    positionMask()
  })
  if (deSubChk) deSubChk.addEventListener('change', () => {
    showMask(deSubChk.checked)
    setStatus(deSubChk.checked ? '已开启去原片字幕：拖动遮罩对准原片字幕条' : '')
  })
  initMaskInteractions()
  displayLangSel.addEventListener('change', async () => {
    const mode = displayLangSel.value
    renderOverlay()
    // 切换到译文模式时若译文为空，按需触发翻译
    if (!state.src.length) return
    const langs = []
    if ((mode === 'zh' || mode === 'zh-ru') && !state.zh.length) langs.push('zh')
    if ((mode === 'ru' || mode === 'zh-ru') && !state.ru.length) langs.push('ru')
    if (!langs.length) return
    setStatus('翻译中…')
    await ensureTranslations(state.src, langs)
    setStatus('')
  })
})()
