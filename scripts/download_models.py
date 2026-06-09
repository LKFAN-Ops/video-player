# 下载更高精度的 Whisper / 翻译模型到本项目 models_cache 目录
# 全程使用 hf-mirror.com 镜像；主动跳过系统代理，避免代理失效时连接被重置
import os
import sys
import time

# === 关键：在导入任何 requests/urllib3/huggingface_hub 之前先清空代理 ===
for k in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
          'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy'):
    os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'   # urllib3 看到这个会全程跳过代理

# 强制把所有 HuggingFace 缓存路径锁到项目内 models_cache
PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
CACHE_DIR    = os.path.join(PROJECT_ROOT, 'models_cache')
os.makedirs(CACHE_DIR, exist_ok=True)

os.environ['HF_HOME']                     = CACHE_DIR
os.environ['HF_HUB_CACHE']                = os.path.join(CACHE_DIR, 'hub')
os.environ['TRANSFORMERS_CACHE']          = CACHE_DIR
os.environ['HF_ENDPOINT']                 = 'https://hf-mirror.com'
os.environ['HF_HUB_ENABLE_HF_TRANSFER']   = '0'
os.environ['HF_HUB_DISABLE_TELEMETRY']    = '1'

print(f"[OK] 模型缓存目录: {CACHE_DIR}")
print(f"[OK] 镜像: {os.environ['HF_ENDPOINT']}")
print(f"[OK] 已禁用系统代理")
print()


def download_repo(repo_id, allow_patterns=None):
    from huggingface_hub import snapshot_download
    print(f"==> 开始下载: {repo_id}")
    t0 = time.time()
    try:
        local_dir = snapshot_download(
            repo_id=repo_id,
            cache_dir=os.path.join(CACHE_DIR, 'hub'),
            allow_patterns=allow_patterns,
            local_files_only=False,
            etag_timeout=30,
            max_workers=4,
        )
        cost = time.time() - t0
        print(f"   [DONE] {cost:.1f}s  -> {local_dir}")
        return True
    except Exception as e:
        print(f"   [FAIL] {e}")
        return False


def convert_bin_to_safetensors():
    """把下载下来的 m2m100 *.bin 权重转成 safetensors。
    旧版 torch(<2.6) 因 CVE-2025-32434 无法直接加载 .bin，必须转成 safetensors。
    直接调用 torch.load 不受该安全限制影响，因此这里能正常工作。"""
    try:
        import torch
        from safetensors.torch import save_file
    except Exception as e:
        print(f"[转换] 跳过（缺少 torch/safetensors）: {e}")
        return
    hub = os.path.join(CACHE_DIR, 'hub')
    if not os.path.isdir(hub):
        return
    for d in os.listdir(hub):
        if not d.startswith('models--facebook--m2m100'):
            continue
        snaps = os.path.join(hub, d, 'snapshots')
        if not os.path.isdir(snaps):
            continue
        for s in os.listdir(snaps):
            bin_p = os.path.join(snaps, s, 'pytorch_model.bin')
            out_p = os.path.join(snaps, s, 'model.safetensors')
            if not os.path.isfile(bin_p) or os.path.isfile(out_p):
                continue
            try:
                print(f"[转换] {bin_p} -> safetensors ...")
                state = torch.load(bin_p, map_location='cpu', weights_only=False)
                cleaned = {k: v.detach().contiguous().clone()
                           for k, v in state.items() if isinstance(v, torch.Tensor)}
                save_file(cleaned, out_p)
                print(f"[转换] 完成: {out_p}")
            except Exception as e:
                print(f"[转换] 失败 {bin_p}: {e}")


def main():
    targets = [
        # 实时翻译默认模型（m2m100 418M）：CPU 上单句约 0.2~0.5s，必须有。
        # 不加 allow_patterns，确保拿到权重文件（.safetensors 或 .bin）。
        ('facebook/m2m100_418M', None),
        # 高精度 Whisper（识别质量明显高于 base）
        ('Systran/faster-whisper-small', None),
        # 顶级精度 Whisper（更准但更慢，可选）
        ('Systran/faster-whisper-medium', None),
        # 大尺寸翻译模型（m2m100 1.2B）：质量更高但 CPU 上较慢，可选，
        # 仅当设置 MODEL_PRECISION=ultra 时才会启用。
        ('facebook/m2m100_1.2B', None),
    ]

    results = []
    for repo, patterns in targets:
        ok = download_repo(repo, patterns)
        results.append((repo, ok))

    # 下载完成后，自动把 m2m100 的 .bin 转成 safetensors，
    # 这样旧版 torch(<2.6) 也能直接加载，国内用户无需任何额外手动步骤。
    print()
    print("=== 转换权重为 safetensors（兼容旧版 torch）===")
    convert_bin_to_safetensors()

    print()
    print("=== 汇总 ===")
    for repo, ok in results:
        flag = '[OK]' if ok else '[FAIL]'
        print(f"  {flag}  {repo}")

    failed = [r for r, ok in results if not ok]
    if failed:
        print()
        print("有失败项，重新执行本脚本可断点续传：")
        for r in failed:
            print(f"  - {r}")
        sys.exit(1)
    print()
    print("全部完成。请重启播放器即可使用新模型。")


if __name__ == '__main__':
    main()
