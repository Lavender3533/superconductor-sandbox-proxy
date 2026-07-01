const express = require('express');
const https = require('https');

const PORT = 9090;
const SC = 'https://www.superconductor.com';
const RUNLOOP_KEY = 'gws_6utbJSKdN7vRZ4KwxD0fmMidPVhrbRtHODt9Xr7kbMnfkxFhm2FUap7msxgkT9xl8lp0ZrmjPP5ydG3hnhLJwKSycNSJAtIMZSct0MmgKNYY4kR15PhETlLVmkZ3jLTRBJEPq2w6xPevWjZpJT1b4OTZtVReO0hAOG7odxXQRnFw48VZrL8sv6qPfqdewKCmigUY0CP6F26IQOYHiqWCfPC4G5fZcLbQ9NPmCEM03gSKTUGlOCN1ExXtSS5t8a5y1Dk3Czl5itLYjK5baAZlzt9n9XU5L3hoe4bJh0L4HSRPZVE8TsrwacWUIyNp';

let COOKIE = '_twpid=tw.1782854565871.321650187223292225; sc_session_token_production=nXjIa6%2FBBm4A2AnqPjmGyyUBnSjMtsBnBT0cxkufNZXE2Se5KgPB%2F9FjviC8mNRBu6Pmiz0CwB2V2NVNdbHyjXsxs5UyMJmuj9FG9EppCGOE2U%2FvLV5C2yrKxc60ewcWRnshkc8vQ48YiEKaGg%3D%3D--XI8D8ubOXlkoTWg8--fm9dhDFNS%2Fh7PEsdtJ6XYw%3D%3D; last_workspace_id=gCQMrnT6DwJM; _superconductor_session=8jeNCfqKH603%2FBNcqgoH7qtnCv98vws3LDzuuVThQ4cKXvSAH0Cl08RSTysni8Kkur%2FV8TgMImimrBib56pXhyWJ7nSpXzDg5wzsFjWBYqULmWQflAMU17RqwT138j1U7ZYI7KdITAcCYlkODvdcInlBiFGZ178Mifi0VKUVCTam6qdOn8kT53tGcdSzqoBFtAq5Wrodztw4z98UNJDYoVVe6mveJt8ADl91SjhH51jkiCNzSbb6qkXl68dFpPTrKfZja8DYyAqKlEU7u4fdTOCMrXPrDngqQ2NV025e8a4zam53v7dxYU9pCJ59TzbujOhjL90kQsJVw0iv43LFrMWcwOx1JnP5FAPnOA%2BhrHRnh%2F75phVCVmzpMG1TcLPyUhVDgbqbHXZzlZ5sHQVbZf7IP4EU%2FJPdMHNChtL9qTG9eiruhx7xXBAVkgNuuKsf8JVOjPJvEW28KrUcSGIdE5YbPyksit56eoCkHR0uU7WBC31FgSZ3--RtfBcPnXK00ePqxz--OqE3uhL1VFrbkDPUb5kMvg%3D%3D';
let CSRF = '';
let convId = 'HTJCtDcc6kWH';
let implUrl = '/tickets/F9PNJqqjKDHW/implementations/cTmFbK8tCfLB';

function scReq(method, path, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, SC);
    const h = { Cookie: COOKIE, 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/149.0.0.0 Safari/537.36', Accept: 'text/html, application/xhtml+xml' };
    if (CSRF) h['X-CSRF-Token'] = CSRF;
    if (body) { h['Content-Type'] = 'application/x-www-form-urlencoded'; h['X-Requested-With'] = 'XMLHttpRequest'; h['X-Turbo-Request-Id'] = Math.random().toString(36).slice(2)+Date.now().toString(36); h.Origin = SC; h.Referer = SC + path; }
    const req = https.request({ hostname: url.hostname, path: url.pathname + url.search, method, headers: h }, res => {
      const sc = res.headers['set-cookie'];
      if (sc) sc.forEach(c => { const m = c.match(/_superconductor_session=([^;]+)/); if (m) COOKIE = COOKIE.replace(/_superconductor_session=[^;]+/, '_superconductor_session=' + m[1]); });
      if (res.statusCode === 302 && res.headers['location']) {
        const p = res.headers['location'].startsWith('http') ? new URL(res.headers['location']).pathname : res.headers['location'];
        return scReq('GET', p).then(resolve).catch(reject);
      }
      const chunks = [];
      res.on('data', d => chunks.push(d));
      res.on('end', () => resolve({ status: res.statusCode, body: Buffer.concat(chunks).toString() }));
    });
    req.on('error', reject);
    req.setTimeout(120000, () => { req.destroy(); reject(new Error('timeout')); });
    if (body) req.write(new URLSearchParams(body).toString());
    req.end();
  });
}

async function init() {
  const r = await scReq('GET', '/');
  const m = r.body.match(/csrf-token.*?content="([^"]+)"/);
  if (m) CSRF = m[1];
  console.log('[CSRF]', CSRF ? 'OK' : 'FAIL');
}

function html2text(html) {
  if (!html) return '';
  return html.replace(/<!DOCTYPE[^>]*>/gi,'').replace(/<\/?(html|body)[^>]*>/gi,'')
    .replace(/<pre[^>]*><code[^>]*>([\s\S]*?)<\/code><\/pre>/gi,'```\n$1\n```')
    .replace(/<code[^>]*>([\s\S]*?)<\/code>/gi,'`$1`')
    .replace(/<strong>([\s\S]*?)<\/strong>/gi,'**$1**').replace(/<em>([\s\S]*?)<\/em>/gi,'*$1*')
    .replace(/<li[^>]*>/gi,'- ').replace(/<\/li>/gi,'\n')
    .replace(/<h([1-6])[^>]*>([\s\S]*?)<\/h[1-6]>/gi,(_,l,t)=>'#'.repeat(+l)+' '+t+'\n')
    .replace(/<p[^>]*>/gi,'').replace(/<\/p>/gi,'\n').replace(/<br\s*\/?>/gi,'\n')
    .replace(/<[^>]+>/g,'').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&nbsp;/g,' ')
    .replace(/\n{3,}/g,'\n\n').trim();
}

function extractClaudeReply(html) {
  const re = /<div id="(message_[^"]+)" class="message group"><div class="w-full flex flex-col gap-2"[^>]*>[\s\S]*?<use href="#custom-claude"><\/use>[\s\S]*?<div class="[^"]*prose[^"]*"[^>]*>([\s\S]*?)<\/div>\s*<\/div>\s*<\/div>\s*<\/div>/g;
  let last = null, m;
  while ((m = re.exec(html)) !== null) last = { id: m[1], text: html2text(m[2]) };
  return last;
}

function flattenMessages(messages) {
  const parts = [];
  for (const msg of messages) {
    if (typeof msg.content === 'string') {
      parts.push(`${msg.role}: ${msg.content}`);
    } else if (Array.isArray(msg.content)) {
      for (const block of msg.content) {
        if (block.type === 'text') parts.push(`${msg.role}: ${block.text}`);
        else if (block.type === 'tool_use') parts.push(`${msg.role}: [tool: ${block.name}(${JSON.stringify(block.input).substring(0,500)})]`);
        else if (block.type === 'tool_result') parts.push(`${msg.role}: [result: ${(typeof block.content==='string'?block.content:JSON.stringify(block.content)).substring(0,500)}]`);
      }
    }
  }
  return parts.join('\n\n');
}

async function chat(systemPrompt, messages) {
  if (!CSRF) await init();
  let fullContent = '';
  if (systemPrompt) fullContent += systemPrompt + '\n\n';
  fullContent += flattenMessages(messages);
  if (fullContent.length > 30000) {
    const recent = messages.slice(-6);
    fullContent = (systemPrompt ? systemPrompt + '\n\n' : '') + flattenMessages(recent);
  }

  const before = await scReq('GET', implUrl);
  const beforeReply = extractClaudeReply(before.body);
  const beforeId = beforeReply?.id || '';

  await scReq('POST', `/conversations/${convId}/messages`, {
    authenticity_token: CSRF,
    'message[messageable_type]': 'ChatMessage',
    'message[shell_mode]': 'false',
    'message[messageable_attributes][content]': fullContent,
    button: ''
  });
  console.log('[Sent] Polling...');

  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 2000));
    const after = await scReq('GET', implUrl);
    const afterReply = extractClaudeReply(after.body);
    if (afterReply && afterReply.id !== beforeId && afterReply.text) {
      console.log(`[Reply] ${afterReply.text.length} chars`);
      return afterReply.text;
    }
    if (i % 5 === 0) console.log(`[Poll] ${i*2}s`);
  }
  throw new Error('Timeout 180s');
}

function makeSSE(res, reply, model) {
  const id = `msg_${Date.now()}`;
  const mdl = model || 'claude-opus-4-8-20250612';
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.write(`event: message_start\ndata: ${JSON.stringify({type:'message_start',message:{id,type:'message',role:'assistant',content:[],model:mdl,stop_reason:null,usage:{input_tokens:0,output_tokens:0}}})}\n\n`);
  res.write(`event: content_block_start\ndata: ${JSON.stringify({type:'content_block_start',index:0,content_block:{type:'text',text:''}})}\n\n`);
  for (let i = 0; i < reply.length; i += 30) {
    res.write(`event: content_block_delta\ndata: ${JSON.stringify({type:'content_block_delta',index:0,delta:{type:'text_delta',text:reply.substring(i,i+30)}})}\n\n`);
  }
  res.write(`event: content_block_stop\ndata: ${JSON.stringify({type:'content_block_stop',index:0})}\n\n`);
  res.write(`event: message_delta\ndata: ${JSON.stringify({type:'message_delta',delta:{stop_reason:'end_turn'},usage:{output_tokens:Math.ceil(reply.length/4)}})}\n\n`);
  res.write(`event: message_stop\ndata: ${JSON.stringify({type:'message_stop'})}\n\n`);
  res.end();
}

const app = express();
app.use(express.json({ limit: '10mb' }));

app.post('/v1/messages', async (req, res) => {
  try {
    const { model, messages, stream, system } = req.body;
    const rawModel = model || 'claude-opus-4-8';
    const scModel = rawModel.replace(/\[1M\]/i, '').replace(/\[1m\]/i, '');
    console.log(`\n[API] model=${rawModel} -> sc=${scModel} stream=${stream} msgs=${messages?.length}`);
    let sysPrompt = system ? (typeof system === 'string' ? system : system.map(s => s.text || s).join('\n')) : '';
    const reply = await chat(sysPrompt, messages);
    if (stream) makeSSE(res, reply, rawModel);
    else res.json({ id:`msg_${Date.now()}`, type:'message', role:'assistant', content:[{type:'text',text:reply}], model:rawModel, stop_reason:'end_turn', usage:{input_tokens:Math.ceil(JSON.stringify(messages).length/4),output_tokens:Math.ceil(reply.length/4)} });
  } catch (e) {
    console.error('[Error]', e.message);
    res.status(500).json({type:'error',error:{type:'api_error',message:e.message}});
  }
});

app.get('/v1/models', (_, res) => res.json({object:'list',data:[{id:'claude-opus-4-8-20250612',object:'model',owned_by:'anthropic'}]}));
app.get('/health', (_, res) => res.json({ok:true}));
app.listen(PORT, async () => { console.log(`\n[SC Proxy] http://localhost:${PORT}\n`); await init(); console.log('[Ready]\n'); });
