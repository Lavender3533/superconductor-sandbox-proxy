#!/bin/bash
# SC 沙箱代理常驻脚本 — 尽最大努力在终端断开/沙箱重启后自愈
# 用法: bash run.sh
set -u
REPO="/workspace/superconductor-sandbox-proxy"
cd "$REPO" || exit 1

# --- 清理旧进程 ---
pkill -f "python3 server.py" 2>/dev/null
pkill -f "proxy-watchdog"    2>/dev/null
sleep 1

git pull 2>/dev/null

# --- 写 watchdog（每 15s 检查一次，挂了立刻拉起）---
cat > /workspace/proxy-watchdog.sh << 'WDOG'
#!/bin/bash
cd /workspace/superconductor-sandbox-proxy
while true; do
    if ! curl -sf http://localhost:8899/health >/dev/null 2>&1; then
        pkill -f "python3 server.py" 2>/dev/null
        sleep 1
        setsid nohup python3 server.py > /workspace/proxy.log 2>&1 < /dev/null &
        echo "[$(date)] proxy restarted, pid $!"
    fi
    sleep 15
done
WDOG
chmod +x /workspace/proxy-watchdog.sh

# --- 用 setsid 彻底脱离当前会话（比单纯 nohup 更硬，扛得住 session 清理）---
setsid nohup python3 server.py             > /workspace/proxy.log    2>&1 < /dev/null &
PROXY_PID=$!
setsid nohup bash /workspace/proxy-watchdog.sh > /workspace/watchdog.log 2>&1 < /dev/null &
WD_PID=$!

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

# --- 漂亮的启动面板 ---
echo ""
echo "╭───────────────────────────────────────────────────────────╮"
echo "│   Superconductor Sandbox Proxy                              │"
echo "├───────────────────────────────────────────────────────────┤"
printf   "│   代理状态   %-46s│\n" "$HSTATUS"
printf   "│   进程 PID   proxy=%-8s watchdog=%-19s│\n" "$PROXY_PID" "$WD_PID"
printf   "│   自启动     %-46s│\n" "$AUTOSTART"
echo "├───────────────────────────────────────────────────────────┤"
if [ -n "$TURL" ]; then
echo "│   你的 tunnel 地址（填进本地 ANTHROPIC_BASE_URL）：         │"
echo "│                                                             │"
printf   "│   %-58s│\n" "$TURL"
else
echo "│   ⚠ 未探测到，手动找：env | grep JUPYTER               │"
echo "│     把输出里的 8888- 换成 8899- 就是你的地址              │"
fi
echo "╰───────────────────────────────────────────────────────────╯"
echo "  关掉终端后：进程靠 setsid 常驻；沙箱重建则下次开终端自动复活。"
echo ""
