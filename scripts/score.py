# -*- coding: utf-8 -*-
"""看板两个核心数字的唯一出口：适配度 / 公司发展。

2026-08-22 从 rebuild-board.py 里提出来，为的是让门禁能**跑生产路径上那一个函数**，
而不是在测试里重抄一遍公式（R35-1 / R10 铁律五：纯函数单测证明不了它被接上了，
所以 gate-score.py 里另有一条断言盯着 rebuild-board.py 确实 import 了这里）。
"""

# ================================================================ 公司发展（0–100，确定性）
# 2026-08-29 重写。Bella：「标签还有一些量化计算都是 Python 固定的，不要用模型。」
#
# 上一版四问由模型判（ai / principal / growing / durable 各 25），后果：
#   ① 没有模型 → 四问全空 → 每个岗判未核 → **排名整个是空的**（一个没输 key 的用户实测）
#   ② 模型给的取值带理由（「no（JD 未出现…）」）、标签和文案打架，不可靠
# 四问里只有两问能从 JD 文本里确定性判出来：
#   ai         这个岗每天碰的是不是 AI 产品本身 —— JD 里 AI/LLM/agent 这类词的密度
#   principal  雇主是不是甲方 —— JD 有没有「our client / staffing / recruitment agency /
#              contract staffing / on behalf of」这类代招字眼
# 另两问（在不在长、三年后值不值钱）JD 里根本没有，代码判不了 —— **不进分数**，
# 不拿模型猜一个数顶上。所以公司发展 = 两问各 50。
import re as _re

AI_RX = _re.compile(r"\b(?:LLM|LLMs|large language model|agentic|AI agent|GenAI|generative AI|"
                    r"machine learning|RAG|prompt|foundation model|model training|inference)\b", _re.I)
AGENCY_RX = _re.compile(r"our client|on behalf of (?:our|a) client|staffing|recruitment agency|"
                        r"recruiting agency|talent partner|contract staffing|C2C|W2 contract|"
                        r"placement agency|consultancy is hiring for", _re.I)
GROWTH_DIMS = [("ai", "碰的是 AI 产品本身"), ("principal", "雇主是甲方")]
GROWTH_SCALE = {"yes": 50, "half": 25, "no": 0}
GROWTH_MARK = {"yes": "✓", "half": "½", "no": "✗"}


def growth_from_jd(jd_text, company=""):
    """从 JD 文本确定性判两问。返回 dict(ai=…, principal=…, why=…)，每道带判据。"""
    t = jd_text or ""
    n_ai = len(AI_RX.findall(t))
    words = max(1, len(t.split()))
    density = n_ai * 1000.0 / words           # 每千词出现几次
    if density >= 8 or n_ai >= 12:
        ai = "yes"
    elif density >= 2 or n_ai >= 3:
        ai = "half"
    else:
        ai = "no"
    ag = AGENCY_RX.search(t) or AGENCY_RX.search(company or "")
    principal = "no" if ag else "yes"
    return dict(ai=ai, principal=principal,
                why="ai：JD 里 AI 类词 %d 次（每千词 %.1f）；principal：%s" % (
                    n_ai, density,
                    ("命中代招字眼「%s」" % ag.group(0)) if ag else "JD 无代招/外包字眼"))


def fmtnum(x):
    return ('%g' % x)


def growth_of(j):
    """→ (分数, 逐条明细) 或 (None, None)。没有 growth_by 就是未核（不许回落到色灯）。"""
    g = j.get("growth_by")
    if not g:
        return None, None
    def _norm(v):
        v = str(v or "no").strip().lower()
        for k in ("yes", "half", "no"):
            if v.startswith(k):
                return k
        return "no"
    detail = [(label, _norm(g.get(k)), GROWTH_SCALE[_norm(g.get(k))]) for k, label in GROWTH_DIMS]
    return sum(d[2] for d in detail), detail

# ================================================================ 适配度（0–100）
# 2026-08-27 重写（Bella 当场纠正，第二次动这一项）。
#
# 上一版：`req=(命中, 总数)` —— **两个手填的整数**。分母由值班员自己归纳，
# 而同一张卡上那句「门槛原文」是另写的一句话，两个字段从来没被要求一致。
# 实测 65 个岗里分母能追溯到逐条 JD 原文的是 **0 个**：
#   · Revolut     分母写 7，它自己的原文里写着「命中 5 条 / 共 5 条」，列出的原话只有 3 句
#   · LogiX       「原文」是「整份 JD 一条年限门槛都没有」—— 那是一个观察不是一份清单，撑起 4/4 = 100%
#   · Propertysuite JD 原话是「This is an open profile, not a fixed job description」，照样给了 6 条
# 而且这三个正好是榜上并列 100% 的那几个 —— **要求写得越少（或压根没有），分数越高。**
# 门禁当时是绿的，因为它只验算术（5/5 要算出 100）和接线，**零条验出处**。
#
# 现在三条硬规矩：
# 1. **分母不许手填**：只能是 extract_reqs.extract() 从 JD 正文里逐条抠出来的条数，
#    每条留原文，卡上逐条印出来、可以逐条吵。
# 2. **must / nice 分开**：must 由 JD 自己的段标题决定，决定分数；
#    nice 只加分不扣分（JD 多列三条 preferred 反而让人掉分，方向就是反的），封顶 +8。
#    **漏 must 不许被 nice 的加分粉饰**：must 命中率 < 60% 一律封顶 60。
# 3. **没有硬门槛的岗不给百分数**：must 为空 = 「无硬门槛」，它不是 100%。
#    这类岗单独标出来、不参与匹配榜排名 —— 「没门槛」和「门槛全中」是两件事，
#    压成同一个数就会让一个没有 JD 的开放岗坐在榜首。
FIT_NICE_CAP = 8          # nice 最多加这么多
FIT_MUST_FLOOR = 0.60     # must 命中率低于它 → 封顶
FIT_WALL_CAP = 60
FIT_MIN_ITEMS = 4         # 少于这么多条，那不是一份要求清单

# ⚠ 2026-08-27 补：只抠出 1–2 条也会算出 100%（实测 Salt「Product Designer」1/1 = 100，
# 排到榜眼）。这跟旧版「要求写得越少分越高」是同一个病换了个入口——
# **分母小到不成清单时，正确答案是「抄不出」，不是满分。**


def fit_of(j):
    """→ (分数, must命中, must总数, 扣分明细, 类别)

    类别: "scored" 正常打分 / "无硬门槛" JD 没有可筛的硬条件 / "未核" 抄不出清单。
    后两类分数一律 None —— **空着比编一个数诚实**，它们不进匹配榜。
    """
    r = j.get("reqs")
    if not r:
        return None, None, None, [], "未核"
    must = r.get("must") or []
    nice = r.get("nice") or []
    for it in must + nice:
        assert isinstance(it, (list, tuple)) and len(it) == 2, ("每条要求必须是 (原文, 命中)", it)
        assert isinstance(it[0], str) and len(it[0].strip()) >= 12, ("要求必须留 JD 原文", it)
        assert it[1] in (0, 0.5, 1), ("命中只能是 0 / 0.5 / 1", it)
    if not must:
        return None, 0, 0, [], "无硬门槛"
    if len(must) < FIT_MIN_ITEMS:
        return None, len(must), len(must), [], "未核"

    hit = sum(x[1] for x in must)
    total = len(must)
    base = 100.0 * hit / total
    bonus = (FIT_NICE_CAP * sum(x[1] for x in nice) / len(nice)) if nice else 0.0

    adj = j.get("fit_adj") or []          # [(-18, "JD 原话…"), …] 每条必须带理由
    for d, why in adj:
        assert why, "扣分必须带原文理由，不许裸扣分"

    v = base + bonus + sum(d for d, _ in adj)
    if hit / total < FIT_MUST_FLOOR:      # 漏掉一多半 must 的岗不许靠加分爬上来
        v = min(v, FIT_WALL_CAP)
    return max(0, min(100, round(v))), hit, total, adj, "scored"
