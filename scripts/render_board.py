# -*- coding: utf-8 -*-
"""scored.json → board.html。每个分数都能展开看它是从 JD 哪句话来的。

用法：python3 scripts/render_board.py workspace/<名字>
"""
import html, io, json, os, sys

MARK = {1: "✓", 0.5: "½", 0: "✗"}
CLS = {1: "hit", 0.5: "half", 0: "miss"}


def e(s):
    return html.escape("" if s is None else str(s), quote=True)


def main():
    ws = sys.argv[1].rstrip("/")
    rows = json.load(io.open(os.path.join(ws, "scored.json"), encoding="utf-8"))
    cfg = json.load(io.open(os.path.join(ws, "config.json"), encoding="utf-8"))
    live = sorted([r for r in rows if not r["closed"] and r["kind"] == "scored"],
                  key=lambda r: -r["fit"])
    nogate = [r for r in rows if r["kind"] == "无硬门槛" and not r["closed"]]
    unk = [r for r in rows if r["kind"] == "未核" and not r["closed"]]

    cards = []
    for i, r in enumerate(live, 1):
        items = "".join(
            '<li class="%s"><b>%s</b> %s<span class="why">%s</span></li>'
            % (CLS[h], MARK[h], e(t), e(w)) for t, h, w in r["must"])
        nice = "".join('<li class="%s"><b>%s</b> %s</li>' % (CLS[h], MARK[h], e(t))
                       for t, h in r.get("nice", []))
        cards.append(f"""<details class="card"><summary>
<span class="rank">{i}</span><span class="score">{r['fit']}</span>
<span class="co">{e(r['co'])}</span><span class="role">{e(r['role'])}</span>
<span class="hit">命中 {r['hit']:g} / 共 {r['tot']}</span></summary>
<div class="meta">{e(r['meta'])}</div>
<p class="lab">硬性要求（决定分数）</p><ul class="req">{items}</ul>
{'<p class="lab">加分项（只加不减）</p><ul class="req">' + nice + '</ul>' if nice else ''}
<a class="jd" href="https://www.linkedin.com/jobs/view/{e(r['id'])}/" target="_blank">看原始 JD →</a>
</details>""")

    doc = f"""<!doctype html><meta charset="utf-8">
<title>求职看板 · {e(cfg.get('name'))}</title>
<style>
:root{{--bg:#F4F5F3;--card:#fff;--ink:#161B18;--dim:#6D7B75;--line:#D3D9D4;
--hit:#1E5A4B;--miss:#A9382A;--half:#8A6410}}
@media(prefers-color-scheme:dark){{:root{{--bg:#101413;--card:#171D1B;--ink:#E7ECE9;
--dim:#7F8C87;--line:#2B3532;--hit:#79C4AA;--miss:#E38271;--half:#D7AC5A}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.7 "Noto Sans SC",system-ui,sans-serif}}
.wrap{{max-width:960px;margin:0 auto;padding:40px 20px 80px}}
h1{{font-size:26px;margin:0 0 6px}} .sub{{color:var(--dim);margin:0 0 28px;font-size:14px}}
.card{{background:var(--card);border:1px solid var(--line);margin-bottom:8px}}
summary{{display:grid;grid-template-columns:34px 52px 1fr 2fr auto;gap:12px;align-items:center;
padding:13px 16px;cursor:pointer;list-style:none}}
summary::-webkit-details-marker{{display:none}}
.rank{{color:var(--dim);font-variant-numeric:tabular-nums;font-size:13px}}
.score{{font-size:22px;font-weight:700;color:var(--hit);font-variant-numeric:tabular-nums}}
.co{{font-weight:700}} .role{{color:var(--dim);font-size:14px}}
.hit{{font-size:12px;color:var(--dim);white-space:nowrap;font-variant-numeric:tabular-nums}}
.meta{{padding:0 16px;color:var(--dim);font-size:12.5px}}
.lab{{padding:0 16px;margin:14px 0 4px;font-size:12px;color:var(--dim);letter-spacing:.08em}}
ul.req{{margin:0;padding:0 16px 8px 16px;list-style:none}}
ul.req li{{padding:5px 0 5px 22px;position:relative;font-size:13.5px;border-top:1px solid var(--line)}}
ul.req li b{{position:absolute;left:0;top:5px}}
.hit b{{color:var(--hit)}} .miss b{{color:var(--miss)}} .half b{{color:var(--half)}}
.why{{display:block;color:var(--dim);font-size:12px}}
.jd{{display:inline-block;margin:6px 16px 14px;font-size:13px;color:var(--hit)}}
.note{{margin-top:34px;padding:14px 16px;border:1px solid var(--line);background:var(--card);font-size:13.5px;color:var(--dim)}}
@media(max-width:640px){{summary{{grid-template-columns:28px 46px 1fr;}}.role,.hit{{grid-column:1/-1}}}}
</style>
<div class="wrap">
<h1>求职看板 · {e(cfg.get('name'))}</h1>
<p class="sub">方向：{e(' / '.join(cfg.get('roles') or [])) or '未设置'}
 · 在招且可打分 <b>{len(live)}</b> 个 · 无硬门槛 {len(nogate)} 个 · 判据未核 {len(unk)} 个<br>
分数 = 这份 JD 的硬性要求里你命中几条 ÷ 一共几条。<b>点开每张卡能看到逐条原文和为什么算命中。</b></p>
{''.join(cards)}
<div class="note"><b>另外 {len(nogate)} 个岗没有硬门槛</b>（JD 里没有可筛的硬条件），
它们不给百分数也不参与排名——「没门槛」和「门槛全中」是两件事。
<b>{len(unk)} 个抄不出要求清单</b>，标未核，同样不给分。空着比编一个数诚实。</div>
</div>"""
    out = os.path.join(ws, "matches.html")
    io.open(out, "w", encoding="utf-8").write(doc)
    print("→ %s（%d 张卡 · 简版匹配表）" % (out, len(live)))


if __name__ == "__main__":
    main()
