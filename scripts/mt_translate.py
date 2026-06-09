import sys
import json
import os
import re
import traceback

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

# 确保字符串以正确的格式处理
def safe_text(text):
    if not isinstance(text, str):
        return str(text)
    # 确保文本使用UTF-8编码
    try:
        return text.encode('utf-8').decode('utf-8')
    except Exception as e:
        print(f"文本编码处理错误: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return text

def main():
    try:
        data = sys.stdin.read()
        payload = json.loads(data)
        items = payload.get("items", [])
        target = payload.get("target", "zh")
    except Exception:
        print(json.dumps({"ok": False, "items": []}))
        return
    try:
        from transformers import MarianTokenizer, MarianMTModel
    except Exception:
        print(json.dumps({"ok": False, "items": []}))
        return
    # 规范化目标语言代码
    tgt = target.lower()
    # 处理zh-CN等变体
    if tgt.startswith('zh'):
        tgt = 'zh'
    elif tgt.startswith('ru'):
        tgt = 'ru'
    elif tgt.startswith('en'):
        tgt = 'en'

    def is_zh(s: str) -> bool:
        for ch in s:
            code = ord(ch)
            if 0x4E00 <= code <= 0x9FFF:
                return True
        return False

    def is_ru(s: str) -> bool:
        for ch in s:
            code = ord(ch)
            if (0x0400 <= code <= 0x04FF) or (0x0500 <= code <= 0x052F):
                return True
        return False

    def detect_src(s: str) -> str:
        if is_zh(s):
            return "zh"
        if is_ru(s):
            return "ru"
        return "en"

    pair_to_model = {
        ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
        ("en", "ru"): "Helsinki-NLP/opus-mt-en-ru",
        ("zh", "ru"): "Helsinki-NLP/opus-mt-zh-ru",
        ("ru", "zh"): "Helsinki-NLP/opus-mt-ru-zh",
    }

    groups = {}
    for idx, it in enumerate(items):
        txt = it.get("text", "")
        src = detect_src(txt)
        key = (src, tgt)
        groups.setdefault(key, []).append((idx, txt))

    loaded = {}
    out_items = [{"start": it.get("start"), "end": it.get("end"), "text": it.get("text", "")} for it in items]

    # 支持更多语言对的fallback机制
    def get_fallback_model(key):
        src, tgt = key
        if (src, tgt) in pair_to_model:
            return pair_to_model[(src, tgt)]
        # 添加更多语言对支持
        if src == "en" and tgt == "zh":
            return "Helsinki-NLP/opus-mt-en-zh"
        if src == "en" and tgt == "ru":
            return "Helsinki-NLP/opus-mt-en-ru"
        if src == "zh" and tgt == "en":
            return "Helsinki-NLP/opus-mt-zh-en"
        if src == "ru" and tgt == "en":
            return "Helsinki-NLP/opus-mt-ru-en"
        if src == "zh" and tgt == "ru":
            return "Helsinki-NLP/opus-mt-zh-ru"
        if src == "ru" and tgt == "zh":
            return "Helsinki-NLP/opus-mt-ru-zh"
        return None
    
    for key, batch in groups.items():
        src, tgt = key
        
        # 即使源语言和目标语言相同，也尝试翻译
        # 这是因为语言检测可能不准确，需要确保真正需要翻译的内容被翻译
        model_name = get_fallback_model(key)
        if not model_name:
            continue
            
        # 处理单步翻译（直接翻译）
        try:
            if model_name not in loaded:
                tok = MarianTokenizer.from_pretrained(model_name)
                # 使用safetensors格式加载模型，避免PyTorch版本限制
                try:
                    mdl = MarianMTModel.from_pretrained(model_name, use_safetensors=True)
                    print(f"使用safetensors格式加载模型 {model_name} 成功")
                except Exception as e:
                    print(f"使用safetensors格式加载模型 {model_name} 失败，回退到默认方式: {e}")
                    mdl = MarianMTModel.from_pretrained(model_name)
                loaded[model_name] = (tok, mdl)
            tok, mdl = loaded[model_name]
            texts = [t for _, t in batch]
            enc = tok(texts, return_tensors="pt", padding=True)
            gen = mdl.generate(**enc, max_length=128, num_beams=1, early_stopping=True)
            outs = tok.batch_decode(gen, skip_special_tokens=True)
            for (idx, _), t in zip(batch, outs):
                if tgt == "ru":
                    # 保留所有内容，包括俄语和英文
                    # t = re.sub(r'\b[A-Za-z]+\b', '', t).strip()
                    # t = re.sub(r'\s{2,}', ' ', t)
                    print(f"俄语翻译结果: {t}")
                # 使用安全文本处理函数
                out_items[idx]["text"] = safe_text(t)
        except Exception:
            # 如果直接翻译失败，尝试通过英语中转翻译
            try:
                src, tgt = key
                if (src, "en") in pair_to_model and ("en", tgt) in pair_to_model:
                    # 先翻译成英语
                    en_model_name = pair_to_model[(src, "en")]
                    if en_model_name not in loaded:
                        tok_en = MarianTokenizer.from_pretrained(en_model_name)
                        # 使用safetensors格式加载模型，避免PyTorch版本限制
                        try:
                            mdl_en = MarianMTModel.from_pretrained(en_model_name, use_safetensors=True)
                            print(f"使用safetensors格式加载模型 {en_model_name} 成功")
                        except Exception as e:
                            print(f"使用safetensors格式加载模型 {en_model_name} 失败，回退到默认方式: {e}")
                            mdl_en = MarianMTModel.from_pretrained(en_model_name)
                        loaded[en_model_name] = (tok_en, mdl_en)
                    tok_en, mdl_en = loaded[en_model_name]
                    
                    # 再翻译成目标语言
                    tgt_model_name = pair_to_model[("en", tgt)]
                    if tgt_model_name not in loaded:
                        tok_tgt = MarianTokenizer.from_pretrained(tgt_model_name)
                        # 使用safetensors格式加载模型，避免PyTorch版本限制
                        try:
                            mdl_tgt = MarianMTModel.from_pretrained(tgt_model_name, use_safetensors=True)
                            print(f"使用safetensors格式加载模型 {tgt_model_name} 成功")
                        except Exception as e:
                            print(f"使用safetensors格式加载模型 {tgt_model_name} 失败，回退到默认方式: {e}")
                            mdl_tgt = MarianMTModel.from_pretrained(tgt_model_name)
                        loaded[tgt_model_name] = (tok_tgt, mdl_tgt)
                    tok_tgt, mdl_tgt = loaded[tgt_model_name]
                    
                    for i, (idx, text) in enumerate(batch):
                        try:
                            # 第一步：翻译成英语
                            enc_en = tok_en([text], return_tensors="pt", padding=True)
                            gen_en = mdl_en.generate(**enc_en, max_length=128, num_beams=1)
                            en_text = tok_en.decode(gen_en[0], skip_special_tokens=True)
                            
                            # 第二步：从英语翻译成目标语言
                            enc_tgt = tok_tgt([en_text], return_tensors="pt", padding=True)
                            gen_tgt = mdl_tgt.generate(**enc_tgt, max_length=128, num_beams=1)
                            translated_text = tok_tgt.decode(gen_tgt[0], skip_special_tokens=True)
                            
                            if tgt == "ru":
                                # 保留所有内容，包括俄语和英文
                                # translated_text = re.sub(r'\b[A-Za-z]+\b', '', translated_text).strip()
                                # translated_text = re.sub(r'\s{2,}', ' ', translated_text)
                                print(f"俄语中转翻译结果: {translated_text}")
                            # 使用安全文本处理函数
                            out_items[idx]["text"] = safe_text(translated_text)
                        except Exception:
                            # 如果中转翻译也失败，保持原文
                            continue
            except Exception:
                # 如果所有翻译尝试都失败，保持原文
                continue

    print(json.dumps({"ok": True, "items": out_items}, ensure_ascii=False))

if __name__ == "__main__":
    main()
