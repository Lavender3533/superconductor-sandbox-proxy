#!/bin/bash
# SC 沙箱代理常驻脚本 — 自动识别 Anthropic / OpenAI 沙箱，起对应代理
# 用法: bash run.sh
set -u
REPO="/workspace/superconductor-sandbox-proxy"
cd "$REPO" || exit 1

# --- 检测沙箱类型：有 ANTHROPIC key 走 Claude，有 OPENAI key 走 GPT ---
have_anthropic=0; have_openai=0
[ -n "${ANTHROPIC:-}" ] && have_anthropic=1
[ -n "${OPENAI:-}" ]    && have_openai=1
grep -q '^ANTHROPIC=' /etc/environment 2>/dev/null && have_anthropic=1
grep -q '^OPENAI='    /etc/environment 2>/dev/null && have_openai=1

if [ "$have_anthropic" = 1 ]; then
    KIND="anthropic"; SERVER="server.py";        CLIENT="Claude Code"
elif [ "$have_openai" = 1 ]; then
    KIND="openai";    SERVER="server_openai.py"; CLIENT="Codex"
else
    echo "!! 没检测到 ANTHROPIC 或 OPENAI key，无法确定沙箱类型"; exit 1
fi

# --- 清理旧进程 ---
pkill -f "python3 server.py"        2>/dev/null
pkill -f "python3 server_openai.py" 2>/dev/null
pkill -f "proxy-watchdog"           2>/dev/null
sleep 1

git pull 2>/dev/null

# --- 写 watchdog（每 15s 检查一次，挂了立刻拉起，起的是检测到的 SERVER）---
cat > /workspace/proxy-watchdog.sh << WDOG
#!/bin/bash
cd /workspace/superconductor-sandbox-proxy
while true; do
    if ! curl -sf http://localhost:8899/health >/dev/null 2>&1; then
        pkill -f "python3 $SERVER" 2>/dev/null
        sleep 1
        setsid nohup python3 $SERVER > /workspace/proxy.log 2>&1 < /dev/null &
        echo "[\$(date)] proxy restarted, pid \$!"
    fi
    sleep 15
done
WDOG
chmod +x /workspace/proxy-watchdog.sh

# --- 心跳记录器：每 60s 往 /workspace/heartbeat.log 写一行时间戳 ---
# 沙箱被冻结时进程停摆，日志会出现"时间空洞"，恢复后看空洞就知道冻了多久。
cat > /workspace/heartbeat.sh << 'HB'
#!/bin/bash
LOG=/workspace/heartbeat.log
echo "=== heartbeat 启动 $(date '+%F %T') uptime=$(cat /proc/uptime|cut -d. -f1)s ===" >> "$LOG"
while true; do
    up=$(cat /proc/uptime 2>/dev/null | cut -d. -f1)
    echo "$(date '+%F %T')  uptime=${up}s" >> "$LOG"
    sleep 60
done
HB
chmod +x /workspace/heartbeat.sh
pkill -f "heartbeat.sh" 2>/dev/null; sleep 1

# --- 用 setsid 彻底脱离当前会话（比单纯 nohup 更硬，扛得住 session 清理）---
setsid nohup python3 "$SERVER"                 > /workspace/proxy.log    2>&1 < /dev/null &
PROXY_PID=$!
setsid nohup bash /workspace/proxy-watchdog.sh > /workspace/watchdog.log 2>&1 < /dev/null &
WD_PID=$!
setsid nohup bash /workspace/heartbeat.sh      > /dev/null              2>&1 < /dev/null &
HB_PID=$!

# --- 把自启动写进 ~/.bashrc：情况 B（沙箱重建）下，下次开终端自动复活 ---
AUTOSTART="未变动"
MARK="# >>> sc-proxy-autostart >>>"
if ! grep -qF "$MARK" ~/.bashrc 2>/dev/null; then
cat >> ~/.bashrc << 'BRC'
# >>> sc-proxy-autostart >>>
# 打开终端时若代理没在跑，自动拉起（沙箱重建自愈）
if ! curl -sf http://localhost:8899/health >/dev/null 2>&1; then
    ( cd /workspace/superconductor-sandbox-proxy 2>/dev/null && setsid nohup bash run.sh >/workspace/autostart.log 2>&1 < /dev/null & )
fi
# <<< sc-proxy-autostart <<<
BRC
AUTOSTART="已写入 ~/.bashrc"
fi

sleep 2
HEALTH=$(curl -s http://localhost:8899/health 2>/dev/null)
[ "$HEALTH" = "ok" ] && HSTATUS="[OK] 运行中" || HSTATUS="[!!] 未就绪 ($HEALTH)"

# --- 自动探测本沙箱的 tunnel URL ---
# 关键：Runloop 把 Jupyter 通过 AGENT_JUPYTER_HOST=8888-<token>.tunnel.runloop.ai 暴露出来，
# 同一沙箱的 8899 端口共用同一个 <token>，只要把 8888 换成 8899 即可。
JHOST="${AGENT_JUPYTER_HOST:-}"
if [ -z "$JHOST" ]; then
    JHOST=$(grep -oE 'AGENT_JUPYTER_HOST=[^ ]+' /etc/environment 2>/dev/null | head -1 | sed 's/AGENT_JUPYTER_HOST=//')
fi
if [ -n "$JHOST" ]; then
    TURL="https://$(echo "$JHOST" | sed 's/^8888-/8899-/')"
else
    TURL=""
fi

# --- 启动面板 ---
echo ""
echo "╭─────────────────────────────────────────────────────────────╮"
echo "│  Superconductor Sandbox Proxy                                 │"
echo "├─────────────────────────────────────────────────────────────┤"
printf   "│  沙箱类型   %-49s│\n" "$KIND  (客户端: $CLIENT)"
printf   "│  代理状态   %-49s│\n" "$HSTATUS"
printf   "│  进程 PID   %-49s│\n" "proxy=$PROXY_PID  watchdog=$WD_PID  自启动:$AUTOSTART"
echo "╰─────────────────────────────────────────────────────────────╯"
echo ""
if [ -n "$TURL" ]; then
    echo "  你的 tunnel 地址（复制到本地客户端）："
    echo "    $TURL"
    echo ""
    if [ "$KIND" = "anthropic" ]; then
        echo "  ▶ Claude Code / CC Switch 配置："
        echo "      ANTHROPIC_BASE_URL = $TURL"
        echo "      ANTHROPIC_AUTH_TOKEN = dummy"
        echo "      可用模型: claude-opus-4-8 / claude-sonnet-4-6 / claude-haiku-4-5"
    else
        echo "  ▶ Codex / OpenAI 客户端配置："
        echo "      base_url = $TURL/v1"
        echo "      api_key  = dummy"
        echo "      可用模型: gpt-5.5 / gpt-5 / o3 / o1 / gpt-4.1 / gpt-4o"
    fi
else
    echo "  ⚠ 未探测到 tunnel 地址，手动找: env | grep JUPYTER"
    echo "    把输出里的 8888- 换成 8899- 就是你的地址"
fi
echo ""
echo "  关掉终端后：进程靠 setsid 常驻；沙箱重建则下次开终端自动复活。"
echo "  查当前沙箱可用模型: python3 models.py"
echo ""
