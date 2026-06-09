import os
import sys
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

# 设置模型缓存目录
download_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models_cache')

# 创建缓存目录（如果不存在）
os.makedirs(download_dir, exist_ok=True)

# 要下载的模型列表
models_to_download = [
    'facebook/m2m100_418M'  # 高精度多语言模型，支持英语到俄语的翻译
]

def download_model(model_name):
    print(f"\n=== 开始下载模型: {model_name} ===")
    print(f"下载目录: {download_dir}")
    
    try:
        # 下载分词器
        print(f"下载分词器...")
        tokenizer = AutoTokenizer.from_pretrained(model_name, cache_dir=download_dir)
        print(f"分词器下载成功: {model_name}")
        
        # 下载模型
        print(f"下载模型...")
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name, cache_dir=download_dir)
        print(f"模型下载成功: {model_name}")
        
        return True
        
    except Exception as e:
        print(f"下载失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=== 模型下载工具 ===")
    print(f"下载目录: {download_dir}")
    
    success_count = 0
    failure_count = 0
    
    for model_name in models_to_download:
        if download_model(model_name):
            success_count += 1
        else:
            failure_count += 1
    
    print(f"\n=== 下载完成 ===")
    print(f"成功下载: {success_count} 个模型")
    print(f"下载失败: {failure_count} 个模型")
    
    if failure_count > 0:
        print("\n警告: 有些模型下载失败，可能会影响翻译功能")
        return 1
    else:
        print("\n所有模型下载成功")
        return 0

if __name__ == '__main__':
    sys.exit(main())