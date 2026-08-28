# -*- coding: utf-8 -*-
"""把「某个人的简历事实」变成可复用的判据。

这个文件是整套东西能给别人用的**唯一关键**：在它之前，判据是把一个人的履历
手写进正则表（judge_fit.py 里 17 处「CV 上有 / CV 上没有」），换个人就得重写一遍。
现在改成读 people/<名字>/facts.json —— 那份 json 由简历生成、**由本人确认**。

facts.json 的形状（每一项都要能在简历上指出来）：
{
  "source": "简历文件名",              # 出处，必填
  "confirmed": false,                  # 本人确认过没有。没确认 = 只出草稿不出分
  "years_total": 5,                    # 总工作年限
  "title_years": {"product manager": 0, "data analyst": 5},
                                       # 专项年限。**绝不拿总年限顶专项**
  "has":     ["sql", "python", ...],   # 简历上能举证的（命中）
  "lacks":   ["arabic", ...],          # 简历上确实没有的（不命中）
  "partial": ["enterprise", ...]       # 方向对但规模/主语差一截（半条）
}
"""
import io, json, re

HIT, HALF, MISS = 1, 0.5, 0

HEADERISH = re.compile(
    r"^\s*(?:required|minimum|basic|preferred|additional)?\s*(?:qualifications?|requirements?|"
    r"relevant [a-z ]+|experience in one or more[^.]*|relevant backgrounds?[^.]*|what (?:we|you)[^.]*|"
    r"education\s*(?:and|&)\s*experience|role details?|about [a-z ]+|nice[- ]to[- ]haves?|"
    r"preferred experience|bonus points?|technologies)\s*[:：]?\s*$", re.I)
YEARS = re.compile(r"(?<![\d.])(\d{1,2})\s*\+?\s*(?:[-–]\s*\d{1,2}\s*)?(?:years?|yrs?)", re.I)
# 「或列表」：一条里列了好几种，占其中一种就算数。
# 但**专项年限不许被它豁免**——「5+ years in a Solutions Architect **or** Pre-Sales
# Engineer role」句子里有 or，不代表你可以不满足那 5 年（2026-08-27 实测踩过）。
ALT = re.compile(r"one or more|such as|e\.g\.|any of|either|,\s*or\s|\bor\b.*\bor\b|/", re.I)


def is_header(line):
    return bool(HEADERISH.match(line.strip())) or line.strip().endswith((":", "："))


class Judge:
    def __init__(self, facts):
        self.f = facts
        self.has = [re.compile(p, re.I) for p in facts.get("has", [])]
        self.lacks = [re.compile(p, re.I) for p in facts.get("lacks", [])]
        self.partial = [re.compile(p, re.I) for p in facts.get("partial", [])]
        self.years_total = facts.get("years_total")
        # 专项年限：{正则: (年数, 人话名字)}
        self.title_years = [(re.compile(k, re.I), v, k)
                            for k, v in (facts.get("title_years") or {}).items()]

    def judge(self, line):
        """→ (命中值, 判据)。判据里必须说清是简历的哪一面对上/对不上。"""
        t = line.lower()
        m = YEARS.search(line)
        if m:
            n = int(m.group(1))
            # ① 先看这条年限说的是哪个主语——有专项就用专项，绝不拿总年限顶
            for rx, have, raw in self.title_years:
                if rx.search(line):
                    if have >= n:
                        return HIT, "要求 %d 年「%s」，简历上有 %g 年" % (n, raw, have)
                    if have == 0:
                        return MISS, "要求 %d 年「%s」，简历上这个主语是 0 年" % (n, raw)
                    return HALF, "要求 %d 年「%s」，简历上只有 %g 年" % (n, raw, have)
            # ② 没有专项主语，才用总年限
            if self.years_total is not None:
                if n > self.years_total + 2:
                    return MISS, "要求 %d 年，简历上总年限 %g 年" % (n, self.years_total)
                if n > self.years_total:
                    return HALF, "要求 %d 年，简历上 %g 年，擦线" % (n, self.years_total)
        yes = [p.pattern for p in self.has if p.search(t)]
        no = [p.pattern for p in self.lacks if p.search(t)]
        half = [p.pattern for p in self.partial if p.search(t)]
        if no and yes:
            if ALT.search(line):
                return HIT, "或列表，简历上占其中一项（%s）" % yes[0]
            return HALF, "一半对得上（%s），一半没有（%s）" % (yes[0], no[0])
        if no:
            return MISS, "简历上没有：%s" % no[0]
        if yes:
            return HIT, "简历上有：%s" % yes[0]
        if half:
            return HALF, "方向对但规模/主语差一截：%s" % half[0]
        return HALF, "判不明确，按半条计（宁可不虚高）"


def load(person_dir):
    """读某个人的 facts.json。**没确认过就拒绝出分**——判据的基准必须本人点过头。"""
    f = json.load(io.open(person_dir + "/facts.json", encoding="utf-8"))
    if not f.get("confirmed"):
        raise SystemExit(
            "facts.json 还没被本人确认（confirmed=false）。\n"
            "  判据的基准是这份清单，没确认就出分 = 拿我猜的东西去判他的岗位。\n"
            "  先让他过一遍 %s/facts.json，改完把 confirmed 改成 true。" % person_dir)
    return Judge(f)
