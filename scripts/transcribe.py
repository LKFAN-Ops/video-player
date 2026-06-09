import argparse
import os
import sys

def to_srt_time(sec: float) -> str:
    if sec < 0: sec = 0.0
    total_ms = int(round(sec * 1000))
    h = total_ms // 3600000
    rem1 = total_ms % 3600000
    m = rem1 // 60000
    rem2 = rem1 % 60000
    s = rem2 // 1000
    ms = rem2 % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def write_srt(segments, out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            f.write(str(i) + "\n")
            f.write(f"{to_srt_time(seg['start'])} --> {to_srt_time(seg['end'])}\n")
            f.write(seg['text'].strip() + "\n\n")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="音频或视频文件路径")
    parser.add_argument("--output_dir", required=True, help="输出目录")
    parser.add_argument("--model", default="base", help="模型名称，如 tiny/base/small/medium")
    parser.add_argument("--language", default=None, help="语言代码，例如 zh/en/ru；留空自动识别")
    parser.add_argument("--compute_type", default="int8", help="计算精度：int8/int8_float32/float16/float32")
    parser.add_argument("--device", default="cpu", help="设备：cpu/cuda")
    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel
    except Exception as e:
        print("ERR: faster_whisper_import", file=sys.stderr)
        sys.exit(2)

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.makedirs(args.output_dir, exist_ok=True)

    base = os.path.basename(args.input)
    name, _ = os.path.splitext(base)
    out_srt = os.path.join(args.output_dir, f"{name}.srt")

    try:
        model = WhisperModel(args.model, device=args.device, compute_type=args.compute_type)
        segments, info = model.transcribe(args.input, language=args.language if args.language else None)

        collected = []
        for s in segments:
            collected.append({
                "start": float(s.start),
                "end": float(s.end),
                "text": s.text or ""
            })
        write_srt(collected, out_srt)
        print(out_srt)
        sys.exit(0)
    except Exception as e:
        print("ERR: transcribe_failed", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
