#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试M2M100模型支持的语言代码
"""

import os
import sys

# 设置模型缓存目录
model_cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models_cache")
os.environ["HF_HOME"] = model_cache_dir

# 导入transformers库
try:
    from transformers import M2M100Tokenizer, M2M100ForConditionalGeneration
    print("✓ 成功导入transformers库")
except ImportError as e:
    print(f"✗ 无法导入transformers库: {e}")
    print("请运行: pip install transformers torch safetensors")
    sys.exit(1)

# 加载模型和分词器
try:
    print("\n正在加载模型和分词器...")
    tokenizer = M2M100Tokenizer.from_pretrained("facebook/m2m100_418M")
    model = M2M100ForConditionalGeneration.from_pretrained("facebook/m2m100_418M")
    print("✓ 成功加载模型和分词器")
    
    print("\n=== M2M100模型支持的语言代码 ===")
    
    # 打印所有支持的语言代码
    print("\n1. 支持的语言代码列表:")
    print(f"支持的语言数量: {len(tokenizer.lang_code_to_id)}")
    print("语言代码:")
    
    # 按字母顺序排序输出
    sorted_langs = sorted(tokenizer.lang_code_to_id.items(), key=lambda x: x[0])
    for lang_code, token_id in sorted_langs:
        print(f"  - {lang_code}")
    
    # 检查特定语言代码
    print("\n2. 检查特定语言代码:")
    check_langs = ["zh", "zh_CN", "zh-Hans", "ru", "en", "en_US"]
    for lang in check_langs:
        if lang in tokenizer.lang_code_to_id:
            print(f"  ✓ '{lang}' 存在，token ID: {tokenizer.lang_code_to_id[lang]}")
        else:
            print(f"  ✗ '{lang}' 不存在")
    
    # 测试翻译
    print("\n3. 测试俄语翻译:")
    
    # 英语到俄语
    print("\n   英语到俄语:")
    tokenizer.src_lang = "en"
    inputs = tokenizer("Hello, world!", return_tensors="pt")
    generated_tokens = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.lang_code_to_id["ru"]
    )
    translation = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    print(f"     原文: Hello, world!")
    print(f"     译文: {translation}")
    
    # 中文到俄语
    print("\n   中文到俄语:")
    tokenizer.src_lang = "zh"
    inputs = tokenizer("你好，世界！", return_tensors="pt")
    generated_tokens = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.lang_code_to_id["ru"]
    )
    translation = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    print(f"     原文: 你好，世界！")
    print(f"     译文: {translation}")
    
    # 俄语到中文
    print("\n   俄语到中文:")
    tokenizer.src_lang = "ru"
    inputs = tokenizer("Привет, мир!", return_tensors="pt")
    generated_tokens = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.lang_code_to_id["zh"]
    )
    translation = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    print(f"     原文: Привет, мир!")
    print(f"     译文: {translation}")
    
    # 俄语到英语
    print("\n   俄语到英语:")
    tokenizer.src_lang = "ru"
    inputs = tokenizer("Привет, мир!", return_tensors="pt")
    generated_tokens = model.generate(
        **inputs,
        forced_bos_token_id=tokenizer.lang_code_to_id["en"]
    )
    translation = tokenizer.batch_decode(generated_tokens, skip_special_tokens=True)[0]
    print(f"     原文: Привет, мир!")
    print(f"     译文: {translation}")
    
    print("\n✓ 测试完成！")
    
except Exception as e:
    print(f"\n✗ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
