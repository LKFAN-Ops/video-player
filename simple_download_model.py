#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简单的高精度翻译模型下载脚本
"""

import os
import sys
import time

# 设置模型缓存目录，避免占用C盘空间
# 可以通过环境变量HF_HOME自定义模型存储位置
model_cache_dir = os.environ.get("HF_HOME")
if not model_cache_dir:
    # 默认使用当前目录下的models_cache文件夹
    model_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models_cache")
    os.environ["HF_HOME"] = model_cache_dir
    print(f"[配置] 模型缓存目录设置为: {model_cache_dir}")

# 创建模型缓存目录（如果不存在）
os.makedirs(model_cache_dir, exist_ok=True)

# 设置镜像源以加快下载速度
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

print("=" * 60)
print("高精度翻译模型下载脚本")
print("模型名称: facebook/m2m100_418M")
print("预计大小: 约1.6GB")
print("=" * 60)
print()

# 先导入必要的库
try:
    from transformers import M2M100Tokenizer, M2M100ForConditionalGeneration
    print("✓ 成功导入transformers库")
except ImportError as e:
    print(f"✗ 无法导入transformers库: {e}")
    print("请运行: pip install transformers torch safetensors")
    sys.exit(1)

# 下载模型
try:
    print("\n1. 开始下载分词器...")
    start_time = time.time()
    tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
    print(f"✓ 分词器下载完成，耗时: {time.time() - start_time:.2f}秒")
    
    print("\n2. 开始下载模型...")
    print("注意: 模型较大，可能需要几分钟时间，请耐心等待...")
    start_time = time.time()
    model = M2M100ForConditionalGeneration.from_pretrained(
        "facebook/m2m100_418M",
        use_safetensors=True
    )
    print(f"✓ 模型下载完成，耗时: {time.time() - start_time:.2f}秒")
    
    print("\n3. 测试模型...")
    tokenizer.src_lang = "en"
    inputs = tokenizer("Hello, world!", return_tensors="pt")
    generated_tokens = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.lang_code_to_id["zh"]
    )
    translation = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    print(f"✓ 测试成功: 'Hello, world!' -> '{translation}'")
    
    print("\n" + "=" * 60)
    print("🎉 下载完成！")
    print("高精度模型已成功下载并可以使用。")
    print("=" * 60)
    
except Exception as e:
    print(f"\n✗ 错误: {e}")
    print(f"详细信息: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
