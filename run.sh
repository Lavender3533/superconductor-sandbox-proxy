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
echo "Proxy started, pid $!"
setsid nohup bash /workspace/proxy-watchdog.sh > /workspace/watchdog.log 2>&1 < /dev/null &
echo "Watchdog started, pid $!"

# --- 把自启动写进 ~/.bashrc：情况 B（沙箱重建）下，下次开终端自动复活 ---
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
echo "autostart 已写入 ~/.bashrc"
fi

sleep 2
echo "Health: $(curl -s http://localhost:8899/health)"
echo "Done. 关掉终端后：情况A靠 setsid 常驻；情况B下次开终端自动复活。"
