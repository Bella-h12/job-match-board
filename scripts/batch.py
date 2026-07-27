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
    try:
        r = m.call(c["tool"], c["args"], timeout=240)
    except Exception as e:
        r = {"error": str(e)}
    results.append({"call": c, "result": r})
    json.dump(results, open(sys.argv[2], "w"), ensure_ascii=False, indent=1)
try:
    m.call("close_session", {}, timeout=30)
except Exception:
    pass
print("done", file=sys.stderr)
