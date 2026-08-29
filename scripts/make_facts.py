# -*- coding: utf-8 -*-
"""简历 → facts.json 草稿。**草稿，不是结论**——必须本人过一遍才允许出分。

用法：python3 make_facts.py <简历文件.pdf|.docx|.txt> <输出目录>

它做三件事：
1. 从日期区间算总年限和**每个 title 的专项年限**（绝不拿总年限顶专项——
   「5 年 PM」和「5 年总工作年限」是两回事，混起来会把人判成达标）。
2. 拿一张**通用能力清单**逐项去简历里找证据：找得到进 has，找不到进 lacks。
   清单是固定的，所以「他没有 X」这个结论也有出处：是在这份简历里没找到 X。
3. 输出 confirmed=false 的 json —— 没人点头之前，打分脚本会拒绝跑。
"""
import io, json, os, re, sys, unicodedata
from datetime import date

# 通用能力清单：左边是判据正则，右边是给人看的名字。
# 一条要求在 JD 里出现时，用这张表决定它算「他有」还是「他没有」。
CHECKLIST = [
    (r"\bsql\b",                              "SQL"),
    (r"\bpython\b",                           "Python"),
    (r"\br\b(?![a-z])|\bstata\b|\bmatlab\b",  "R/Stata/MATLAB"),
    (r"tableau|power ?bi|looker|superset",    "BI 工具"),
    (r"data analy|analytics|business intelligence|数据分析|商业分析|指标体系|经营分析", "数据分析"),
    (r"experiment|a/b[- ]?test|hypothes|randomi[sz]ed",         "实验/AB"),
    (r"funnel|conversion|retention|churn|cohort|\bltv\b|漏斗|留存|流失|召回|转化|归因", "漏斗与留存分析"),
    (r"regression|random forest|decision tree|clustering|segmentation|arima|forecast|propensity|xgboost"
     r"|预测模型|建模|回归|聚类|分群", "统计建模/经典 ML"),
    (r"pytorch|tensorflow|deep learning|neural network|fine[- ]?tun|computer vision|diffusion",
                                              "深度学习训练"),
    (r"\bllm\b|large language model|genai|generative ai", "LLM"),
    (r"\bprompt", "prompt 工程"), (r"\bagent", "agent 系统"),
    (r"\brag\b|retrieval", "RAG"), (r"\beval", "模型评测"),
    (r"typescript|javascript|react|node|next\.js", "前端/全栈"),
    (r"\bapi\b|integration", "API 与集成"),
    (r"postgres|mysql|mongo|clickhouse|hive|snowflake|bigquery", "数据库/数仓"),
    (r"kubernetes|\bk8s\b|terraform|docker|\bci/cd\b|devops", "云原生/DevOps"),
    (r"\bjava\b|golang|\bc\+\+|\.net\b|scala|spark|hadoop|kafka", "后端/大数据栈"),
    (r"\bfigma\b|sketch|design system|wireframe|\bux\b", "设计工具"),
    (r"product manage|product owner|\bprd\b|roadmap|user stor|产品经理|需求文档", "产品管理"),
    (r"pre[- ]?sales|solution architect|sales engineer", "售前/方案架构"),
    (r"stakeholder|present|communicat|汇报|跨部门|协作", "沟通与汇报"),
    (r"crypto|blockchain|web3|exchange|trading|derivativ|区块链|交易所|链上", "加密/交易"),
    (r"fintech|payment|\bkyc\b|compliance|regulated", "金融科技/合规"),
    (r"\bERP\b|\bCRM\b|\bSAP\b|salesforce|workday", "ERP/CRM"),
    (r"aviation|airline|oil ?(&|and)? ?gas|construction|insurance|telecom", "重工业领域"),
    (r"arabic", "阿语"), (r"mandarin|chinese|中文", "中文"),
    (r"consult(ing|ancy)", "咨询背景"),
    (r"manage(d|s)? a team|line manage|direct reports|led a team", "带团队"),
    (r"\bphd\b", "博士"),
    (r"\bmsc\b|master'?s|硕士", "硕士"),
    (r"bachelor|\bbsc\b|本科|学士", "本科"),
    (r"statistic|econometric|mathematics|quantitative", "定量学位"),
]
# 「方向对但规模/主语差一截」——这些不判有也不判无
PARTIAL = [r"\benterprise\b|\bb2b\b", r"\bsaas\b", r"\bscrum\b|\bagile\b|backlog",
           r"\bcloud\b|\baws\b|azure|\bgcp\b", r"government|public sector", r"go[- ]to[- ]market|\bgtm\b"]

TITLE_RX = [
    (r"product (?:manage(?:r|ment)|owner)|\bpm\b", "product manager"),
    (r"data analyst|business intelligence|\bbi analyst\b", "data analyst"),
    (r"data scientist|applied scientist", "data scientist"),
    (r"(?:machine learning|ml) engineer", "ml engineer"),
    (r"software engineer|developer|full[- ]?stack", "software engineer"),
    (r"pre[- ]?sales|solutions? architect|sales engineer", "pre-sales"),
    (r"consultant", "consultant"),
    (r"founder|co[- ]?founder", "founder"),
    (r"designer|设计师", "designer"),
    (r"增长|growth (?:manager|lead|analyst)", "growth"),
    (r"(?:qa|test|quality)\s*(?:engineer|analyst|automation)|测试工程师|自动化测试|质量工程师", "qa engineer"),
    (r"marketing|市场|营销", "marketing"),
    (r"sales|销售|商务拓展|\bBD\b", "sales"),
    (r"project manager|项目经理|delivery manager", "project manager"),
    (r"运营(?!商)|operations? (?:manager|analyst|specialist)", "operations"),
]
# 中文职位名并进上面那张表（同一个键，正则里用 | 连起来）
_CN = {"product manager": r"产品经理|产品负责人", "data analyst": r"数据分析师?|商业分析师?|数据运营|BI 分析",
       "data scientist": r"数据科学家|算法工程师", "ml engineer": r"机器学习工程师|算法工程师",
       "software engineer": r"软件工程师|开发工程师|研发工程师", "consultant": r"顾问|咨询顾问",
       "founder": r"创始人|联合创始人", "designer": r"设计师"}
TITLE_RX = [((rx + "|" + _CN[name]) if name in _CN else rx, name) for rx, name in TITLE_RX]
MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
# 英文式：Nov 2020 – Jul 2022 / 2020 - 2022
RANGE = re.compile(r"(?:(%s)\w*\s+)?(\d{4})\s*[–\-—~至]+\s*(?:(%s)\w*\s+)?(\d{4}|present|now|至今|now)" % (MONTHS, MONTHS), re.I)
# 中文/点号式：2024.03 - 2026.04 · 2024年3月-2026年4月 · 2024/03-至今
# ⚠ 这条是拿真简历跑出来才补的：第一版只认英文月份，中文简历整份日期一条都没认出来，
# 总年限直接变成 None（2026-08-27 实测，陈若龙那份 6 年经验被算成 0）。
# ⚠ 「至今」要先于分隔符判：分隔符类里含「至」，会把「至今」的「至」吃掉、只剩「今」，
# 于是「2025.09 至今」整条不匹配（实测一份简历最近那段工作因此没被算进年限）。
RANGE_CN = re.compile(r"(\d{4})\s*[./年]\s*(\d{1,2})?\s*月?\s*"
                      r"(?:至今|now|present|[–\-—~至到]+\s*(?:至今|now|present|"
                      r"(\d{4})\s*[./年]\s*(\d{1,2})?\s*月?))", re.I)
MIDX = {m: i + 1 for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split())}


def read_text(path):
    p = path.lower()
    if p.endswith(".txt"):
        return io.open(path, encoding="utf-8", errors="replace").read()
    if p.endswith(".docx"):
        import zipfile
        x = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
        t = re.sub(r"<w:p[ >]", "\n", x)
        return re.sub(r"<[^>]+>", "", t)
    if p.endswith(".pdf"):
        import subprocess
        for cmd in (["pdftotext", "-layout", path, "-"], ["python3", "-m", "pdfminer.high_level", path]):
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if r.returncode == 0 and len(r.stdout) > 200:
                    return r.stdout
            except Exception:
                pass
        raise SystemExit("读不出 PDF 正文，先转成 .txt 或 .docx 再跑（brew install poppler 可装 pdftotext）")
    raise SystemExit("只认 .pdf / .docx / .txt")


def months_between(y1, m1, y2, m2):
    return max(0, (y2 - y1) * 12 + (m2 - m1))


def main():
    src, outdir = sys.argv[1], sys.argv[2]
    raw = unicodedata.normalize("NFKC", read_text(src))
    low = raw.lower()
    today = date.today()

    # ---- 年限：按「同一行里既有 title 又有日期区间」来算专项 ----
    spans = []           # (title 或 None, 月数)
    lines = raw.split("\n")
    for idx, line in enumerate(lines):
        m = RANGE.search(line)
        mc = RANGE_CN.search(line)
        if not m and not mc:
            continue
        if mc:
            sy, m1 = int(mc.group(1)), int(mc.group(2) or 1)
            if mc.group(3):
                y2, m2 = int(mc.group(3)), int(mc.group(4) or 12)
            else:
                y2, m2 = today.year, today.month
        else:
            sm, sy, em, ey = m.group(1), int(m.group(2)), m.group(3), m.group(4)
            y2 = today.year if not ey.isdigit() else int(ey)
            m2 = today.month if not ey.isdigit() else (MIDX.get((em or "jan").lower()[:3], 1))
            m1 = MIDX.get((sm or "jan").lower()[:3], 1)
        if sy < 1990 or y2 > today.year + 1:
            continue
        mo = months_between(sy, m1, y2, m2)
        if mo <= 0 or mo > 600:
            continue
        # ⚠ 2026-08-28：职位名和日期**常常不在同一行**（实测一份测试工程师简历，
        # 「网易popo — 自动化测试工程师(派驻)」在上一行、「2025.09 至今」在下一行），
        # 只看本行会让每一段的 title 都是 None，专项年限整个变成空的。往回看两行。
        ctx = " ".join(lines[max(0, idx - 2): idx + 1])
        title = None
        for rx, name in TITLE_RX:
            if re.search(rx, ctx, re.I):
                title = name
                break
        spans.append((title, mo, sy, m1, y2, m2, line.strip()[:90]))
    # 学历段要排除（它们也是日期区间，但不是工作年限）
    spans = [s for s in spans if not re.search(r"university|bachelor|\bbsc\b|\bmsc\b|master|degree|大学|学院", s[6], re.I)]

    # ⚠ 2026-08-28：**区间重叠不能相加**。实测那份简历里
    # 「服务端测试(2023.06 — 2024.03)」和「客户端测试(2021.07 — 2023.06)」
    # 是「2021.07 — 2024.03」那一段的两个子区间，三段一加总年限虚高到 6.7 年。
    # 正解：把区间并起来再量长度（同一段时间只算一次）。
    def merge_months(items):
        iv = sorted((sy * 12 + m1, y2 * 12 + m2) for _, _, sy, m1, y2, m2, _ in items)
        out = []
        for a, b in iv:
            if out and a <= out[-1][1]:
                out[-1][1] = max(out[-1][1], b)
            else:
                out.append([a, b])
        return sum(b - a for a, b in out)

    total = round(merge_months(spans) / 12, 1) if spans else None
    title_years = {}
    for rx, name in TITLE_RX:
        sub = [s for s in spans if s[0] == name]
        title_years[rx] = round(merge_months(sub) / 12, 1) if sub else 0.0

    # ---- 能力：清单逐项找证据 ----
    has, lacks, evidence = [], [], {}
    for rx, name in CHECKLIST:
        m = re.search(rx, low)
        if m:
            i = max(0, m.start() - 60)
            has.append(rx); evidence[name] = raw[i:m.end() + 60].replace("\n", " ").strip()
        else:
            lacks.append(rx)

    out = dict(source=os.path.basename(src), confirmed=False,
               years_total=total, title_years=title_years,
               has=has, lacks=lacks, partial=PARTIAL,
               _evidence=evidence,
               _spans=[dict(title=t, years=round(mo / 12, 1), line=l) for t, mo, _, _, _, _, l in spans],
               _note="confirmed 改成 true 之前不会出分。请逐条核 title_years 和 lacks——"
                     "lacks 的意思是「这份简历里没找到」，不是「他一定没有」。")
    os.makedirs(outdir, exist_ok=True)
    json.dump(out, io.open(outdir + "/facts.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    io.open(outdir + "/CV.txt", "w", encoding="utf-8").write(raw)
    print("→ %s/facts.json" % outdir)
    print("总年限 %s 年" % total)
    print("专项年限：" + " · ".join("%s %g年" % (n, title_years[rx]) for rx, n in TITLE_RX if title_years[rx] > 0))
    print("简历上找到 %d 项 / 没找到 %d 项" % (len(has), len(lacks)))


if __name__ == "__main__":
    main()
