#!/usr/bin/env python3
"""探测 SC 沙箱里有没有办法重置 Runloop idle timer / 控制 devbox 生命周期。
只读探测，不改任何东西。把输出全部发回给我。"""
import os, subprocess, json, glob

def sh(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception as e:
        return f"(err {e})"

print("=" * 60)
print("1) 有没有 runloop / devbox 相关的 CLI 命令")
print("=" * 60)
for c in ["runloop", "devbox", "rl", "runloopctl"]:
    p = sh(f"which {c} 2>/dev/null")
    print(f"  {c:12} -> {p or '(无)'}")

print()
print("=" * 60)
print("2) 环境变量里所有 runloop/devbox/idle 线索（脱敏）")
print("=" * 60)
for k, v in sorted(os.environ.items()):
    kl = k.lower()
    if any(t in kl for t in ("runloop", "devbox", "idle", "tunnel", "agent", "jupyter", "session")):
        vv = v if len(v) < 40 else v[:20] + "..." + v[-6:]
        print(f"  {k} = {vv}")

print()
print("=" * 60)
print("3) devbox id / hostname / metadata 文件")
print("=" * 60)
print("  hostname:", sh("hostname"))
for pat in ["/etc/runloop*", "/etc/runloop/*", "/run/runloop*", "/var/run/runloop*",
            "/opt/runloop*", "/root/.runloop*", "/workspace/.runloop*"]:
    for f in glob.glob(pat):
        print(f"  found: {f}")

print()
print("=" * 60)
print("4) 有没有本地 metadata/control endpoint（常见于云沙箱）")
print("=" * 60)
for url in ["http://localhost:8080/", "http://169.254.169.254/",
            "http://localhost:9990/", "http://metadata.runloop/"]:
    r = sh(f'curl -s --max-time 3 "{url}" 2>&1 | head -c 120')
    print(f"  {url} -> {r or '(空/超时)'}")

print()
print("=" * 60)
print("5) /etc/environment 全文（找 devbox id / token）")
print("=" * 60)
print(sh("cat /etc/environment 2>/dev/null | sed -E 's/(=.{12}).*/\\1.../'"))

print()
print("完成。把以上全部输出发回。")
