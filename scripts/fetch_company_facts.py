# -*- coding: utf-8 -*-
"""用本机 Claude Code / Codex 联网查公司事实（融资 / Glassdoor）→ companies.json

用法：python3 scripts/fetch_company_facts.py workspace/<名字>

Bella 2026-08-29：「你直接用我的 Claude Code 去查不就好了？用户接入之后也可以直接用他的
Codex 或 Claude Code。」——对，它们自带联网搜索，走用户已有的订阅，不需要任何 API key。

模型在这里**只做检索员**：找公开事实、给出处 URL，查不到写 null。
**打分不在这里，在 score.py 里按这些事实确定性算**（融资阶段 / Glassdoor 分数各有写死的阈值）。
实测 claude -p 守规矩：没网络权限时全部 null 并明说「是没查到不是没有」，不凭记忆填。

字段：funding_stage / funding_total_usd / last_round_year / glassdoor_rating / glassdoor_reviews / source_urls
"""
import io, json, os, shutil, subprocess, sys

WS = os.path.abspath(sys.argv[1])
cp = os.path.join(WS, "companies.json")
cos = json.load(io.open(cp, encoding="utf-8")) if os.path.exists(cp) else {}


def _find(cmd):
    p = shutil.which(cmd)
    if p:
        return p
    for c in (os.path.expanduser("~/.local/bin/" + cmd), os.path.expanduser("~/.npm-global/bin/" + cmd)):
        if os.path.exists(c):
            return c


CLI = ("claude", _find("claude")) if _find("claude") else (("codex", _find("codex")) if _find("codex") else (None, None))
if not CLI[0]:
    print("本机没有 claude / codex 命令，跳过公司事实检索（融资 / Glassdoor 那一问会是未核）。")
    sys.exit(0)

PROMPT = """查这家公司的公开事实，只回 JSON，不要别的。查不到的字段写 null，**绝不凭记忆猜**。
公司：%s（LinkedIn: linkedin.com/company/%s）
{"funding_stage":"最近一轮，如 Seed / Series A-H / IPO / Public / Bootstrapped / null",
 "funding_total_usd":数字或null,"last_round_year":年份或null,
 "glassdoor_rating":数字或null,"glassdoor_reviews":数字或null,
 "source_urls":["每个字段的出处 URL"]}"""


def ask(text):
    if CLI[0] == "claude":
        r = subprocess.run([CLI[1], "-p", "--output-format", "text", "--allowedTools", "WebSearch,WebFetch"],
                           input=text, capture_output=True, text=True, timeout=300)
    else:
        r = subprocess.run([CLI[1], "exec", "--skip-git-repo-check", "-s", "read-only", text],
                           capture_output=True, text=True, timeout=300)
    out = r.stdout
    try:
        return json.loads(out[out.index("{"): out.rindex("}") + 1])
    except Exception:
        return None


# 只查还没查过的；companies.json 里 slug → 记录，name 从 JD 缓存里对
name_of = {}
cache = os.path.join(WS, "jd-cache")
for f in os.listdir(cache):
    if f.endswith("-out.json") and "search" not in f and "companies" not in f:
        for it in json.load(io.open(os.path.join(cache, f), encoding="utf-8")):
            try:
                r = json.loads(it["result"])
                cref = [x for x in r.get("references", {}).get("job_posting", []) if x.get("kind") == "company"]
                head = [l.strip() for l in r["sections"]["job_posting"].split("\n") if l.strip()]
                if cref and head:
                    name_of[cref[0]["url"].strip("/").split("/")[-1]] = head[0]
            except Exception:
                pass
todo = [s for s in cos if cos[s].get("funding") is None and "facts_checked" not in cos[s]]
print("用本机 %s 查 %d 家公司的融资 / Glassdoor（已查过 %d 家跳过）" % (CLI[0], len(todo), len(cos) - len(todo)))
for i, slug in enumerate(todo, 1):
    facts = ask(PROMPT % (name_of.get(slug, slug), slug))
    cos[slug]["facts_checked"] = True
    if facts:
        cos[slug]["funding"] = dict(stage=facts.get("funding_stage"), total_usd=facts.get("funding_total_usd"),
                                    year=facts.get("last_round_year"))
        cos[slug]["glassdoor"] = dict(rating=facts.get("glassdoor_rating"), reviews=facts.get("glassdoor_reviews"))
        cos[slug]["source_urls"] = facts.get("source_urls") or []
        print("  %2d/%d  %-24s 融资 %-12s Glassdoor %s" % (i, len(todo), name_of.get(slug, slug)[:23],
              str(facts.get("funding_stage"))[:12], facts.get("glassdoor_rating")))
    else:
        print("  %2d/%d  %-24s 没拿到可解析的结果（留 null）" % (i, len(todo), name_of.get(slug, slug)[:23]))
    json.dump(cos, io.open(cp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("→ %s" % cp)
