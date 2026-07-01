#!/bin/bash
# SC 沙箱代理常驻脚本 — 终端断开后继续运行
cd /workspace/superconductor-sandbox-proxy
pkill -f "python3 server.py" 2>/dev/null
pkill -f "proxy-watchdog" 2>/dev/null
sleep 1
git pull 2>/dev/null

# 写 watchdog 脚本
cat > /workspace/proxy-watchdog.sh << 'WDOG'
#!/bin/bash
cd /workspace/superconductor-sandbox-proxy
while true; do
    if ! curl -sf http://localhost:8899/health > /dev/null 2>&1; then
        echo "[$(date)] Proxy down, restarting..."
        pkill -f "python3 server.py" 2>/dev/null
        sleep 1
        nohup python3 server.py > /workspace/proxy.log 2>&1 &
        echo "[$(date)] Restarted, PID: $!"
    fi
    sleep 30
done
WDOG
chmod +x /workspace/proxy-watchdog.sh

# 用 nohup 启动 watchdog（独立于当前终端）
nohup bash /workspace/proxy-watchdog.sh > /workspace/watchdog.log 2>&1 &
echo "Watchdog started, PID: $!"

# 立即启动代理
nohup python3 server.py > /workspace/proxy.log 2>&1 &
echo "Proxy started, PID: $!"
sleep 2
echo "Health: $(curl -s http://localhost:8899/health)"
echo ""
echo "Done. You can close this terminal now."
