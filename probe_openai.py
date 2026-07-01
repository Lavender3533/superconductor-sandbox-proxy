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

# 1) 列模型（只打印含 gpt/o 的，太多了过滤下）
print("=== GET /v1/models (gpt/o 系列) ===")
s, body = call('/v1/models')
print(f"HTTP {s}")
ids = []
try:
    ids = [m['id'] for m in json.loads(body).get('data', [])]
    gpts = [i for i in ids if i.startswith(('gpt-5', 'gpt-4', 'o1', 'o3', 'o4'))]
    print('\n'.join(sorted(gpts)) if gpts else body[:400])
    print(f"...(共 {len(ids)} 个模型)")
except Exception:
    print(body)

# 2) chat/completions 实测：新模型用 max_completion_tokens，老模型用 max_tokens
print("\n=== POST /v1/chat/completions (逐个实测，自动适配参数) ===")
test = ['gpt-5.5', 'gpt-5', 'gpt-5-turbo', 'gpt-4.1', 'gpt-4o', 'o3', 'o1']
for m in test:
    # 新模型(gpt-5*/o*)不支持 max_tokens，改用 max_completion_tokens
    base = {'model': m, 'messages': [{'role': 'user', 'content': 'Reply with just your exact model name.'}]}
    s, b = call('/v1/chat/completions', {**base, 'max_completion_tokens': 30})
    if s != 200 and 'max_completion_tokens' in b:
        s, b = call('/v1/chat/completions', {**base, 'max_tokens': 30})
    rm, txt = '', ''
    try:
        j = json.loads(b); rm = j.get('model', '')
        txt = j['choices'][0]['message']['content'][:50]
    except Exception:
        txt = b[:80]
    tag = 'OK真实' if s == 200 else 'x'
    print(f"{m:14} HTTP={s:<4} {tag}  返回model={rm}  {txt}")
