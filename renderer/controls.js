// =============== 自定义播放器控制条 ===============
// 与 renderer.js 解耦：仅负责播放交互（播放/进度/音量/倍速/全屏/快捷键/自动隐藏）。
// 字幕、翻译、去字幕等业务逻辑仍在 renderer.js。
(() => {
  const $ = id => document.getElementById(id)
  const video   = $('video')
  const player   = $('player')
  if (!video || !player) return

  const controls   = $('controls')
  const centerPlay = $('centerPlay')
  const playBtn    = $('playBtn')
  const muteBtn    = $('muteBtn')
  const volSlider  = $('volSlider')
  const curTime    = $('curTime')
  const durTime    = $('durTime')
  const speedBtn   = $('speedBtn')
  const speedMenu  = $('speedMenu')
  const fsBtn      = $('fullscreenBtn')
  const seek       = $('seek')
  const seekPlayed = $('seekPlayed')
  const seekBuffered = $('seekBuffered')
  const seekThumb  = $('seekThumb')
  const seekTooltip= $('seekTooltip')

  // ---------- 工具 ----------
  const fmt = s => {
    if (!isFinite(s) || s < 0) s = 0
    s = Math.floor(s)
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    const sec = s % 60
    const mm = String(m).padStart(2, '0')
    const ss = String(sec).padStart(2, '0')
    return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`
  }

  // ---------- 播放 / 暂停 ----------
  const togglePlay = () => { if (video.paused) video.play(); else video.pause() }
  playBtn.addEventListener('click', togglePlay)
  centerPlay.addEventListener('click', togglePlay)
  // 单击画面播放/暂停（避开遮罩拖动区）
  video.addEventListener('click', togglePlay)

  video.addEventListener('play',  () => { player.classList.add('playing'); player.classList.remove('paused'); scheduleHide() })
  video.addEventListener('pause', () => { player.classList.remove('playing'); player.classList.add('paused'); showControls() })

  // ---------- 进度 ----------
  let seeking = false
  const updateProgress = () => {
    const d = video.duration || 0
    const pct = d ? (video.currentTime / d) * 100 : 0
    seekPlayed.style.width = pct + '%'
    seekThumb.style.left = pct + '%'
    curTime.textContent = fmt(video.currentTime)
  }
  const updateBuffered = () => {
    const d = video.duration || 0
    if (d && video.buffered.length) {
      const end = video.buffered.end(video.buffered.length - 1)
      seekBuffered.style.width = Math.min(100, (end / d) * 100) + '%'
    }
  }
  video.addEventListener('timeupdate', () => { if (!seeking) updateProgress() })
  video.addEventListener('progress', updateBuffered)
  video.addEventListener('loadedmetadata', () => {
    durTime.textContent = fmt(video.duration)
    updateProgress(); updateBuffered()
  })

  const seekRatioFromEvent = e => {
    const r = seek.getBoundingClientRect()
    return Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
  }
  const applySeek = e => {
    const d = video.duration || 0
    if (!d) return
    video.currentTime = seekRatioFromEvent(e) * d
    updateProgress()
  }
  seek.addEventListener('mousedown', e => { seeking = true; applySeek(e) })
  window.addEventListener('mousemove', e => { if (seeking) applySeek(e) })
  window.addEventListener('mouseup', () => { seeking = false })
  // 悬停提示时间
  seek.addEventListener('mousemove', e => {
    const d = video.duration || 0
    const ratio = seekRatioFromEvent(e)
    seekTooltip.textContent = fmt(ratio * d)
    seekTooltip.style.left = (ratio * 100) + '%'
  })

  // ---------- 音量 ----------
  const reflectVolume = () => {
    player.classList.toggle('muted', video.muted || video.volume === 0)
    volSlider.value = video.muted ? 0 : video.volume
  }
  muteBtn.addEventListener('click', () => { video.muted = !video.muted; reflectVolume() })
  volSlider.addEventListener('input', () => {
    video.muted = false
    video.volume = parseFloat(volSlider.value)
    reflectVolume()
  })
  video.addEventListener('volumechange', reflectVolume)

  // ---------- 倍速 ----------
  speedBtn.addEventListener('click', e => { e.stopPropagation(); speedMenu.classList.toggle('open') })
  speedMenu.querySelectorAll('button').forEach(b => {
    b.addEventListener('click', () => {
      const rate = parseFloat(b.dataset.rate)
      video.playbackRate = rate
      speedBtn.textContent = rate.toFixed(2).replace(/0$/, '') + 'x'
      speedMenu.querySelectorAll('button').forEach(x => x.classList.remove('active'))
      b.classList.add('active')
      speedMenu.classList.remove('open')
    })
  })
  document.addEventListener('click', () => speedMenu.classList.remove('open'))

  // ---------- 全屏 ----------
  const toggleFs = () => {
    if (document.fullscreenElement) document.exitFullscreen()
    else player.requestFullscreen && player.requestFullscreen()
  }
  fsBtn.addEventListener('click', toggleFs)
  document.addEventListener('fullscreenchange', () => {
    player.classList.toggle('fs', !!document.fullscreenElement)
  })
  // 双击全屏
  video.addEventListener('dblclick', toggleFs)

  // ---------- 自动隐藏 ----------
  let hideTimer = null
  const showControls = () => {
    player.classList.add('controls-visible')
    player.classList.remove('hide-cursor')
  }
  const hideControls = () => {
    if (video.paused) return
    player.classList.remove('controls-visible')
    player.classList.add('hide-cursor')
  }
  const scheduleHide = () => {
    showControls()
    clearTimeout(hideTimer)
    hideTimer = setTimeout(hideControls, 2600)
  }
  player.addEventListener('mousemove', scheduleHide)
  player.addEventListener('mouseleave', () => { if (!video.paused) hideControls() })
  controls.addEventListener('mousemove', e => e.stopPropagation())
  controls.addEventListener('mouseenter', () => { clearTimeout(hideTimer); showControls() })

  // ---------- 视频载入时标记 ----------
  const markHasVideo = () => { player.classList.add('has-video'); showControls() }
  video.addEventListener('loadedmetadata', markHasVideo)
  if (video.src) markHasVideo()

  // ---------- 键盘快捷键 ----------
  window.addEventListener('keydown', e => {
    const tag = (e.target.tagName || '').toLowerCase()
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return
    switch (e.key) {
      case ' ': case 'k': e.preventDefault(); togglePlay(); break
      case 'ArrowLeft':  video.currentTime = Math.max(0, video.currentTime - 5); scheduleHide(); break
      case 'ArrowRight': video.currentTime = Math.min(video.duration || 0, video.currentTime + 5); scheduleHide(); break
      case 'ArrowUp':   e.preventDefault(); video.volume = Math.min(1, video.volume + 0.1); reflectVolume(); break
      case 'ArrowDown': e.preventDefault(); video.volume = Math.max(0, video.volume - 0.1); reflectVolume(); break
      case 'm': case 'M': video.muted = !video.muted; reflectVolume(); break
      case 'f': case 'F': toggleFs(); break
    }
  })

  // 初始化
  reflectVolume()
  player.classList.add('paused')
})()
