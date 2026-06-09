// SRT/VTT 工具模块
// 数据结构: { start: "HH:MM:SS,mmm", end: "HH:MM:SS,mmm", text: string }
// 之所以保留字符串格式的时间戳，是为了与 mt_server.py 的 IPC 契约保持一致。
window.SRT = (function () {
  const TS_RE = /(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{1,3})/

  function pad(n, l) { return String(n).padStart(l, '0') }

  function toSeconds(t) {
    if (typeof t === 'number') return t
    const m = String(t).match(/(\d+):(\d{2}):(\d{2})[,.](\d{1,3})/)
    if (!m) return 0
    return (+m[1]) * 3600 + (+m[2]) * 60 + (+m[3]) + (+m[4]) / 1000
  }

  function fromSeconds(sec) {
    const ms = Math.max(0, Math.round(sec * 1000))
    const h = Math.floor(ms / 3600000)
    const m = Math.floor((ms % 3600000) / 60000)
    const s = Math.floor((ms % 60000) / 1000)
    const r = ms % 1000
    return `${pad(h, 2)}:${pad(m, 2)}:${pad(s, 2)},${pad(r, 3)}`
  }

  // 将 SRT/VTT 字符串解析为 items 数组
  function parse(text) {
    const blocks = String(text || '').replace(/\r/g, '').split(/\n\n+/)
    const items = []
    for (const b of blocks) {
      const lines = b.split('\n').map(l => l.trim()).filter(Boolean)
      if (!lines.length) continue
      let i = 0
      if (/^\d+$/.test(lines[0])) i = 1
      const ts = lines[i]
      const m = ts && ts.match(TS_RE)
      if (!m) continue
      const start = `${m[1]}:${m[2]}:${m[3]},${pad(m[4], 3)}`
      const end   = `${m[5]}:${m[6]}:${m[7]},${pad(m[8], 3)}`
      const content = lines.slice(i + 1).join('\n').trim()
      if (!content) continue
      items.push({ start, end, text: content })
    }
    return items
  }

  // VTT 文本（去掉 WEBVTT 头之后用同一个解析器即可）
  function parseVTT(text) {
    const cleaned = String(text || '').replace(/^WEBVTT[^\n]*\n+/i, '')
    return parse(cleaned)
  }

  function toVTT(items) {
    const out = ['WEBVTT', '']
    for (const it of items) {
      out.push(`${it.start.replace(',', '.')} --> ${it.end.replace(',', '.')}`)
      out.push(it.text || '')
      out.push('')
    }
    return out.join('\n')
  }

  function stringify(items) {
    const out = []
    items.forEach((it, idx) => {
      out.push(String(idx + 1))
      out.push(`${it.start} --> ${it.end}`)
      out.push(it.text || '')
      out.push('')
    })
    return out.join('\n')
  }

  function offset(items, sec) {
    return items.map(it => ({
      start: fromSeconds(toSeconds(it.start) + sec),
      end:   fromSeconds(toSeconds(it.end)   + sec),
      text:  it.text
    }))
  }

  // 排序 + 近似时间去重（用于实时模式不断追加片段时的合并）
  function sortAndDedupe(items) {
    const sorted = items.slice().sort((a, b) =>
      toSeconds(a.start) - toSeconds(b.start) ||
      toSeconds(a.end)   - toSeconds(b.end)
    )
    const out = []
    for (const it of sorted) {
      const last = out[out.length - 1]
      if (last
          && Math.abs(toSeconds(last.start) - toSeconds(it.start)) < 0.05
          && Math.abs(toSeconds(last.end)   - toSeconds(it.end))   < 0.05) {
        // 同一段时间，保留更长/更可信的文本
        if ((it.text || '').length > (last.text || '').length) last.text = it.text
        continue
      }
      out.push({ ...it })
    }
    return out
  }

  // 在排好序的 items 中根据时间二分查找
  function findAt(items, sec) {
    if (!items || !items.length) return null
    let lo = 0, hi = items.length - 1
    while (lo <= hi) {
      const mid = (lo + hi) >> 1
      const s = toSeconds(items[mid].start)
      const e = toSeconds(items[mid].end)
      if (sec < s) hi = mid - 1
      else if (sec > e) lo = mid + 1
      else return items[mid]
    }
    return null
  }

  return {
    parse, parseVTT, toVTT, stringify,
    offset, findAt, sortAndDedupe,
    toSeconds, fromSeconds
  }
})()
