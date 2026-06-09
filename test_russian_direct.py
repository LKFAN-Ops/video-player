import sys
import json
import os
from transformers import MarianTokenizer, MarianMTModel
import traceback

# 设置环境变量
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

def test_russian_translation():
    """直接测试俄语翻译模型的输出"""
    try:
        # 测试英语到俄语翻译
        print("=== 直接测试英语到俄语翻译 ===")
        en_ru_model_name = "Helsinki-NLP/opus-mt-en-ru"
        
        # 加载分词器和模型
        print(f"加载模型: {en_ru_model_name}")
        tokenizer = MarianTokenizer.from_pretrained(en_ru_model_name)
        
        try:
            model = MarianMTModel.from_pretrained(en_ru_model_name, use_safetensors=True)
            print("✅ 使用safetensors格式加载模型成功")
        except Exception as e:
            print(f"❌ 使用safetensors格式加载模型失败: {e}")
            print("尝试使用默认方式加载模型...")
            model = MarianMTModel.from_pretrained(en_ru_model_name)
            print("✅ 使用默认方式加载模型成功")
        
        # 测试翻译
        test_texts = [
            "I want you to see a lawyer",
            "It's too expensive",
            "Please don't go",
            "I love you",
            "Hello world"
        ]
        
        for text in test_texts:
            print(f"\n原文: {text}")
            
            # 进行翻译
            inputs = tokenizer([text], return_tensors="pt", padding=True)
            outputs = model.generate(**inputs, max_length=128, num_beams=1)
            translated = tokenizer.decode(outputs[0], skip_special_tokens=True)
            
            print(f"俄语翻译结果: {translated}")
            print(f"翻译结果类型: {type(translated)}")
            print(f"字符数量: {len(translated)}")
            print(f"字符编码: {[hex(ord(c)) for c in translated]}")
            print(f"UTF-8编码字节: {[hex(b) for b in translated.encode('utf-8')]}")
            
            # 测试编码转换
            try:
                encoded = translated.encode('utf-8')
                decoded = encoded.decode('utf-8')
                print(f"UTF-8编码/解码验证: {decoded}")
            except Exception as e:
                print(f"UTF-8编码/解码错误: {e}")
        
        print("\n✅ 测试完成")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    test_russian_translation()