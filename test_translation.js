// 测试翻译服务是否正常工作
const https = require('https');
const http = require('http');

// 测试mymemory翻译服务
function testMymemory(text, src, target) {
    return new Promise((resolve, reject) => {
        const url = `https://api.mymemory.translated.net/get?q=${encodeURIComponent(text)}&langpair=${encodeURIComponent(src)}|${encodeURIComponent(target)}`;
        
        console.log('测试mymemory翻译服务:', url);
        
        https.get(url, (res) => {
            let data = '';
            
            res.on('data', (chunk) => {
                data += chunk;
            });
            
            res.on('end', () => {
                try {
                    const result = JSON.parse(data);
                    console.log('mymemory翻译结果:', result);
                    if (result.responseData && result.responseData.translatedText) {
                        resolve(result.responseData.translatedText);
                    } else {
                        reject(new Error('mymemory返回空结果'));
                    }
                } catch (e) {
                    reject(new Error(`解析mymemory响应失败: ${e.message}`));
                }
            });
        }).on('error', (e) => {
            reject(new Error(`mymemory请求失败: ${e.message}`));
        });
    });
}

// 测试libretranslate翻译服务
function testLibretranslate(text, src, target) {
    return new Promise((resolve, reject) => {
        const postData = JSON.stringify({
            q: text,
            source: src,
            target: target,
            format: 'text'
        });
        
        const options = {
            hostname: 'libretranslate.com',
            port: 443,
            path: '/translate',
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': Buffer.byteLength(postData)
            }
        };
        
        console.log('测试libretranslate翻译服务:', options.hostname + options.path);
        
        const req = https.request(options, (res) => {
            let data = '';
            
            res.on('data', (chunk) => {
                data += chunk;
            });
            
            res.on('end', () => {
                try {
                    const result = JSON.parse(data);
                    console.log('libretranslate翻译结果:', result);
                    if (result.translatedText) {
                        resolve(result.translatedText);
                    } else {
                        reject(new Error('libretranslate返回空结果'));
                    }
                } catch (e) {
                    reject(new Error(`解析libretranslate响应失败: ${e.message}`));
                }
            });
        });
        
        req.on('error', (e) => {
            reject(new Error(`libretranslate请求失败: ${e.message}`));
        });
        
        req.write(postData);
        req.end();
    });
}

// 运行测试
async function runTests() {
    console.log('开始测试翻译服务...');
    
    const testText = 'Hello, world!';
    const srcLang = 'en';
    const targetLang = 'ru';
    
    try {
        console.log('\n1. 测试mymemory翻译服务:');
        const mymemoryResult = await testMymemory(testText, srcLang, targetLang);
        console.log('✓ mymemory翻译成功:', testText, '->', mymemoryResult);
    } catch (e) {
        console.log('✗ mymemory翻译失败:', e.message);
    }
    
    try {
        console.log('\n2. 测试libretranslate翻译服务:');
        const libreResult = await testLibretranslate(testText, srcLang, targetLang);
        console.log('✓ libretranslate翻译成功:', testText, '->', libreResult);
    } catch (e) {
        console.log('✗ libretranslate翻译失败:', e.message);
    }
    
    console.log('\n测试完成!');
}

runTests();