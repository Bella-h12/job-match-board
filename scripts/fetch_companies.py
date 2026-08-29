# -*- coding: utf-8 -*-
"""抓公司页 → workspace/<名字>/companies.json（公司发展「在不在长」那一问的事实源）

用法：python3 scripts/fetch_companies.py workspace/<名字>

从 LinkedIn 公司页确定性读这些公开事实（不用模型）：
  employees  员工规模区间（51-200 这种）
  founded    成立年份
  industry   行业
  growth_2y  两年员工增速 %（在 Insights 页，**要 LinkedIn Premium 才有**；没有就 None）
  tenure     中位任期（同上）
读不到的字段就是 None——下游按「未核」处理，不猜。

Bella 2026-08-29：「公司的发展你还是要去调研，MRR / 融资几轮 / Glassdoor 分数这些。」
融资和 Glassdoor 没有公开免费 API，这版先把 LinkedIn 公司页能读的接上，
其余字段留位（funding / glassdoor），来源接上之前一律 None。
"""
import io, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
WS = os.path.abspath(sys.argv[1])
cache = os.path.join(WS, "jd-cache")
out_p = os.path.join(WS, "companies.json")
have = json.load(io.open(out_p, encoding="utf-8")) if os.path.exists(out_p) else {}

# ① 从已抓的 JD 里抠公司 slug
slugs = {}
for f in os.listdir(cache):
    if not f.endswith("-out.json") or "search" in f:
        continue
    for it in json.load(io.open(os.path.join(cache, f), encoding="utf-8")):
        try:
            r = json.loads(it["result"])
            refs = [x for x in r.get("references", {}).get("job_posting", []) if x.get("kind") == "company"]
            head = [l.strip() for l in r["sections"]["job_posting"].split("\n") if l.strip()]
            if refs and head:
                slugs[head[0]] = refs[0]["url"].strip("/").split("/")[-1]
        except Exception:
            pass
todo = {co: s for co, s in slugs.items() if s not in have}
print("公司 %d 家，已有 %d，要抓 %d" % (len(slugs), len(slugs) - len(todo), len(todo)))

# ② 抓 about + insights
if todo:
    calls = []
    for s in todo.values():
        calls.append({"tool": "get_company_profile", "args": {"company_name": s, "sections": "about"}})
    cp = os.path.join(cache, "companies.calls.json"); op = os.path.join(cache, "companies-out.json")
    json.dump(calls, io.open(cp, "w", encoding="utf-8"))
    subprocess.run([sys.executable, os.path.join(HERE, "batch.py"), cp, op])
    for it in json.load(io.open(op, encoding="utf-8")):
        s = it["call"]["args"]["company_name"]
        r = it.get("result"); txt = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        def g(pat, cast=str):
            m = re.search(pat, txt, re.I)
            return cast(m.group(1)) if m else None
        have[s] = dict(
            employees=g(r"Company size\\n([\d,]+-?[\d,]*\+?) employees"),
            founded=g(r"Founded\\n(\d{4})", int),
            industry=g(r"Industry\\n([^\\n]+)"),
            growth_2y=g(r"(-?\d+)%\s*(?:company-wide )?(?:2|two)[- ]?year growth", int),
            tenure=g(r"median (?:employee )?tenure[^\d]{0,12}([\d.]+)", float),
            funding=None, glassdoor=None,
            source="linkedin company page",
        )
json.dump(have, io.open(out_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
n_g = sum(1 for v in have.values() if v.get("growth_2y") is not None)
print("→ %s：%d 家有员工规模，%d 家有两年增速（Insights 要 Premium）" % (
    out_p, sum(1 for v in have.values() if v.get("employees")), n_g))
