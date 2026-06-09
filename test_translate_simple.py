import json
import requests

# 测试文本
text = "You didn't hear that?"
target = "ru"

def test_online_translation():
    print(f"\n=== 测试在线翻译服务 ===")
    print(f"测试文本: '{text}'")
    print(f"目标语言: {target}")
    
    try:
        # 使用mymemory翻译服务（无需API密钥）
        import urllib.parse
        encoded_text = urllib.parse.quote(text)
        url = f"https://api.mymemory.translated.net/get?q={encoded_text}&langpair=en|{target}"
        
        print(f"请求URL: {url}")
        response = requests.get(url, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            
            if result.get('responseStatus') == 200 and result.get('responseData'):
                translated_text = result['responseData']['translatedText']
                print(f"翻译成功: '{text}' -> '{translated_text}'")
                return translated_text
            else:
                print(f"翻译失败: {result}")
                return None
        else:
            print(f"请求失败，状态码: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"在线翻译测试失败: {e}")
        return None

def main():
    print("=== 简单翻译测试工具 ===")
    
    # 首先尝试在线翻译
    translated_text = test_online_translation()
    
    if translated_text:
        print(f"\n=== 测试完成 ===")
        print(f"翻译结果: '{text}' -> '{translated_text}'")
        return 0
    else:
        print(f"\n=== 测试失败 ===")
        print(f"无法获取翻译结果")
        return 1

if __name__ == '__main__':
    exit(main())