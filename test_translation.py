import requests
import json
import time

def test_translation():
    print('测试俄语翻译功能')
    
    try:
        # 测试文本
        text = "You didn't hear that?"
        
        print(f"准备翻译文本: '{text}'")
        print(f"目标语言: ru")
        
        # 构建请求数据
        request_data = {
            'items': [{ 'text': text }],
            'target': 'ru'
        }
        
        print(f"请求数据: {json.dumps(request_data)}")
        
        # 尝试调用翻译服务
        print("发送请求到 http://localhost:8000/translate...")
        response = requests.post(
            'http://localhost:8000/translate',
            headers={
                'Content-Type': 'application/json'
            },
            data=json.dumps(request_data),
            timeout=30  # 设置30秒超时
        )
        
        print(f"收到响应，状态码: {response.status_code}")
        print(f"响应头: {dict(response.headers)}")
        
        if not response.ok:
            print(f"响应内容: {response.text}")
            raise Exception(f'HTTP错误! 状态: {response.status_code}, 内容: {response.text}')
        
        result = response.json()
        print(f"响应内容: {json.dumps(result, indent=2, ensure_ascii=False)}")
        
        if result and result['ok'] and result['items'] and len(result['items']) > 0:
            print(f'翻译成功: "{text}" -> "{result["items"][0]["text"]}"')
        else:
            print(f'翻译失败: {json.dumps(result, ensure_ascii=False)}')
        
    except requests.exceptions.RequestException as e:
        print(f'网络请求失败: {type(e).__name__}: {e}')
        import traceback
        traceback.print_exc()
    except json.JSONDecodeError as e:
        print(f'JSON解析失败: {e}')
        import traceback
        traceback.print_exc()
    except Exception as error:
        print(f'测试失败: {type(error).__name__}: {error}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print('开始测试...')
    test_translation()
    print('测试结束.')