const http = require('http');
const https = require('https');
const net = require('net');

// 首先测试能否连接到 gateway
const g = process.env.ANTHROPIC_BASE_URL || 'https://gateway.runloop.ai';
const k = process.env.ANTHROPIC || process.env.ANTHROPIC_API_KEY || '';

console.log('Gateway:', g);
console.log('Key present:', k ? 'yes (len=' + k.length + ')' : 'no');

// 直接测试调用
function testCall() {
  return new Promise((resolve, reject) => {
    const u = new URL('/v1/messages', g);
    const body = JSON.stringify({
      model: 'claude-opus-4-8-20250612',
      messages: [{ role: 'user', content: 'say hi' }],
      max_tokens: 20,
      stream: true
    });
    console.log('Testing direct call to', u.href);
    const x = https.request({
      hostname: u.hostname,
      path: u.pathname,
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'anthropic-version': '2023-06-01',
        'x-api-key': k
      }
    }, p => {
      let data = '';
      p.on('data', d => { data += d.toString(); process.stdout.write('.'); });
      p.on('end', () => { console.log('\nResponse:', p.statusCode, data.substring(0, 500)); resolve(data); });
    });
    x.on('error', e => { console.log('Error:', e.message); reject(e); });
    x.setTimeout(15000, () => { x.destroy(); console.log('Timeout'); reject(new Error('timeout')); });
    x.write(body);
    x.end();
  });
}

// 也测试 TCP 连接
function testTCP() {
  return new Promise((resolve) => {
    const u = new URL(g);
    const sock = net.connect(443, u.hostname, () => {
      console.log('TCP connect to', u.hostname, ':443 OK');
      sock.destroy();
      resolve(true);
    });
    sock.on('error', e => { console.log('TCP error:', e.message); resolve(false); });
    sock.setTimeout(5000, () => { sock.destroy(); console.log('TCP timeout'); resolve(false); });
  });
}

(async () => {
  await testTCP();
  try { await testCall(); } catch (e) { console.log('Direct call failed:', e.message); }

  // 启动代理服务器
  const server = http.createServer((q, r) => {
    if (q.url === '/v1/messages' && q.method === 'POST') {
      let b = '';
      q.on('data', d => b += d);
      q.on('end', () => {
        const u = new URL('/v1/messages', g);
        const x = https.request({
          hostname: u.hostname, path: u.pathname, method: 'POST',
          headers: { 'Content-Type': 'application/json', 'anthropic-version': '2023-06-01', 'x-api-key': k }
        }, p => {
          r.writeHead(p.statusCode, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' });
          p.pipe(r);
        });
        x.on('error', e => { r.writeHead(500); r.end(e.message); });
        x.write(b); x.end();
      });
    } else if (q.url === '/health') {
      r.writeHead(200); r.end('ok');
    } else {
      r.writeHead(404); r.end('no');
    }
  });
  server.listen(8899, '0.0.0.0', () => console.log('Proxy on :8899'));
})();
