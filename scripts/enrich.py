# -*- coding: utf-8 -*-
"""可选的一步：给每个岗写给人看的文案——「为什么」「弹药」「缺口」「触达路径」。

**它不产生任何数字，不影响排名。**（2026-08-29 Bella：「标签和量化计算都是 Python 固定的，
不要用模型。」）分数、公司发展、动作标签全在 score.py / make_board_json.py 里确定性算。
没有模型 → 这些文案为空，卡上少几行字，排名照旧。

用法：python3 scripts/enrich.py workspace/<名字>

**不需要 API key。**按这个顺序找模型，找到哪个用哪个：
  1. 环境变量 JMB_MODEL_KEY（自己的 key：Anthropic 格式或 OpenAI 兼容格式）
  2. 本机的 `claude` 命令（Claude Code，走你已有的订阅）
  3. 本机的 `codex` 命令（Codex CLI，走你已有的订阅）
  4. 都没有 → 跳过，并且**明说排名会是空的**

prose.json —— 跟打分数据分开存，重跑打分不会冲掉它。
纪律：公司发展四问每道要带出处，给不出出处一律记 no；触达路径不许编人名。
"""
import io, json, os, shutil, subprocess, sys, urllib.request

WS = os.path.abspath(sys.argv[1])
KEY = os.environ.get("JMB_MODEL_KEY")
PROVIDER = os.environ.get("JMB_MODEL_PROVIDER", "anthropic")
MODEL = os.environ.get("JMB_MODEL") or ("claude-sonnet-5" if PROVIDER == "anthropic" else "gpt-5")

def _find(cmd):
    p = shutil.which(cmd)
    if p:
        return p
    for c in (os.path.expanduser("~/.local/bin/" + cmd), os.path.expanduser("~/.npm-global/bin/" + cmd),
              "/usr/local/bin/" + cmd, "/opt/homebrew/bin/" + cmd):
        if os.path.exists(c):
            return c
    return None

if KEY:
    BACKEND = "key"
elif _find("claude"):
    BACKEND = "claude"
elif _find("codex"):
    BACKEND = "codex"
else:
    BACKEND = None

if not BACKEND:
    print("没有模型可用：没有 JMB_MODEL_KEY，本机也没有 claude / codex 命令。")
    print("跳过文案：卡上少「为什么 / 弹药 / 缺口 / 触达」几行字，**分数和排名不受影响**。")
    sys.exit(0)
print("模型后端：%s" % {"key": "自己的 key（%s / %s）" % (PROVIDER, MODEL),
                      "claude": "本机 Claude Code（走你的订阅）",
                      "codex": "本机 Codex（走你的订阅）"}[BACKEND])

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
1. 你不打分、不定动作——那些由代码算。你只写给人看的文案。
2. reach（触达路径）**绝不编人名**。JD 没露出招聘团队就写 kind="none"。
3. ammo（弹药）只能引用候选人事实清单里有的东西；gapnote（缺口）要引 JD 原文。
4. 不知道就说不知道，不要用「可能」「应该」编内容。"""

def ask(prompt):
    if BACKEND == "claude":
        r = subprocess.run([_find("claude"), "-p", "--output-format", "text"],
                           input=SYSTEM + "\n\n" + prompt, capture_output=True, text=True, timeout=180)
        return r.stdout
    if BACKEND == "codex":
        r = subprocess.run([_find("codex"), "exec", "--skip-git-repo-check", SYSTEM + "\n\n" + prompt],
                           capture_output=True, text=True, timeout=180)
        return r.stdout
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
{{"why": "一句话结论 ≤40 字",
 "ammo": "候选人的弹药（只引事实清单）", "gapnote": "缺口（引 JD 原文）",
 "reach": {{"kind":"none|poster|alumni|referral","note":"怎么触达，不编人名"}}}}"""
    try:
        out = ask(prompt)
        out = out[out.index("{"): out.rindex("}") + 1]
        prose[r["id"]] = json.loads(out)
        print("  %2d/%d  %s · %s  → %s" % (i, len(todo), r["co"][:20], r["role"][:30], prose[r["id"]].get("why", "")[:20]))
    except Exception as e:
        print("  %2d/%d  %s 失败：%s（留空，不编）" % (i, len(todo), r["co"][:20], str(e)[:60]))
    json.dump(prose, io.open(pp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("→ %s" % pp)
