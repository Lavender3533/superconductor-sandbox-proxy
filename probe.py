#!/usr/bin/env python3
"""直连 gateway.runloop.ai 逐个实测模型是否真实可用。
用法（在 SC 沙箱里）: python3 probe.py
读取沙箱环境变量 ANTHROPIC 作为 key。"""
import os, json, ssl, urllib.request

K = os.environ.get('ANTHROPIC', '')
CTX = ssl.create_default_context()

# 要测的模型：GPT 系列各种写法 + Claude 对照
MODELS = [
    # ---- GPT 各种命名格式 ----
    'gpt-5.5',
    'gpt-5-5',
    'gpt-5.5-turbo',
    'gpt-5',
    'gpt-5-turbo',
    'gpt-4.5',
    'gpt-4o',
    'o3',
    'o1',
    # ---- Sonnet 5 再确认 ----
    'claude-sonnet-5',
    'claude-opus-5',
    # ---- 已知真实，做对照 ----
    'claude-opus-4-8',
    'claude-sonnet-4-6',
    'claude-haiku-4-5',
]

def call(m):
    body = json.dumps({
        'model': m,
        'messages': [{'role': 'user', 'content': 'Reply with just your exact model name.'}],
        'max_tokens': 30, 'stream': False,
    }).encode()
    req = urllib.request.Request('https://gateway.runloop.ai/v1/messages', data=body,
        headers={'Content-Type': 'application/json', 'anthropic-version': '2023-06-01', 'x-api-key': K},
        method='POST')
    try:
        r = urllib.request.urlopen(req, context=CTX, timeout=40)
        d = json.loads(r.read())
        return r.status, d.get('model', '?'), d['content'][0]['text'][:50].replace('\n', ' ')
    except Exception as e:
        b = ''
        try: b = e.read().decode()[:100]
        except: pass
        return getattr(e, 'code', 'ERR'), '-', b.replace('\n', ' ')

print(f"key length: {len(K)}\n")
print(f"{'请求的模型':32} {'HTTP':5} {'返回model':22} 说明")
print('-' * 90)
for m in MODELS:
    s, rm, t = call(m)
    ok = '✓真实' if s == 200 else ('✗不存在' if s in (404, 400) else '?')
    print(f"{m:32} {str(s):5} {str(rm):22} {ok}  {t}")
