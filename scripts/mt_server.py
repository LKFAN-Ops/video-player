import sys
import json
import os
import traceback
from typing import List, Tuple, Dict
from collections import OrderedDict
import re
import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

# 共享术语表（专有名词固定译法 / 误译修正）；缺失时优雅降级
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import term_utils
except Exception:  # noqa: BLE001
    term_utils = None

# 设置模型缓存目录，避免占用C盘空间
# 可以通过环境变量HF_HOME自定义模型存储位置
model_cache_dir = os.environ.get("HF_HOME")
if not model_cache_dir:
    # 默认使用当前目录下的models_cache文件夹
    model_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../models_cache")
    os.environ["HF_HOME"] = model_cache_dir
    print(f"[配置] 模型缓存目录设置为: {model_cache_dir}")

# 创建模型缓存目录（如果不存在）
os.makedirs(model_cache_dir, exist_ok=True)

# 设置镜像源以加快下载速度
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

loaded: Dict[str, Tuple[object, object]] = {}
cache: "OrderedDict[str, str]" = OrderedDict()
CACHE_LIMIT = 500

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

def cache_get(key: str) -> str:
    v = cache.get(key)
    if v is not None:
        cache.move_to_end(key)
    return v

def cache_set(key: str, value: str):
    cache[key] = value
    cache.move_to_end(key)
    while len(cache) > CACHE_LIMIT:
        cache.popitem(last=False)

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
    """检测源语言，优先识别中文和俄语"""
    if is_zh(s):
        print(f"[语言检测] 识别为中文: {s}")
        return "zh"
    if is_ru(s):
        print(f"[语言检测] 识别为俄语: {s}")
        return "ru"
    print(f"[语言检测] 识别为英语: {s}")
    return "en"

# 模型精度配置：base（基础）、high（高精度）、ultra（超高精度）
# 高精度模型虽然更准确，但需要更多的内存和计算资源
MODEL_PRECISION = os.environ.get("MODEL_PRECISION", "high")  # 默认使用高精度模型

# 基础模型（原模型）
BASE_MODELS = {
    ("en", "zh"): "Helsinki-NLP/opus-mt-en-zh",
    ("en", "ru"): "Helsinki-NLP/opus-mt-en-ru",
    ("zh", "ru"): "Helsinki-NLP/opus-mt-zh-ru",
    ("ru", "zh"): "Helsinki-NLP/opus-mt-ru-zh",
}

# 高精度模型（m2m100系列，支持多语言，更高精度）
HIGH_PRECISION_MODELS = {
    ("en", "zh"): "facebook/m2m100_418M",
    ("en", "ru"): "facebook/m2m100_418M",
    ("zh", "ru"): "facebook/m2m100_418M",
    ("ru", "zh"): "facebook/m2m100_418M",
    ("zh", "en"): "facebook/m2m100_418M",
    ("ru", "en"): "facebook/m2m100_418M",
}

# 超高精度模型（更大的模型，最高精度但需要更多资源）
ULTRA_PRECISION_MODELS = {
    ("en", "zh"): "facebook/m2m100_1.2B",
    ("en", "ru"): "facebook/m2m100_1.2B",
    ("zh", "ru"): "facebook/m2m100_1.2B",
    ("ru", "zh"): "facebook/m2m100_1.2B",
    ("zh", "en"): "facebook/m2m100_1.2B",
    ("ru", "en"): "facebook/m2m100_1.2B",
}

# 自动检测 1.2B 是否已经下载完成；若有则升级到 ultra
def _has_full_snapshot(name: str) -> bool:
    org_model = name.replace('/', '--')
    for base in [model_cache_dir, os.path.join(model_cache_dir, 'hub')]:
        snap_base = os.path.join(base, f"models--{org_model}", 'snapshots')
        if not os.path.exists(snap_base):
            continue
        for snap in os.listdir(snap_base):
            d = os.path.join(snap_base, snap)
            has_cfg = os.path.isfile(os.path.join(d, 'config.json'))
            has_w = (os.path.isfile(os.path.join(d, 'model.safetensors'))
                     or os.path.isfile(os.path.join(d, 'pytorch_model.bin')))
            if has_cfg and has_w:
                return True
    return False


if MODEL_PRECISION == "base":
    PAIR_TO_MODEL = BASE_MODELS
    print(f"使用基础精度模型集: {MODEL_PRECISION}")
elif MODEL_PRECISION == "ultra" and _has_full_snapshot('facebook/m2m100_1.2B'):
    # 仅当用户显式要求 ultra 且 1.2B 已下载时才使用超大模型。
    # 注意：1.2B 在 CPU 上单句推理约 1~3 秒、占用 ~6.5GB 内存，
    # 实时字幕场景会明显卡顿，因此默认不再自动升级。
    PAIR_TO_MODEL = ULTRA_PRECISION_MODELS
    print(f"使用超高精度模型集: m2m100_1.2B（CPU 上较慢，适合离线高质量翻译）")
else:
    # 默认使用 418M：CPU 上单句约 0.2~0.5 秒，兼顾实时性与质量
    PAIR_TO_MODEL = HIGH_PRECISION_MODELS
    if MODEL_PRECISION == "ultra":
        print(f"未检测到完整的 m2m100_1.2B，回退到高精度模型集: m2m100_418M")
    else:
        print(f"使用高精度模型集: m2m100_418M（实时翻译推荐）")

# 当前 torch 是否能安全加载 .bin 权重（torch >= 2.6 才解除 CVE-2025-32434 限制）。
# 旧版本 transformers/torch 会直接拒绝加载 pytorch_model.bin，因此必须优先用 safetensors。
def _torch_can_load_bin() -> bool:
    try:
        import torch
        parts = torch.__version__.split('+')[0].split('.')
        major, minor = int(parts[0]), int(parts[1])
        return (major, minor) >= (2, 6)
    except Exception:
        return False


_CAN_LOAD_BIN = _torch_can_load_bin()


def _scan_snapshots(name: str):
    """
    扫描所有快照，返回 (tok_dir, weights_path)
    - tok_dir：包含 tokenizer + config 的目录
    - weights_path：权重文件，强制优先 safetensors。
      仅当本机 torch >= 2.6 时才允许回退到 pytorch_model.bin，
      否则旧 torch 会因 CVE-2025-32434 直接拒绝加载 .bin。
    优先选择「同时含 tokenizer/config/safetensors」的完整快照，
    这样可直接用 from_pretrained 加载，最稳。
    """
    org_model = name.replace('/', '--')
    tok_dir = None
    weights_safetensors = None
    weights_bin = None
    complete_dir = None  # tokenizer+config+safetensors 都在同一目录

    for base in [model_cache_dir, os.path.join(model_cache_dir, 'hub')]:
        snap_base = os.path.join(base, f"models--{org_model}", 'snapshots')
        if not os.path.exists(snap_base):
            continue
        for snap in os.listdir(snap_base):
            snap_dir = os.path.join(snap_base, snap)
            has_tok = (os.path.isfile(os.path.join(snap_dir, 'sentencepiece.bpe.model')) or
                       os.path.isfile(os.path.join(snap_dir, 'vocab.json')))
            has_cfg = os.path.isfile(os.path.join(snap_dir, 'config.json'))
            st = os.path.join(snap_dir, 'model.safetensors')
            pb = os.path.join(snap_dir, 'pytorch_model.bin')
            has_st = os.path.isfile(st)
            has_pb = os.path.isfile(pb)

            if has_tok and has_cfg:
                if tok_dir is None:
                    tok_dir = snap_dir
                if has_st and complete_dir is None:
                    complete_dir = snap_dir
            if has_st and weights_safetensors is None:
                weights_safetensors = st
            if has_pb and weights_bin is None:
                weights_bin = pb

    # 完整快照优先：tokenizer/config/safetensors 同目录
    if complete_dir is not None:
        return complete_dir, os.path.join(complete_dir, 'model.safetensors')

    # 否则 tokenizer 目录 + 独立权重；safetensors 优先，旧 torch 不回退 .bin
    weights_path = weights_safetensors
    if weights_path is None and _CAN_LOAD_BIN:
        weights_path = weights_bin
    return tok_dir, weights_path

def load_model(name: str):
    print(f"[模型] 尝试加载模型: {name}")
    if name in loaded:
        print(f"[模型] 已在内存中: {name}")
        return loaded[name]

    is_m2m100 = "m2m100" in name
    tok_dir, weights_path = _scan_snapshots(name)
    print(f"[模型] tok_dir={tok_dir}  weights={weights_path}")

    try:
        if is_m2m100:
            from transformers import M2M100Tokenizer, M2M100ForConditionalGeneration

            if not tok_dir:
                raise FileNotFoundError(f"未找到本地 M2M100 模型: {name}")

            print(f"[模型] 加载 M2M100 tokenizer 从: {tok_dir}")
            tok = M2M100Tokenizer.from_pretrained(tok_dir, local_files_only=True)

            # 只有当 tok_dir 自身含 safetensors 时才用 from_pretrained（最稳）。
            # 注意：不能因为存在 pytorch_model.bin 就走这条路——旧版 torch(<2.6)
            # 会因 CVE-2025-32434 拒绝加载 .bin，必须改走 safetensors 手动拼装。
            same_dir_weights = os.path.isfile(os.path.join(tok_dir, 'model.safetensors'))
            if same_dir_weights:
                print(f"[模型] 使用 from_pretrained 直接加载: {tok_dir}")
                mdl = M2M100ForConditionalGeneration.from_pretrained(tok_dir, local_files_only=True)
                mdl.eval()
            else:
                # 否则手动拼装：tokenizer/config 在 tok_dir，权重在另一个 snapshot
                from transformers import M2M100Config
                if not weights_path:
                    raise FileNotFoundError(f"找不到权重文件: {name}")
                print(f"[模型] 拼装：config 来自 {tok_dir}，权重来自 {weights_path}")
                config = M2M100Config.from_pretrained(tok_dir, local_files_only=True)
                mdl = M2M100ForConditionalGeneration(config)
                if weights_path.endswith('.safetensors'):
                    from safetensors.torch import load_file
                    state_dict = load_file(weights_path)
                else:
                    import torch
                    state_dict = torch.load(weights_path, map_location='cpu')
                mdl.load_state_dict(state_dict, strict=False)
                mdl.tie_weights()
                mdl.eval()

        else:
            from transformers import MarianTokenizer, MarianMTModel
            if not tok_dir:
                raise FileNotFoundError(f"未找到本地 MarianMT 模型: {name}")
            print(f"[模型] 加载 MarianMT 从: {tok_dir}")
            tok = MarianTokenizer.from_pretrained(tok_dir, local_files_only=True)
            mdl = MarianMTModel.from_pretrained(tok_dir, local_files_only=True)
            is_m2m100 = False

        print(f"[模型] 加载完成: {type(mdl).__name__}")
        loaded[name] = (tok, mdl, is_m2m100)
        return tok, mdl, is_m2m100

    except Exception as e:
        print(f"[模型] 加载失败: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        raise

def process(items: List[dict], target: str) -> List[dict]:
    # 规范化目标语言代码
    tgt = target.lower()
    # 处理zh-CN等变体
    if tgt.startswith('zh'):
        tgt = 'zh'
    elif tgt.startswith('ru'):
        tgt = 'ru'
    elif tgt.startswith('en'):
        tgt = 'en'
    
    groups: Dict[Tuple[str, str], List[Tuple[int, str]]] = {}
    for idx, it in enumerate(items):
        txt = it.get("text", "")
        src = detect_src(txt)
        key = (src, tgt)
        groups.setdefault(key, []).append((idx, txt))
    out_items = [{"start": it.get("start"), "end": it.get("end"), "text": it.get("text", "")} for it in items]
    
    # 支持更多语言对的fallback机制
    def get_fallback_model(key):
        src, tgt = key
        if (src, tgt) in PAIR_TO_MODEL:
            return PAIR_TO_MODEL[(src, tgt)]
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
        # 跨语言对的fallback：通过英语中转
        if (src, "en") in PAIR_TO_MODEL and ("en", tgt) in PAIR_TO_MODEL:
            return "Helsinki-NLP/opus-mt-" + src + "-en"  # 先翻译成英语
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
            tok, mdl, is_m2m100 = load_model(model_name)
            # Split cached vs uncached
            uncached_indices: List[int] = []
            uncached_texts: List[str] = []
            produced: Dict[int, str] = {}
            for i, (idx, text) in enumerate(batch):
                ck = f"{key[0]}->{key[1]}::{text}"
                cv = cache_get(ck)
                if cv is not None:
                    produced[i] = cv
                else:
                    uncached_indices.append(i)
                    uncached_texts.append(text)
            outs_uncached: List[str] = []
            if uncached_texts:
                if is_m2m100:
                    # M2M100模型处理（高精度模型）
                    src_lang = key[0]
                    tgt_lang = key[1]
                    
                    # 处理M2M100模型的语言代码映射
                    lang_code_map = {
                        'zh': 'zh',   # m2m100_418M tokenizer 中文代码为 zh
                        'ru': 'ru',
                        'en': 'en'
                    }
                    
                    # 映射到M2M100支持的语言代码
                    m2m100_src_lang = lang_code_map.get(src_lang, src_lang)
                    m2m100_tgt_lang = lang_code_map.get(tgt_lang, tgt_lang)
                    
                    print(f"使用高精度m2m100模型翻译：{src_lang}({m2m100_src_lang}) -> {tgt_lang}({m2m100_tgt_lang})")
                    
                    try:
                        # 检查语言代码是否存在
                        if m2m100_src_lang not in tok.lang_code_to_id:
                            print(f"[警告] 源语言代码 {m2m100_src_lang} 不被支持，使用默认语言")
                        if m2m100_tgt_lang not in tok.lang_code_to_id:
                            print(f"[错误] 目标语言代码 {m2m100_tgt_lang} 不被支持")
                            continue
                            
                        # 设置源语言
                        tok.src_lang = m2m100_src_lang
                        
                        # 编码输入文本（增大长度上限避免被截断）
                        enc = tok(uncached_texts, return_tensors="pt", padding=True, truncation=True, max_length=256)

                        # 1.2B 在 CPU 上 beam=5 太慢；用 beam=1 跟得上播放节奏，
                        # 1.2B@beam=1 的质量仍优于 418M@beam=5
                        is_large = "1.2B" in str(model_name) or "1.2b" in str(model_name)
                        beams = 1 if is_large else 5
                        generated_tokens = mdl.generate(
                            **enc,
                            forced_bos_token_id=tok.lang_code_to_id[m2m100_tgt_lang],
                            max_length=256,
                            num_beams=beams,
                            early_stopping=True,
                            no_repeat_ngram_size=3,
                            length_penalty=1.0,
                            do_sample=False,
                        )
                        
                        # 解码生成的tokens
                        outs_uncached = tok.batch_decode(generated_tokens, skip_special_tokens=True)
                        
                        print(f"[翻译结果] 输入: {uncached_texts}")
                        print(f"[翻译结果] 输出: {outs_uncached}")
                        
                    except Exception as e:
                        print(f"[翻译错误] {e}")
                        import traceback
                        traceback.print_exc(file=sys.stderr)
                else:
                    # MarianMT 同样开 beam=5 提升精度
                    enc = tok(uncached_texts, return_tensors="pt", padding=True, truncation=True, max_length=256)
                    gen = mdl.generate(
                        **enc,
                        max_length=256,
                        num_beams=5,
                        early_stopping=True,
                        no_repeat_ngram_size=3,
                        length_penalty=1.0,
                        do_sample=False,
                    )
                    outs_uncached = tok.batch_decode(gen, skip_special_tokens=True)
            # Stitch results, update cache
            u_ptr = 0
            final_outs: List[str] = []
            for i in range(len(batch)):
                if i in produced:
                    final_outs.append(produced[i])
                else:
                    t = outs_uncached[u_ptr] if u_ptr < len(outs_uncached) else batch[i][1]
                    u_ptr += 1
                    ck = f"{key[0]}->{key[1]}::{batch[i][1]}"
                    cache_set(ck, t)
                    final_outs.append(t)
            for (idx, _), t in zip(batch, final_outs):
                if tgt == "ru":
                    # 保留所有内容，包括俄语和英文
                    # t = re.sub(r'\b[A-Za-z]+\b', '', t).strip()
                    # t = re.sub(r'\s{2,}', ' ', t)
                    print(f"俄语翻译结果: {t}")
                # 使用安全文本处理函数
                out_items[idx]["text"] = safe_text(t)
        except Exception as e:
            # 如果直接翻译失败，尝试通过英语中转翻译
            try:
                src, tgt = key
                if (src, "en") in PAIR_TO_MODEL and ("en", tgt) in PAIR_TO_MODEL:
                    # 先翻译成英语
                    en_model_name = PAIR_TO_MODEL[(src, "en")]
                    tok_en, mdl_en, _ = load_model(en_model_name)

                    # 再翻译成目标语言
                    tgt_model_name = PAIR_TO_MODEL[("en", tgt)]
                    tok_tgt, mdl_tgt, _ = load_model(tgt_model_name)
                    
                    for i, (idx, text) in enumerate(batch):
                        ck = f"{src}->{tgt}::{text}"
                        cv = cache_get(ck)
                        if cv is not None:
                            out_items[idx]["text"] = cv
                            continue
                            
                        try:
                            # 第一步：翻译成英语
                            enc_en = tok_en([text], return_tensors="pt", padding=True)
                            gen_en = mdl_en.generate(**enc_en, max_length=128, num_beams=1)
                            en_text = tok_en.decode(gen_en[0], skip_special_tokens=True)
                            
                            # 第二步：从英语翻译成目标语言
                            enc_tgt = tok_tgt([en_text], return_tensors="pt", padding=True)
                            gen_tgt = mdl_tgt.generate(**enc_tgt, max_length=128, num_beams=1)
                            translated_text = tok_tgt.decode(gen_tgt[0], skip_special_tokens=True)
                            
                            cache_set(ck, translated_text)
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

    # 术语表后处理：整句强制译法优先，其次对模型输出做误译修正替换。
    # 显著改善「专有名词/固定译法」这类模型反复译错的情况。
    if term_utils:
        for idx, it in enumerate(items):
            orig = it.get("text", "") or ""
            try:
                forced = term_utils.forced_translation(orig, tgt)
                if forced is not None:
                    out_items[idx]["text"] = safe_text(forced)
                else:
                    fixed = term_utils.apply_replacements(out_items[idx].get("text", ""), tgt)
                    out_items[idx]["text"] = safe_text(fixed)
            except Exception:  # noqa: BLE001 - 术语表问题不应影响翻译结果
                continue
    return out_items

# HTTP请求处理程序类
class TranslationHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        # 解析请求路径
        parsed_path = urlparse(self.path)
        
        # 只处理/translate路径的POST请求
        if parsed_path.path != '/translate':
            self.send_error(404, "Not Found")
            return
        
        try:
            # 获取请求体大小
            content_length = int(self.headers['Content-Length'])
            
            # 读取请求体
            post_data = self.rfile.read(content_length)
            
            # 解析JSON请求
            req = json.loads(post_data.decode('utf-8'))
            
            # 验证请求参数
            if 'items' not in req:
                self.send_error(400, "Bad Request: Missing 'items' parameter")
                return
            
            # 获取请求参数
            items = req.get('items', [])
            target = req.get('target', 'zh')
            
            # 处理翻译请求
            res_items = process(items, target)
            
            # 构建响应
            resp = {
                'ok': True,
                'items': res_items
            }
            
            # 设置响应头
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            # 发送响应体
            self.wfile.write(json.dumps(resp, ensure_ascii=False).encode('utf-8'))
            
        except Exception as e:
            print(f"处理请求时发生错误: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            
            # 发送错误响应
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            error_resp = {
                'ok': False,
                'error': str(e)
            }
            
            self.wfile.write(json.dumps(error_resp, ensure_ascii=False).encode('utf-8'))
    
    def do_GET(self):
        # 简单的健康检查
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok'}).encode('utf-8'))
        else:
            self.send_error(404, "Not Found")
    
    def log_message(self, format, *args):
        # 自定义日志格式，包含时间戳
        import datetime
        now = datetime.datetime.now()
        timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {self.address_string()} - {format % args}")

def main():
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='Machine Translation Server')
    parser.add_argument('--port', type=int, default=8000, help='服务器端口号')
    args = parser.parse_args()
    
    # 创建HTTP服务器
    server_address = ('', args.port)
    httpd = HTTPServer(server_address, TranslationHandler)
    
    print(f"[服务器] 翻译服务已启动，监听端口 {args.port}")
    print(f"[服务器] 健康检查: http://localhost:{args.port}/health")
    print(f"[服务器] 翻译API: POST http://localhost:{args.port}/translate")
    print("[服务器] 按 Ctrl+C 停止服务")
    
    try:
        # 启动服务器
        httpd.serve_forever()
    except KeyboardInterrupt:
        # 处理Ctrl+C中断
        print("\n[服务器] 正在停止服务...")
        httpd.shutdown()
        print("[服务器] 服务已停止")
    except Exception as e:
        print(f"[服务器] 启动失败: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
