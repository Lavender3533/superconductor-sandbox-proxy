#!/usr/bin/env python3
"""
gateway.runloop.ai 综合探测器（gateway 是内网私有IP，只能在 SC/Runloop 沙箱里跑）。

自动完成：
  1) 收集可用 key：沙箱自带 ANTHROPIC / OPENAI + 可选的外部 gateway key
  2) 对每把 key 自动尝试 (x-api-key / Bearer) × (messages / chat / responses)，
     用已知真实的对照模型确认哪种组合能认证
  3) 在能认证的组合上，逐个探测 Fable 5 的各种写法，比对返回 model 揪出 silent 替换

外部 key（朋友给的 gws_...）怎么给（任选其一，存一次之后可反复重跑）：
    echo 'gws_xxxxxx' > /workspace/gwkey.txt      # 推荐，控制台断了重跑不用再打
  或  export GW_KEY='gws_xxxxxx'

用法:  python3 probe.py
"""
import os, json, ssl, time, urllib.request, urllib.error

CTX = ssl.create_default_context()
GATEWAY = 'https://gateway.runloop.ai'


def read_external_key():
    k = os.environ.get('GW_KEY', '').strip()
    if k:
        return k
    for p in ('/workspace/gwkey.txt', os.path.expanduser('~/.gwkey')):
        try:
            with open(p) as f:
                k = f.read().strip()
                if k:
                    return k
        except Exception:
            pass
    return ''


def env_key(name):
    v = os.environ.get(name, '')
    if v:
        return v
    try:
        with open('/etc/environment') as f:
            for line in f:
                if line.startswith(name + '='):
                    return line.strip().split('=', 1)[1].strip('"')
    except Exception:
        pass
    return ''


def call(endpoint, auth, key, model, retries=2):
    """向 gateway 发一次请求。返回 (http_code, 返回的model, 文本/错误片段)。"""
    if endpoint == 'messages':
        path = '/v1/messages'
        payload = {'model': model, 'max_tokens': 20,
                   'messages': [{'role': 'user', 'content': 'reply your exact model name'}]}
    elif endpoint == 'chat':
        path = '/v1/chat/completions'
        payload = {'model': model, 'max_tokens': 20,
                   'messages': [{'role': 'user', 'content': 'reply your exact model name'}]}
    else:  # responses
        path = '/v1/responses'
        payload = {'model': model, 'max_output_tokens': 20, 'input': 'reply your exact model name'}

    body = json.dumps(payload).encode()
    headers = {'Content-Type': 'application/json'}
    if endpoint == 'messages':
        headers['anthropic-version'] = '2023-06-01'
    if auth == 'x-api-key':
        headers['x-api-key'] = key
    else:
        headers['Authorization'] = 'Bearer ' + key

    last = None
    for _ in range(retries):
        try:
            req = urllib.request.Request(GATEWAY + path, data=body, headers=headers, method='POST')
            r = urllib.request.urlopen(req, context=CTX, timeout=40)
            d = json.loads(r.read())
            rm = d.get('model', '?')
            txt = ''
            try:
                if endpoint == 'messages':
                    txt = d['content'][0]['text']
                elif endpoint == 'chat':
                    txt = d['choices'][0]['message']['content']
                else:
                    msg = [o for o in d.get('output', []) if o.get('type') == 'message']
                    txt = msg[0]['content'][0]['text'] if msg else json.dumps(d.get('output_text', ''))
            except Exception:
                pass
            return r.status, rm, (txt or '')[:45].replace('\n', ' ')
        except urllib.error.HTTPError as e:
            b = ''
            try:
                b = e.read().decode()[:80]
            except Exception:
                pass
            if e.code in (500, 502, 503, 429):   # 上游抖动，重试
                last = (e.code, '-', b.replace('\n', ' '))
                time.sleep(0.5)
                continue
            return e.code, '-', b.replace('\n', ' ')
        except Exception as e:
            last = ('ERR', '-', str(e)[:60])
            time.sleep(0.5)
    return last or ('ERR', '-', '?')


# 已知真实的对照模型：用来判断某种(端点,认证头)组合能不能认证
CONTROL = {'messages': 'claude-opus-4-8', 'chat': 'gpt-5.5', 'responses': 'gpt-5.5'}
# 要探的 Fable 5 各种写法（+ 顺带试 opus-5 / sonnet-5）
FABLE = ['claude-fable-5', 'fable-5', 'claude-fable-5-latest',
         'claude-fable-5-20260101', 'claude-fable', 'fable', 'claude-opus-5', 'claude-sonnet-5']


def looks_real(requested, returned):
    a = requested.split('[')[0].lower().rstrip('-0123456789').replace('-latest', '')
    b = (returned or '').lower()
    return b.startswith(a[:10]) or 'fable' in b if 'fable' in requested else b.startswith(a[:10])


# ---- 收集 key ----
KEYS = []
ext = read_external_key()
if ext:
    KEYS.append(('外部key', ext))
for envn, lbl in (('ANTHROPIC', '沙箱ANTHROPIC'), ('OPENAI', '沙箱OPENAI')):
    v = env_key(envn)
    if v:
        KEYS.append((lbl, v))

print('=== 收集到的 key ===')
for lbl, k in KEYS:
    print(f'  {lbl:16} {len(k)} chars  前缀 {k[:8]}…')
if not KEYS:
    print('  ⚠ 一把 key 都没有！先: echo \'gws_...\' > /workspace/gwkey.txt')
    raise SystemExit
if not ext:
    print('  (没读到外部 key；要测朋友那把: echo \'gws_...\' > /workspace/gwkey.txt 再重跑)')
print()

# ---- 步骤1：找每把 key 的正确用法 ----
print('=== 步骤1：探测每把 key 的正确用法（对照模型试认证）===')
print(f"{'key':16}{'端点':11}{'认证头':11}{'HTTP':6}{'返回model':20}说明")
print('-' * 92)
working = []
for lbl, k in KEYS:
    for ep in ('messages', 'chat', 'responses'):
        for auth in ('x-api-key', 'Bearer'):
            code, rm, txt = call(ep, auth, k, CONTROL[ep])
            if code == 200:
                note = '✓认证通过'
                working.append((lbl, k, ep, auth))
            elif code == 401:
                note = '✗ 401 认证头不对/无权限'
            elif code in (400, 404):
                note = f'✗ {code} {txt}'
            else:
                note = f'{code} {txt}'
            print(f"{lbl:16}{ep:11}{auth:11}{str(code):6}{str(rm):20}{note}")
print()

# ---- 步骤2：在能认证的组合上探 Fable 5 ----
print('=== 步骤2：在能认证的组合上探 Fable 5 ===')
if not working:
    print('  没有任何组合认证通过，无法测 Fable。确认 key 是否正确、是否在沙箱内网跑。')
else:
    print(f"{'key':16}{'端点':11}{'请求模型':26}{'HTTP':6}{'返回model':20}说明")
    print('-' * 100)
    for lbl, k, ep, auth in working:
        for m in FABLE:
            code, rm, txt = call(ep, auth, k, m)
            if code == 200 and looks_real(m, rm):
                note = '✓✓ 真实可用！'
            elif code == 200:
                note = f'⚠ 被替换成 {rm}（gateway 不认这名字）'
            elif code in (400, 404):
                note = '✗ 不存在'
            else:
                note = f'{code} {txt}'
            print(f"{lbl:16}{ep:11}{m:26}{str(code):6}{str(rm):20}{note}")
print()
print('=== 完成，把整个输出发我 ===')
