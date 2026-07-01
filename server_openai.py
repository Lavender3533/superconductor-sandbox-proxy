#!/usr/bin/env python3
"""GPT 沙箱代理 — 把本地 Codex 的 OpenAI 请求透明转发给 gateway.runloop.ai。
和 Anthropic 版不同：不改模型名、不做协议转换，原样转发 + 注入 OPENAI key。"""
import http.server
import json
import os
import ssl
import time
import urllib.request
from urllib.parse import urlparse

PORT = 8899
GATEWAY = 'https://gateway.runloop.ai'

# 读取 OPENAI key
KEY = os.environ.get('OPENAI') or os.environ.get('OPENAI_API_KEY') or ''
if not KEY:
    try:
        with open('/etc/environment') as f:
            for line in f:
                if line.startswith('OPENAI='):
                    KEY = line.strip().split('=', 1)[1].strip('"')
    except Exception:
        pass

print(f'[proxy-oai] Gateway: {GATEWAY}')
print(f'[proxy-oai] Key: {len(KEY)} chars' if KEY else '[proxy-oai] Key: NOT FOUND')
if not KEY:
    print('[proxy-oai] ERROR: No OPENAI key found!')
    exit(1)

CTX = ssl.create_default_context()


class Handler(http.server.BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.end_headers()

    def _forward(self, method):
        parsed = urlparse(self.path)
        if parsed.path == '/health':
            self.send_response(200); self.end_headers(); self.wfile.write(b'ok'); return

        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length else None
        url = GATEWAY + parsed.path + (('?' + parsed.query) if parsed.query else '')

        resp = None
        last_err = None
        for attempt in range(6):
            try:
                req = urllib.request.Request(url, data=body, method=method)
                req.add_header('Content-Type', 'application/json')
                req.add_header('Authorization', f'Bearer {KEY}')
                resp = urllib.request.urlopen(req, context=CTX, timeout=300)
                break
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code == 401 or e.code >= 500:
                    print(f'[proxy-oai] gateway {e.code}, retry {attempt+1}/6')
                    time.sleep(0.4)
                    continue
                # 4xx 真错，原样回传
                eb = b''
                try: eb = e.read()
                except Exception: pass
                self.send_response(e.code)
                self.send_header('Content-Type', 'application/json'); self.end_headers()
                self.wfile.write(eb or json.dumps({'error': f'gateway {e.code}'}).encode())
                return
            except Exception as e:
                last_err = e
                time.sleep(0.4)
        if resp is None:
            self.send_response(502); self.send_header('Content-Type', 'application/json')
            self.end_headers(); self.wfile.write(json.dumps({'error': str(last_err)}).encode())
            return

        self.send_response(resp.status)
        ct = resp.headers.get('Content-Type', 'application/json')
        self.send_header('Content-Type', ct)
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        while True:
            chunk = resp.read(4096)
            if not chunk:
                break
            self.wfile.write(chunk)
            self.wfile.flush()

    def do_GET(self):
        self._forward('GET')

    def do_POST(self):
        self._forward('POST')

    def log_message(self, fmt, *args):
        print(f'[http] {fmt % args}')


print(f'[proxy-oai] Listening on http://0.0.0.0:{PORT}')
http.server.HTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
