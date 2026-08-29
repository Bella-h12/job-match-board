# -*- coding: utf-8 -*-
"""把一份 board.json 渲染成看板的各个片段（parts/*.html）。

这是从一块跑了一个月的真实看板里**原样抽出来的渲染层**，所以格式一模一样，换的只是数据。
原文件 3669 行里 2735 行是那个人的岗位内容（已移进 board.json），剩下这 900 多行才是模板。

用法：python3 scripts/board/render.py <workspace 目录>
读 <ws>/board.json + <ws>/config.json，写 <ws>/parts/*.html
"""
import datetime, html, io, json, os, re, subprocess, sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # scripts/

WS = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
PARTS = os.path.join(WS, "parts")
os.makedirs(PARTS, exist_ok=True)
# 静态模板件（侧栏骨架、交互脚本、样式、皮肤）每次从 assets/board/ 铺进工作区。
# **产物的身份不许从上一版继承**，否则被写脏一次就永久粘住。
_ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "assets", "board")
if os.path.isdir(_ASSETS):
    import shutil
    for _f in os.listdir(_ASSETS):
        shutil.copyfile(os.path.join(_ASSETS, _f), os.path.join(PARTS, _f))
    # 品牌行 / 标题是**身份字段**，每次从用户配置归一，不从上一版产物继承。
    # 2026-08-29 实锤：模板件是从原版看板原样拷的，侧栏写着「UAE 求职作战板 8-28」、
    # 标题写着「UAE 求职看板」——一个找美国 QA 岗的人打开看到的是别人的地区和日期。
    _cfg0 = json.load(io.open(os.path.join(WS, "config.json"), encoding="utf-8"))
    _b0 = json.load(io.open(os.path.join(WS, "board.json"), encoding="utf-8"))
    _brand = "%s · 求职作战板" % (_cfg0.get("display_name") or _cfg0.get("name") or "")
    _d = (_b0.get("today") or "")[5:].replace("-0", "-").replace("-", "-")
    _nav_path = os.path.join(PARTS, "nav.html")
    _n = io.open(_nav_path, encoding="utf-8").read().replace("{{BRAND}}", _brand).replace("{{DATE}}", _d)
    io.open(_nav_path, "w", encoding="utf-8").write(_n)

_B = json.load(io.open(os.path.join(WS, "board.json"), encoding="utf-8"))
_CFG = json.load(io.open(os.path.join(WS, "config.json"), encoding="utf-8"))
JOBS = _B["jobs"]
PAY_FLOOR = _CFG.get("pay_floor_monthly") or 0      # 以前写死 25000
CALLOUTS = _B.get("callouts") or []                 # 「二选一」这类人工提示，没有就不渲染
_t = _B.get("today")
TODAY = datetime.date(*[int(x) for x in _t.split("-")]) if _t else date.today()
DELTA_LBL = "今日"


def days(d):
    if not d:
        return None
    if isinstance(d, str):
        d = [int(x) for x in d.split("-")]
    return (TODAY - datetime.date(*d)).days


# ------------------------------------------------- 排序：可复算的公式
# ================================================================ 评分（2026-08-14 Bella 改口径）
# Bella 的原话：「薪资、公司发展、适配度这三个指标很重要。2 4 4 的比重。」
# 所以总分不再是七项相加，而是**三项加权，满分 100**：
#
#     总分 = 0.2×薪资 + 0.4×公司发展 + 0.4×适配度
#
# 其余四项的去处（都不进分数，理由各不相同）：
#   · 门槛（年限硬杠）→ **闸门不是加权项**（R7 2026-08-03）：年限是 HR 硬筛的第一道，
#     别的项全满分也不该把它抬回「强匹配」。所以硬挡的岗**总分封顶 60**，卡上明写。
#   · 时效 / 竞争 / 摩擦 → 进**动作分档**和 chip，不进排序（R18-3：增速高说明窗口在关，
#     不说明这个岗更好；摩擦决定今天做还是本周做）。同分时它们仍是裁决键。
#
# ⚠ 这次改动会让**整板分数一次性全变**，页面上必须写清楚，否则看起来像发生了什么事
#   （R18-4）。旧分是 44–101 的加总分，新分是 0–100 的加权分，两套数字不可比。
LIGHT_W = dict(green=6, yellow=0, red=-12)     # 只留给旧展示用，不再进总分
GATE_TXT = dict(ok="够得着", na="未写死", high="偏高", wall="硬挡")

W_PAY, W_GROWTH, W_FIT = 0.2, 0.4, 0.4
WALL_CAP = 60          # 年限硬挡 → 总分封顶

# 适配度 / 公司发展的唯一出口在 score.py（提出去是为了让门禁跑得到生产函数本身）
from score import GROWTH_DIMS, GROWTH_SCALE, GROWTH_MARK, fmtnum, growth_of, fit_of


# 薪资（0–100）——**只认证据，绝不估**。2026-08-14 实测 114 份 JD：出现钱的数字的 18 份，
# 而其中**只有 8 份是这个岗自己的薪酬**，其余是融资额（$781M raised）、办公补贴（$500
# stipend）、以及**推荐位里别家公司别的岗**的薪酬——正是 R18-2 那个坑。所以：
#   pay_aed = JD 明写的**月薪**（AED，取区间中值；美元年薪按 /12 折 AED 换算后填）
#   pay_sig = 没有数字但 JD 明写股权 / RSU / 住房补贴 / "top of the benchmark" → 40
#   两者都没有 → **该维度不计入**，权重归一到 0.5/0.5，卡上写「薪资未披露 · 未计入」。
#   给 0 是在惩罚「没披露」，给 50 是在编一个数，两个都不对。
# 一条实测规律：**写薪资的几乎全是猎头/招聘代理发的帖，甲方自己发的基本不写。**
def pay_score(j):
    a = j.get("pay_aed")
    if a is not None:
        if PAY_FLOOR and a < PAY_FLOOR: return 0        # 低于她的底线，这一项就是 0，不是「没数据」
        if a < 30000: return 50
        if a < 35000: return 65
        if a < 40000: return 80
        if a < 50000: return 90
        return 100
    if j.get("pay"): return 40        # 只有结构性信号（股权/RSU/住房补贴）
    return None                        # 未披露 → 不计入

def freshness(d):
    if d is None: return 0          # 页面没给发布天数：不加分也不猜（原版每岗都有，新用户不一定）
    if d <= 2: return 6
    if d <= 7: return 4
    if d <= 14: return 2
    return 0

def crowd(j):
    """竞争扣分。两个口径的数字含义差一个量级（点了跳转 vs 真的投了），
    所以各定各的阈值，绝不把一边换算成另一边。页面上两条阈值都写出来。"""
    a = j.get("applicants")
    if a is not None:                       # Easy Apply：真实申请人数
        if a > 1000: return -4
        if a > 400: return -2
        return 0
    c = j.get("clicked")                    # 站外申请：点击跳转人数
    if c is None: return 0
    if c > 1500: return -4
    if c > 800: return -2
    return 0

# 已投的岗从在投池和 Top 10 里整体剔除——它们的状态归第二部分的投递台账管。
# 2026-08-10 加：此前 Ode 和 Murphy PM 一直挂在待投位置上（还标着「未投第 19 天」），
# 实际 8-3 就投了、Ode 8-6 已被拒——因为走的是公司 ATS，LinkedIn 一无所知。
APPLIED = [j for j in JOBS if j.get("applied")]
JOBS = [j for j in JOBS if not j.get("applied")]
# 2026-08-12 加：有些岗不是「没投」，是「现在投不了」（同域冷却 / 同时只准一个 live application）。
# 留在待投位置上＝每天推一个点了也没用的动作，属于「谁乐观谁赢」。单独成段并写明解冻条件。
BLOCKED = [j for j in JOBS if j.get("blocked")]
JOBS = [j for j in JOBS if not j.get("blocked")]
# 2026-08-16 加：**「已关闭」和「现在投不了」是两回事**，此前没有前者的出口，
# 差点被塞进 blocked（那一段写的是冷却和二选一，语义不对）。关闭的岗整条退出在投池，
# 归档的「已关闭」段留一行痕——判死也好、窗口自己关也好，都不许让它无声消失。
# ------------------------------------------------- 盲掉的渠道（2026-08-20 加）
# R43：「连续第 N 天」这种数**必须去查历史**，不许沿用上一版正文里写的那个数——
# 8-20 实测：看板连着好几天印「163 连续第二天没查成」，回查 applications.json 的
# git 历史才发现 8-15 起每天的 last_error 都是同一句，真值是 6 天。错的方向永远是低估，
# 因为抄来的数只会比真值旧。所以这里现算，不接受任何手写的天数。
try:
    _apps_live = json.load(io.open(os.path.join(WS, 'applications.json'), encoding='utf-8'))
except Exception:
    _apps_live = {}


def _blind_days_by_channel():
    """每条渠道各自连续失败了几天。

    ⚠ 第一版是「数任意渠道有错的天数，再贴上今天那个渠道的名字」——
    8-20 晚上 Gmail 刚掉登录（当天早上还好好的 40 行），页面上立刻印出
    「gmail 已盲 6 天」：那 6 天是 163 的。**两件事粘成一个数，而且名字取得像。**
    这就是 R7 那条：一个对外的数字，它算的必须是它自称的那个东西。
    last_error 的格式是 "<渠道>: 说明"，所以按渠道前缀分别数。
    """
    import subprocess, json as _json
    try:
        revs = subprocess.run(
            ['git', '-C', WS, 'log',
             '--format=%H', '--', 'applications.json'],
            capture_output=True, text=True, timeout=30).stdout.split()
    except Exception:
        return {}
    # 2026-08-22 修：原来是「按 | 切开，冒号前面那一截就是渠道名」。
    # 但**单条错误信息里本来就带 |**（163 的报错会把页面标题和正文头一起贴进来：
    # `mail163: ... | 页面现场={'t': '163网易免费邮...'}`），于是页面上印出了一条
    # 叫「页面现场={'t'」的渠道，还煞有介事地写着「已盲 1 天」。
    # 渠道名是脚本自己写的 ASCII 标识（gmail / mail163 / linkedin），
    # 判据收窄成「小写字母开头的 ASCII 标识 + 冒号」，中文那一截就落不进来了。
    _CH = re.compile(r'^([a-z][a-z0-9_]{2,19}):')

    def _chans(err):
        out = set()
        for part in (err or '').split('|'):
            m = _CH.match(part.strip())
            if m:
                out.add(m.group(1))
        return out

    # ⚠ git show 读的是**已提交**的版本。工作区里刚改过的 applications.json 还没提交时，
    # hist[0] 会是上一次提交的状态 —— 8-20 晚上就这么印出「mail163 已盲 2 天」，
    # 而 163 当时已经修好了。**当前状态的事实源是磁盘上那份文件，不是最后一次提交。**
    per_day = {}                                # {日期: [{渠道...}, ...]}，一天可能有好几次记录
    _live_day = (_apps_live.get('last_checked_at') or '')[:10]
    if _live_day:
        per_day.setdefault(_live_day, []).append(_chans(_apps_live.get('last_error')))
    for rev in revs:
        try:
            blob = subprocess.run(
                ['git', '-C', WS, 'show', rev + ':applications.json'],
                capture_output=True, text=True, timeout=30).stdout
            dd = _json.loads(blob)
        except Exception:
            continue
        day = (dd.get('last_checked_at') or '')[:10]
        if not day:
            continue
        # ⚠ 2026-08-21 修：原来是「同一天只取最新那次提交」（`if day in seen: continue`）。
        # 8-20 那天有两次记录 —— 早班 09:07 Gmail 好好的 40 行、晚上 22:08 才掉登录 ——
        # 取最新那次就把 8-20 算成了「Gmail 盲的一天」，于是今天页面印「已盲 2 天」，
        # 而真相是**今天才是第一个拿不到它的早班**。
        # 判据改成：**一天里只要有过一次成功，这天对那条渠道就不算盲**（按天取交集）。
        # 同 R47：一个复合统计要说清「按什么分组、数到哪一天为止、事实源是谁」；
        # 这里错的是第一条——分组的单位是「天」，但天里面有好几次记录。
        per_day.setdefault(day, []).append(_chans(dd.get('last_error')))
    # 每天取交集：那天所有记录里都报错的渠道，才算这天是盲的。
    hist = [(d, set.intersection(*sets) if sets else set())
            for d, sets in sorted(per_day.items(), reverse=True)]
    out = {}
    for ch in (hist[0][1] if hist else set()):  # 只关心「今天正在盲」的那几条
        n = 0
        for _day, chans in hist:
            if ch in chans:
                n += 1
            else:
                break                            # 数的是**连续**，断了就停
        out[ch] = n
    return out

_apps = _apps_live
_blind = _blind_days_by_channel() if _apps.get('last_error') else {}
if _blind:
    # 多条同时盲就都列出来，别合并成一个数（合并＝又一次把两件事粘成一个）
    # 渠道名在数据里是脚本的 ASCII 标识，印给人看要换成她认得的说法
    _CH_LABEL = {'gmail': 'Gmail', 'mail163': '163 邮箱', 'linkedin': 'LinkedIn 投递列表'}
    BLIND_CHANNELS = ' · '.join(
        '%s 已盲 <b>%d</b> 天' % (_CH_LABEL.get(ch, ch), n)
        for ch, n in sorted(_blind.items(), key=lambda x: -x[1]))
else:
    BLIND_CHANNELS = None
print("盲渠道:", BLIND_CHANNELS)

CLOSED_TODAY = [j for j in JOBS if j.get("closed")]
JOBS = [j for j in JOBS if not j.get("closed")]
print("今天关闭退出在投池:", [(j["co"], j["role"][:26], j["closed"]) for j in CLOSED_TODAY] or "无")

for j in JOBS:
    # 2026-08-07 证伪：页面的 "in the past day" 字段不是新增人数（已关闭的岗还在报新增）。
    # 字段已从数据里删除；这条断言防止它被重新引入并悄悄渲染出去。
    assert "clicked_day" not in j and "applicants_day" not in j, ("已废弃的日增量字段", j["id"])
    # ⚠ 2026-08-27 修：score.fit_of 今早改成返回 5 个值（多了 kind），这里还只接 4 个，
    # 于是整块板从今早那次提交起就**跑不起来**（ValueError），而 gate-fit.py 全绿——
    # 它只跑纯函数和「有没有 import」，从没真的把 rebuild-board 跑一遍（R10 铁律五）。
    j["v_fit"], j["fit_hit"], j["fit_total"], j["fit_adj_d"], j["fit_kind"] = fit_of(j)
    j["v_growth"], j["growth_detail"] = growth_of(j)
    j["v_pay"] = pay_score(j)
    # 2026-08-22：两个核心维度都可能是 None＝未核。**未核不许拿数顶上**，
    # 也不许把它从公式里悄悄剔掉当没发生（那等于让缺判据的岗跟判据齐全的岗同台排名）。
    # 缺任何一个 → 这个岗**没有优先级**，进「判据未核」段，页面上明写缺哪一条。
    # 适配度为 None 有两种原因，页面上不许说成同一种：
    #   「未核」＝没抄清单（我的欠账）；「无硬门槛」＝JD 自己就没有可筛的硬条件（核过了，结论就是没有）。
    # 都不给百分数、都不进匹配榜，但说法必须分开——把后者写成「还没核过」是在页面上说一句假话。
    _fitmiss = {"未核": "适配度未核", "无硬门槛": "JD 无硬门槛"}.get(j.get("fit_kind"), "适配度未核")
    j["unscored"] = ([_fitmiss] if j["v_fit"] is None else []) + (["公司发展未核"] if j["v_growth"] is None else [])
    # chip / 动作分档 / 同分裁决用的几项，未核的岗也要有（它们不进总分）
    j["p_fresh"] = freshness(j["posted"])
    j["p_crowd"] = crowd(j)
    j["p_fric"] = 3 if "Easy Apply" in j["apply"] else 0
    if "first_seen" in j:
        j["backlog"] = days(j["first_seen"])
    if j["unscored"]:
        j["prio_raw"] = None
        j["prio"] = None
        j["capped"] = False
        j["w_used"] = "未核"
        continue
    if j["v_pay"] is None:
        # 未披露：不计入，权重归一到 0.5 / 0.5（不给 0＝不惩罚没披露，不给 50＝不编数）
        raw = 0.5 * j["v_fit"] + 0.5 * j["v_growth"]
        j["w_used"] = "fit50/growth50"
    else:
        raw = W_PAY * j["v_pay"] + W_GROWTH * j["v_growth"] + W_FIT * j["v_fit"]
        j["w_used"] = "pay20/growth40/fit40"
    j["prio_raw"] = round(raw)
    # 年限硬挡＝筛选闸门，不是扣分项：别的项全满分也不该抬回强匹配档
    j["capped"] = j["gate"] == "wall" and j["prio_raw"] > WALL_CAP
    j["prio"] = WALL_CAP if j["capped"] else j["prio_raw"]

# 2026-08-13 起分组标准换了：Bella 要的导航是「按一个人从申请到拿面试的流程」走，
# 第一段「今日待申请」下面分 (a) 近一周内发布 (b) 其他。所以这里不再按
# 「今天是不是第一次进池」（g=new/old）分，改按**岗位本身的发布时间**分——
# 前者是本页的内部账，后者才是她做决定时真正在意的东西（新坑池子浅、竞争少）。
# ---------------------------------------------------------------- 层级闸门
# 2026-08-13 Bella 定：「明显在你范围之外的就不用考虑了 —— 没有 leadership
# 经验就别投 VP / Lead」。按 R7 2026-08-03，**筛选闸门型条件不能只当加权项**：
# 层级是 HR 硬筛的第一道，别的项全满分也不该把它抬回在投池。所以这里是
# 硬排除，不是扣分。
#
# 判据只看职位名里的层级词，且按 R7 2026-08-07 ④「判死比放行更需要证据」：
# 每条被排除的都要在归档里写出**命中的是哪个词**，引得出原文才算数。
# 事实来源：job-applications/PROFILE.md —— 总工作年限 5+，
# **PM / Product Owner title 年限 = 0**，无管理 title。
import re as _re
# 2026-08-25 修一条真的假阳性：这条闸门给出的理由是「无管理 title」，
# 而 **Staff / Principal 在技术业里是 IC 序列的职级词，根本不是管理 title**——
# 今天 Deel「Staff Product Manager · Deel IT」被它挡下，而那份 JD 自己写的是
# 「at least 1 year at Staff PM level **or equivalent senior IC role**」，
# 挡她的从来不是「要不要带人」。R44-3 的同一条：**判死的理由不许写错**，
# 写错下次就没人知道该翻哪一条。这两个词移出闸门后，真正的门槛仍由
# gate="wall"（JD 原文写死的年限/资历）挡——每条新岗本来就都开 JD。
# `Lead` 留着：它在本板的用法是「Delivery Lead / Head-of 型的带线角色」，
# 而且已有一条（Halian PO · Delivery Lead）挂在同一段等她拍板，**口径要全库一致**（R25-3）。
SENIORITY_WALL = _re.compile(
    r'\b(VP|Vice\s+President|Head\s+of|Director|Chief|C[TPOE]O|Lead)\b',
    _re.I)


def seniority_hit(role):
    m = SENIORITY_WALL.search(role or '')
    return m.group(0) if m else None


# 自检：两个方向都要判（R33-1：恒亮和恒灭是同一个 bug 的两个方向）。
# 改坏任何一个方向，跑批当场 AssertionError，不会静默放行也不会静默判死。
assert seniority_hit("Staff Product Manager · Deel IT") is None, "Staff 是 IC 职级，不该被层级闸挡"
assert seniority_hit("Principal Product Manager") is None, "Principal 是 IC 职级，不该被层级闸挡"
assert seniority_hit("Head of AI Solutions") == "Head of"
assert seniority_hit("VP of Product") == "VP"
assert seniority_hit("Product Owner · Delivery Lead") == "Lead"


FRESH_DAYS = 7
# 2026-08-14 Bella：「门槛 硬挡 · 类似这种就不能放入」。
# 层级闸门早就是硬排除了，门槛闸门却还只是 -8 分的加权项 —— 同一条规矩
# （R7：筛选闸门型条件不能只当加权项）没贯彻到底，于是 NEXT Ventures 这种
# 「JD 写死 5 年 PM、她 0 年」的岗还能带着「硬挡」两个字挂在待申请里。
# 两个闸门合并成同一个出口。
def wall_reason(j):
    hit = seniority_hit(j["role"])
    if hit:
        return '职位名里的 %s（无管理 title）' % hit
    if j.get("gate") == "wall":
        return 'JD 门槛硬挡'
    return None


OVERREACH = [(j, wall_reason(j)) for j in JOBS if wall_reason(j)]
_over_ids = {j["id"] for j, _ in OVERREACH}
POOL = [j for j in JOBS if j["id"] not in _over_ids]
print("闸门挡下:", [(j["co"], j["role"][:28], hit) for j, hit in OVERREACH] or "无")

# 2026-08-22：两个核心维度缺判据的岗**不参与排名**，单独成段。
# 以前它们照样有分（适配度是凭空一个数、公司发展是色灯换算），跟判据齐全的岗
# 混在同一张榜上——排序看起来很正常，其实一半的名次没有来处。
UNSCORED = [j for j in POOL if j.get("unscored")]
POOL = [j for j in POOL if not j.get("unscored")]
UNSCORED.sort(key=lambda x: (x.get("posted") or 999))
print("判据未核（不参与排名）:", len(UNSCORED), "/ 在投池", len(POOL) + len(UNSCORED))

fresh = sorted([j for j in POOL if (j.get("posted") or 999) <= FRESH_DAYS], key=lambda x: -(x["prio"] if x["prio"] is not None else -1))
rest = sorted([j for j in POOL if (j.get("posted") or 999) > FRESH_DAYS], key=lambda x: -(x["prio"] if x["prio"] is not None else -1))
new = sorted([j for j in JOBS if j["g"] == "new" and j["prio"] is not None], key=lambda x: -(x["prio"] if x["prio"] is not None else -1))
old = sorted([j for j in JOBS if j["g"] == "old" and j["prio"] is not None], key=lambda x: -(x["prio"] if x["prio"] is not None else -1))

LIGHT_TXT = dict(green="🟢 绿灯", yellow="🟡 黄灯", red="🔴 红灯")

def sign(n):
    return f"+{n}" if n > 0 else str(n)

# ============================================================ 折叠视图的短动作句
# 2026-08-18 Bella：「一句话行动建议（控制在 15 字以内）」。收起状态里那句话是
# 唯一告诉她「今天拿这条怎么办」的东西，长了就等于没有。
#
# **不自动截断**：截断会把「本周投 · 但先投隔壁那条，别同时投两个」切成
# 「本周投 · 但先投隔壁那条」还算通顺，但换一条就可能切出反义。所以短句逐条手写，
# 查不到的岗**只降级成动作前缀**（「今天投」/「本周投」），宁可少说不说错，
# 并在跑批日志里打印欠账清单——完整版仍在展开后的 jc-act 里，一个字没删。
# ACT_SHORT 原来是一张写死的表（61 个岗各一句手写行动建议）。
# 现在跟着岗位走：board.json 里每个岗的 act_short 字段。
ACT_SHORT = {j["id"]: j["act_short"] for j in JOBS if j.get("act_short")}

ACT_SHORT_MAX = 15          # 去掉空白后的字数上限，gate-density.py 会再判一次
_ACT_DEBT = []


def short_act(j):
    s = ACT_SHORT.get(j["id"])
    if s and len(re.sub(r'\s+', '', s)) <= ACT_SHORT_MAX:
        return s
    if s:                                   # 写了但超长：当成没写，别把长句放进收起态
        _ACT_DEBT.append((j["id"], j["co"], '超 %d 字' % ACT_SHORT_MAX))
        return j["act"].split('·')[0].strip()
    _ACT_DEBT.append((j["id"], j["co"], '缺短句'))
    return j["act"].split('·')[0].strip()


def card(j, rank):
    u = f"https://www.linkedin.com/jobs/view/{j['id']}/"
    o = io.StringIO()
    # 2026-08-13 Bella：「这种太长了，先收起，用户点击的时候再展开」。
    # 用原生 <details>，不写 JS —— 收起状态只留「谁 / 什么岗 / 几个关键事实 /
    # 分数怎么来的」，其余全部折进去。
    o.write(f'<details class="jc {j["light"]}" id="job-{j["id"]}">\n')
    # 2026-08-18 Bella：「每条只默认显示 排名 + 公司 + 职位 + 分数 + 三个核心标签
    # + 一句话行动建议 + 右侧按钮」。所以收起态只剩这七样，**竞争人数 / 发布天数 /
    # 申请方式这些 chip 全部下沉到展开区**——它们是决定「怎么投」的，不是决定
    # 「投不投」的，前者不该占第一屏。
    o.write(f'  <summary class="jc-sum">\n')
    o.write(f'    <div class="jc-rank">{rank}</div>\n')
    o.write(f'    <div class="jc-id">\n')
    o.write(f'      <div class="jc-co"><a class="jd-link" href="{u}" target="_blank" rel="noopener">{html.escape(j["co"])}</a>'
            f' <span class="prospect {j["light"]}">{LIGHT_TXT[j["light"]]}</span></div>\n')
    o.write(f'      <div class="jc-role">{html.escape(j["role"])}</div>\n')
    _pay_s = ('<b>%d</b>' % j["v_pay"]) if j["v_pay"] is not None else '<b>未披露</b>'
    _g_s = ('<b>%d</b>' % j["v_growth"]) if j["v_growth"] is not None else '<b>未核</b>'
    _f_s = ('<b>%d</b>' % j["v_fit"]) if j["v_fit"] is not None else '<b>未核</b>'
    o.write(f'      <div class="jc-mini"><span>薪资 {_pay_s}</span>'
            f'<span>公司发展 {_g_s}</span>'
            f'<span>适配度 {_f_s}</span></div>\n')
    o.write(f'      <div class="jc-lead"><span class="act-s {j["act_kind"]}">{html.escape(short_act(j))}</span></div>\n')
    o.write(f'    </div>\n')
    _prio_s = j["prio"] if j["prio"] is not None else '—'
    o.write(f'    <div class="jc-score"><b>{_prio_s}</b><small>优先级</small></div>\n')
    # 按钮容器：board.js 往这里插「不适合」和 ✓，「查看详情」是原生 summary 的开合，
    # 不需要 JS。空的时候也要在，否则 JS 会退回旧位置（.jc-top）而那个已经没了。
    o.write(f'    <div class="jc-ops"><span class="jc-more">查看详情</span></div>\n')
    o.write(f'  </summary>\n')

    o.write(f'  <div class="jc-body">\n')
    chips = [f'<span class="chip">{html.escape(j["loc"])}</span>',
             f'<span class="chip">{html.escape(j["posted_txt"])}</span>',
             f'<span class="chip">{html.escape(j["apply"])}</span>']
    if j.get("backlog"):
        chips.append(f'<span class="chip warnchip">未投第 {j["backlog"]} 天</span>')
    # 增量一律用 d1（昨天到今天两次观测相减），不用页面自带的 "in the past day"——
    # 那个字段已在 2026-08-07 被证伪（已关闭的岗还在报新增）。
    if j.get("applicants"):
        t = f'{j["applicants"]} 人<b>已申请</b>'
        if j.get("d1") is not None:
            t += f' · {DELTA_LBL} {sign(j["d1"])}'
        chips.append(f'<span class="chip">{t}</span>')
    elif j.get("clicked"):        # 8-24：原来写的是 j["clicked"]，没有这个键的岗直接 KeyError
        t = f'{j["clicked"]} 人已点申请'
        if j.get("d1") is not None:
            t += f' · {DELTA_LBL} {sign(j["d1"])}'
        chips.append(f'<span class="chip">{t}</span>')
    o.write(f'    <div class="jc-chips">{"".join(chips)}</div>\n')

    # 分数怎么算出来的：从收起态挪到这里。收起态只给三个数字，公式和权重是
    # 「为什么是这个数」，属于详情。
    _pay = ('薪资 <b>%d</b> ×0.2' % j["v_pay"]) if j["v_pay"] is not None else '薪资 <b>未披露</b> · 未计入'
    _cap = ' <span>年限硬挡 · 封顶 %d</span>' % WALL_CAP if j["capped"] else ''
    _g_n = ('<b>%d</b>' % j["v_growth"]) if j["v_growth"] is not None else '<b>未核</b>'
    _f_n = ('<b>%d</b>' % j["v_fit"]) if j["v_fit"] is not None else '<b>未核</b>'
    o.write(f'    <div class="jc-calc">{_pay}'
            f' <span>公司发展 {_g_n} ×0.4</span>'
            f' <span>适配度 {_f_n} ×0.4</span>'
            f' <span>门槛 {GATE_TXT[j["gate"]]}</span>{_cap}'
            f' <em>= {_prio_s}</em></div>\n')
    # 2026-08-22 加：**两个核心数字必须当场写出怎么算的**。Bella 的原话是
    # 「公司的这个评分怎么来的，说的也不清晰」——在这一行之前，页面上确实
    # 一个字都没有：适配度是凭空一个数，公司发展是色灯换算出来的三档之一。
    if j["v_fit"] is not None:
        _adj = ''.join(' <span class="d-adj">%+d %s</span>' % (d, why) for d, why in (j["fit_adj_d"] or []))
        o.write(f'    <div class="jc-why-n"><b>适配度 {j["v_fit"]}</b> ＝ 这份 JD 的要求清单里'
                f' <b>命中 {fmtnum(j["fit_hit"])} 条 / 共 {fmtnum(j["fit_total"])} 条</b>'
                f'（{round(100.0*j["fit_hit"]/j["fit_total"])}）{_adj}'
                f' <span class="d-note">逐条原文见下面的「门槛原文」</span></div>\n')
    if j["v_growth"] is not None:
        _d = ''.join('<span class="d-dim">%s <b>%s</b> %s</span>' % (GROWTH_MARK[v], sc, lbl)
                     for lbl, v, sc in j["growth_detail"])
        _why = (j.get("growth_by") or {}).get("why", "")
        o.write(f'    <div class="jc-why-n"><b>公司发展 {j["v_growth"]}</b> ＝ 两问各 50 分：{_d}'
                + (f'<span class="d-note">{_why}</span>' if _why else '') + '</div>\n')
    if j.get("unscored"):
        _why = j.get("unscored_why") or ""
        o.write(f'    <div class="jc-why-n warn"><b>这个岗没有优先级</b>——'
                f'{"、".join(j["unscored"])}，所以不参与排名。'
                f'{("<br>" + html.escape(_why)) if _why else ""}'
                f'<span class="d-note">空着比编一个数诚实：这种情况以前会照样给一个数，排序看起来正常但没有来处。</span></div>\n')
    # gate_txt 里写的是 <b> 标记（和 why / ammo / gapnote 一样），escape 会把它变成
    # 屏幕上的 &lt;b&gt; 字面量 —— 8-13 在线上抓到，21/36 张卡的「门槛原文」都是这样。
    # 数据里已断言过没有裸露的 & 和 <（只有 <b></b>），所以这里原样输出。
    o.write(f'    <p class="jc-gate"><b>门槛原文</b>{j["gate_txt"]}</p>\n')
    # 2026-08-13 Bella 明确要删：卡片中间那段「昨天雷达的真命中…」叙事。
    # 有用的东西已经在门槛原文、左右两栏和动作句里，这段是复述。
    o.write(f'    <div class="cols">\n')
    o.write(f'      <div class="col ammo"><h4>拿什么打</h4><p>{j["ammo"]}</p></div>\n')
    o.write(f'      <div class="col gap"><h4>拦你的是什么</h4><p>{j["gapnote"]}</p></div>\n')
    o.write(f'    </div>\n')
    o.write(f'    <p class="jc-act"><span class="act {j["act_kind"]}">{html.escape(j["act"])}</span></p>\n')

    r = j["reach"]
    o.write(f'    <div class="jc-reach">\n')
    o.write(f'      <div class="jc-reach-hd">触达路径</div>\n')
    if r["kind"] == "draft":
        conn = r["conn"]
        assert len(conn) <= 300, (j["co"], len(conn))
        o.write(f'      <p class="who"><a href="https://www.linkedin.com/in/{r["slug"]}/" target="_blank" rel="noopener">{html.escape(r["name"])}</a> · {r["deg"]}</p>\n')
        o.write(f'      <p class="role">{r["title"]}</p>\n')
        o.write(f'      <div class="gate">{r["gate"]}</div>\n')
        o.write(f'      <div class="msg"><span class="lbl">连接请求附言 · {len(conn)} / 300 字符</span>{html.escape(conn)}</div>\n')
        o.write(f'      <div class="msg dm"><span class="lbl">私信版（已连上或用 InMail）</span>{r["dm"]}</div>\n')
    else:
        # 2026-08-24 新增 hire：页面「People you can reach out to」给的是「这家最近招过同岗的人」，
        # 既不是校友也不是熟人。R34：复用别的 kind 会让页面印出「校友线」这句假话，所以开新出口。
        # 2026-08-28 新增两个出口（R34：复用别的 kind 会让页面印出一句假话）：
        #   agency＝猎头代理，本板口径是「不投这个岗也值得加个顾问」，不是熟人也不是校友；
        #   live＝这条线上已经有在跑的对话（对方来过信/面过她），跟冷触达完全两件事。
        # 模型/别人写的 kind 可能超出这几种（实测 DeepSeek 写了 poster / alumni / referral）。
        # 认不出的不崩、也不编——按「无人可触达」渲染，note 原样带上。
        tag = dict(none="无人可触达", alum="校友线", alumni="校友线", warm="熟人线", ref="并到另一条",
                   referral="熟人线", poster="发帖人线", hire="同岗前辈线", agency="猎头线",
                   live="在跑的对话").get(r.get("kind"), "无人可触达")
        o.write(f'      <p class="jc-reach-none"><span class="rtag">{tag}</span>{r["note"]}</p>\n')
    o.write(f'    </div>\n')
    o.write(f'  </div>\n')
    o.write(f'</details>\n')
    return o.getvalue()

body = io.StringIO()

# --- 2026-08-12：现在投不了的岗，单独成段，不占待投位置 ---
if BLOCKED:
    # 2026-08-18：这块原来是展开的一大段，占掉第一屏。它不是今天要做的动作
    # （定义就是「现在做不了」），所以默认收起，标题里把条数和它是什么说清。
    body.write('  <details class="fold gold">\n')
    body.write('    <summary><span class="tag">现在投不了</span>%d 个 · 不是没投，是投不出去（每条写明解冻条件）</summary>\n' % len(BLOCKED))
    body.write('    <div class="fold-body">\n')
    for j in BLOCKED:
        u = f"https://www.linkedin.com/jobs/view/{j['id']}/"
        body.write(f'    <p style="margin:10px 0 0"><b><a class="jd-link" href="{u}" target="_blank" rel="noopener">{html.escape(j["co"])} · {html.escape(j["role"])}</a></b><br>{j["blocked"]}</p>\n')
    body.write('    </div>\n  </details>\n')

# --- 人工提示块（原来写死着一条「Revolut 同时只准一个 live application」的口径）---
# 「同一家只能投一个」「同域 90 天冷却」这类规矩因人因公司而异，写死在模板里换个用户就是假话。
for c in CALLOUTS:
    body.write('  <details class="fold">\n')
    body.write('    <summary><span class="tag">%s</span><b>%s</b></summary>\n'
               % (html.escape(c.get("tag", "提示")), html.escape(c.get("title", ""))))
    body.write('    <div class="fold-body">\n')
    for jid in (c.get("job_ids") or []):
        jj = next((x for x in JOBS if x["id"] == jid), None)
        if jj:
            body.write('    <p style="margin:8px 0 0">· <b><a class="jd-link" '
                       'href="https://www.linkedin.com/jobs/view/%s/" target="_blank" rel="noopener">%s</a></b>'
                       '（优先级 %s）</p>\n' % (jid, html.escape(jj["role"]), jj.get("prio")))
    if c.get("body"):
        body.write('    <p style="margin:10px 0 0">%s</p>\n' % c["body"])
    body.write('    </div>\n  </details>\n')

n = 0
body.write('  <div class="grp" id="fresh"><span class="grp-badge new">近一周内发布</span>'
           '<span class="grp-t">%d 个 · 池子最浅、招聘方最饿</span></div>\n' % len(fresh))
for j in fresh:
    n += 1
    body.write(card(j, n))

body.write('  <div class="grp" id="rest"><span class="grp-badge old">其他</span>'
           '<span class="grp-t">%d 个 · 发布超过一周</span></div>\n' % len(rest))
for j in rest:
    n += 1
    body.write(card(j, n))

# 2026-08-22 加：判据未核的岗单独成段，排在有分的后面，且**不给名次**。
# 之前它们混在上面两段里，靠一个没有来处的数字排位——Bella 报的「匹配的工作不准确」
# 就是这么来的：把 81 张卡的适配度和卡上唯一的判据（命中 X/共 Y）对了一遍，
# 差值 -42 ~ +26，而且 67 张卡连那个判据都没写。
if UNSCORED:
    body.write('  <div class="grp" id="unscored"><span class="grp-badge old">判据未核</span>'
               '<span class="grp-t">%d 个 · 还没核出「命中几条 / 公司发展凭什么」，'
               '所以不给分也不排名——空着比编一个数诚实</span></div>\n' % len(UNSCORED))
    for j in UNSCORED:
        body.write(card(j, '—'))

# 被层级闸门挡下的，单独出一块——**判死的东西必须留痕**，否则它从此不再出现、
# 也没人知道为什么消失了（R7 2026-08-07 ④：错误的「否」不会有第二次机会）。
ov = io.StringIO()
ov.write('<details class="fold" id="overreach">\n')
if OVERREACH:
    ov.write('  <summary><span class="tag">层级够不着 · 不进池</span>%d 个 · 被闸门挡下的，点开看判据</summary>\n' % len(OVERREACH))
    ov.write('  <div class="fold-body">\n')
    ov.write('  <p style="margin:0">按 <code>PROFILE.md</code>：总工作年限 5+、<b>PM/Product Owner title 年限 0</b>、无管理 title。'
             '下面这些在 HR 硬筛第一道就会被刷，所以不进在投池——'
             '不是分数低，是这一项别的分再高也抬不回来。</p>\n')
    for j, hit in OVERREACH:
        u = f"https://www.linkedin.com/jobs/view/{j['id']}/"
        ov.write(f'  <p style="margin:8px 0 0">· <b><a class="jd-link" href="{u}" target="_blank" '
                 f'rel="noopener">{html.escape(j["co"])} · {html.escape(j["role"])}</a></b>'
                 f'（原优先级 {j["prio"]}）—— {html.escape(hit)}</p>\n')
    # 「这批里最可能是误伤的是哪条」是值班员对当天那批的判读，跟着数据走：board.json 的
    # overreach_note，没有就不写。原来这里写死着一段 Halian 的手记，换个人就是一段假话。
    if _B.get("overreach_note"):
        ov.write('  <p style="margin:10px 0 0" class="hilite">%s</p>\n' % _B["overreach_note"])
    ov.write('  <p style="margin:10px 0 0"><b>想放行某一条就说一声</b>：闸门只看职位名、不看 JD 正文，'
             '所以它会误伤「名字带 Lead 但其实是 IC」的岗。</p>\n')
    ov.write('  </div>\n')
else:
    ov.write('  <summary><span class="tag">层级够不着 · 不进池</span>今天没有被层级闸门挡下的岗</summary>\n')
    ov.write('  <div class="fold-body"><p style="margin:0">闸门在 <code>rebuild-board.py</code> 的 <code>SENIORITY_WALL</code>。</p></div>\n')
ov.write('</details>\n')
open(os.path.join(PARTS, 'overreach.html'), 'w').write(ov.getvalue())

open(os.path.join(PARTS, 'part1.html'), 'w').write(body.getvalue())
print("cards:", n, "new:", len(new), "old:", len(old))
print("order:", [(j["co"], j["prio"]) for j in new + old])

# ------------------------------------------------------- 今日 Top 10
# 排序＝优先级降序。**同分怎么办要写死，不能靠字典顺序**：
#   第一顺位 优先级 → 第二顺位 今日增速 d1 大的在前（窗口关得快，今天做比明天做值钱）
#   → 第三顺位 积压天数多的在前（backlog）→ 第四顺位 竞争池小的在前。
# 8-9 晚间 94 分处出现四路并列（Scale AI / Confidential / Cohere / ElevenLabs），
# 没有这条规则的话第 10 名是谁完全取决于代码里谁先被写进列表——那是黑箱。
def tiebreak(j):
    return (-(j["prio"] if j["prio"] is not None else -1), -(j.get("d1") or 0), -(j.get("backlog") or 0),
            (j.get("applicants") or j.get("clicked") or 0))

ranked = sorted(POOL, key=tiebreak)
# 2026-08-14 加：**一个公司最多占 Top 10 的 2 席**。换成加权分之后「公司发展」占 40%，
# 同一家绿灯大厂的多条岗会整齐地挤进前十（实测 Amazon 一次占了 3 席），把别的公司挤出去。
# 榜单的用处是「今天该看哪几家」，不是「哪家分高」。被挤下去的仍在下面的完整列表里。
# 同分裁决键不变：优先级 → 今日增速 → 积压天数 → 池子小的在前。
PER_CO = 2
_seen_co, TOP = {}, []
for _j in ranked:
    if _seen_co.get(_j["co"], 0) >= PER_CO:
        continue
    _seen_co[_j["co"]] = _seen_co.get(_j["co"], 0) + 1
    TOP.append(_j)
    if len(TOP) == 10:
        break

def pool_chip(j):
    if j.get("applicants") is not None:
        t = f'{j["applicants"]} 人已申请'
    elif j.get("clicked"):
        t = f'{j["clicked"]} 人已点申请'
    else:
        return None
    if j.get("d1") is not None:
        t += f' · {DELTA_LBL} {sign(j["d1"])}'
    return t

# 2026-08-14 Bella：「不要这么展示（纯文字列表），还是要这么展示（Top 10 那种行）」。
# 所以把行渲染抽成一个函数，Top 10 和「今天新扫到」共用同一份 DOM 结构——
# 好处不只是长得一样：`parts/board.js` 的 ✓ / 「不适合」是按 `.jc, .t10row` 挂的，
# 而且按 job id 找 twins，所以同一个岗在两个位置点任意一个，另一个会跟着收走。
# 复用结构＝白拿交互；自己另写一套 <p> 列表＝那两个按钮永远不会出现（就是刚才那版）。
def row_html(j, rank):
    u = f"https://www.linkedin.com/jobs/view/{j['id']}/"
    # 这一行只放**评分是怎么算出来的**（8-13 Bella：小字太多看不清，只留关键信息）。
    # 唯一的例外是积压天数——它不是评分维度，是「窗口在关」的行动信号。
    # 2026-08-18：跟岗位卡收起态口径一致——只留三个核心数字。
    # 门槛和总分算式属于详情，右边那个大数字已经是总分了，别在同一行再写一遍。
    parts = [('薪资 %d' % j["v_pay"]) if j["v_pay"] is not None else '薪资 未披露',
             f'公司发展 {j["v_growth"]}',
             f'适配度 {j["v_fit"]}']
    # 绿底＝动作清单点名的那几条，**不是所有 act_kind==go 的**。
    # 9 张卡同时写「今天投」＝没有重点，8-6 实测那样的一天只投出 1 条。
    hot = ' hot' if j.get('pick') else ''
    dims = "".join(f'<span>{html.escape(p)}</span>' for p in parts)
    backlog_tag = f'<i>未投第 {j["backlog"]} 天</i>' if j.get("backlog") else ""
    o = io.StringIO()
    o.write(f'  <div class="t10row{hot}">\n')
    o.write(f'    <div class="t10rank">{rank}</div>\n')
    o.write(f'    <div class="t10main">\n')
    o.write(f'      <div class="t10co"><a class="jd-link" href="{u}" target="_blank" rel="noopener">{html.escape(j["co"])}</a>'
            f' <span class="t10role">{html.escape(j["role"])}</span></div>\n')
    o.write(f'      <div class="t10calc">{dims}{backlog_tag}</div>\n')
    o.write(f'      <div class="t10act"><span class="act-s {j["act_kind"]}">{html.escape(short_act(j))}</span></div>\n')
    o.write(f'    </div>\n')
    o.write(f'    <div class="t10sc"><b>{j["prio"]}</b><small>优先级</small></div>\n')
    o.write(f'    <div class="t10ops"><a class="jc-more t10more" href="#job-{j["id"]}">查看详情</a></div>\n')
    o.write(f'  </div>\n')
    return o.getvalue()

# ============================================================ 今日决策台（2026-08-18 改版）
# Bella：「换一个更清晰、更明显的 MVP」。旧的第一屏是「Top 10 一行一条」——
# 十行长得一模一样，等于把「先投哪个」这个决定又推回给她。
# 新的第一屏只回答一句话：**今天投这几个**。
#   · 判据不是分数最高的前三，是**动作已经判成「今天投」的那几条**里分数最高的三条
#     （分数管排序，动作管今天做不做，两件事）。
#   · 每张卡上只有：一个大分数 / 谁 / 什么岗 / 一句为什么 / 三个数字 / 两个按钮。
#   · 下面一条漏斗写清整条流水线现在各卡着多少个 —— 第二个问题「我进度到哪」。
# Top 10 那一条整块删掉：它和下面 26 张卡是同一批岗的两个排序，同屏出现两次
# （CONTENT.md §3.4：同一类事实只出现一次）。
# ------------------------------------------------- 今天新扫到的（2026-08-14 下午加）
# Bella 打开页面的原话：「我看到的这些岗位都是历史的了呀」。
# 原因不是没扫到新的，是**新岗的匹配度分数普遍低于板上那批手写多轮的老岗**，
# 于是全被压到 Top 10 以下，她第一屏看到的全是积压岗。
# 分数不改（改了整板会假动一次，R18-4），改的是**先给它们一个自己的位置**。
# 8-24 个性化页扫 5 页、失败页 0、118 个岗、30 条没见过、19 份 JD 全开、净进池 11。
# ⚠ 这个列表只放**今天**净进池的 ID —— 昨天那批到今天就是「积压」，它们该靠自己的分数排，
#   不该再占「今天新扫到」这个位置（这颗 chip 的数只能来自它自己那一个来源，R7）。
# 「今天新扫到」的 ID 只能来自数据（原来写死着某个人的三个岗位 ID）
TODAY_IDS = list(_B.get("new_today_ids") or [])
_by_id = {j["id"]: j for j in JOBS}
_today = [_by_id[i] for i in TODAY_IDS if i in _by_id]
_today.sort(key=lambda j: -(j["prio"] if j["prio"] is not None else -1))

TODAY_PICKS = 3
# 2026-08-29 Bella：「按照最优先排 3 个」。决策台 = 优先级前三，不再看动作标签。
_go = ranked[:TODAY_PICKS]

WEEK = '一二三四五六日'[TODAY.weekday()]

t = io.StringIO()
t.write('<section class="part first" id="apply">\n')
t.write('  <div class="today">\n')
t.write('    <div class="today-date">%d 月 %d 日 · 周%s</div>\n' % (TODAY.month, TODAY.day, WEEK))
t.write('    <h1 class="today-h">今天投这 %d 个</h1>\n' % len(_go))

# ------------------------------------------------- 「今天变了什么」（2026-08-20 加）
# Bella 的原话：「今日怎么没更新呢」——而板子那天**是**更新了、也发布了。
# 真因是**她唯一会看的那块地方看起来没变**：3 张大卡里 2 张跟昨天一模一样
# （同一个岗、同一句为什么），因为岗还开着、她没投。日期从 8-19 变成 8-20，
# 而今天真跑出来的东西（净进池 5 / 关闭 3 / 渠道盲 6 天）一条都不在第一屏上。
# 这是 R28/R15-2 的同一个形态：**「没更新」和「更新了但看不出来」在页面上长得一模一样**。
# 修法不是改分数、不是换卡（R18-4：改权重会让整板假动一次），是**把当天的增量显式说出来**。
# 每颗 chip 的数都取自本文件里已有的那个唯一来源，不另算（R7：一个数字一个来源）。
_delta = []
# 2026-08-23 加：「今天复核了几个岗、还剩几个在招」此前只写在 footer 正文里，
# 而正文是手写的——手写的数会被下一轮值班原样抄走（R43 实锤过一次）。
# 现在读 recheck-latest.json（复核那一步自己落的盘），**文件日期不是今天就明写没复核成**，
# 绝不拿昨天的数顶上（R48 / R10 铁律二：伪装成正常值的失败比报错更坏）。
try:
    _rc = json.load(io.open(os.path.join(WS, 'recheck-latest.json'), encoding='utf-8'))
except Exception:
    _rc = None
rc_fresh = bool(_rc) and (_rc.get('checked_at') or '')[:10] == TODAY.isoformat()
if rc_fresh:
    _delta.append(('', '复核 <b>%d</b> 岗 · 仍在招 <b>%d</b>' % (_rc['n'], _rc['open']), '#apply'))
else:
    _delta.append(('warn', '今天没复核成 · 下面的在招状态是旧的', '#apply'))
_delta.append(('new', '新扫到 <b>%d</b> 条' % len(_today), '#newtoday'))
# ⚠ CLOSED_TODAY 这个名字骗人：它是**历来**判过关闭的全部（8-20 有 10 条，最早 8-16），
# 不是今天关的。第一屏写「关闭 N 条」必须只数今天那几条，否则又是一个名不副实的数
# （R7：一个对外的数字，它算的必须是它自称的那个东西）。
_closed_today = [j for j in CLOSED_TODAY if j.get("closed") == TODAY.isoformat()]
if _closed_today:
    _delta.append(('', '在投池关闭 <b>%d</b> 条' % len(_closed_today), '#archive'))
# 2026-08-25 加：复核读到「No longer accepting applications」的岗里，有一部分是她
# **已经投过**的。那不是池子少了一条，是她手上一份还在等回音的申请、它的 req 关掉了——
# 属于台账那半边的事实。今天 43 个岗读到 5 条关闭，其中只有 1 条在投池，
# 另外 4 条全是已投的岗；并进上面那颗就等于说「池子今天少了 5 个」，那是假的
# （R7：一个对外的数字只能算它自称的那个东西）。
# 唯一来源仍是 recheck-latest.json：closed 总数 − 在投池今天关闭的条数，不另外数一遍。
if rc_fresh:
    # ⚠ 2026-08-27 改口径：这里原来减的是 `_rc['closed']`＝**今天复核的那批里所有关着的岗**。
    # 那个数随「今天复核了多少个」变化，不随事实变化——昨天复核 45 个得 4，今天复核 94 个
    # （同样的事实、没有任何新变化）会得 9。而它坐的位置是「今天变了什么」那条 delta，
    # 说的必须是**今天才变的**（R7 / R45-5：一个数字要对得起它自称的那个东西）。
    # 现在读 d27-parse.py 算好的 closed_new：拿今天的状态跟历史上最后一次已知状态比，
    # 只数「非 CLOSED → CLOSED」的那几个。缺这个字段就当没有，不拿旧口径顶上（R10 铁律二）。
    _applied_closed = _rc.get('closed_new', 0) - len(_closed_today)
    if _applied_closed > 0:
        _delta.append(('', '已投的 req 关了 <b>%d</b> 个' % _applied_closed, '#waiting'))
# 2026-08-28 加：今天新进池的岗里，有没有「这家她已经投过 / 已经在跑流程」的。
# 这类岗的行动完全不一样——不是冷投，是回一封已经在跑的信；而它的**分数不会反映这件事**
# （IC Markets 只有 62 分，排在第 35 位，第一屏根本看不到它）。
# 分数不动（R18-4：改权重会让整板假动一次），改的是**把这个事实说出来**。
# 数只有一个来源：今天新进池的 ID × 台账里已有的公司名，现算，不手填。
def _co_key(t):
    return (t or '').split('（')[0].split('(')[0].strip().lower()
_ledger_cos = {_co_key(a.get('company')) for a in _apps.get('applications', []) if a.get('company')}
WARM_TODAY = [j for j in _today if _co_key(j['co']) in _ledger_cos]
if WARM_TODAY:
    # 链到 #newtoday 那一段而不是某一张卡：两条都在那儿，挑一张就是替她排了个我说不清的序。
    # 位置必须紧跟「新扫到 N 条」那颗——「其中」指的是它，排在关闭那几颗后面就指错了对象。
    _i = next((k for k, c in enumerate(_delta) if c[2] == '#newtoday'), len(_delta) - 1)
    _delta.insert(_i + 1, ('warm', '其中 <b>%d</b> 条来自已经在跑的公司' % len(WARM_TODAY), '#newtoday'))
print("已在跑的公司里新挂的坑:", [(j["co"][:24], j["id"]) for j in WARM_TODAY] or "无")
if BLIND_CHANNELS:
    # 渠道盲了＝「没人回」这个结论在那条渠道上不成立，属于必须顶到第一屏的那类
    # （R19-2：一个渠道连续失败要升级成结论，不能继续当播报）。
    _delta.append(('warn', BLIND_CHANNELS, '#waiting'))
t.write('    <div class="hdbar delta">\n')
for _kind, _txt, _href in _delta:
    t.write('      <a class="hd-chip%s" href="%s">%s</a>\n'
            % ((' ' + _kind) if _kind else '', _href, _txt))
t.write('    </div>\n')
t.write('    <div class="tcards">\n')
for j in _go:
    u = f"https://www.linkedin.com/jobs/view/{j['id']}/"
    why = short_act(j).split('·')[-1].strip()
    _pay = ('%d' % j["v_pay"]) if j["v_pay"] is not None else '未披露'
    t.write('      <div class="tcard" data-job-id="%s">\n' % j["id"])
    t.write('        <div class="tc-score">%d</div>\n' % j["prio"])
    t.write('        <div class="tc-co"><a class="jd-link" href="%s" target="_blank" rel="noopener">%s</a></div>\n'
            % (u, html.escape(j["co"])))
    t.write('        <div class="tc-role">%s</div>\n' % html.escape(j["role"]))
    t.write('        <div class="tc-why">%s</div>\n' % html.escape(why))
    # 卡片重复出现在第一屏是常态（岗还开着、她没投），但**不说出来就等于页面没变**。
    # backlog 在 1084 行早就算好了，此前只渲染在下面的行里，第一屏反而没有。
    if j.get("backlog"):
        # 措辞照抄下面那些行里已有的「未投第 N 天」——同一个字段在同一页上
        # 只许有一种说法，否则就是 R24 那条（一个字段多个渲染点，口径必须统一）。
        t.write('        <div class="tc-again">未投第 <b>%d</b> 天</div>\n' % j["backlog"])
    t.write('        <div class="tc-mini"><span>薪资 <b>%s</b></span><span>公司发展 <b>%d</b></span>'
            '<span>适配度 <b>%d</b></span></div>\n' % (_pay, j["v_growth"], j["v_fit"]))
    t.write('        <div class="tc-ops"><a class="jc-more t10more" href="#job-%s">详情</a></div>\n' % j["id"])
    t.write('      </div>\n')
t.write('    </div>\n')
# 漏斗：这四个数各自的唯一来源都在下面那几段，board.js 现数 DOM 回填，这里只出骨架
t.write('    <div class="funnel">\n')
# 2026-08-20 Bella：「已投递里被拒的有多少？在看板上帮我列出来呗」——
# 被拒那 4 条**一直在板上**（05 段，侧栏也有计数），但**漏斗里没有它**，
# 所以第一屏这条「我进度到哪」的链子是断的：投出去的 54 条，漏斗只解释了 49+1+0。
# 数字对不上的时候人不会去翻侧栏，只会以为板子没记（R38：验入口，不验存在）。
# `rejected` 的计数 board.js 早就在数了，纯粹是没给它一个位置。
for anchor, label in (('apply', '还能投'), ('waiting', '已投无消息'),
                      ('interviewing', '有面试'), ('offers', 'offer'),
                      ('rejected', '已被拒')):
    t.write('      <a class="fn" href="#%s"><b data-count="%s">·</b><span>%s</span></a>\n'
            % (anchor, anchor, label))
t.write('    </div>\n')
t.write('  </div>\n')
open(os.path.join(PARTS, 'today.html'), 'w').write(t.getvalue())
print("top10:", [(j["co"], j["prio"], j.get("d1")) for j in TOP])
print("第 11 名（差一点）:", [(j["co"], j["role"][:24], j["prio"]) for j in ranked[10:13]])

_blocked_today = {j["id"] for j, _ in OVERREACH}

# 2026-08-18 Bella：「顶部只保留极简信息，一行状态提示用小标签，不要大段文字」。
# 所以扫描实况拆成两层：SCAN_NOTE 是顶部那颗 chip（一句话，能读懂就行），
# 完整解释收进 details。**收起不等于删**——扫描失败必须留在页面上（R19-3），
# 只是不再占第一屏。
# 扫描实况每轮都不一样，只能来自数据；没有就不渲染那颗 chip 和那段说明。
# **残缺的扫描要当残缺报**——「今天只看到 N 个」和「今天只有 N 个」是两件事。
SCAN_NOTE = _B.get("scan_note") or ""
SCAN_DETAIL = _B.get("scan_story") or ""
nt = io.StringIO()
if _today:
    nt.write('<div class="grp" id="newtoday"><span class="grp-badge new">今天新扫到 %d 条</span>'
             '<span class="grp-t">来自 LinkedIn 个性化推荐页</span></div>\n' % len(_today))
else:
    nt.write('<div id="newtoday"></div>\n')
nt.write('<details class="fold thin"><summary>%s</summary><div class="fold-body"><p style="margin:0">%s</p></div></details>\n'
         % ('今天这 0 条是怎么来的' if not _today else '这批是怎么筛的',
            SCAN_DETAIL if not _today else
            '扫到的新 ID 里，下面是判「能投」的——<b>它们混在下面的完整排名里，分数没有优待</b>。'
            '判死的那些逐条引了 JD 原文躺在归档里，<b>觉得哪条判错了直接说，都好推翻。</b>'))
nt.write('<div class="t10">\n')
for _i, _j in enumerate(_today, 1):
    nt.write(row_html(_j, _i))
nt.write('</div>\n')
open(os.path.join(PARTS, 'newtoday.html'), 'w').write(nt.getvalue())
print("newtoday:", len(_today))

# ------------------------------------------------- 01 的头部（2026-08-18 改）
# 以前 part1-head.html 是手写的，于是 h2 里的岗位数和卡片数是两个来源——
# 8-18 实测它写着 23 而池子是 26（R7：一个对外的数字只能有一个来源）。
# 现在它跟卡片同源生成，改不动也漏不了。
hd = io.StringIO()
hd.write('  <div class="rest-hd">\n')
# ⚠ 2026-08-27 修：这里减的基数原来只有 POOL，而页面上渲染的卡是 POOL + UNSCORED
# （判据未核 / JD 无硬门槛那几条也在 01 这一屏里）。今早适配度改版后 UNSCORED 从 0 变成 4，
# 标题就跟卡片数对不上了（写 3+49、实际 56 张）——同一屏上两个来源，正是这条标题当初被生成化的原因。
hd.write('    <h2>其余 %d 个还能投的岗</h2>\n' % (len(POOL) + len(UNSCORED) - len(_go)))
hd.write('  </div>\n')
hd.write('  <div class="hdbar">\n')
# 「今天新扫到 N 条」这颗 chip 挪到第一屏的 delta 条去了（2026-08-20）。
# 留在这里就是同一个事实在同一屏上印两遍（CONTENT.md §3.4），
# 而且两颗 chip 长得几乎一样，读起来像两件事。**这里不再重复，delta 那颗链到 #newtoday。**
if SCAN_NOTE:
    hd.write('    <span class="hd-chip warn">%s</span>\n' % SCAN_NOTE)
hd.write('    <details class="hd-note"><summary>评分说明</summary>\n')
hd.write('      <p>总分＝<b>薪资 ×0.2 + 公司发展 ×0.4 + 适配度 ×0.4</b>，满分 100。'
         '年限硬挡的岗封顶 %d；<b>时效、竞争、摩擦不进分数</b>，只决定「今天投还是本周投」，'
         '同分时当裁决键；Top 10 里一个公司最多占 2 席。薪资未披露的岗该项不计入，'
         '权重归一到公司发展 / 适配度各 50%%——<b>不估薪</b>（JD 里写薪酬数字的极少，估出来的你没法验）。</p>\n' % WALL_CAP)
hd.write('      <p><b>适配度 ＝ 命中条数 / 要求总条数</b>，清单取 JD 自己写的那一段，'
         '逐条落在每张卡的「门槛原文」里，半条记 0.5。JD 里的<b>反向限定</b>'
         '（例如 JD 明写「本岗面向初中级候选人」）不揉进这个比例，'
         '写成一条带原文的具名扣分单独列出来。</p>\n')
hd.write('      <p><b>公司发展 ＝ 两问各 50 分</b>，全部从 JD 文本确定性判、不用模型：'
         '①<b>碰的是 AI 产品本身</b>吗（JD 里 AI / LLM / agent 这类词的密度，不是「一家用 AI 的公司」）'
         '②<b>雇主是甲方</b>吗（JD 有没有 our client / staffing / recruitment agency 这类代招字眼）。'
         '「在不在长」「三年后值不值钱」JD 里没有、代码判不了，<b>所以不进分数</b>——不拿模型猜一个数顶上。'
         '<b>两项缺任何一项，这个岗就没有优先级。</b></p>\n')
hd.write('    </details>\n')
hd.write('  </div>\n')
open(os.path.join(PARTS, 'part1-head.html'), 'w').write(hd.getvalue())

# 侧边栏品牌行 / 日期已在文件头铺模板件时注入（从 config.json 归一，不写死地区）。

if _ACT_DEBT:
    print("⚠ 短动作句欠账（收起态只显示动作前缀）:", _ACT_DEBT)
_stale = [k for k in ACT_SHORT if k not in {j["id"] for j in POOL}]
if _stale:
    print("ACT_SHORT 里已不在池的条目（可删）:", _stale)
