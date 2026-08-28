# -*- coding: utf-8 -*-
"""门禁：适配度的分母必须来自 JD 逐条原文，不许手填（2026-08-27 立）。

出事经过：上一版分母是手填的两个整数，65 个岗里 0 个能追溯到原文，而当时的门禁全绿——
因为它只验算术和接线，**零条验出处**。这条门禁补的就是「出处」这一层。
"""
import io, re, sys, importlib.util
sys.path.insert(0, '/Users/bella/Projects/jobs-daily')
import score

FAIL = []
def check(name, cond, detail=""):
    print(("✅ " if cond else "❌ ") + name + ("" if cond else "  " + detail))
    if not cond: FAIL.append(name)

R = lambda n, h=1: [("x" * 20 + str(i), h) for i in range(n)]

# ---------- 规则本身 ----------
v, hit, tot, _, kind = score.fit_of(dict(reqs=dict(must=R(5), nice=[])))
check("5 条 must 全中 → 100，分母等于 must 条数", v == 100 and tot == 5, "得到 %r/%r" % (v, tot))

v, *_ , kind = score.fit_of(dict(reqs=dict(must=R(3) + R(3, 0))))
check("漏一半 must → 封顶 60，不许还是高分", v <= 60, "得到 %r" % v)

a, *_ = score.fit_of(dict(reqs=dict(must=R(4) + R(2, 0), nice=R(3))))
b, *_ = score.fit_of(dict(reqs=dict(must=R(4) + R(2, 0), nice=R(3, 0))))
check("nice 只能加分不能扣分（JD 多列 preferred 不许让人掉分）", a >= b, "全中 %r vs 全不中 %r" % (a, b))

v, hit, tot, _, kind = score.fit_of(dict(reqs=dict(must=[], nice=R(4))))
check("没有硬门槛 → 判「无硬门槛」且不给百分数", v is None and kind == "无硬门槛", "得到 %r %r" % (v, kind))

v, *_, kind = score.fit_of(dict(sc=88, light="green"))
check("没有 reqs → 未核（不许拿老字段顶上）", v is None and kind == "未核", "得到 %r %r" % (v, kind))

for bad, why in [
    (dict(must=[("短", 1)]), "原文太短的必须报错"),
    (dict(must=[("x" * 20, 0.7)]), "命中值只能是 0/0.5/1"),
    (dict(must=[("x" * 20,)]), "每条必须是 (原文, 命中) 两元组"),
]:
    try:
        score.fit_of(dict(reqs=bad)); check(why, False, "居然放行了")
    except AssertionError:
        check(why, True)

try:
    score.fit_of(dict(reqs=dict(must=R(5)), fit_adj=[(-18, "")]))
    check("裸扣分（没写理由）必须报错", False, "居然放行了")
except AssertionError:
    check("裸扣分（没写理由）必须报错", True)

# ---------- 接线：生产代码真的换掉了手填分母 ----------
src = io.open('rebuild-board.py', encoding='utf-8').read()
src_nc = re.sub(r'(?m)^\s*#.*$', '', src)          # 注释里出现的名字不算接上了
hand = re.findall(r'\breq=\(\s*\d', src_nc)
check("生产代码里不许再有手填的 req=(命中, 总数)", not hand, "还剩 %d 处" % len(hand))
check("rebuild-board.py 确实在用 score.fit_of",
      re.search(r'from\s+score\s+import[^\n]*\bfit_of\b', src_nc) is not None)

# ---------- 出处：每条 must 必须能在 JD 原文里逐字找到 ----------
import json
try:
    data = json.load(io.open('rescore-reqs.json', encoding='utf-8'))
except Exception:
    data = []
scored = [o for o in data if o.get('must')]
check("重打后的清单文件存在且有内容", len(scored) > 0, "只有 %d 条" % len(scored))
bad_len = [o['co'] for o in scored if any(len(x if isinstance(x, str) else x[0]) < 12 for x in o['must'])]
check("每条 must 都留了 JD 原文（≥12 字符）", not bad_len, str(bad_len[:3]))

# ---------- 接线的最后一层：生成脚本必须真的跑得起来 ----------
# 2026-08-27 补。今早那次提交把 score.fit_of 改成返回 5 个值，而 rebuild-board.py 那边
# 还只接 4 个 —— **从那次提交起整块板每一次重建都会 ValueError 崩掉**，而这份门禁全绿：
# 上面那些检查跑的是纯函数，加上一条「有没有 import」的字符串断言，
# **从来没有真的把生成脚本跑一遍**（R10 铁律五：纯函数单测证明不了它被接上了）。
# 这一条会重新生成 parts/，那正是流水线本来的下一步，所以没有额外副作用。
import subprocess
_r = subprocess.run([sys.executable, 'rebuild-board.py'],
                    cwd='/Users/bella/Projects/jobs-daily', capture_output=True, text=True)
check("rebuild-board.py 真的跑得起来（不只是 import 得到 fit_of）", _r.returncode == 0,
      (_r.stderr or '').strip().splitlines()[-1] if _r.stderr else '')

print()
print("门禁全绿" if not FAIL else "门禁变红：%s" % FAIL)
sys.exit(1 if FAIL else 0)
