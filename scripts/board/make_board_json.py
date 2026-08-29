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


def act_kind_of(p):
    """动作标签只从文案推，不信模型自己给的 act_kind。

    2026-08-29 实测：模型给 Huntington 写「先问再投：年资微差」却标 go，Capgemini
    「先问再投：确认缺口」也标 go——文案和标签打架，而标签直接决定第一屏放哪三张。
    一个决定第一屏的字段不能靠模型自报；文案是给人看的，就按人看到的那句判。
    """
    t = ((p.get("act_short") or "") + " " + (p.get("act") or "")).strip()
    if not t:
        return "ref"
    if re.match(r"^\s*(今天投|立即投|马上投)", t):
        return "go"
    if re.match(r"^\s*(不投|跳过|放弃|别投)", t):
        return "skip"
    return "ref"          # 本周投 / 先问再投 / 其他 → 都不是「今天」


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
        unscored_why=("JD 抠出的硬性要求只有 %d 条，不足 4 条不当清单——打开 JD 自己看一眼" % (r.get("tot") or 0)
                      if r.get("kind") == "未核" else
                      "JD 里没有可筛的硬性要求（没年限、没学位、没必备技能）——不是 100%，是没门槛"
                      if r.get("kind") == "无硬门槛" else ""),
        reqs=dict(must=[[t, h] for t, h, _ in (r.get("must") or [])],
                  nice=[[t, h] for t, h in (r.get("nice") or [])]),
        growth_by=p.get("growth_by"),
        pay_aed=p.get("pay_aed"), pay=p.get("pay"),
        clicked=clicked(meta), d1=None, applicants=None,
        senior="", apply="linkedin",
        # 下面这些是「看板」那一层，没写就留空，页面上不渲染
        why=p.get("why", ""), ammo=p.get("ammo", ""), gapnote=p.get("gapnote", ""),
        act=p.get("act", ""), act_kind=act_kind_of(p),
        act_short=p.get("act_short", ""),
        reach=p.get("reach") or dict(kind="none", note=""),
        kind="job", note="",
    ))

n_scored = sum(1 for j in jobs if j.get("growth_by"))
out = dict(today=date.today().isoformat(), owner=cfg.get("name", ""),
           roles=cfg.get("roles", []), jobs=jobs, callouts=prose.get("_callouts", []),
           scan_note="方向 %s · 抓到 %d 个岗 · 有公司发展判定的 %d 个" % (" / ".join(cfg.get("roles", [])[:3]), len(jobs), n_scored),
           footer_line="%s · 首次生成 · %d 个岗 · 公司发展已核 %d 个 · 台账 0 条" % (date.today().isoformat(), len(jobs), n_scored))
json.dump(out, io.open(os.path.join(WS, "board.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
need = [j["id"] for j in jobs if not j["act_short"]]
print("board.json：%d 个岗" % len(jobs))
print("待补一句话行动建议的：%d 个（没补的页面上不显示这一行，不会编）" % len(need))
