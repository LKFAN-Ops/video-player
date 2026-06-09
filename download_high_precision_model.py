#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接下载高精度翻译模型的脚本
无需运行完整的Electron应用程序即可预下载模型
"""

import os
import sys
import time
from transformers import M2M100Tokenizer, M2M100ForConditionalGeneration

# 设置模型名称
HIGH_PRECISION_MODEL = "facebook/m2m100_418M"

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
print(f"模型名称: {HIGH_PRECISION_MODEL}")
print(f"预计大小: 约1.6GB")
print("=" * 60)
print()

try:
    # 开始下载和加载分词器
    print("[1/2] 开始下载分词器...")
    start_time = time.time()
    tokenizer = M2M100Tokenizer.from_pretrained(HIGH_PRECISION_MODEL)
    tokenizer_time = time.time() - start_time
    print(f"✓ 分词器下载完成，耗时: {tokenizer_time:.2f}秒")
    print()
    
    # 开始下载和加载模型
    print("[2/2] 开始下载模型...")
    print("注意: 模型较大，可能需要几分钟时间，请耐心等待...")
    start_time = time.time()
    model = M2M100ForConditionalGeneration.from_pretrained(
        HIGH_PRECISION_MODEL,
        use_safetensors=True  # 使用safetensors格式加速下载和加载
    )
    model_time = time.time() - start_time
    print(f"✓ 模型下载完成，耗时: {model_time:.2f}秒")
    print()
    
    # 测试模型是否正常工作
    print("[3/3] 测试模型是否正常工作...")
    test_texts = [
        "Hello, how are you?",  # 英文
        "你好，你好吗？",        # 中文
        "Привет, как дела?"     # 俄语
    ]
    
    for text in test_texts:
        # 检测语言
        has_zh = any(0x4E00 <= ord(c) <= 0x9FFF for c in text)
        has_ru = any(0x0400 <= ord(c) <= 0x04FF for c in text)
        
        if has_zh:
            src_lang = "zh"
        elif has_ru:
            src_lang = "ru"
        else:
            src_lang = "en"
        
        # 设置源语言
        tokenizer.src_lang = src_lang
        
        # 翻译为中文
        inputs = tokenizer(text, return_tensors="pt")
        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.lang_code_to_id["zh"]
        )
        translation_zh = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
        
        # 翻译为俄语
        generated_tokens = model.generate(
            **inputs,
            forced_bos_token_id=tokenizer.lang_code_to_id["ru"]
        )
        translation_ru = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
        
        print(f"原文 ({src_lang}): {text}")
        print(f"译文 (中文): {translation_zh}")
        print(f"译文 (俄语): {translation_ru}")
        print()
    
    print("=" * 60)
    print("🎉 下载和测试完成！")
    print("高精度模型已成功下载并可以正常使用。")
    print("当您运行视频播放器应用程序时，它将自动使用这个高精度模型进行翻译。")
    print("=" * 60)
    
except KeyboardInterrupt:
    print("\n\n⚠️  下载被用户中断")
    sys.exit(1)
except Exception as e:
    print(f"\n\n❌ 下载或测试失败: {e}")
    print(f"详细错误信息: {str(e)}")
    print("\n请检查网络连接后重试。")
    sys.exit(1)
