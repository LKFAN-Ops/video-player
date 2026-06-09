# 商业级硬字幕去除（STTN 时序视频补全，GPU）
# 用法（由主进程调用）：
#   python desub_sttn.py --input IN --output OUT --model sttn.pth \
#       --region_norm x,y,w,h  [--mask_mode auto|box] [--device cuda]
# 设计：
#   - 用户在播放器画的区域框 = 字幕条所在的水平带（strip）。
#   - 逐帧在 strip 内用阈值生成「文字 mask」（只挖掉文字像素，背景保留）。
#   - STTN 参考相邻帧 + 全局参考帧，把文字背后的画面「补」回来（时序连贯、不闪）。
#   - 仅替换文字像素，strip 内非文字区域保持原始清晰。
#   - 用 ffmpeg 重新编码并保留原音轨。
#   进度以 "PROGRESS done total" 打到 stdout，供主进程解析。
import argparse
import os
import sys
import subprocess

import numpy as np
import cv2
import torch

# 让 from network_sttn / spectral_norm 可被导入
_STTN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sttn")
sys.path.insert(0, _STTN_DIR)
from network_sttn import InpaintGenerator  # noqa: E402

MODEL_W, MODEL_H = 432, 240
# STTN 采样参数（与原始实现一致）
NEIGHBOR_STRIDE = 5
REF_LENGTH = 10

import contextlib


def _nullctx():
    return contextlib.nullcontext()


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def progress(done, total):
    print(f"PROGRESS {done} {total}", flush=True)


STTN_URL = "https://raw.githubusercontent.com/YaoFANGUK/video-subtitle-remover/main/backend/models/sttn-det/sttn.pth"


def ensure_weights(model_path):
    """权重不存在时自动从 GitHub 直连下载（约 66MB，免代理）。"""
    if os.path.exists(model_path) and os.path.getsize(model_path) > 60_000_000:
        return
    os.makedirs(os.path.dirname(os.path.abspath(model_path)), exist_ok=True)
    log(f"INFO: 下载 STTN 权重到 {model_path} …")
    import urllib.request
    tmp = model_path + ".part"
    req = urllib.request.Request(STTN_URL, headers={"User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        f.write(r.read())
    os.replace(tmp, model_path)
    log(f"INFO: 权重就绪 {os.path.getsize(model_path)} bytes")


def load_model(model_path, device):
    ensure_weights(model_path)
    model = InpaintGenerator(init_weights=False).to(device)
    ckpt = torch.load(model_path, map_location="cpu")
    state = ckpt.get("netG", ckpt) if isinstance(ckpt, dict) else ckpt
    model.load_state_dict(state)
    model.eval()
    return model


def build_text_mask(strip_bgr, bright_thr, dilate_px):
    """在字幕带内生成文字 mask：高亮度（白/黄字）+ 膨胀覆盖描边/抗锯齿。返回 {0,1} uint8 HxW。"""
    gray = cv2.cvtColor(strip_bgr, cv2.COLOR_BGR2GRAY)
    _, m = cv2.threshold(gray, bright_thr, 1, cv2.THRESH_BINARY)
    if dilate_px > 0:
        k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_px, dilate_px))
        m = cv2.dilate(m, k, iterations=1)
    return m.astype(np.uint8)


def get_ref_index(neighbor_ids, length):
    return [i for i in range(0, length, REF_LENGTH) if i not in neighbor_ids]


@torch.no_grad()
def inpaint_clip(model, frames_model_rgb, masks_model, device, fp16=True):
    """frames_model_rgb: list[HxWx3 uint8 RGB] @ 模型尺寸; masks_model: list[HxW uint8 {0,1}]。
    返回 list[HxWx3 uint8 RGB] 补全结果（模型尺寸）。"""
    L = len(frames_model_rgb)
    # (L,3,H,W) in [-1,1]
    feats = torch.from_numpy(np.stack(frames_model_rgb, 0)).float().permute(0, 3, 1, 2) / 255.0
    feats = feats * 2 - 1
    masks_t = torch.from_numpy(np.stack(masks_model, 0)).float().unsqueeze(1)  # (L,1,H,W)
    feats, masks_t = feats.to(device), masks_t.to(device)
    bin_masks = [m[:, :, None] for m in masks_model]  # HxWx1

    # fp16 自动混合精度：在 4060 上约 2× 提速、显存减半（CPU 时关闭）
    use_amp = fp16 and str(device).startswith("cuda")
    amp = torch.autocast("cuda", dtype=torch.float16) if use_amp else _nullctx()
    with amp:
        enc = model.encoder((feats * (1 - masks_t)).view(L, 3, MODEL_H, MODEL_W))
        _, c, fh, fw = enc.size()
        enc = enc.view(1, L, c, fh, fw)

        comp = [None] * L
        for f in range(0, L, NEIGHBOR_STRIDE):
            neighbor_ids = list(range(max(0, f - NEIGHBOR_STRIDE), min(L, f + NEIGHBOR_STRIDE + 1)))
            ref_ids = get_ref_index(neighbor_ids, L)
            sel = neighbor_ids + ref_ids
            pred_feat = model.infer(enc[0, sel], masks_t[sel])
            pred_img = torch.tanh(model.decoder(pred_feat[:len(neighbor_ids)]))
            pred_img = ((pred_img + 1) / 2).float().cpu().permute(0, 2, 3, 1).numpy() * 255
            for i, idx in enumerate(neighbor_ids):
                img = pred_img[i].astype(np.uint8) * bin_masks[idx] + \
                      frames_model_rgb[idx] * (1 - bin_masks[idx])
                if comp[idx] is None:
                    comp[idx] = img
                else:
                    comp[idx] = (comp[idx].astype(np.float32) * 0.5 + img.astype(np.float32) * 0.5).astype(np.uint8)
    return comp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--model", required=True, help="sttn.pth 路径")
    ap.add_argument("--region_norm", help="x,y,w,h 归一化(0~1)，相对原始帧")
    ap.add_argument("--region", help="x,y,w,h 像素，优先于 region_norm")
    ap.add_argument("--mask_mode", default="auto", choices=["auto", "box"])
    ap.add_argument("--bright_thr", type=int, default=190)
    ap.add_argument("--dilate_px", type=int, default=7)
    ap.add_argument("--clip_len", type=int, default=50)
    ap.add_argument("--device", default="cuda")
    ap.add_argument("--ffmpeg", default="ffmpeg")
    ap.add_argument("--crf", type=int, default=18)
    ap.add_argument("--encoder", default="auto", help="auto|nvenc|x264 视频编码器")
    ap.add_argument("--no_fp16", action="store_true", help="关闭半精度推理")
    ap.add_argument("--no_skip", action="store_true", help="不跳过无字幕片段（每帧都跑 STTN）")
    args = ap.parse_args()

    device = args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        log("WARN: CUDA 不可用，回退 CPU（会很慢）")
        device = "cpu"
    if str(device).startswith("cuda"):
        torch.backends.cudnn.benchmark = True  # 固定尺寸输入下自动选最快卷积算法

    # 用内置 ffmpeg 探测分辨率/帧率/时长/音频编码——比 cv2 更稳，支持 mkv/HEVC 及中文路径
    W, H, fps, total, acodec = probe_video(args.ffmpeg, args.input)
    if not W or not H:
        log("ERR: cannot probe input (无法解析视频，可能是不支持的封装/编码)")
        sys.exit(1)

    # 解析区域 -> 像素 strip [y0,y1) 全宽
    if args.region:
        rx, ry, rw, rh = [int(round(float(v))) for v in args.region.split(",")]
    else:
        nx, ny, nw, nh = [float(v) for v in (args.region_norm or "0.06,0.80,0.88,0.16").split(",")]
        rx, ry, rw, rh = int(nx * W), int(ny * H), int(nw * W), int(nh * H)
    y0 = max(0, min(ry, H - 2))
    y1 = max(y0 + 1, min(ry + rh, H))
    x0 = max(0, min(rx, W - 2))
    x1 = max(x0 + 1, min(rx + rw, W))
    log(f"INFO: {W}x{H}@{fps:.2f} frames={total} strip y[{y0}:{y1}] x[{x0}:{x1}] device={device} mask={args.mask_mode}")

    model = load_model(args.model, device)

    # 解码：内置 ffmpeg 把视频解成 rawvideo(BGR24) 从 stdout 流出（全格式支持）
    dec_args = [
        args.ffmpeg, "-hide_banner", "-loglevel", "error",
        "-i", args.input, "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]
    dec = subprocess.Popen(dec_args, stdout=subprocess.PIPE)

    # 音频策略：mp4 容器能直接容纳的编码就「原样复制」（保留 5.1，不过编码器，最稳）；
    # 否则降混成立体声 AAC——内置 aac 编码器不支持 6 声道(5.1)，直接编码会失败。
    MP4_COPYABLE = {"aac", "ac3", "eac3", "mp3", "alac"}
    if acodec in MP4_COPYABLE:
        audio_args = ["-c:a", "copy"]
    else:
        audio_args = ["-c:a", "aac", "-b:a", "192k", "-ac", "2"]
    log(f"INFO: 音频编码={acodec or '无'} -> {'copy' if acodec in MP4_COPYABLE else 'aac/stereo'}")

    # 视频编码器：优先 NVENC（GPU 硬件编码，比 CPU x264 快数倍），不可用时回退 x264
    venc = args.encoder
    if venc == "auto":
        venc = "nvenc" if (str(device).startswith("cuda") and nvenc_available(args.ffmpeg)) else "x264"
    if venc == "nvenc":
        video_args = ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr", "-cq", "21", "-b:v", "0"]
    else:
        video_args = ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(args.crf)]
    log(f"INFO: 视频编码器={venc}")

    # 编码：rawvideo(BGR) 经 stdin 作视频，原文件作音频，重新编码并保留音轨。
    # scale=trunc(iw/2)*2:... 强制偶数尺寸——奇数宽/高会让 libx264+yuv420p 直接报错退出。
    ff_args = [
        args.ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", f"{fps}", "-i", "-",
        "-i", args.input,
        "-map", "0:v:0", "-map", "1:a:0?",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        *video_args, "-pix_fmt", "yuv420p",
        *audio_args, "-shortest", args.output,
    ]
    ff = subprocess.Popen(ff_args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    # 后台线程收集编码器 stderr，BrokenPipe 时用它给出真正的失败原因
    enc_err = []
    import threading

    def _drain():
        try:
            for line in ff.stderr:
                enc_err.append(line.decode("utf-8", "ignore"))
        except Exception:
            pass
    threading.Thread(target=_drain, daemon=True).start()

    def write_frame(frame):
        try:
            ff.stdin.write(frame.astype(np.uint8).tobytes())
        except BrokenPipeError:
            ff.wait()
            msg = "".join(enc_err).strip() or f"ffmpeg 编码器提前退出(code={ff.returncode})"
            raise RuntimeError("编码失败: " + msg[-500:])

    frame_bytes = W * H * 3
    done = 0

    def process_clip(clip_bgr):
        nonlocal done
        # 抽 strip，生成文字 mask，缩放到模型尺寸
        frames_model_rgb, masks_model, full_masks = [], [], []
        for fr in clip_bgr:
            strip = fr[y0:y1, x0:x1]
            if args.mask_mode == "box":
                fm = np.ones(strip.shape[:2], np.uint8)
            else:
                fm = build_text_mask(strip, args.bright_thr, args.dilate_px)
            full_masks.append(fm)
            strip_rgb = cv2.cvtColor(cv2.resize(strip, (MODEL_W, MODEL_H)), cv2.COLOR_BGR2RGB)
            m_small = cv2.resize(fm, (MODEL_W, MODEL_H), interpolation=cv2.INTER_NEAREST)
            frames_model_rgb.append(strip_rgb)
            masks_model.append((m_small > 0).astype(np.uint8))

        # 跳过无字幕片段：整段检测不到亮文字 -> 不跑 STTN，直接原样透传（大幅提速）
        if args.mask_mode != "box" and not args.no_skip:
            if sum(int(m.sum()) for m in masks_model) == 0:
                for fr in clip_bgr:
                    write_frame(fr)
                    done += 1
                    if done % 10 == 0 or done == total:
                        progress(done, total)
                return

        comp = inpaint_clip(model, frames_model_rgb, masks_model, device, fp16=not args.no_fp16)
        # 回贴：模型结果缩放回 strip 尺寸，仅替换全分辨率文字像素
        sh, sw = y1 - y0, x1 - x0
        for i, fr in enumerate(clip_bgr):
            comp_bgr = cv2.cvtColor(cv2.resize(comp[i], (sw, sh)), cv2.COLOR_RGB2BGR)
            fm = full_masks[i]
            if args.mask_mode != "box":
                fm3 = fm[:, :, None]
                orig = fr[y0:y1, x0:x1]
                fr[y0:y1, x0:x1] = comp_bgr * fm3 + orig * (1 - fm3)
            else:
                fr[y0:y1, x0:x1] = comp_bgr
            write_frame(fr)
            done += 1
            if done % 10 == 0 or done == total:
                progress(done, total)

    def read_frame():
        buf = dec.stdout.read(frame_bytes)
        if not buf or len(buf) < frame_bytes:
            return None
        return np.frombuffer(buf, np.uint8).reshape(H, W, 3).copy()

    clip = []
    while True:
        frame = read_frame()
        if frame is None:
            break
        clip.append(frame)
        if len(clip) >= args.clip_len:
            process_clip(clip)
            clip = []
    if clip:
        process_clip(clip)

    try:
        dec.stdout.close()
    except Exception:
        pass
    dec.wait()
    try:
        ff.stdin.close()
    except BrokenPipeError:
        pass
    rc = ff.wait()
    if rc != 0:
        log(f"ERR: ffmpeg encode exit {rc}: " + ("".join(enc_err).strip()[-500:] or "(no stderr)"))
        sys.exit(1)
    if done == 0:
        log("ERR: no frames decoded (解码 0 帧，ffmpeg 无法解码该视频)")
        sys.exit(1)
    progress(total or done, total or done)
    print(args.output, flush=True)


_nvenc_cache = None


def nvenc_available(ffmpeg):
    """实测一帧 h264_nvenc 编码能否成功（仅列在 -encoders 不代表驱动/会话可用）。"""
    global _nvenc_cache
    if _nvenc_cache is not None:
        return _nvenc_cache
    try:
        p = subprocess.run(
            [ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "color=c=black:s=320x240:d=1", "-frames:v", "1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        _nvenc_cache = (p.returncode == 0)
    except Exception:
        _nvenc_cache = False
    return _nvenc_cache


def probe_video(ffmpeg, path):
    """用 ffmpeg -i 解析 宽/高/帧率/总帧数/音频编码。返回 (W,H,fps,total,acodec)。"""
    import re
    p = subprocess.Popen([ffmpeg, "-hide_banner", "-i", path],
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    _, err = p.communicate()
    s = err.decode("utf-8", "ignore")
    W = H = 0
    fps = 25.0
    total = 0
    # 逐条 Video 流解析；mkv 常内嵌封面图(attached pic / mjpeg)作额外视频流，
    # ffmpeg 解码默认选「面积最大」的流，这里也取最大，避免误用封面分辨率。
    best_area = -1
    for vm in re.finditer(r"Stream #\d+:\d+.*?:\s*Video:\s*(.*)", s):
        line = vm.group(1)
        if "attached pic" in line:   # 跳过封面图流
            continue
        dm = re.search(r"(\d{2,5})x(\d{2,5})", line)
        if not dm:
            continue
        w, h = int(dm.group(1)), int(dm.group(2))
        area = w * h
        if area > best_area:
            best_area = area
            W, H = w, h
            fm = re.search(r"(\d+(?:\.\d+)?)\s*fps", line)
            if fm:
                try:
                    fps = float(fm.group(1))
                except ValueError:
                    pass
    if W == 0:  # 兜底：宽松匹配
        m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", s)
        if m:
            W, H = int(m.group(1)), int(m.group(2))
    md = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", s)
    if md:
        dur = int(md.group(1)) * 3600 + int(md.group(2)) * 60 + float(md.group(3))
        total = int(dur * fps)
    am = re.search(r"Audio:\s*([A-Za-z0-9_]+)", s)
    acodec = am.group(1).lower() if am else ""
    return W, H, fps, total, acodec


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        log(f"ERR: {type(e).__name__}: {e}")
        sys.exit(1)
