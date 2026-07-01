#!/usr/bin/env python3
"""
通过 SC 的 22222 终端 WebSocket 唤醒沙箱并起代理。
流程：调 terminal.json 拿 url+token -> 连 WS(这一步唤醒 VM) -> 发 bash run.sh -> server.py 起来 -> 8899 活
用法: python ws_wake.py <terminal.json_url> <cookie_file> <tunnel_8899_url>
"""
import sys, json, time, ssl, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import websocket  # websocket-client

TJSON = sys.argv[1]
COOKIE = open(sys.argv[2]).read().strip()
TUNNEL = sys.argv[3]

def get_terminal():
    req = urllib.request.Request(TJSON, headers={
        'accept': '*/*',
        'cookie': COOKIE,
        'referer': TJSON.rsplit('/', 1)[0],
    })
    d = json.loads(urllib.request.urlopen(req, timeout=25).read())
    return d

def health():
    try:
        return urllib.request.urlopen(TUNNEL + '/health', timeout=10).read().decode()
    except Exception as e:
        return f'ERR({e})'

print('[1] 反复调 terminal.json 唤醒 VM 直到 ready...')
url = None
for i in range(20):
    info = get_terminal()
    url = info['url']
    print(f'    尝试 {i+1}: ready = {info.get("ready")}')
    if info.get('ready'):
        break
    time.sleep(6)

# http(s) -> ws(s)
ws_url = url.replace('https://', 'wss://').replace('http://', 'ws://')

print('[2] 连 WebSocket(带重试，等 VM 隧道就绪)...')
ws = None
for i in range(15):
    try:
        ws = websocket.create_connection(
            ws_url,
            sslopt={'cert_reqs': ssl.CERT_NONE},
            timeout=30,
            http_proxy_host=None,
        )
        print(f'    WS 连上了 (第 {i+1} 次)')
        break
    except Exception as e:
        print(f'    握手失败 {i+1}: {str(e)[:60]}')
        time.sleep(5)
if ws is None:
    print('    !! WS 始终连不上，VM 可能未完全就绪，退出')
    sys.exit(1)

# 等 shell 提示符
time.sleep(2)
try:
    ws.settimeout(3)
    banner = ws.recv()
    print('    banner:', repr(banner)[:120])
except Exception:
    pass

print('[3] 发命令: cd 项目 && bash run.sh')
cmd = 'cd /workspace/superconductor-sandbox-proxy 2>/dev/null && bash run.sh\n'
ws.send(cmd)

# 读几秒输出
print('[4] 读终端输出(8秒)...')
ws.settimeout(2)
buf = ''
end = time.time() + 8
while time.time() < end:
    try:
        data = ws.recv()
        if isinstance(data, bytes):
            data = data.decode('utf-8', 'replace')
        buf += data
    except Exception:
        pass
print('---- 终端输出 ----')
print(buf[-800:])
print('------------------')

ws.close()

print('[5] 等 6s 后探 8899...')
for i in range(6):
    h = health()
    print(f'    探 {i+1}: 8899 = {h}')
    if h == 'ok':
        print('    *** 8899 活了！唤醒+起代理 全自动成功 ***')
        break
    time.sleep(5)
