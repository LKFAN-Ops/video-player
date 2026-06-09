import argparse
import os
import sys

# 共享术语表 / CPU 线程配置（可选；缺失时优雅降级）
try:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import term_utils
except Exception:  # noqa: BLE001
    term_utils = None


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


def write_srt(segments, out_path: str):
    with open(out_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(segments, start=1):
            f.write(str(i) + "\n")
            f.write(f"{to_srt_time(seg['start'])} --> {to_srt_time(seg['end'])}\n")
            f.write(seg['text'].strip() + "\n\n")


def _cpu_threads():
    if term_utils:
        try:
            return term_utils.cpu_threads()
        except Exception:  # noqa: BLE001
            pass
    n = os.cpu_count() or 4
    return max(1, min(8, n // 2 if n > 4 else n))


def _hotwords():
    if term_utils:
        try:
            return term_utils.hotwords_string() or None
        except Exception:  # noqa: BLE001
            return None
    return None


def _load_model_with_fallback(name, device, compute_type, threads):
    """按 用户指定 → small → base → tiny 回退加载，最大化「能跑起来 + 尽量准」。"""
    from faster_whisper import WhisperModel
    chain, seen = [], set()
    for n in [name, "small", "base", "tiny"]:
        if n and n not in seen:
            chain.append(n)
            seen.add(n)
    last_err = None
    for cand in chain:
        try:
            print(f"INFO: loading model {cand} (device={device}, compute={compute_type}, threads={threads})",
                  file=sys.stderr)
            return WhisperModel(cand, device=device, compute_type=compute_type, cpu_threads=threads), cand
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"INFO: load {cand} failed: {e}", file=sys.stderr)
    raise RuntimeError(f"all models failed: {last_err}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="音频或视频文件路径")
    parser.add_argument("--output_dir", required=True, help="输出目录")
    parser.add_argument("--model", default=os.environ.get("WHISPER_MODEL", "base"),
                        help="模型名称，如 tiny/base/small/medium")
    parser.add_argument("--language", default=None, help="语言代码，例如 zh/en/ru；留空自动识别")
    parser.add_argument("--compute_type", default=os.environ.get("WHISPER_COMPUTE", "int8"),
                        help="计算精度：int8/int8_float32/float16/float32")
    parser.add_argument("--device", default="cpu", help="设备：cpu/cuda")
    parser.add_argument("--batch_size", type=int,
                        default=int(os.environ.get("WHISPER_BATCH_SIZE", "8") or "8"),
                        help="批量推理大小（越大越快、占用越高；0=关闭批量）")
    parser.add_argument("--beam_size", type=int, default=5, help="beam 大小，整片转写默认 5 提升精度")
    args = parser.parse_args()

    try:
        from faster_whisper import WhisperModel  # noqa: F401
    except Exception:
        print("ERR: faster_whisper_import", file=sys.stderr)
        sys.exit(2)

    os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
    os.makedirs(args.output_dir, exist_ok=True)

    base = os.path.basename(args.input)
    name, _ = os.path.splitext(base)
    out_srt = os.path.join(args.output_dir, f"{name}.srt")

    threads = _cpu_threads()
    hotwords = _hotwords()
    language = args.language if args.language else None

    try:
        model, used = _load_model_with_fallback(args.model, args.device, args.compute_type, threads)

        # 整片转写不要求实时，开 beam=5 + temperature 回退链，兼顾精度与抗幻觉。
        common = dict(
            language=language,
            beam_size=args.beam_size,
            temperature=[0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            compression_ratio_threshold=2.4,
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
            hallucination_silence_threshold=2.0,
            hotwords=hotwords,
            word_timestamps=False,
        )

        # 批量推理：长视频整片转写的关键提速（CPU 上常见 4~10×）。
        # 注意：批量模式内部强制启用 VAD、且不使用 condition_on_previous_text。
        segments = None
        if args.batch_size and args.batch_size > 1:
            try:
                from faster_whisper import BatchedInferencePipeline
                pipe = BatchedInferencePipeline(model=model)
                print(f"INFO: batched transcribe batch_size={args.batch_size}", file=sys.stderr)
                segments, info = pipe.transcribe(args.input, batch_size=args.batch_size, **common)
            except Exception as e:  # noqa: BLE001 - 批量不可用则回退顺序模式
                print(f"INFO: batched unavailable, fallback sequential: {e}", file=sys.stderr)
                segments = None

        if segments is None:
            segments, info = model.transcribe(
                args.input, condition_on_previous_text=True, **common
            )

        collected = []
        for s in segments:
            collected.append({
                "start": float(s.start) if s.start is not None else 0.0,
                "end": float(s.end) if s.end is not None else 0.0,
                "text": s.text or ""
            })
        write_srt(collected, out_srt)
        print(out_srt)
        sys.exit(0)
    except Exception as e:
        print(f"ERR: transcribe_failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
