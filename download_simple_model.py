import os
import sys
from transformers import MarianTokenizer, MarianMTModel

# 设置模型缓存目录
download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models_cache')

# 创建缓存目录（如果不存在）
os.makedirs(download_dir, exist_ok=True)

# 下载一个基础的英语到俄语的翻译模型
model_name = 'Helsinki-NLP/opus-mt-en-ru'

def download_model():
    print(f"\n=== 开始下载模型: {model_name} ===")
    print(f"下载目录: {download_dir}")
    
    try:
        # 下载分词器
        print(f"下载分词器...")
        tokenizer = MarianTokenizer.from_pretrained(model_name, cache_dir=download_dir)
        print(f"分词器下载成功: {model_name}")
        
        # 下载模型
        print(f"下载模型...")
        model = MarianMTModel.from_pretrained(model_name, cache_dir=download_dir)
        print(f"模型下载成功: {model_name}")
        
        # 测试翻译功能
        print(f"测试翻译功能...")
        text = "You didn't hear that?"
        translated = model.generate(**tokenizer([text], return_tensors="pt", padding=True))
        result = tokenizer.batch_decode(translated, skip_special_tokens=True)
        print(f"翻译测试结果: {text} -> {result[0]}")
        
        return True
        
    except Exception as e:
        print(f"下载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=== 简单模型下载工具 ===")
    print(f"下载目录: {download_dir}")
    
    if download_model():
        print(f"\n=== 下载完成 ===")
        print(f"模型 {model_name} 下载成功！")
        return 0
    else:
        print(f"\n=== 下载失败 ===")
        print(f"模型 {model_name} 下载失败！")
        return 1

if __name__ == '__main__':
    sys.exit(main())