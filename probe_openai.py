#!/usr/bin/env python3
"""探测 OpenAI 类网关：自动读环境变量里的 key/url，试 chat/completions 和 /v1/models。
用法（SC 沙箱）: python3 probe_openai.py"""
import os, json, ssl, urllib.request

CTX = ssl.create_default_context()

# 自动找 key 和 url
KEY = os.environ.get('OPENAI') or os.environ.get('OPENAI_API_KEY') or ''
URL = (os.environ.get('OPENAI_URL') or os.environ.get('OPENAI_BASE_URL')
       or os.environ.get('OPENAI_API_BASE') or '').rstrip('/')

print(f"key: {KEY[:8]}... (len={len(KEY)})")
print(f"url: {URL}\n")

if not URL:
    print("!! 没找到 OPENAI_URL，请手动看: env | grep -i openai")
    raise SystemExit

def call(path, body=None, auth_bearer=True):
    hdr = {'Content-Type': 'application/json'}
    hdr['Authorization' if auth_bearer else 'x-api-key'] = (f'Bearer {KEY}' if auth_bearer else KEY)
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(URL + path, data=data, headers=hdr, method=('POST' if body else 'GET'))
    try:
        r = urllib.request.urlopen(req, context=CTX, timeout=40)
        return r.status, r.read().decode()[:600]
    except Exception as e:
        b = ''
        try: b = e.read().decode()[:300]
        except: pass
        return getattr(e, 'code', 'ERR'), b

# 1) 列模型
print("=== GET /v1/models ===")
s, body = call('/v1/models')
print(f"HTTP {s}")
ids = []
try:
    ids = [m['id'] for m in json.loads(body).get('data', [])]
    print('\n'.join(ids) if ids else body)
except Exception:
    print(body)

# 2) chat/completions 实测：优先用列出的模型，否则试常见名
print("\n=== POST /v1/chat/completions (逐个实测) ===")
test = ids[:12] if ids else ['gpt-5.5', 'gpt-5', 'gpt-4o', 'gpt-4.1', 'o3']
for m in test:
    s, b = call('/v1/chat/completions',
                {'model': m, 'messages': [{'role': 'user', 'content': 'hi'}], 'max_tokens': 10})
    tag = 'OK' if s == 200 else 'x'
    # 尝试抽取返回的 model 字段
    rm = ''
    try: rm = json.loads(b).get('model', '')
    except Exception: pass
    print(f"{m:22} HTTP={s:<4} {tag}  model={rm}  {b[:90]}")
