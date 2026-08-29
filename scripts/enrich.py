# -*- coding: utf-8 -*-
"""唯一需要模型的一步：给每个岗写「公司发展四问」和「行动建议 / 触达 / 弹药 / 缺口」。

用法：
    export JMB_MODEL_KEY=...          # 用户自己的 key
    export JMB_MODEL_PROVIDER=anthropic|openai   # 默认 anthropic
    export JMB_MODEL=claude-sonnet-5  # 可选
    export JMB_MODEL_BASE=https://…   # 可选：任何兼容接口（DeepSeek / OpenRouter / 自建）
    python3 scripts/enrich.py workspace/<名字>

产物 workspace/<名字>/prose.json —— 跟打分数据分开存，重跑打分不会冲掉它。
没有 key 就跳过：看板照样出，只是决策台是空的、卡上没有点评。**不编。**

两条纪律：
· 公司发展四问每一道都要带出处（JD 或公司页的原话），给不出出处一律记 no。
· 触达路径不许编人名——JD 没露出招聘团队，就写「无人可触达」。
"""
import io, json, os, sys, urllib.request

WS = os.path.abspath(sys.argv[1])
KEY = os.environ.get("JMB_MODEL_KEY")
PROVIDER = os.environ.get("JMB_MODEL_PROVIDER", "anthropic")
MODEL = os.environ.get("JMB_MODEL") or ("claude-sonnet-5" if PROVIDER == "anthropic" else "gpt-5")

if not KEY:
    print("没有 JMB_MODEL_KEY —— 跳过点评，看板照出但决策台为空（不编内容）")
    sys.exit(0)

scored = json.load(io.open(os.path.join(WS, "scored.json"), encoding="utf-8"))
facts = json.load(io.open(os.path.join(WS, "facts.json"), encoding="utf-8"))
cfg = json.load(io.open(os.path.join(WS, "config.json"), encoding="utf-8"))
pp = os.path.join(WS, "prose.json")
prose = json.load(io.open(pp, encoding="utf-8")) if os.path.exists(pp) else {}

# 拿 JD 全文
import glob
jd = {}
for f in glob.glob(os.path.join(WS, "jd-cache", "*-out.json")):
    for it in json.load(io.open(f, encoding="utf-8")):
        try:
            jid = it["call"]["args"]["job_id"]
            t = json.loads(it["result"]).get("sections", {}).get("job_posting", "")
            if t and len(t) > len(jd.get(jid, "")):
                jd[jid] = t
        except Exception:
            pass

SYSTEM = """你是求职情报值班员。只输出 JSON，不输出别的。
判据铁律：
1. 公司发展四问（ai / principal / growing / durable）每道取 yes/half/no，**每道必须带一句出处**（JD 或公司页原话）。给不出出处一律 no。
2. 行动建议 act_short ≤ 15 个字，只说「今天投 / 本周投 / 先问再投 / 不投」+ 一句为什么。
3. reach（触达路径）**绝不编人名**。JD 没露出招聘团队就写 kind="none"。
4. ammo（弹药）只能引用候选人事实清单里有的东西；gapnote（缺口）要引 JD 原文。
5. 不知道就说不知道，不要用「可能」「应该」编内容。"""

def ask(prompt):
    if PROVIDER == "anthropic":
        base = os.environ.get("JMB_MODEL_BASE", "https://api.anthropic.com")
        req = urllib.request.Request(base.rstrip("/") + "/v1/messages",
            data=json.dumps(dict(model=MODEL, max_tokens=1200, system=SYSTEM,
                                 messages=[dict(role="user", content=prompt)])).encode(),
            headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        r = json.load(urllib.request.urlopen(req, timeout=90))
        return r["content"][0]["text"]
    base = os.environ.get("JMB_MODEL_BASE", "https://api.openai.com/v1")
    req = urllib.request.Request(base + "/chat/completions",
        data=json.dumps(dict(model=MODEL, messages=[dict(role="system", content=SYSTEM),
                                                    dict(role="user", content=prompt)])).encode(),
        headers={"Authorization": "Bearer " + KEY, "content-type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=90))
    return r["choices"][0]["message"]["content"]

facts_brief = dict(years_total=facts.get("years_total"),
                   title_years={k.split("|")[0]: v for k, v in (facts.get("title_years") or {}).items() if v},
                   has=list((facts.get("_evidence") or {}).keys()),
                   roles=cfg.get("roles"), location=cfg.get("location"))

todo = [r for r in scored if not r.get("closed") and r.get("kind") == "scored" and r["id"] not in prose]
print("要点评的岗：%d（已有 %d 条跳过）" % (len(todo), len(prose)))
for i, r in enumerate(todo, 1):
    text = jd.get(r["id"], "")[:6000]
    judged = "\n".join("%s %s" % ({1: "✓", 0.5: "½", 0: "✗"}[h], t[:120]) for t, h, _ in r.get("must", []))
    prompt = f"""候选人事实清单：{json.dumps(facts_brief, ensure_ascii=False)}

岗位：{r['co']} · {r['role']}
逐条判定（已由代码算好，不要改）：
{judged}
适配度 {r['fit']}（命中 {r['hit']}/{r['tot']}）

JD 原文：
{text}

输出 JSON：
{{"growth_by": {{"ai":"yes|half|no","principal":"yes|half|no","growing":"yes|half|no","durable":"yes|half|no","why":"四道各一句出处"}},
 "why": "一句话结论 ≤40 字", "act": "行动建议一句", "act_kind": "go|ref|skip", "act_short": "≤15字",
 "ammo": "候选人的弹药（只引事实清单）", "gapnote": "缺口（引 JD 原文）",
 "reach": {{"kind":"none|poster|alumni|referral","note":"怎么触达，不编人名"}}}}"""
    try:
        out = ask(prompt)
        out = out[out.index("{"): out.rindex("}") + 1]
        prose[r["id"]] = json.loads(out)
        print("  %2d/%d  %s · %s  → %s" % (i, len(todo), r["co"][:20], r["role"][:30], prose[r["id"]].get("act_short", "")[:15]))
    except Exception as e:
        print("  %2d/%d  %s 失败：%s（留空，不编）" % (i, len(todo), r["co"][:20], str(e)[:60]))
    json.dump(prose, io.open(pp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("→ %s" % pp)
