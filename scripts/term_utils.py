# 共享术语表 / 性能配置工具
# - glossary.json 由用户自由编辑，用于显著提升「专有名词」的识别与翻译准确度：
#     * hotwords : 给语音识别（faster-whisper）做偏置的专有名词/人名/品牌
#     * replace  : 翻译完成后按目标语言做的「误译修正」替换表
#     * forced   : 整句强制译法（源文 -> 目标文，精确匹配优先于模型输出）
# - 文件不存在时一切优雅降级，不影响原有功能。
# - 自动热重载：编辑 glossary.json 后无需重启服务。
import os
import json
import threading

_GLOSSARY_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "glossary.json")
_lock = threading.Lock()
_cache = {"mtime": None, "data": {}}


def _empty():
    return {"hotwords": [], "replace": {}, "forced": {}}


def load_glossary() -> dict:
    """读取并缓存 glossary.json；按文件修改时间热重载。出错时返回空表。"""
    try:
        st = os.stat(_GLOSSARY_PATH)
    except OSError:
        return _empty()
    with _lock:
        if _cache["mtime"] == st.st_mtime and _cache["data"]:
            return _cache["data"]
        try:
            with open(_GLOSSARY_PATH, "r", encoding="utf-8") as f:
                raw = json.load(f)
            data = _empty()
            if isinstance(raw.get("hotwords"), list):
                data["hotwords"] = [str(w).strip() for w in raw["hotwords"] if str(w).strip()]
            if isinstance(raw.get("replace"), dict):
                data["replace"] = {k: v for k, v in raw["replace"].items() if isinstance(v, dict)}
            if isinstance(raw.get("forced"), dict):
                data["forced"] = {k: v for k, v in raw["forced"].items() if isinstance(v, dict)}
            _cache["mtime"] = st.st_mtime
            _cache["data"] = data
            return data
        except Exception as e:  # noqa: BLE001 - 配置坏了不该让主流程崩
            print(f"[术语表] 解析 glossary.json 失败，已忽略: {e}")
            return _empty()


def hotwords_string(extra=None) -> str:
    """返回供 faster-whisper hotwords 使用的字符串（逗号分隔）。"""
    words = list(load_glossary().get("hotwords", []))
    if extra:
        if isinstance(extra, str):
            extra = [extra]
        words.extend([str(w).strip() for w in extra if str(w).strip()])
    # 去重保序
    seen, out = set(), []
    for w in words:
        if w and w not in seen:
            seen.add(w)
            out.append(w)
    return ", ".join(out)


def forced_translation(text: str, tgt: str):
    """整句强制译法：精确匹配（忽略首尾空白）则直接返回固定译文，否则 None。"""
    if not text:
        return None
    table = load_glossary().get("forced", {}).get(tgt, {})
    if not table:
        return None
    return table.get(text.strip())


def apply_replacements(text: str, tgt: str) -> str:
    """对翻译输出做目标语言的「误译修正」子串替换。"""
    if not text:
        return text
    table = load_glossary().get("replace", {}).get(tgt, {})
    if not table:
        return text
    out = text
    # 先长后短，避免短词先替换破坏长词
    for src in sorted(table.keys(), key=len, reverse=True):
        if src:
            out = out.replace(src, table[src])
    return out


def cpu_threads(default_cap: int = 8) -> int:
    """供 faster-whisper 使用的线程数：优先环境变量 WHISPER_CPU_THREADS，
    否则取物理核估算值（cpu_count 的一半，1~default_cap 之间）。
    线程过多在小模型上反而因调度开销变慢，故设上限。"""
    env = os.environ.get("WHISPER_CPU_THREADS")
    if env and env.isdigit() and int(env) > 0:
        return int(env)
    n = os.cpu_count() or 4
    return max(1, min(default_cap, n // 2 if n > 4 else n))


if __name__ == "__main__":
    print("glossary:", json.dumps(load_glossary(), ensure_ascii=False, indent=2))
    print("hotwords:", hotwords_string())
    print("cpu_threads:", cpu_threads())
