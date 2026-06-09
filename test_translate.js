const fetch = require('node-fetch');

async function testTranslation() {
  console.log('测试俄语翻译功能');
  
  try {
    // 测试文本
    const text = "You didn't hear that?";
    
    // 尝试调用翻译服务
    const response = await fetch('http://localhost:8000/translate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        items: [{ text: text }],
        target: 'ru'
      })
    });
    
    if (!response.ok) {
      throw new Error(`HTTP错误! 状态: ${response.status}`);
    }
    
    const result = await response.json();
    console.log('翻译结果:', result);
    
    if (result && result.ok && result.items && result.items.length > 0) {
      console.log('翻译成功:', text, '->', result.items[0].text);
    } else {
      console.error('翻译失败:', result);
    }
    
  } catch (error) {
    console.error('测试失败:', error);
  }
}

testTranslation();