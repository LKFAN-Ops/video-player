// 翻译模块
// 优先使用本地 mt_server (IPC: window.api.translateItems)
// 失败时回退到在线服务，逐条调用以维持顺序与字幕时间戳。
window.Translate = (function () {

  // ------- 简单 LRU 缓存 -------
  class LRU {
    constructor(max = 1000) { this.max = max; this.map = new Map() }
    get(k) {
      if (!this.map.has(k)) return null
      const v = this.map.get(k); this.map.delete(k); this.map.set(k, v); return v
    }
    set(k, v) {
      if (this.map.has(k)) this.map.delete(k)
      this.map.set(k, v)
      if (this.map.size > this.max) this.map.delete(this.map.keys().next().value)
    }
    has(k) { return this.map.has(k) }
  }
  const cache = new LRU(2000)

  // ------- 语言代码归一化 -------
  function normTarget(t) {
    if (!t) return 'en'
    if (t.startsWith('zh')) return 'zh'
    if (t.startsWith('ru')) return 'ru'
    if (t.startsWith('en')) return 'en'
    return t
  }

  function detectSource(text) {
    if (!text) return 'en'
    if (/[一-龥]/.test(text)) return 'zh'
    if (/[Ѐ-ӿ]/.test(text)) return 'ru'
    return 'en'
  }

  // ------- 在线服务（仅中国大陆可访问的，不依赖代理） -------
  async function fetchJson(url, opts = {}, timeoutMs = 6000) {
    const ac = new AbortController()
    const timer = setTimeout(() => ac.abort(), timeoutMs)
    try {
      const res = await fetch(url, { ...opts, signal: ac.signal })
      if (!res.ok) return null
      return await res.json()
    } catch (_) {
      return null
    } finally {
      clearTimeout(timer)
    }
  }

  // MyMemory：在国内不需代理可直连，作为唯一的在线回退
  async function myMemoryTrans(text, src, tgt) {
    const url = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(text)}&langpair=${src}|${tgt}`
    const data = await fetchJson(url)
    const t = data && data.responseData && data.responseData.translatedText
    return (typeof t === 'string' && t) ? t : null
  }

  async function translateText(text, target) {
    if (!text || typeof text !== 'string') return text
    const trimmed = text.trim()
    if (!trimmed) return ''

    const tgt = normTarget(target)
    const src = detectSource(trimmed)
    if (src === tgt) return trimmed

    const key = `${src}->${tgt}::${trimmed}`
    if (cache.has(key)) return cache.get(key)

    // 国内可访问的唯一回退；本地 mt_server 优先在 translateSrtItems 中尝试
    let translated = await myMemoryTrans(trimmed, src, tgt)
    if (!translated) translated = trimmed   // 兜底返回原文，避免显示空白

    cache.set(key, translated)
    return translated
  }

  // ------- 字幕批量翻译入口 -------
  async function translateSrtItems(items, target) {
    if (!items || !items.length) return []
    const tgt = normTarget(target)

    // 命中缓存的与未命中的分开
    const result = new Array(items.length)
    const todoIdx = []
    const todoItems = []

    for (let i = 0; i < items.length; i++) {
      const it = items[i]
      const ck = `*->${tgt}::${(it.text || '').trim()}`
      if (cache.has(ck)) {
        result[i] = { start: it.start, end: it.end, text: cache.get(ck) }
      } else {
        todoIdx.push(i)
        todoItems.push(it)
      }
    }
    if (!todoItems.length) return result

    // 1) 优先批量调用本地 mt_server（重试 1 次缓解模型预热抖动）
    let localItems = null
    if (window.api && window.api.translateItems) {
      for (let attempt = 0; attempt < 2 && !localItems; attempt++) {
        try {
          const resp = await window.api.translateItems(todoItems, tgt)
          if (resp && resp.ok && Array.isArray(resp.items) && resp.items.length === todoItems.length) {
            localItems = resp.items
          } else if (attempt === 0) {
            await new Promise(r => setTimeout(r, 600))
          }
        } catch (e) {
          console.warn(`本地翻译第 ${attempt + 1} 次失败：`, e && e.message)
          if (attempt === 0) await new Promise(r => setTimeout(r, 600))
        }
      }
    }

    if (localItems) {
      for (let j = 0; j < todoItems.length; j++) {
        const src = todoItems[j]
        const out = localItems[j]
        const text = (out && out.text) ? out.text : src.text
        cache.set(`*->${tgt}::${(src.text || '').trim()}`, text)
        result[todoIdx[j]] = { start: src.start, end: src.end, text }
      }
      return result
    }

    // 2) 回退：在线翻译，串行避免被限流
    for (let j = 0; j < todoItems.length; j++) {
      const src = todoItems[j]
      let text = src.text
      try {
        text = await translateText(src.text, tgt)
      } catch (_) { /* keep original */ }
      cache.set(`*->${tgt}::${(src.text || '').trim()}`, text)
      result[todoIdx[j]] = { start: src.start, end: src.end, text }
    }
    return result
  }

  return { translateText, translateSrtItems }
})()
