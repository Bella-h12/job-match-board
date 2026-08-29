# -*- coding: utf-8 -*-
"""scored.json（打分结果）+ config.json → board.json（看板要的数据形状）

用法：python3 scripts/board/make_board_json.py <workspace>

**能算的算出来，算不出来的留空 —— 留空的字段在页面上不渲染，不编。**
哪些必须由人或模型补：
  act / act_short   这一条今天做不做、一句话为什么（≤15 字）
  reach             触达路径（谁能引荐、问什么），**不许编人名**
  ammo / gapnote    你的弹药 / 你的缺口
  why               一句话结论
这些是「看板」区别于「排序表」的地方，也是唯一需要模型的地方。
"""
import io, json, os, re, sys, unicodedata
from datetime import date

WS = os.path.abspath(sys.argv[1])
scored = json.load(io.open(os.path.join(WS, "scored.json"), encoding="utf-8"))
cfg = json.load(io.open(os.path.join(WS, "config.json"), encoding="utf-8"))
prose = {}
pp = os.path.join(WS, "prose.json")          # 模型/人写的那部分，单独一份，重跑不会被冲掉
if os.path.exists(pp):
    prose = json.load(io.open(pp, encoding="utf-8"))

DAYS = re.compile(r"(\d+)\s*(day|week|month|hour)s?\s*ago", re.I)
CLICK = re.compile(r"([\d,]+)\s*(?:people clicked apply|applicants?)", re.I)


def posted_days(meta):
    m = DAYS.search(meta or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    return {"hour": 0, "day": n, "week": n * 7, "month": n * 30}[unit]


def clicked(meta):
    m = CLICK.search(meta or "")
    return int(m.group(1).replace(",", "")) if m else None


jobs = []
for r in scored:
    if r.get("closed"):
        continue
    jid = r["id"]
    p = prose.get(jid, {})
    meta = r.get("meta", "")
    d = posted_days(meta)
    # 门槛原文：把逐条 must 拼成可核的一段（每条前面标 ✓ / ½ / ✗）
    mark = {1: "✓", 0.5: "½", 0: "✗"}
    gate_txt = " · ".join("%s%s" % (mark[h], t[:70]) for t, h, _ in (r.get("must") or [])[:6])
    jobs.append(dict(
        id=jid, co=r.get("co", ""), role=r.get("role", ""),
        loc=(meta.split("·")[0].strip() if "·" in meta else meta)[:40],
        posted=d, posted_txt=(meta.split("·")[1].strip() if meta.count("·") >= 1 else ""),
        g="new", first_seen=None,
        light="yellow",                    # 公司灯：没核过一律黄，不许猜绿
        gate="ok", gate_txt=gate_txt,
        # 打分的三项：适配度来自逐条判定；公司发展和薪资没核就是 None（页面写「未核」）
        reqs=dict(must=[[t, h] for t, h, _ in (r.get("must") or [])],
                  nice=[[t, h] for t, h in (r.get("nice") or [])]),
        growth_by=p.get("growth_by"),
        pay_aed=p.get("pay_aed"), pay=p.get("pay"),
        clicked=clicked(meta), d1=None, applicants=None,
        senior="", apply="linkedin",
        # 下面这些是「看板」那一层，没写就留空，页面上不渲染
        why=p.get("why", ""), ammo=p.get("ammo", ""), gapnote=p.get("gapnote", ""),
        act=p.get("act", ""), act_kind=p.get("act_kind", "ref"),
        act_short=p.get("act_short", ""),
        reach=p.get("reach") or dict(kind="none", note=""),
        kind="job", note="",
    ))

out = dict(today=date.today().isoformat(), owner=cfg.get("name", ""),
           roles=cfg.get("roles", []), jobs=jobs, callouts=prose.get("_callouts", []))
json.dump(out, io.open(os.path.join(WS, "board.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
need = [j["id"] for j in jobs if not j["act_short"]]
print("board.json：%d 个岗" % len(jobs))
print("待补一句话行动建议的：%d 个（没补的页面上不显示这一行，不会编）" % len(need))
