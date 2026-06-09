# 常驻 faster-whisper HTTP 服务，避免每段都重新加载模型
# 端点：POST /transcribe  body: { "input": "/path/to/audio.wav", "language": "auto"|"en"|"zh"|"ru" }
#       返回: { "ok": true, "items": [ {start_sec, end_sec, text} ], "srt": "..." }
import argparse
import json
import os
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


_model = None
_loaded_name = None
_model_lock = threading.Lock()
_model_ready = threading.Event()
_load_error = None


def to_srt_time(sec: float) -> str:
    if sec is None or sec < 0:
        sec = 0.0
    total_ms = int(round(sec * 1000))
    h = total_ms // 3600000
    rem1 = total_ms % 3600000
    m = rem1 // 60000
    rem2 = rem1 % 60000
    s = rem2 // 1000
    ms = rem2 % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def items_to_srt(items):
    lines = []
    for i, it in enumerate(items, start=1):
        lines.append(str(i))
        lines.append(f"{to_srt_time(it['start_sec'])} --> {to_srt_time(it['end_sec'])}")
        lines.append((it.get('text') or '').strip())
        lines.append('')
    return '\n'.join(lines)


def _try_load(name: str, device: str, compute_type: str, local_only: bool):
    from faster_whisper import WhisperModel
    print(f"[whisper] 尝试加载模型: {name} (device={device}, compute_type={compute_type}, local_only={local_only})", flush=True)
    return WhisperModel(name, device=device, compute_type=compute_type, local_files_only=local_only)


def load_model_background(name: str, device: str, compute_type: str):
    """后台线程加载模型。优先按指定大小→更小尺寸回退；先纯本地、再允许下载。"""
    global _model, _loaded_name, _load_error
    # 精度从高到低的回退链：用户指定 → small → base → tiny
    fallback_chain = []
    seen = set()
    for n in [name, 'small', 'base', 'tiny']:
        if n and n not in seen:
            fallback_chain.append(n)
            seen.add(n)

    # 先全部纯本地尝试，再允许联网
    candidates = [(n, True) for n in fallback_chain] + [(n, False) for n in fallback_chain]

    for cand_name, local_only in candidates:
        try:
            with _model_lock:
                m = _try_load(cand_name, device, compute_type, local_only)
                _model = m
                _loaded_name = cand_name
                _load_error = None
                print(f"[whisper] 模型已就绪: {cand_name}", flush=True)
                _model_ready.set()
                return
        except Exception as e:
            print(f"[whisper] 加载 {cand_name} (local={local_only}) 失败: {e}", flush=True)
            _load_error = str(e)
            continue
    print(f"[whisper] 所有候选模型加载均失败", file=sys.stderr, flush=True)
    _model_ready.set()  # 解除等待，由 _model 是否为 None 表示成功


def wait_for_model(timeout=120):
    if _model_ready.wait(timeout):
        return _model is not None
    return False


def transcribe(audio_path: str, language: str = None):
    if not wait_for_model(timeout=120):
        raise RuntimeError(f"模型未就绪: {_load_error or '未知错误'}")
    model = _model
    if model is None:
        raise RuntimeError(f"模型加载失败: {_load_error or '未知错误'}")
    lang = None if (not language or language == 'auto') else language
    # 实时优先：beam=1 (3-4× 速度，精度损失轻微)，保留 VAD 与上下文
    segments, info = model.transcribe(
        audio_path,
        language=lang,
        beam_size=1,
        best_of=1,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
        condition_on_previous_text=True,
        temperature=0.0,
        compression_ratio_threshold=2.4,
        no_speech_threshold=0.6,
        word_timestamps=False,
    )
    items = []
    for s in segments:
        items.append({
            'start_sec': float(s.start) if s.start is not None else 0.0,
            'end_sec':   float(s.end)   if s.end   is not None else 0.0,
            'text':      s.text or ''
        })
    return items


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == '/health':
            return self._send_json(200, {
                'ok': True,
                'ready': _model is not None,
                'model': _loaded_name,
                'error': _load_error
            })
        return self._send_json(404, {'ok': False, 'error': 'not_found'})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != '/transcribe':
            return self._send_json(404, {'ok': False, 'error': 'not_found'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            data = self.rfile.read(length)
            req = json.loads(data.decode('utf-8'))
            audio_path = req.get('input')
            if not audio_path or not os.path.exists(audio_path):
                return self._send_json(400, {'ok': False, 'error': 'invalid_input'})
            language = req.get('language')
            items = transcribe(audio_path, language)
            srt = items_to_srt(items)
            self._send_json(200, {'ok': True, 'items': items, 'srt': srt})
        except Exception as e:
            print(f"[whisper] 转写失败: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            self._send_json(500, {'ok': False, 'error': str(e)})

    def log_message(self, fmt, *args):
        # 静默逐行请求日志，减少噪音
        return


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8001)
    # 默认使用 base：体积适中、识别质量稳定，且用户机器上已完整缓存
    p.add_argument('--model', default='base', help='tiny/base/small/medium')
    p.add_argument('--device', default='cpu')
    p.add_argument('--compute_type', default='int8')
    args = p.parse_args()

    os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')

    # 后台异步加载模型，不阻塞 HTTP 端口启动
    t = threading.Thread(
        target=load_model_background,
        args=(args.model, args.device, args.compute_type),
        daemon=True
    )
    t.start()

    httpd = HTTPServer(('127.0.0.1', args.port), Handler)
    print(f"[whisper] 服务监听 http://127.0.0.1:{args.port}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == '__main__':
    main()
