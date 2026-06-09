# 把 pytorch_model.bin 转成 model.safetensors（避免 torch 安全限制）
import os
import sys

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))
CACHE_DIR    = os.path.join(PROJECT_ROOT, 'models_cache')

os.environ['HF_HOME'] = CACHE_DIR
for k in ('HTTP_PROXY','HTTPS_PROXY','http_proxy','https_proxy','ALL_PROXY','all_proxy'):
    os.environ.pop(k, None)
os.environ['NO_PROXY'] = '*'

import torch
from safetensors.torch import save_file


def convert(bin_path):
    if not os.path.isfile(bin_path):
        print(f"[skip] 找不到: {bin_path}")
        return False
    out_path = os.path.join(os.path.dirname(bin_path), 'model.safetensors')
    if os.path.isfile(out_path):
        print(f"[skip] 已存在: {out_path}")
        return True
    print(f"[load] {bin_path}")
    state = torch.load(bin_path, map_location='cpu', weights_only=False)
    if not isinstance(state, dict):
        print(f"[fail] 不是 state_dict: {type(state)}")
        return False
    # safetensors 不允许共享内存的 tensor，强制 contiguous + clone 打破内存共享
    cleaned = {}
    for k, v in state.items():
        if isinstance(v, torch.Tensor):
            cleaned[k] = v.detach().contiguous().clone()
    print(f"[save] {out_path}  ({len(cleaned)} tensors)")
    save_file(cleaned, out_path)
    print(f"[done] -> {out_path}")
    return True


def main():
    targets = []
    # 扫描 hub 目录下所有 m2m100 模型的 snapshot
    hub = os.path.join(CACHE_DIR, 'hub')
    for d in os.listdir(hub):
        if not d.startswith('models--facebook--m2m100'):
            continue
        snaps = os.path.join(hub, d, 'snapshots')
        if not os.path.isdir(snaps):
            continue
        for s in os.listdir(snaps):
            bin_p = os.path.join(snaps, s, 'pytorch_model.bin')
            if os.path.isfile(bin_p):
                targets.append(bin_p)

    if not targets:
        print('未找到任何 pytorch_model.bin，无需转换')
        return

    for p in targets:
        try:
            convert(p)
        except Exception as e:
            print(f"[error] {p}: {e}")
            import traceback; traceback.print_exc()


if __name__ == '__main__':
    main()
