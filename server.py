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

# 上游健康状态：搭真实 /v1/messages 流量的车被动记录，零额外开销。
# /status 接口返回它，守护软件据此判断"活着但上游挂了"的僵死态。
import time as _time
UPSTREAM = {'ok': None, 'ts': 0.0, 'code': 0}  # 被动:搭真实流量的车记录
PROBE = {'ok': None, 'ts': 0.0, 'code': 0}     # 主动:后台定时探测(补空闲盲区)
PROBE_INTERVAL = 45   # 秒;每隔这么久主动 ping 一次上游
PROBE_MODEL = 'claude-haiku-4-5'  # 用最便宜的模型探测


def _mark_upstream(ok, code=0):
    UPSTREAM['ok'] = bool(ok)
    UPSTREAM['ts'] = _time.time()
    UPSTREAM['code'] = code

# 当前代码版本（git commit 短哈希）——/version 接口返回，用来确认沙箱是否已 git pull 到最新
# [update-test 2026-07-03] 验证私有仓库 PAT 拉取 + 软件更新链路是否打通
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
        elif path == '/status':
            # 深度健康：进程活着 + 上游端到端是否真通。
            # 判定优先级：60s 内的真实流量最权威 > 后台主动探测 > 未知。
            # 这样即使空闲无流量，主动探测也能反映上游真实状态，杜绝"假活"。
            now = _time.time()
            traffic_age = (now - UPSTREAM['ts']) if UPSTREAM['ts'] else None
            probe_age = (now - PROBE['ts']) if PROBE['ts'] else None
            if traffic_age is not None and traffic_age <= 60:
                overall, source, code, age = UPSTREAM['ok'], 'traffic', UPSTREAM['code'], traffic_age
            elif probe_age is not None:
                overall, source, code, age = PROBE['ok'], 'probe', PROBE['code'], probe_age
            else:
                overall, source, code, age = None, 'none', 0, None
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({
                'alive': True,
                'upstream_ok': overall,
                'source': source,
                'last_code': code,
                'age_sec': round(age, 1) if age is not None else None,
            }).encode())
        elif path == '/v1/models':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            # app 的模型下拉直接读这个列表；实测 gateway 真实存在的模型放最前
            _ids = [
                'claude-fable-5', 'claude-fable-5[1m]',
                'claude-opus-4-8', 'claude-opus-4-8[1m]',
                'claude-sonnet-5', 'claude-sonnet-5[1m]',
                'claude-haiku-4-5',
                'claude-sonnet-4-6', 'claude-sonnet-4-6[1m]',
            ]
            self.wfile.write(json.dumps({
                'object': 'list',
                'data': [{'id': m, 'object': 'model', 'owned_by': 'anthropic'} for m in _ids]
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
                MAX_ATTEMPTS = 10
                for attempt in range(MAX_ATTEMPTS):
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
                            back = min(0.4 * (attempt + 1), 2.0)  # 渐进退避，最多 2s
                            print(f'[proxy] gateway {e.code}, retry {attempt+1}/{MAX_ATTEMPTS} (+{back}s)')
                            _t.sleep(back)
                            continue
                        raise
                    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
                        # 连接超时/被重置/DNS 抖动——沙箱网络抽风的常见形态，同样重试
                        last_err = e
                        back = min(0.4 * (attempt + 1), 2.0)
                        print(f'[proxy] gateway conn error ({e}), retry {attempt+1}/{MAX_ATTEMPTS} (+{back}s)')
                        _t.sleep(back)
                        continue
                if resp is None:
                    raise last_err

                _mark_upstream(resp.status < 500, resp.status)
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
                _mark_upstream(e.code < 500, e.code)
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(err_body if err_body else json.dumps({'error': f'gateway {e.code}'}).encode())
            except Exception as e:
                print(f'[proxy] Error: {e}')
                _mark_upstream(False, 502)
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


def upstream_prober():
    """后台每 PROBE_INTERVAL 秒主动 ping 一次上游,补足空闲时的健康盲区。
    只测'能不能连通':拿到任何 <500 的响应就算上游可达(哪怕 4xx),
    只有 5xx / 连接错误才判失败。用 haiku + max_tokens=1,成本可忽略,还兼做保活。"""
    time.sleep(5)
    ctx = ssl.create_default_context()
    while True:
        code = 0
        try:
            data = json.dumps({
                'model': PROBE_MODEL,
                'messages': [{'role': 'user', 'content': 'hi'}],
                'max_tokens': 1,
                'stream': False,
            }).encode()
            req = urllib.request.Request(GATEWAY + '/v1/messages', data=data, method='POST')
            req.add_header('Content-Type', 'application/json')
            req.add_header('anthropic-version', '2023-06-01')
            req.add_header('x-api-key', KEY)
            resp = urllib.request.urlopen(req, context=ctx, timeout=20)
            resp.read()
            code = resp.status
            PROBE['ok'] = True
        except urllib.error.HTTPError as e:
            code = e.code
            PROBE['ok'] = e.code < 500   # 4xx=上游可达;5xx=上游挂
        except Exception:
            PROBE['ok'] = False
        PROBE['ts'] = _time.time()
        PROBE['code'] = code
        print(f'[probe] upstream {"OK" if PROBE["ok"] else "FAIL"} (code {code})')
        time.sleep(PROBE_INTERVAL)


threading.Thread(target=self_test, daemon=True).start()
threading.Thread(target=upstream_prober, daemon=True).start()

# 多线程：单线程 HTTPServer 会被一个长流式请求占死，期间所有 /health /status 探测
# (guard 每10s + router 每22s + 客户端并发) 全排队超时 → 调度器误判节点死 → flapping/断流。
# 换 ThreadingHTTPServer 让探测与流式并发共存。Handler 只做每请求转发，
# 全局仅 PROBE(prober线程写、handler读，GIL下安全)，无共享写冲突。
server = http.server.ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
server.daemon_threads = True
print(f'[proxy] Listening on http://0.0.0.0:{PORT} (threaded)')
server.serve_forever()
