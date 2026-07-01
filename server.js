const express = require('express');
const https = require('https');

const PORT = 9090;
const TUNNEL_URL = 'https://8899-f9w6uga8u9mq62mlazus1pslbv0tuq2dsq0wtf99ekmri8f208g.tunnel.runloop.ai';

const ALL_MODELS = [
  'claude-opus-4-8', 'claude-opus-4-8[1m]', 'claude-opus-4-8[1M]',
  'claude-sonnet-4-6', 'claude-sonnet-4-6[1m]', 'claude-sonnet-4-6[1M]',
  'claude-opus-4-8-20250612', 'claude-sonnet-4-6-20250514',
  'claude-haiku-4-5-20251001', 'claude-fable-5',
];

function tunnelReq(method, path, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, TUNNEL_URL);
    const h = {
      'Content-Type': 'application/json',
      'anthropic-version': '2023-06-01',
      'x-api-key': 'dummy',
      ...headers,
    };
    if (body) {
      const b = typeof body === 'string' ? body : JSON.stringify(body);
      h['Content-Length'] = Buffer.byteLength(b);
    }
    const req = https.request({
      hostname: url.hostname,
      path: url.pathname + url.search,
      method,
      headers: h,
    }, res => {
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks), headers: res.headers }));
    });
    req.on('error', reject);
    req.setTimeout(300000, () => { req.destroy(); reject(new Error('timeout')); });
    if (body) req.write(typeof body === 'string' ? body : JSON.stringify(body));
    req.end();
  });
}

const app = express();
app.use(express.json({ limit: '10mb' }));

app.post('/v1/messages', async (req, res) => {
  const { model } = req.body;
  console.log(`[API] POST /v1/messages model=${model} stream=${req.body.stream}`);

  try {
    // 直接转发给 tunnel（tunnel 里 SC 代理会做模型映射）
    const r = await tunnelReq('POST', '/v1/messages', req.body);

    res.setHeader('Content-Type', r.headers['content-type'] || 'text/event-stream');
    res.setHeader('Cache-Control', 'no-cache');
    res.status(r.status);
    res.end(r.body);
  } catch (e) {
    console.error('[Error]', e.message);
    res.status(502).json({ type: 'error', error: { type: 'api_error', message: e.message } });
  }
});

app.get('/v1/models', (_, res) => res.json({
  object: 'list',
  data: ALL_MODELS.map(id => ({ id, object: 'model', owned_by: 'anthropic' })),
}));

app.get('/health', (_, res) => res.json({ ok: true }));

app.listen(PORT, () => {
  console.log(`\n[Local Proxy] http://localhost:${PORT}`);
  console.log(`[Tunnel] ${TUNNEL_URL}`);
  console.log('[Ready]\n');
});
