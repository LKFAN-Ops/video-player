import sys
import subprocess

def check_python_module(module_name):
    """检查Python模块是否已安装"""
    try:
        __import__(module_name)
        return True
    except ImportError:
        return False

def check_python_version():
    """检查Python版本"""
    print(f"Python版本: {sys.version}")
    return sys.version_info.major >= 3 and sys.version_info.minor >= 8

def check_transformers():
    """检查Transformers库是否已安装"""
    if check_python_module('transformers'):
        import transformers
        print(f"Transformers库已安装，版本: {transformers.__version__}")
        return True
    else:
        print("Transformers库未安装")
        return False

def check_torch():
    """检查PyTorch库是否已安装"""
    if check_python_module('torch'):
        import torch
        print(f"PyTorch库已安装，版本: {torch.__version__}")
        print(f"CUDA可用: {torch.cuda.is_available()}")
        return True
    else:
        print("PyTorch库未安装")
        return False

def check_requests():
    """检查Requests库是否已安装"""
    if check_python_module('requests'):
        import requests
        print(f"Requests库已安装，版本: {requests.__version__}")
        return True
    else:
        print("Requests库未安装")
        return False

def main():
    print("=== 检查翻译服务依赖 ===")
    
    # 检查Python版本
    if not check_python_version():
        print("警告: Python版本可能太低，需要3.8或更高版本")
    
    print()
    
    # 检查必要的库
    transformers_installed = check_transformers()
    torch_installed = check_torch()
    requests_installed = check_requests()
    
    print()
    
    # 总结
    if transformers_installed and torch_installed:
        print("✅ 所有必要的库都已安装")
        return 0
    else:
        print("❌ 缺少必要的库")
        if not transformers_installed:
            print("   请安装Transformers库: pip install transformers")
        if not torch_installed:
            print("   请安装PyTorch库: pip install torch")
        return 1

if __name__ == '__main__':
    sys.exit(main())