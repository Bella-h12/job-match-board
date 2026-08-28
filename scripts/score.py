# -*- coding: utf-8 -*-
"""看板两个核心数字的唯一出口：适配度 / 公司发展。

2026-08-22 从 rebuild-board.py 里提出来，为的是让门禁能**跑生产路径上那一个函数**，
而不是在测试里重抄一遍公式（R35-1 / R10 铁律五：纯函数单测证明不了它被接上了，
所以 gate-score.py 里另有一条断言盯着 rebuild-board.py 确实 import 了这里）。
"""

# ================================================================ 公司发展（0–100）
# 2026-08-22 重写。Bella 的原话：「公司的这个评分怎么来的，说的也不清晰。」
# 她是对的，而且比「不清晰」更糟——**它压根没有来处**：整个 8 月这一项都是
#   GROWTH_BY_LIGHT = dict(green=85, yellow=50, red=15)
# 也就是说，占总分 40% 的这个数只有三个取值，全靠一盏手工点的色灯，
# 而「色灯凭什么是绿的」页面上一个字都没写。三个取值意味着：81 个岗里，
# 44 个公司发展是 85、37 个是 50——**它没有在区分公司，它只是把色灯换了个写法。**
#
# 现在改成四道可核的问题，各 25 分，每一道都必须带一句能对回原文/公开事实的依据。
# 挑这四道的判据是「三年后回头看，这段经历还值不值钱」——不是公司现在多有名。
# 标签写短是为了在 390px 上一行一条读得下（8-22 实测长句在手机上横向溢出）；
# 每道题完整的判据写在下面这段注释里，也写在页面「评分说明」那个折叠块里。
#   ai        这个岗每天碰的是不是 AI 产品本身（不是「一家用 AI 的公司」）
#   principal 雇主是不是甲方（甲方 > 甲方的交付方 > 招聘代理/人力外包）——决定这段经历在简历上叫什么
#   growing   公司在不在长（融资 / 扩编 / UAE 实体与牌照，要有可核出处，猜的一律记 0）
#   durable   这段经历三年后还值不值钱（前沿实验室·生态大厂 > 本土甲方 > 通用外包）
GROWTH_DIMS = [
    ("ai",        "碰的是 AI 产品本身"),
    ("principal", "雇主是甲方"),
    ("growing",   "公司在长"),
    ("durable",   "三年后还值钱"),
]
GROWTH_SCALE = {"yes": 25, "half": 12, "no": 0}
GROWTH_MARK = {"yes": "✓", "half": "½", "no": "✗"}

def fmtnum(x):
    """5.5 写成 5.5，5.0 写成 5 —— 半条命中的岗（Halian 5.5/7）不许被四舍五入掉。"""
    return ('%g' % x)


def growth_of(j):
    """返回 (分数, 逐条明细) 或 (None, None)。

    **未核就是 None，不许回落到色灯。**（R48 / R10-⑨：取不到就说取不到，
    绝不拿一个看起来正常的数顶上——那正是这一项之前干的事。）
    数据里的写法：growth_by=dict(ai="yes", principal="no", growing="half", durable="yes",
                                why="每条为什么，带可核出处")
    """
    g = j.get("growth_by")
    if not g:
        return None, None
    detail = [(label, g.get(k, "no"), GROWTH_SCALE[g.get(k, "no")]) for k, label in GROWTH_DIMS]
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
