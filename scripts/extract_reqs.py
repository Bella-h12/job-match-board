# -*- coding: utf-8 -*-
"""从 JD 全文里逐条抠出「要求」原文，按 JD 自己的小标题分成 must / nice。

为什么要有这个文件（2026-08-27 Bella 当场纠正）：
在这之前适配度的分母 `req=(命中, 总数)` 是**手填的两个整数**，而卡上那句「门槛原文」
是另写的一句话——两个字段从来没被要求一致。实测 65 个岗里，分母能追溯到逐条 JD 原文的
是 **0 个**：Revolut 分母写 7，它自己的原文里写着「命中 5 条 / 共 5 条」，列出来的原话
只有 3 句；LogiX 的「原文」是「整份 JD 一条年限门槛都没有」——那是一个观察不是一份清单，
却撑起了 4/4 = 100%；Propertysuite 的 JD 原话是「This is an open profile, not a fixed
job description」，照样给了 6 条。

所以分母不许再由人给：**它只能等于这个函数从 JD 正文里数出来的条数**，每条留原文。

两条设计判据：
1. **小标题不用固定词表匹配，用结构切段再判类别。**第一版列了 20 个 MUST_HEADS，
   Deel 那份写的是「You'll Be a Great Fit If You」/「Bonus If You」，一条都没命中，
   于是 must=0 —— 而 must=0 在下游是「无硬门槛」，等于把一个有 7 条硬要求的岗
   误判成没门槛。词表覆盖不了自然语言的写法，结构可以。
2. **must / nice 由 JD 自己的段标题决定，不由我判。**标题里有 bonus / preferred /
   nice to have 的那段就是 nice，只加分不扣分（JD 多列三条 preferred 反而让候选人掉分，
   方向就是反的）。判据落在文本上，你能逐条复核。
"""
import re
import unicodedata

NICE_START = re.compile(r"^\s*(?:nice[- ]?to[- ]?have|preferred|bonus|good to have|"
                       r"pluses?|it'?s a plus|desirable|advantageous|加分|优先)", re.I)
NICE_KW = re.compile(r"nice[- ]?to[- ]?have|preferred|bonus|good to have|"
                     r"a plus|pluses|desirable|advantageous|加分|优先", re.I)
# ⚠ 「require」不能裸放：Unicorn Lab 的职责标题「Business Analysis & Requirements
# Engineering」命中了它，于是整份 JD 从职责段一路被收进 must（150 条）。
# 收窄成「requirement(s) 后面不接工程/分析/管理这类职责词」。
MUST_KW = re.compile(r"require(?:d|ments?)?(?!\s*(?:engineering|analysis|gathering|management|"
                     r"traceability|elicitation))|qualificat|what you'?ll need|looking for|"
                     r"you'?(?:ll)? bring|great fit|who you are|you have|"
                     r"education (?:and|&) experience|experience (?:and|&) education|"
                     r"must[- ]?have|essential|skills? (?:and|&) experience|"
                     r"your profile|candidate profile|experience (?:required|needed)|"
                     r"we want|you'?ll need|about you|fit if|you are a fit|you'?re a fit|"
                     r"ideal candidate|your background|we'?d love|what makes you|"
                     r"^you$|^experience$|^skills$|任职要求|岗位要求|任职资格", re.I)
STOP_KW = re.compile(r"responsibilit|what you'?ll do|about (?:us|the company|the team|the role)|"
                     r"benefit|what we offer|perk|compensation|total rewards|why (?:join|this role)|"
                     r"our (?:values|mission|culture)|equal opportunit|how to apply|"
                     r"interview process|some things you'?ll enjoy|what you'?ll get|what you get|"
                     r"referr|know someone|our process|the process|next steps?|"
                     r"requirements added by the job poster|screening questions?|"
                     r"application|diversity|accommodat|岗位职责|我们提供|公司介绍", re.I)
# LinkedIn 页面自己的 UI 文本，从这里往下全部不是 JD
TAIL = re.compile(r"^(set alert|candidates? who clicked|candidate seniority|candidate education|"
                  r"about the company|looking for talent|show more|see how you compare|"
                  r"people you can reach out to|similar jobs|more jobs)", re.I)
HEAD_START = re.compile(r"^about the job\s*$", re.I)

STRONG_MUST = re.compile(
    r"^\s*(?:required\s+)?(?:requirements?|qualifications?|basic qualifications?|"
    r"minimum qualifications?|required qualifications?|what we'?re looking for|"
    r"what we are looking for|what you bring|what you'?ll bring|who you are|"
    r"you have|must[- ]haves?|education\s*(?:and|&)\s*experience|essential|"
    r"about you|your profile|you are a fit if you|you'?ll be a great fit if you|"
    r"任职要求|岗位要求|任职资格)\b", re.I)

BULLET = re.compile(r"^\s*(?:[-•·*▪◦‣]|\d+[.)]|[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮])\s+")


def _is_heading(line):
    """段标题的结构特征：短、不是项目符号、不以句号收尾。"""
    t = line.strip()
    if not t or len(t) > 72 or BULLET.match(line):
        return False
    if t.endswith((".", "!", "。")):
        return False
    # 一句正常的要求句几乎必然含逗号、或者以年限/动词开头；标题通常不含
    if "," in t or ";" in t or "、" in t:
        return False
    if re.match(r"^\d+\+?\s*(?:years?|yrs?|年)", t, re.I):   # 「5+ years …」是要求不是标题
        return False
    return len(t.split()) <= 9 or len(t) <= 24


def _clean(line):
    return BULLET.sub("", line).strip().rstrip(";；,，.。")


def extract(jd_text):
    """→ dict(must=[原文…], nice=[原文…], heads=[(标题, 类别)…])

    must 为空 = **无硬门槛**，调用方必须原样标出来，
    绝不能回落成「所有条都算命中」——那正是 LogiX / Propertysuite 拿到 100% 的路径。
    """
    jd_text = unicodedata.normalize("NFKC", jd_text or "")
    lines = jd_text.split("\n")
    # 只取「About the job」到 LinkedIn UI 尾巴之间那一段
    start = 0
    for i, l in enumerate(lines):
        if HEAD_START.match(l.strip()):
            start = i + 1
            break
    body = []
    for l in lines[start:]:
        if TAIL.match(l.strip()):
            break
        body.append(l)

    must, nice, heads, mode = [], [], [], None
    strong_seen = False
    for raw in body:
        line = raw.strip()
        if not line:
            continue
        if _is_heading(raw):
            # ⚠ 2026-08-28 修：这三个分支原来**没有 continue**，于是段标题本身
            # 也掉进了下面那段「收成一条要求」的代码 —— 每个 JD 的分母都因此虚高
            # 一到三条（「Requirements」「Nice to have」这些被当成了要求）。
            # 生产侧一直靠下游 is_header() 兜着，所以没露馅；给别人用的版本不能靠兜。
            if NICE_START.match(line):
                mode = "nice"; heads.append((line, "nice")); continue
            elif STOP_KW.search(line):
                mode = None; heads.append((line, "stop")); continue
            elif MUST_KW.search(line):
                strong = bool(STRONG_MUST.match(line))
                mode = "must"; heads.append((line, "must!" if strong else "must"))
                if strong and not strong_seen:
                    strong_seen = True
                    must = []          # 正牌资格段出现 → 之前收的职责段全部作废
                continue
            elif mode is None:
                heads.append((line, "-"))                   # 段外的无名标题：忽略
                continue
            else:
                # ⚠ 2026-08-27 修：原来这里是 `mode = None`——**认不出的短行会把整段打断**。
                # 实测 Citi 的「Qualifications:」下面第二条是「Demonstrated analytical skills」，
                # 短、无逗号，被当成新标题于是整段只收到 0 条；BCG X、Deel、Enhance 同一个死法。
                # 正解：只有 STOP 段或另一个具名要求段才换 mode，认不出的行按内容处理。
                heads.append((line, "~"))
                cur = must if mode == "must" else nice
                if len(cur) >= 15:      # 段已经很长还在冒无名标题＝多半已经走出要求段了
                    mode = None; continue
                item = _clean(line)
                if 12 <= len(item) <= 400:
                    (must if mode == "must" else nice).append(item)
                continue
        if mode is None:
            continue
        if mode == "must" and strong_seen and heads and heads[-1][1] == "must":
            continue                   # 已经有正牌段了，弱标题段不再收
        item = _clean(line)
        if not (12 <= len(item) <= 400):
            continue
        (must if mode == "must" else nice).append(item)

    def dedup(xs):
        seen, out = set(), []
        for x in xs:
            k = re.sub(r"\W+", "", x.lower())[:60]
            if k and k not in seen:
                seen.add(k); out.append(x)
        return out
    return dict(must=dedup(must), nice=dedup(nice), heads=heads)
