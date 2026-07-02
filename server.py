#!/usr/bin/env python3
"""Superconductor Sandbox Proxy - 直接调用 Runloop gateway.runloop.ai"""
import http.server
import json
import os
import ssl
import subprocess
import urllib.request
from urllib.parse import urlparse

PORT = 8899
GATEWAY = 'https://gateway.runloop.ai'
DEFAULT_MODEL = 'claude-opus-4-8'

# 当前代码版本（git commit 短哈希）——/version 接口返回，用来确认沙箱是否已 git pull 到最新
try:
    COMMIT = subprocess.check_output(
        ['git', 'rev-parse', '--short', 'HEAD'],
        cwd=os.path.dirname(os.path.abspath(__file__)),
        stderr=subprocess.DEVNULL).decode().strip()
except Exception:
    COMMIT = 'unknown'

# 读取 key
KEY = os.environ.get('ANTHROPIC') or os.environ.get('ANTHROPIC_API_KEY') or ''
if not KEY:
    try:
        with open('/etc/environment') as f:
            for line in f:
                if line.startswith('ANTHROPIC='):
                    KEY = line.strip().split('=', 1)[1].strip('"')
    except:
        pass

print(f'[proxy] Gateway: {GATEWAY}')
print(f'[proxy] Key: {len(KEY)} chars' if KEY else '[proxy] Key: NOT FOUND')

if not KEY:
    print('[proxy] ERROR: No ANTHROPIC key found!')
    exit(1)


class Handler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/health':
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'ok')
        elif path == '/version':
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(COMMIT.encode())
        elif path == '/v1/models':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                'object': 'list',
                'data': [
                    {'id': 'claude-opus-4-8', 'object': 'model', 'owned_by': 'anthropic'},
                    {'id': 'claude-opus-4-8[1m]', 'object': 'model', 'owned_by': 'anthropic'},
                    {'id': 'claude-opus-4-8[1M]', 'object': 'model', 'owned_by': 'anthropic'},
                    {'id': 'claude-sonnet-4-6', 'object': 'model', 'owned_by': 'anthropic'},
                    {'id': 'claude-sonnet-4-6[1m]', 'object': 'model', 'owned_by': 'anthropic'},
                    {'id': 'claude-sonnet-4-6[1M]', 'object': 'model', 'owned_by': 'anthropic'},
                    {'id': 'claude-opus-4-8-20250612', 'object': 'model', 'owned_by': 'anthropic'},
                    {'id': 'claude-sonnet-4-6-20250514', 'object': 'model', 'owned_by': 'anthropic'},
                ]
            }).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/v1/messages':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            print(f'[proxy] {self.path} ({length} bytes)')

            try:
                data = json.loads(body)
                original_model = data.get('model', '')

                # 策略：默认原样放行，绝不静默改模型。
                # 只对 REMAP 里“gateway 不认的老名字”做指定改名；其它模型全部透传，
                # 所以 claude-fable-5 / claude-opus-4-8 / claude-sonnet-5 等永远不会被误判成别的模型。
                # gateway 若真不认某个名字，会回明确的 404，而不是悄悄变成 opus。
                REMAP = {
                    'claude-sonnet-4-6': 'claude-opus-4-8',        # gateway 无此名，替代为 opus
                    'claude-sonnet-4-6-20250514': 'claude-opus-4-8',
                }
                clean_model = original_model.split('[')[0]         # 去掉 [1m]/[1M] 等后缀
                data['model'] = REMAP.get(clean_model) or clean_model or DEFAULT_MODEL
                if original_model != data['model']:
                    print(f'[proxy] Model: {original_model} -> {data["model"]}')

                body = json.dumps(data).encode()
                # 把 query string 一起带给 gateway（claude 会发 ?beta=true）
                url = GATEWAY + '/v1/messages'
                if parsed.query:
                    url += '?' + parsed.query
                beta = self.headers.get('anthropic-beta')
                anthropic_version = self.headers.get('anthropic-version', '2023-06-01')
                ctx = ssl.create_default_context()

                # 上游 gateway 会间歇性抽风（401/5xx）——在代理侧快速重试，
                # 不把抖动透给 claude（claude 默认重试慢、退避长）
                import time as _t
                resp = None
                last_err = None
                for attempt in range(6):
                    try:
                        req = urllib.request.Request(url, data=body, method='POST')
                        req.add_header('Content-Type', 'application/json')
                        req.add_header('anthropic-version', anthropic_version)
                        req.add_header('x-api-key', KEY)
                        if beta:
                            req.add_header('anthropic-beta', beta)
                        resp = urllib.request.urlopen(req, context=ctx, timeout=300)
                        break
                    except urllib.error.HTTPError as e:
                        last_err = e
                        # 401 和 5xx 是上游抖动，快速重试；4xx（非401）是真错，直接抛
                        if e.code == 401 or e.code >= 500:
                            print(f'[proxy] gateway {e.code}, retry {attempt+1}/6')
                            _t.sleep(0.4)
                            continue
                        raise
                if resp is None:
                    raise last_err

                self.send_response(resp.status)
                self.send_header('Content-Type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()

                while True:
                    chunk = resp.read(4096)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()

                print('[proxy] Done')
            except urllib.error.HTTPError as e:
                # gateway 返回了错误状态码——把它的原始 body 打出来并原样回传
                err_body = b''
                try:
                    err_body = e.read()
                except Exception:
                    pass
                print(f'[proxy] Gateway HTTP {e.code}: {err_body[:800].decode("utf-8","replace")}')
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(err_body if err_body else json.dumps({'error': f'gateway {e.code}'}).encode())
            except Exception as e:
                print(f'[proxy] Error: {e}')
                self.send_response(502)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        print(f'[http] {format % args}')


import threading
import time


def self_test():
    """启动后自动测试"""
    time.sleep(1)
    print('[test] Testing gateway directly...')
    models = ['claude-opus-4-8', 'claude-sonnet-4-6']
    for model in models:
        try:
            data = json.dumps({
                'model': model,
                'messages': [{'role': 'user', 'content': 'say hi'}],
                'max_tokens': 20,
                'stream': False
            }).encode()
            req = urllib.request.Request(GATEWAY + '/v1/messages', data=data, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('anthropic-version', '2023-06-01')
            req.add_header('x-api-key', KEY)
            ctx = ssl.create_default_context()
            resp = urllib.request.urlopen(req, context=ctx, timeout=30)
            body = resp.read().decode()
            print(f'[test] {model} -> {resp.status}: {body[:300]}')
        except urllib.error.HTTPError as e:
            body = ''
            try:
                body = e.read().decode()
            except:
                pass
            print(f'[test] {model} -> {e.code}: {body[:150]}')
        except Exception as e:
            print(f'[test] {model} -> Error: {e}')


threading.Thread(target=self_test, daemon=True).start()

server = http.server.HTTPServer(('0.0.0.0', PORT), Handler)
print(f'[proxy] Listening on http://0.0.0.0:{PORT}')
server.serve_forever()
