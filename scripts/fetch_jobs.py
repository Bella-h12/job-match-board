# -*- coding: utf-8 -*-
"""抓岗位：按用户配置的方向搜 + 抓每个岗的 JD 全文 → workspace/<名字>/jd-cache/

用法：python3 scripts/fetch_jobs.py workspace/<名字> [--max-per-role 25]

它用的是**用户自己已登录的浏览器会话**（mcp-server-linkedin 驱动本机 Chrome）。
不代登录、不存密码——LinkedIn 的推荐页在登录墙后面，代登录违反条款且封的是用户的号。
"""
import argparse, io, json, os, re, subprocess, sys, time

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
    # 方向词 → 标题匹配用的词干（QA Automation Engineer → qa / automation / test / sdet …）
    _stems = set()
    for r in roles:
        for w in re.findall(r"[A-Za-z]+", r.lower()):
            if w not in ("engineer", "senior", "junior", "lead", "manager", "ai", "and", "of", "the"):
                _stems.add(w)
    _stems |= {"sdet", "test", "testing", "qa", "quality"} if _stems & {"qa", "sdet", "test", "automation"} else set()

    def role_hit(title):
        t = title.lower()
        return any(w in t for w in _stems)

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

    # ⚠ search_jobs 只给「被选中那一条」的 Job ID，其余条目只有标题（SKILL §31，2026-08-11 实测）。
    # 所以要两段：第一段从文本里抠出「标题 | 公司」，第二段用「公司名 + 岗位名」定向补搜，
    # 那条几乎必然成为 Selected，ID 就拿到了。第一版只跑第一段，美国 QA 岗 1,000+ 条结果、0 个 ID。
    import re
    ids, seen = [], set()
    pairs = []
    for it in json.load(io.open(s_out, encoding="utf-8")):
        r = it.get("result"); blob = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        for m in re.findall(r'/jobs/view/(\d{6,})/|"job_ids"\s*:\s*\[\s*"(\d{6,})"', blob):
            jid = m[0] or m[1]
            if jid not in seen:
                seen.add(jid); ids.append(jid)
        try:
            txt = json.loads(blob).get("sections", {}).get("search_results", "") if isinstance(r, str) else (r.get("sections", {}) or {}).get("search_results", "")
        except Exception:
            txt = ""
        lines = [l.strip() for l in txt.split("\n") if l.strip()]
        # 列表里每条的形状：标题 / 「标题 with verification」/ 公司 / 地点 …；取「with verification」前那行 + 下一行
        for k, l in enumerate(lines):
            if l.endswith("with verification") and k + 1 < len(lines):
                title = l[: -len("with verification")].strip()
                co = lines[k + 1]
                # ⚠ 2026-08-29：搜「SDET」第一条是「Founding Prompt Engineer」——那是 LinkedIn
                # 塞进结果页的推荐位，不是搜索命中。照单全收的结果：60 个岗里只有 19 个是测试岗，
                # 决策台三张卡全不是测试岗（Bella 当场指出）。**标题必须跟方向词对得上才收。**
                if not role_hit(title):
                    continue
                if 3 < len(title) < 90 and 1 < len(co) < 60 and (title, co) not in pairs:
                    pairs.append((title, co))
    pairs = pairs[: a.max_per_role * max(1, len(roles))]
    print("第一段拿到 %d 个直接 ID、%d 个「标题 | 公司」对；第二段定向补搜逼 ID" % (len(ids), len(pairs)))
    if pairs:
        s2 = os.path.join(cache, "search2-out.json")
        run_batch([{"tool": "search_jobs", "args": {"keywords": "%s %s" % (co, t), "location": loc,
                                                     "max_pages": 1, "date_posted": "past month"}}
                   for t, co in pairs], s2)
        for it in json.load(io.open(s2, encoding="utf-8")):
            r = it.get("result"); blob = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
            for m in re.findall(r'/jobs/view/(\d{6,})/|"job_ids"\s*:\s*\[\s*"(\d{6,})"', blob)[:1]:   # 只取 Selected 那条
                jid = m[0] or m[1]
                if jid not in seen:
                    seen.add(jid); ids.append(jid)
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
