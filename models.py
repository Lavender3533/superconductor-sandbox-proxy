#!/usr/bin/env python3
"""通用模型可用性探测：自动识别沙箱是 Anthropic 还是 OpenAI 网关，
逐个实测并输出可用清单。用法（SC 沙箱）: python3 models.py"""
import os, json, ssl, urllib.request

CTX = ssl.create_default_context()
A_KEY = os.environ.get('ANTHROPIC', '')
O_KEY = os.environ.get('OPENAI') or os.environ.get('OPENAI_API_KEY') or ''
A_URL = (os.environ.get('ANTHROPIC_BASE_URL') or 'https://gateway.runloop.ai').rstrip('/')
O_URL = (os.environ.get('OPENAI_URL') or os.environ.get('OPENAI_BASE_URL')
         or os.environ.get('OPENAI_API_BASE') or 'https://gateway.runloop.ai').rstrip('/')

ANTHROPIC_MODELS = ['claude-opus-4-8', 'claude-sonnet-4-6', 'claude-haiku-4-5',
                    'claude-opus-4-7', 'claude-sonnet-5', 'claude-opus-5']
OPENAI_MODELS = ['gpt-5.5', 'gpt-5', 'gpt-5-turbo', 'gpt-4.1', 'gpt-4o', 'o3', 'o1']

def http(url, path, hdr, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url + path, data=data, headers=hdr, method=('POST' if body else 'GET'))
    try:
        r = urllib.request.urlopen(req, context=CTX, timeout=40)
        return r.status, r.read().decode()
    except Exception as e:
        b = ''
        try: b = e.read().decode()
        except: pass
        return getattr(e, 'code', 'ERR'), b

def test_anthropic():
    print(f"\n===== Anthropic 网关 ({A_URL}) | key len={len(A_KEY)} =====")
    hdr = {'Content-Type': 'application/json', 'anthropic-version': '2023-06-01', 'x-api-key': A_KEY}
    for m in ANTHROPIC_MODELS:
        body = {'model': m, 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 10, 'stream': False}
        s, b = http(A_URL, '/v1/messages', hdr, body)
        rm = ''
        try: rm = json.loads(b).get('model', '')
        except: pass
        print(f"  {m:22} HTTP={s:<4} {'✓可用 '+rm if s==200 else '✗ '+b[:60]}")

def test_openai():
    print(f"\n===== OpenAI 网关 ({O_URL}) | key len={len(O_KEY)} =====")
    hdr = {'Content-Type': 'application/json', 'Authorization': f'Bearer {O_KEY}'}
    for m in OPENAI_MODELS:
        base = {'model': m, 'messages': [{'role': 'user', 'content': 'hi'}]}
        s, b = http(O_URL, '/v1/chat/completions', hdr, {**base, 'max_completion_tokens': 10})
        if s != 200 and 'max_completion_tokens' in b:
            s, b = http(O_URL, '/v1/chat/completions', hdr, {**base, 'max_tokens': 10})
        rm = ''
        try: rm = json.loads(b).get('model', '')
        except: pass
        print(f"  {m:14} HTTP={s:<4} {'✓可用 '+rm if s==200 else '✗ '+b[:60]}")

print(f"检测到的 key: ANTHROPIC={'有' if A_KEY else '无'}  OPENAI={'有' if O_KEY else '无'}")
if A_KEY: test_anthropic()
if O_KEY: test_openai()
if not A_KEY and not O_KEY:
    print("!! 没找到 key，看: env | grep -iE 'anthropic|openai'")
