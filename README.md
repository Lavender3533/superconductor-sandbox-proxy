# Superconductor Sandbox Proxy

把 Superconductor (SC) 沙箱里的 Claude 额度，通过一个小代理暴露成标准 Anthropic Messages API，
供本地 Claude Code / CC Switch 使用。

代理跑在 SC 沙箱内，直接调 `gateway.runloop.ai`，用的是**你自己 SC 账号的额度**。

---

## ⚠️ 部署前必读

- **每个人的 tunnel URL 不一样。** URL 格式是 `https://8899-<你沙箱的ID>.tunnel.runloop.ai`，
  ID 是你沙箱专属的。别人的 URL 你用不了，你必须找到自己的。
- **额度是你自己的。** 代理自动从沙箱 `/etc/environment` 读 `ANTHROPIC` gateway key，
  烧的是你 SC 账号的 $20 信用。
- **沙箱空闲会被 SC 冻结。** 你不在 SC 活动时，整个沙箱被挂起，tunnel 会返回 `bad_gateway`。
  这是 SC 平台机制，脚本无法绕过。重开 SC 终端会自动复活（见下）。

---

## 部署步骤

### 1. 在 SC 沙箱的 Terminal 里部署代理

```bash
cd /workspace
git clone https://github.com/Lavender3533/superconductor-sandbox-proxy.git
cd superconductor-sandbox-proxy
bash run.sh
```

看到 `Health: ok` 就成功了。`run.sh` 会：
- 用 `setsid` 后台常驻代理（听沙箱内 8899 端口）
- 起一个 watchdog，代理挂了 15 秒内自动重启
- 写进 `~/.bashrc`：下次开终端若代理没跑，自动拉起（应对沙箱重建）

### 2. 找到你自己的 tunnel URL

Runloop 会自动把沙箱的 8899 端口 tunnel 出去，URL 形如：

```
https://8899-XXXXXXXXXXXXXXXX.tunnel.runloop.ai
```

> **怎么找到 `XXXX` 部分？** 见下方「找 tunnel URL」一节。

拿到后先在**本地**验证它通不通（把下面 URL 换成你的）：

```bash
curl https://8899-XXXX.tunnel.runloop.ai/health
# 应返回: ok
```

### 3. 配置本地 Claude Code

把 `~/.claude/settings.json`（或 CC Switch 供应商配置）设成：

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://8899-XXXX.tunnel.runloop.ai",
    "ANTHROPIC_AUTH_TOKEN": "dummy",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    "DISABLE_TELEMETRY": "1",
    "CLAUDE_CODE_MAX_RETRIES": "3"
  },
  "skipDangerousModePermissionPrompt": true,
  "model": "opus[1m]"
}
```

- `ANTHROPIC_BASE_URL`：换成**你自己的** tunnel URL
- `ANTHROPIC_AUTH_TOKEN`：填 `dummy` 即可（真 key 在沙箱侧）
- `model`：`opus[1m]` 会被代理映射到 `claude-opus-4-8`

启动 Claude Code，发 `hi` 测试。

---

## 找 tunnel URL

> **TODO（待补充确认）**：SC / Runloop 里查看沙箱 8899 端口对外 tunnel 地址的具体位置。
> 可能来源：SC 界面的端口/预览面板、Runloop dashboard、或沙箱内某个环境变量/命令。

---

## 验证部署是否成功

在本地跑（换成你的 URL）：

```bash
curl -X POST "https://8899-XXXX.tunnel.runloop.ai/v1/messages?beta=true" \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -H "x-api-key: dummy" \
  -d '{"model":"claude-opus-4-8","messages":[{"role":"user","content":"hi"}],"max_tokens":20,"stream":false}'
```

返回带 `"content":[{"type":"text","text":"Hi..."}]` 就说明端到端通了。

---

## 常见问题

**`bad_gateway`** — 沙箱被 SC 冻结/重启了。回 SC 开个终端，`.bashrc` 会自动拉起代理；
或手动 `cd /workspace/superconductor-sandbox-proxy && bash run.sh`。

**`401 unauthorized`（偶发）** — 上游 gateway 间歇抖动。代理已内置快速重试消化，
客户端配 `CLAUDE_CODE_MAX_RETRIES=3` 双保险。

**报"模型不存在/没权限"** — 确认 `ANTHROPIC_BASE_URL` 是你的 tunnel URL 且没被
CC Switch 覆盖回它自己的端口。用 `cat ~/.claude/settings.json` 检查实际生效的值。

**代理老是断** — SC 空闲冻结沙箱导致，无法根治。只在你开着 SC 干活时可用。
```
