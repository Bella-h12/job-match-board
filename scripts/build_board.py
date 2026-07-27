#!/usr/bin/env python3
"""Build the job match board HTML from a board.json.

Usage:
    build_board.py board.json out.html [--template assets/template.html]

The JSON is validated before rendering: a missing required field or a bad
enum stops the build with a message naming the offending path, so a typo
never ships as a silently empty section.
"""
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, "..", "assets", "template.html")

LIGHTS = {"green": "🟢 值得投", "yellow": "🟡 待确认", "red": "🔴 避开"}
STATUS = {
    "open": ("st-open", "✓ 在招"),
    "verify": ("st-verify", "待确认"),
    "filled": ("st-filled", "已招满"),
    "stale": ("st-stale", "未再查"),
}
ACTION_KIND = {"go": "go", "later": "ref", "skip": "skip"}
FLOOR_KIND = {"over": "ok", "edge": "meh", "under": "no"}
TIER_ORDER = ["s", "a", "broker", "out"]


class BuildError(Exception):
    pass


def e(s):
    """Escape for HTML text and attribute values."""
    return html.escape("" if s is None else str(s), quote=True)


def need(obj, key, path, kind=None):
    if not isinstance(obj, dict) or key not in obj:
        raise BuildError(f"{path}.{key} 缺失")
    v = obj[key]
    if kind is list and not isinstance(v, list):
        raise BuildError(f"{path}.{key} 必须是数组")
    if kind is dict and not isinstance(v, dict):
        raise BuildError(f"{path}.{key} 必须是对象")
    return v


def enum(value, table, path):
    if value not in table:
        raise BuildError(f"{path} = {value!r}，只能是 {sorted(table)} 之一")
    return table[value]


def jd_link(url, text, cls="jd-link"):
    if not url:
        return e(text)
    return (
        f'<a class="{cls}" href="{e(url)}" target="_blank" rel="noopener">{e(text)}</a>'
    )


def dots(n, total=5, gold=False):
    n = max(0, min(total, int(n)))
    cls = "dots v" if gold else "dots"
    pips = "".join('<i class="on"></i>' for _ in range(n)) + "<i></i>" * (total - n)
    return f'<span class="{cls}">{pips}</span>'


# --------------------------------------------------------------------------
# sections
# --------------------------------------------------------------------------

def render_verdict(data):
    paras = need(data, "verdict", "$", list)
    if not paras:
        raise BuildError("$.verdict 至少要有一段")
    body = "\n    ".join(f"<p>{p}</p>" for p in paras)
    return f'<div class="verdict">\n    <div class="label">核心结论</div>\n    {body}\n  </div>'


def render_changes(data):
    ch = data.get("changes")
    if not ch:
        return ""
    groups = [
        ("new", "new", "◉ 今日新增"),
        ("confirmed", "hold", "⟳ 已确认还在招"),
        ("dropped", "cut", "✕ 从清单里划掉"),
    ]
    cards = []
    for key, cls, heading in groups:
        items = ch.get(key) or []
        if not items:
            continue
        lis = "\n        ".join(
            f'<li><b>{e(it.get("name", ""))}</b> <span>{it.get("note", "")}</span></li>'
            for it in items
        )
        cards.append(
            f'<div class="rf {cls}">\n      <h3>{heading}</h3>\n      <ul>\n        {lis}\n      </ul>\n    </div>'
        )
    if not cards:
        return ""
    return '<section class="refresh">\n    ' + "\n    ".join(cards) + "\n  </section>"


def render_ranking(data):
    rows = need(data, "ranking", "$", list)
    if not rows:
        return ""
    out = []
    for i, r in enumerate(rows, 1):
        p = f"$.ranking[{i - 1}]"
        title = jd_link(r.get("url"), need(r, "title", p))
        act_cls = enum(need(r, "action_kind", p), ACTION_KIND, f"{p}.action_kind")
        out.append(
            "      <tr>\n"
            f'        <td>{r.get("rank", i)}</td>'
            f'<td>{title}<span class="co">{e(r.get("context", ""))}</span></td>\n'
            f'        <td>{dots(need(r, "odds", p))}</td>\n'
            f'        <td>{dots(need(r, "value", p), gold=True)}</td>\n'
            f'        <td class="act {act_cls}">{e(need(r, "action", p))}</td>\n'
            "      </tr>"
        )
    head = (
        "      <tr><th>#</th><th>岗位</th><th>投中概率</th>"
        "<th>对你的价值</th><th>该做什么</th></tr>"
    )
    return (
        '<div class="table-scroll">\n    <table class="rank-table">\n'
        + head
        + "\n"
        + "\n".join(out)
        + "\n    </table>\n  </div>"
    )


def render_deepdives(data):
    cards = []
    for i, d in enumerate(data.get("deepdives") or []):
        p = f"$.deepdives[{i}]"
        hot = " hot" if d.get("hot") else ""
        title = jd_link(d.get("url"), need(d, "title", p))
        badge = (
            f'<div class="rank-chip">{e(d["badge"])}</div>' if d.get("badge") else ""
        )
        sub = f'<div class="sub">{d["subtitle"]}</div>' if d.get("subtitle") else ""
        paras = "\n      ".join(f"<p>{x}</p>" for x in (d.get("paras") or []))
        comp = (
            f'<div class="comp-line">{d["comp_line"]}</div>' if d.get("comp_line") else ""
        )

        cols = ""
        strengths, gaps = d.get("strengths") or [], d.get("gaps") or []
        if strengths or gaps:
            def col(items, cls, heading):
                if not items:
                    return ""
                lis = "\n            ".join(f"<li>{x}</li>" for x in items)
                return (
                    f'<div class="col {cls}">\n          <h4>{heading}</h4>\n'
                    f"          <ul>\n            {lis}\n          </ul>\n        </div>"
                )

            cols = (
                '<div class="cols">\n        '
                + col(strengths, "ammo", d.get("strengths_title", "你的优势"))
                + "\n        "
                + col(gaps, "gap", d.get("gaps_title", "你的短板"))
                + "\n      </div>"
            )

        verd = (
            f'<div class="verd"><b>判断：</b>{d["verdict"]}</div>'
            if d.get("verdict")
            else ""
        )
        cards.append(
            f'<div class="job{hot}">\n    <div class="job-head">\n      {badge}\n'
            f'      <h3>{title}<small>{e(d.get("company", ""))}</small></h3>\n      {sub}\n'
            f'    </div>\n    <div class="job-body">\n      {paras}\n      {comp}\n'
            f"      {cols}\n      {verd}\n    </div>\n  </div>"
        )
    return "\n\n  ".join(cards)


def render_salary(data):
    rows = data.get("salary") or []
    if not rows:
        return ""
    out = []
    for i, r in enumerate(rows):
        p = f"$.salary[{i}]"
        cls = enum(need(r, "floor_kind", p), FLOOR_KIND, f"{p}.floor_kind")
        out.append(
            f'      <tr><td>{e(need(r, "label", p))}</td>'
            f'<td class="num">{e(need(r, "estimate", p))}</td>'
            f'<td class="{cls}">{e(need(r, "vs_floor", p))}</td></tr>'
        )
    head = f'      <tr><th>公司 · 岗位</th><th>{e(data.get("salary_unit", "月薪估算"))}</th><th>{e(data.get("salary_floor_label", "对比底线"))}</th></tr>'
    return (
        '<div class="table-scroll">\n    <table>\n'
        + head
        + "\n"
        + "\n".join(out)
        + "\n    </table>\n  </div>"
    )


def render_skips(data):
    items = data.get("skips") or []
    if not items:
        return ""
    out = []
    for i, s in enumerate(items):
        p = f"$.skips[{i}]"
        out.append(
            f'    <div class="skip-item"><b>{jd_link(s.get("url"), need(s, "title", p))}</b>'
            f'<span>{need(s, "reason", p)}</span></div>'
        )
    return '<div class="skip-list">\n' + "\n".join(out) + "\n  </div>"


def render_leads(data):
    items = data.get("leads") or []
    if not items:
        return ""
    lis = "\n      ".join(
        f'<li><b>{e(x.get("name", ""))}</b> <span>{x.get("note", "")}</span></li>'
        for x in items
    )
    title = e(data.get("leads_title", "顺带看到的其他岗位"))
    return f'<div class="leads">\n    <h4>{title}</h4>\n    <ul>\n      {lis}\n    </ul>\n  </div>'


def render_steps(data):
    items = data.get("steps") or []
    if not items:
        return ""
    lis = "\n    ".join(f"<li>{x}</li>" for x in items)
    return f'<ol class="steps">\n    {lis}\n  </ol>'


def render_board_data(data):
    """Emit the JS payload for the filterable full board."""
    rows = data.get("board") or []
    jobs, urls = [], {}
    seen = set()
    for i, b in enumerate(rows):
        p = f"$.board[{i}]"
        co = need(b, "company", p)
        if co in seen:
            raise BuildError(f"{p}.company = {co!r} 重复；同一家公司在总表里只能出现一次")
        seen.add(co)
        tier = need(b, "tier", p)
        if tier not in TIER_ORDER:
            raise BuildError(f"{p}.tier = {tier!r}，只能是 {TIER_ORDER} 之一")
        enum(need(b, "light", p), LIGHTS, f"{p}.light")
        enum(need(b, "status", p), STATUS, f"{p}.status")
        jobs.append(
            {
                "t": tier,
                "sc": int(need(b, "score", p)),
                "co": co,
                "role": need(b, "role", p),
                "lv": b.get("level", "—"),
                "loc": b.get("location", "—"),
                "remote": 1 if b.get("remote") else 0,
                "light": b["light"],
                "channel": b.get("channel", "直招"),
                "status": b["status"],
                "note": b.get("note", ""),
                "gap": b.get("gap", "—"),
                "fix": b.get("fix", "—"),
                "hook": b.get("hook", "—"),
            }
        )
        if b.get("url"):
            urls[co] = [b["url"], bool(b.get("url_exact", True))]

    tiers = data.get("tiers") or {}
    for tk in TIER_ORDER:
        if any(j["t"] == tk for j in jobs) and tk not in tiers:
            raise BuildError(f"$.tiers.{tk} 缺失，但 $.board 里有属于这一档的岗位")

    payload = {
        "jobs": jobs,
        "urls": urls,
        "tiers": tiers,
        "tierOrder": TIER_ORDER,
        "lights": LIGHTS,
        "status": {k: list(v) for k, v in STATUS.items()},
        "labels": data.get("board_labels")
        or {"gap": "短板", "fix": "怎么补", "hook": "怎么切入", "score": "匹配度"},
    }
    return json.dumps(payload, ensure_ascii=False, indent=1)


def render_filters(data):
    tiers = data.get("tiers") or {}
    btns = ['<button class="filter" data-tier="all" aria-pressed="true">全部</button>']
    for tk in TIER_ORDER:
        if tk in tiers:
            label = tiers[tk].get("t", tk.upper()) + " · " + tiers[tk].get("title", "")
            btns.append(
                f'<button class="filter" data-tier="{tk}" aria-pressed="false">{e(label)}</button>'
            )
    return "\n    ".join(btns)


# --------------------------------------------------------------------------

def build(data, template):
    meta = need(data, "meta", "$", dict)
    metas = "".join(f"<span>{e(x)}</span>" for x in (meta.get("meta_items") or []))

    subs = {
        "TITLE": e(need(meta, "title", "$.meta")),
        "KICKER": e(meta.get("kicker", "")),
        "HEADLINE": need(meta, "headline", "$.meta"),
        "META_ITEMS": metas,
        "VERDICT": render_verdict(data),
        "CHANGES": render_changes(data),
        "RANKING": render_ranking(data),
        "RANKING_NOTE": data.get("ranking_note", ""),
        "DEEPDIVES": render_deepdives(data),
        "DEEPDIVES_HEADING": e(data.get("deepdives_heading", "重点岗位")),
        "DEEPDIVES_NOTE": data.get("deepdives_note", ""),
        "BOARD_HEADING": e(data.get("board_heading", "全部岗位总表")),
        "BOARD_NOTE": data.get("board_note", ""),
        "FILTERS": render_filters(data),
        "BOARD_DATA": render_board_data(data),
        "SALARY": render_salary(data),
        "SALARY_NOTE": data.get("salary_note", ""),
        "SKIPS": render_skips(data),
        "LEADS": render_leads(data),
        "STEPS": render_steps(data),
        "FOOTER": data.get("footer", ""),
    }

    out = template
    for k, v in subs.items():
        out = out.replace("{{" + k + "}}", v)

    leftover = re.findall(r"\{\{([A-Z_]+)\}\}", out)
    if leftover:
        raise BuildError(f"模板里还有没填的占位符：{sorted(set(leftover))}")

    # Drop headings whose section rendered empty, so the page never shows a
    # bare title with nothing under it.
    for marker in ("CHANGES", "SALARY", "SKIPS", "LEADS", "STEPS"):
        if not subs[marker].strip():
            out = re.sub(
                rf"<!--section:{marker}-->.*?<!--/section:{marker}-->",
                "",
                out,
                flags=re.S,
            )
    out = re.sub(r"<!--/?section:[A-Z_]+-->", "", out)
    return out


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    tpl_path = DEFAULT_TEMPLATE
    if "--template" in sys.argv:
        tpl_path = sys.argv[sys.argv.index("--template") + 1]

    with open(args[0], encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as ex:
            print(f"board.json 不是合法 JSON：{ex}", file=sys.stderr)
            return 1
    with open(tpl_path, encoding="utf-8") as f:
        template = f.read()

    try:
        out = build(data, template)
    except BuildError as ex:
        print(f"构建失败：{ex}", file=sys.stderr)
        return 1

    with open(args[1], "w", encoding="utf-8") as f:
        f.write(out)
    n = len(data.get("board") or [])
    print(f"已生成 {args[1]}（{n} 个岗位，{len(out)} 字节）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
