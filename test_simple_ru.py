import sys
import os
from transformers import MarianTokenizer, MarianMTModel

# 设置环境变量
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

def simple_test():
    """简单测试俄语翻译模型"""
    try:
        print("=== 简单俄语翻译测试 ===")
        
        # 加载模型
        model_name = "Helsinki-NLP/opus-mt-en-ru"
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        
        try:
            model = MarianMTModel.from_pretrained(model_name, use_safetensors=True)
            print("✅ 模型加载成功")
        except Exception as e:
            print(f"❌ 模型加载失败: {e}")
            return False
        
        # 简单测试
        text = "Hello world"
        print(f"原文: {text}")
        
        inputs = tokenizer([text], return_tensors="pt", padding=True)
        outputs = model.generate(**inputs, max_length=128, num_beams=1)
        translated = tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        print(f"翻译结果: {translated}")
        print(f"类型: {type(translated)}")
        print(f"长度: {len(translated)}")
        
        # 直接输出字符编码
        for i, c in enumerate(translated):
            print(f"字符 {i+1}: '{c}' (ord: {ord(c)}, hex: {hex(ord(c))})")
        
        return True
    
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = simple_test()
    sys.exit(0 if success else 1)