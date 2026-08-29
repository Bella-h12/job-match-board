# -*- coding: utf-8 -*-
"""零网络回归测试。跑：python3 tests/test_pipeline.py

守的是这套东西的几条命根子——每一条都是真出过事才写的：
· 分母必须来自 JD 原文，不许手填（原版 70 个岗里 0 个能追溯，而门禁当时全绿）
· 没有硬门槛的岗不给 100（一个写着「not a fixed job description」的岗曾坐在榜首）
· 条数太少不算清单（1/1 = 100% 曾排到榜眼）
· nice 只能加分（JD 多列 preferred 反而让人掉分，方向就是反的）
· 专项年限不许拿总年限顶，也不许被「或列表」豁免
· facts 没本人确认 → 拒绝出分
· 中文简历的日期要认得出来（只认英文时，6 年经验被算成 0 年）
"""
import io, json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import facts as F
import score
import importlib.util
spec = importlib.util.spec_from_file_location("er", os.path.join(ROOT, "scripts", "extract_reqs.py"))
er = importlib.util.module_from_spec(spec); spec.loader.exec_module(er)

FAIL = []
def ck(name, cond, detail=""):
    print(("  ✅ " if cond else "  ❌ ") + name + ("" if cond else "   " + str(detail)))
    if not cond: FAIL.append(name)

R = lambda n, h=1: [("x" * 20 + str(i), h) for i in range(n)]

print("打分规则")
v, hit, tot, _, kind = score.fit_of(dict(reqs=dict(must=R(5))))
ck("5 条全中 = 100，分母等于条数", v == 100 and tot == 5, (v, tot))
v, *_ = score.fit_of(dict(reqs=dict(must=R(3) + R(3, 0))))
ck("漏一半 must → 封顶 60", v <= 60, v)
a, *_ = score.fit_of(dict(reqs=dict(must=R(4) + R(2, 0), nice=R(3))))
b, *_ = score.fit_of(dict(reqs=dict(must=R(4) + R(2, 0), nice=R(3, 0))))
ck("nice 只加分不扣分", a >= b, (a, b))
v, _, _, _, kind = score.fit_of(dict(reqs=dict(must=[], nice=R(4))))
ck("没有硬门槛 → 不给百分数，单独标类别", v is None and kind == "无硬门槛", (v, kind))
v, _, _, _, kind = score.fit_of(dict(reqs=dict(must=R(1))))
ck("只抠出 1 条 → 判未核，不判 100", v is None and kind == "未核", (v, kind))
v, _, _, _, kind = score.fit_of(dict(sc=88))
ck("没有 reqs → 未核", v is None and kind == "未核", kind)
for bad, why in [(dict(must=[("短", 1)]), "原文太短要报错"),
                 (dict(must=[("x" * 20, 0.7)]), "命中值只能 0/0.5/1")]:
    try:
        score.fit_of(dict(reqs=bad)); ck(why, False, "居然放行")
    except AssertionError:
        ck(why, True)

print("公司发展两问（确定性，从 JD 文本）")
g = score.growth_from_jd("We build LLM agents. Our agentic platform uses RAG and prompt engineering. " * 5, "Acme")
ck("AI 词密度高 → ai=yes", g["ai"] == "yes", g)
g = score.growth_from_jd("Our client, a bank, is hiring a QA engineer via our staffing team.", "Hire Feed")
ck("代招字眼 → principal=no", g["principal"] == "no", g)
g = score.growth_from_jd("We are a bank hiring a QA engineer for our own team.", "Bank")
ck("没有代招字眼 → principal=yes", g["principal"] == "yes", g)
v, d = score.growth_of(dict(growth_by=dict(ai="yes", principal="no", growing="yes", durable="na")))
ck("三问核出 25+0+25、第四问未核不进分母 → 67", v == 67 and len(d) == 4, (v, d))
v, d = score.growth_of(dict(growth_by=dict(ai="na", principal="na", growing="na", durable="na")))
ck("四问全未核 → None（不是 0）", v is None, v)
gv, gw = score.growing_from_company(dict(growth_2y=45, tenure=2.3))
ck("两年增速 45% → growing=yes", gv == "yes", (gv, gw))
gv, gw = score.growing_from_company(dict(growth_2y=45, tenure=1.1))
ck("增速高但任期 1.1 年 → 降一档", gv == "half", (gv, gw))
gv, gw = score.growing_from_company(None)
ck("没抓到公司页 → na 不猜", gv == "na", gv)

print("逐条判定（拿一份合成事实清单）")
j = F.Judge(dict(years_total=5, title_years={r"product (manage(ment|r)|owner)": 0,
                                             r"data analyst|analytics": 5},
                 has=[r"\bsql\b", r"\bpython\b"], lacks=[r"\barabic\b", r"pre[- ]?sales"], partial=[]))
ck("专项年限不拿总年限顶：6 年 PM → 不命中",
   j.judge("6+ years of product management experience")[0] == 0)
ck("专项够 → 命中：3 年 analytics", j.judge("3+ years in analytics")[0] == 1)
ck("总年限不够 → 不命中：10 年", j.judge("10 years of experience")[0] == 0)
ck("专项年限不许被「或列表」豁免",
   j.judge("Bachelor's degree or equivalent with 5+ years in a Pre-Sales role")[0] == 0)
ck("或列表：占其中一项就算", j.judge("Proficient in Python, Java, or Go")[0] == 1)
ck("简历上没有的判 0", j.judge("Native Arabic speaker required")[0] == 0)

print("JD 逐条抽取")
JD = """About the job
About Us
We are a fast growing team.
What we're looking for
- 5+ years of experience in data analysis
- Strong SQL and Python
- Experience with dashboards
Nice to have
- Arabic language
Benefits
- Health insurance
"""
e = er.extract(JD)
ck("按 JD 自己的段标题分 must / nice", len(e["must"]) == 3 and len(e["nice"]) == 1, (len(e["must"]), len(e["nice"])))
ck("福利段不算要求", not any("insurance" in x.lower() for x in e["must"]))

print("事实清单的闸门")
with tempfile.TemporaryDirectory() as d:
    json.dump(dict(confirmed=False, has=[], lacks=[]), io.open(d + "/facts.json", "w", encoding="utf-8"))
    try:
        F.load(d); ck("没确认 → 必须拒绝出分", False, "居然放行")
    except SystemExit:
        ck("没确认 → 必须拒绝出分", True)

print("简历解析（中英文都要认）")
with tempfile.TemporaryDirectory() as d:
    cn = "张三\n某公司|数据分析师   2019.07 - 2022.05\n某公司|产品经理  2022.06 - 至今\n技能:SQL、Python\n"
    io.open(d + "/cv.txt", "w", encoding="utf-8").write(cn)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_facts.py"), d + "/cv.txt", d],
                       capture_output=True, text=True)
    ok = r.returncode == 0 and os.path.exists(d + "/facts.json")
    f = json.load(io.open(d + "/facts.json", encoding="utf-8")) if ok else {}
    ck("中文简历能算出总年限（只认英文时这里是 None）",
       bool(f.get("years_total")) and f["years_total"] > 2, f.get("years_total"))
    ck("中文职位名能对上专项年限",
       any(v > 0 for k, v in (f.get("title_years") or {}).items() if "data analyst" in k), f.get("title_years"))
    ck("草稿默认 confirmed=false", f.get("confirmed") is False)

print("简历解析（陌生简历撞出来的四个坑）")
with tempfile.TemporaryDirectory() as d:
    cv = ("李四\n某公司 — 自动化测试工程师(派驻)\n2025.09 至今\n负责……\n"
          "另一公司 — 测试工程师\n2021.07 — 2024.03\n服务端测试(2023.06 — 2024.03):\n客户端测试(2021.07 — 2023.06):\n"
          "技能: Python, pytest\n")
    io.open(d + "/cv.txt", "w", encoding="utf-8").write(cv)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "make_facts.py"), d + "/cv.txt", d],
                       capture_output=True, text=True)
    f = json.load(io.open(d + "/facts.json", encoding="utf-8")) if r.returncode == 0 else {}
    qa = next((v for k, v in (f.get("title_years") or {}).items() if "qa" in k), 0)
    ck("职位名在日期上一行也认得出（专项年限不为空）", qa > 3, f.get("title_years"))
    ck("重叠区间合并不相加（2021.07–2024.03 的两个子段不能算两遍）",
       f.get("years_total") and 3.5 <= f["years_total"] <= 4.2, f.get("years_total"))
    ck("「2025.09 至今」能解析（最近那段要算进去）",
       any("至今" in x.get("line", "") for x in f.get("_spans", [])), [x.get("line") for x in f.get("_spans", [])])
    ck("方向从简历推出（QA 简历不许被推成 Data Analyst）",
       any("QA" in x or "SDET" in x or "Test" in x for x in f.get("suggested_roles", [])), f.get("suggested_roles"))

print()
print("全绿" if not FAIL else "变红：%s" % FAIL)
sys.exit(1 if FAIL else 0)
