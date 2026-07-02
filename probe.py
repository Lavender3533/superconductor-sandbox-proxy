#!/usr/bin/env python3
"""直连 gateway.runloop.ai 逐个实测模型是否真实可用。
gateway 是内网(私有IP)，只能在 SC/Runloop 沙箱里跑。
用法（在沙箱里）:
    python3 probe.py                      # 用沙箱自带的 ANTHROPIC key
    GW_KEY='gws_xxx' python3 probe.py     # 用朋友给的 gateway key 测（比如测 Fable 5）
"""
import os, json, ssl, urllib.request

K = os.environ.get('GW_KEY') or os.environ.get('ANTHROPIC', '')
CTX = ssl.create_default_context()

# 要测的模型：Fable 5 各种可能写法 + 已知真实做对照
# 判读：返回 model == 请求的名字 => 真实可用；返回变成别的名字(如 opus-4-8) => gateway 不认，被替换
MODELS = [
    # ---- Fable 5 各种命名猜测 ----
    'claude-fable-5',
    'fable-5',
    'claude-fable-5-latest',
    'claude-fable-5-20260101',
    'claude-fable',
    'fable',
    'claude-fable-5[1m]',
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
def core(name):  # 去掉后缀/日期，取可比对的核心
    return name.split('[')[0].replace('-latest', '').rstrip('-0123456789').lower()

for m in MODELS:
    s, rm, t = call(m)
    if s != 200:
        ok = '✗不存在' if s in (404, 400) else f'?({s})'
    elif core(rm) == core(m) or rm.lower() == m.lower():
        ok = '✓真实可用'
    else:
        ok = f'⚠被替换成 {rm}（说明 gateway 不认这个名）'
    print(f"{m:32} {str(s):5} {str(rm):22} {ok}  {t}")
