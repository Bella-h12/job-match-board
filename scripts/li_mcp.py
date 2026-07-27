#!/usr/bin/env python3
"""Minimal stdio JSON-RPC client for mcp-server-linkedin.

Launches the server with `uvx`. Override either piece if your setup differs:
    LI_MCP_UVX=/path/to/uvx        # default: whichever uvx is on PATH
    LI_MCP_PACKAGE=some-package    # default: mcp-server-linkedin@latest
"""
import json, subprocess, sys, threading, queue, os, shutil


def _find_uvx():
    explicit = os.environ.get("LI_MCP_UVX")
    if explicit:
        return explicit
    # uv installs to ~/.local/bin, which login shells have but GUI-launched
    # processes often don't — look there before giving up.
    found = shutil.which("uvx")
    if found:
        return found
    fallback = os.path.expanduser("~/.local/bin/uvx")
    if os.path.exists(fallback):
        return fallback
    sys.exit(
        "找不到 uvx。装一个：curl -LsSf https://astral.sh/uv/install.sh | sh\n"
        "或者用 LI_MCP_UVX 指定路径。"
    )


UVX = _find_uvx()
PACKAGE = os.environ.get("LI_MCP_PACKAGE", "mcp-server-linkedin@latest")
CMD = [UVX, "--with", "rich", PACKAGE]
ENV = dict(
    os.environ,
    UV_HTTP_TIMEOUT="300",
    PATH=os.pathsep.join(
        [os.path.dirname(UVX), os.environ.get("PATH", "/usr/bin:/bin")]
    ),
)

class MCP:
    def __init__(self):
        self.p = subprocess.Popen(CMD, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, env=ENV, text=True)
        self.q = queue.Queue()
        self.id = 0
        t = threading.Thread(target=self._reader, daemon=True)
        t.start()
        self.req("initialize", {"protocolVersion": "2024-11-05",
                                "capabilities": {}, "clientInfo": {"name": "cli", "version": "1.0"}})
        self.notify("notifications/initialized")

    def _reader(self):
        for line in self.p.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                self.q.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params: msg["params"] = params
        self.p.stdin.write(json.dumps(msg) + "\n"); self.p.stdin.flush()

    def req(self, method, params=None, timeout=120):
        self.id += 1
        msg = {"jsonrpc": "2.0", "id": self.id, "method": method}
        if params is not None: msg["params"] = params
        self.p.stdin.write(json.dumps(msg) + "\n"); self.p.stdin.flush()
        while True:
            r = self.q.get(timeout=timeout)
            if r.get("id") == self.id:
                return r

    def call(self, tool, args, timeout=180):
        r = self.req("tools/call", {"name": tool, "arguments": args}, timeout=timeout)
        if "error" in r:
            return {"error": r["error"]}
        content = r.get("result", {}).get("content", [])
        out = []
        for c in content:
            if c.get("type") == "text":
                out.append(c["text"])
        return "\n".join(out)

if __name__ == "__main__":
    m = MCP()
    action = sys.argv[1]
    if action == "list":
        r = m.req("tools/list")
        for t in r["result"]["tools"]:
            print(t["name"], "-", t.get("description", "")[:120])
    else:
        args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(m.call(action, args))
