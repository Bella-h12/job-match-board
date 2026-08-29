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


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import score as _score
import glob as _glob
_jd = {}
_all_items = []
for _f in _glob.glob(os.path.join(WS, "jd-cache", "*-out.json")):
    if "search" in os.path.basename(_f) or "companies" in os.path.basename(_f):
        continue
    for _it in json.load(io.open(_f, encoding="utf-8")):
        _all_items.append(_it)
        try:
            _jid = _it["call"]["args"]["job_id"]
            _t = json.loads(_it["result"]).get("sections", {}).get("job_posting", "")
            if _t and len(_t) > len(_jd.get(_jid, "")):
                _jd[_jid] = _t
        except Exception:
            pass

_cos_p = os.path.join(WS, "companies.json")
_cos = json.load(io.open(_cos_p, encoding="utf-8")) if os.path.exists(_cos_p) else {}


def growth_full(jid, co):
    """公司发展四问：ai/principal 从 JD 判，growing 从公司页判，durable 目前无来源 → na。"""
    g = _score.growth_from_jd(_jd.get(jid, ""), co)
    slug = None
    try:
        refs = json.loads(next(it["result"] for it in _all_items if it["call"]["args"]["job_id"] == jid))
        cref = [x for x in refs.get("references", {}).get("job_posting", []) if x.get("kind") == "company"]
        slug = cref[0]["url"].strip("/").split("/")[-1] if cref else None
    except Exception:
        pass
    c = _cos.get(slug) if slug else None
    gv, gw = _score.growing_from_company(c)
    g["growing"] = gv
    g["durable"] = "na"
    g["why"] = g["why"] + "；growing：%s；durable：融资/Glassdoor 暂无可核来源，未核" % gw
    return g


# 动作标签：纯代码，按适配度分档。2026-08-29 Bella：「标签和量化计算都是 Python 固定的，不要用模型。」
ACT_GO, ACT_ASK = 60, 40


def _short(t, n=22):
    t = (t or "").strip()
    return t if len(t) <= n else t[:n] + "…"


def act_of(r):
    """动作 + 一句人话。全部由命中/未命中的 JD 原文推出，不用模型。"""
    fit = r.get("fit")
    if fit is None:
        return "ref", ""
    must = r.get("must") or []
    miss = [t for t, h, *_ in must if h == 0]
    half = [t for t, h, *_ in must if h == 0.5]
    if r.get("wall"):
        return "skip", "不投：年限硬挡"
    if fit >= ACT_GO:
        return "go", "今天投：硬性要求 %g/%d 条对得上" % (r["hit"], r["tot"])
    if fit >= ACT_ASK:
        gap = miss[0] if miss else (half[0] if half else "")
        return "ref", ("先问再投：JD 要「%s」，你没有，先问是不是硬筛" % _short(gap)) if gap else "先问再投"
    return "skip", "不投：%d 条硬性要求里只对上 %g 条" % (r["tot"], r["hit"])


def ammo_of(r):
    """「拿什么打」= 命中的 JD 要求原文；「拦你的」= 没命中的。数据本来就有，不靠模型。"""
    must = r.get("must") or []
    hit = [t for t, h, *_ in must if h == 1]
    miss = [t for t, h, *_ in must if h == 0]
    half = [t for t, h, *_ in must if h == 0.5]
    ammo = "；".join("「%s」" % _short(t, 60) for t in hit[:4]) if hit else ""
    gap = "；".join("「%s」" % _short(t, 60) for t in (miss + half)[:4]) if (miss or half) else ""
    if half and not miss:
        gap = "没有硬缺，但这几条只对上一半：" + gap
    return ammo, gap


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
        growth_by=growth_full(jid, r.get("co", "")),
        pay_aed=p.get("pay_aed"), pay=p.get("pay"),
        clicked=clicked(meta), d1=None, applicants=None,
        senior="", apply="linkedin",
        # 下面这些是「看板」那一层，没写就留空，页面上不渲染
        why=p.get("why", ""), ammo=(p.get("ammo") or ammo_of(r)[0]), gapnote=(p.get("gapnote") or ammo_of(r)[1]),
        act=(p.get("act") or act_of(r)[1]), act_kind=act_of(r)[0],
        act_short=act_of(r)[1],
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
