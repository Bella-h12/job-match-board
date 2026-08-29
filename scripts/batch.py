#!/usr/bin/env python3
"""Run multiple LinkedIn MCP calls in one browser session. Usage: batch.py calls.json out.json"""
import json, sys
import os, sys as _s; _s.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from li_mcp import MCP

calls = json.load(open(sys.argv[1]))
m = MCP()
results = []
for c in calls:
    print(f">>> {c['tool']} {json.dumps(c['args'])[:100]}", file=sys.stderr)
    r = None
    for attempt in range(4):
        try:
            r = m.call(c["tool"], c["args"], timeout=240)
        except Exception as e:
            r = {"error": str(e)}
        # ⚠ 2026-08-29：两个抓取进程并行时，后起的那个每一条都拿到
        # 「Another LinkedIn MCP client is currently using the browser」——这不是数据，
        # 原来直接当结果写进文件，下游就把 60 个岗全算成「抓不到 JD」。等一会儿重试。
        if "Another LinkedIn MCP client" in str(r):
            import time; time.sleep(15 * (attempt + 1)); continue
        break
    results.append({"call": c, "result": r})
    json.dump(results, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
try:
    m.call("close_session", {}, timeout=30)
except Exception:
    pass
print("done", file=sys.stderr)
