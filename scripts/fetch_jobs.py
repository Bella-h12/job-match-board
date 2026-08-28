# -*- coding: utf-8 -*-
"""抓岗位：按用户配置的方向搜 + 抓每个岗的 JD 全文 → workspace/<名字>/jd-cache/

用法：python3 scripts/fetch_jobs.py workspace/<名字> [--max-per-role 25]

它用的是**用户自己已登录的浏览器会话**（mcp-server-linkedin 驱动本机 Chrome）。
不代登录、不存密码——LinkedIn 的推荐页在登录墙后面，代登录违反条款且封的是用户的号。
"""
import argparse, io, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))


def run_batch(calls, out_path):
    calls_path = out_path + ".calls.json"
    json.dump(calls, io.open(calls_path, "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run([sys.executable, os.path.join(HERE, "batch.py"), calls_path, out_path])
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace")
    ap.add_argument("--max-per-role", type=int, default=25)
    a = ap.parse_args()
    ws = a.workspace.rstrip("/")
    cfg = json.load(io.open(os.path.join(ws, "config.json"), encoding="utf-8"))
    cache = os.path.join(ws, "jd-cache")
    os.makedirs(cache, exist_ok=True)

    roles = cfg.get("roles") or []
    if not roles:
        raise SystemExit("config.json 里没有 roles —— 先说清楚想投什么方向，否则只能瞎搜")
    loc = cfg.get("location") or ""

    # ① 按方向搜岗位，拿 ID
    search = [{"tool": "search_jobs",
               "args": {"keywords": r, "location": loc, "max_pages": 2, "date_posted": "past week"}}
              for r in roles]
    s_out = os.path.join(cache, "search-out.json")
    print("搜 %d 个方向：%s" % (len(roles), " / ".join(roles)))
    if not run_batch(search, s_out):
        raise SystemExit("搜索失败：多半是 LinkedIn 没登录，或 uvx 起不来。先跑一次 "
                         "`python3 scripts/li_mcp.py` 看报什么")

    ids, seen = [], set()
    for it in json.load(io.open(s_out, encoding="utf-8")):
        blob = json.dumps(it.get("result"), ensure_ascii=False)
        import re
        for jid in re.findall(r'"job_id"\s*:\s*"?(\d{6,})"?', blob):
            if jid not in seen:
                seen.add(jid); ids.append(jid)
    ids = ids[: a.max_per_role * max(1, len(roles))]
    print("拿到 %d 个岗位 ID" % len(ids))
    if not ids:
        raise SystemExit("一个 ID 都没拿到 —— 取到 0 条要当失败处理，不是「今天没岗位」。"
                         "先确认浏览器里 LinkedIn 是登录状态。")

    # ② 逐个抓 JD 全文
    jd_out = os.path.join(cache, "jd-out.json")
    run_batch([{"tool": "get_job_details", "args": {"job_id": j}} for j in ids], jd_out)
    got = 0
    for it in json.load(io.open(jd_out, encoding="utf-8")):
        try:
            if len(json.loads(it["result"])["sections"]["job_posting"]) > 500:
                got += 1
        except Exception:
            pass
    print("抓到 JD 正文 %d / %d 份 → %s" % (got, len(ids), cache))
    if got == 0:
        raise SystemExit("一份 JD 都没抓到 —— 判失败，不要继续往下算分")


if __name__ == "__main__":
    main()
