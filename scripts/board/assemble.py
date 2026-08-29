import os, json
# -*- coding: utf-8 -*-
"""把两部分正文装回基线文件的 <style> 骨架里。

parts/ 是仓库内的持久目录（不再用会话 scratchpad —— 那是临时目录，清一次流水线就失忆）：
  nav.html        顶部导航（8-10 起；masthead + verdict 已按 Bella 要求整体去掉）
  part1-head.html 第一部分的标题 + 排序公式 callout
  top10.html      今日 Top 10，由 rebuild-board.py 生成（和岗位卡同源，同一个 prio）
  part1.html      岗位卡，由 rebuild-board.py 生成
  part2.html      第二部分 · 进行中的追踪
  archive.html    归档折叠区
CSS 已经在基线文件的 <style> 里，本脚本只取 </style> 之前的头部原样复用，不再追加。
"""
import io, os

# ⚠ 2026-08-28：这两行原来把路径写死成某一个人的目录。拿它给另一个人拼版时，
# **直接覆盖了那个人正在用的看板文件**（当场靠 git 恢复的）。
# 现在必须显式传工作区：python3 scripts/board/assemble.py <workspace>
import sys as _sys
_WS = os.path.abspath(_sys.argv[1]) if len(_sys.argv) > 1 else os.path.abspath('.')
if not os.path.isdir(os.path.join(_WS, 'parts')):
    raise SystemExit('用法：python3 scripts/board/assemble.py <workspace 目录>\n'
                     '  （%s 下面没有 parts/，先跑 render.py）' % _WS)
SRC = os.path.join(_WS, 'board.html')
P = os.path.join(_WS, 'parts') + '/' 

# 第一次跑没有 board.html，用模板种子（只取 <style> 之前那段 head）。
# **不从上一版产物继承身份**——标题被写脏一次就永久粘住，替换锚点没了就再也改不回来。
_seed = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'assets', 'board', 'seed.html')
old = io.open(SRC if os.path.exists(SRC) else _seed, encoding='utf-8').read()
_owner = ''
try:
    _owner = json.load(io.open(os.path.join(_WS, 'config.json'), encoding='utf-8')).get('name') or ''
except Exception:
    pass
# CSS 的唯一事实源是 parts/style.css。**别再从上一版 HTML 里抠 <style>**——
# 8-10 就是这么翻车的：改了 parts/style.css、跑了 assemble，页面纹丝不动，
# 因为 head 是从旧 HTML 里剪下来的，压根没读那个文件。
head = old[:old.index('<style>')]
_cfgT = json.load(io.open(os.path.join(_WS, 'config.json'), encoding='utf-8'))
_title = '求职看板 · %s' % (_cfgT.get('display_name') or _cfgT.get('name') or '')
head = head.replace('{{TITLE}}', _title)
head = __import__('re').sub(r'<title>[^<]*</title>', '<title>%s</title>' % _title, head)
assert 'name="viewport"' in head, '缺 viewport，CDP 量出来的 clientWidth 会是 980'
# 2026-08-13：本地文件从来没有 charset，Chrome 只能靠猜。猜错就整页按 GBK 解 UTF-8
# （「今日」变成「浠婃棩」）。线上没事——Artifact 外壳自己带 charset——但本地的
# 截图验收和门禁全跑在这个文件上，等于验收结果是随机的。实测：同一套 HTML 换个
# 皮肤重跑，中文就从正常变成满屏乱码，而我差点把它当成字体问题。
if 'charset' not in head.lower():
    head = '<meta charset="utf-8">\n' + head
# 2026-08-13：CSS 拆成两层，换皮只换上面那层。
#   skin-<名>.css  颜色 / 字体 / 圆角 / 元件调性（每套一份 design.md 的落地）
#   style.css      布局、组件结构、侧边栏、✓ 交互 —— 跟皮肤无关，换皮不动它
# 换皮：SKIN=monochrome python3 assemble-board.py
#
# 2026-08-18：默认值从写死的 'signal' 改成读 parts/SKIN。原因是 R20-4 那条又踩了一次——
# 线上跑的是 blue，代码里的默认是 signal，**不带变量重跑一次就把全站配色静默换掉**，
# 而 diff 看起来只是几百行 CSS 动了（CSS 是超长行，看不出是换了整套皮）。
# 现在「线上是哪套皮」有唯一事实源，改皮＝改这个文件，跑批不带变量也复现得出来。
SKIN = os.environ.get('SKIN') or io.open(P + 'SKIN', encoding='utf-8').read().strip()
skin = io.open(P + 'skin-%s.css' % SKIN, encoding='utf-8').read()
css = skin + '\n' + io.open(P + 'style.css', encoding='utf-8').read()
# 2026-08-19：皮肤可以有第二层 skin-<名>.after.css，拼在 style.css **之后**。
# 原因：skin 层排在前面，只改得动 style.css 没设过的属性——换个 token 够用，
# 但「描边卡改成实底卡」这种要盖掉 style.css 已经写死的 border/background，
# 排在前面就一定输。可选文件，没有就当没有（blue / signal / mono / studio 都没有）。
_after = P + 'skin-%s.after.css' % SKIN
if os.path.exists(_after):
    css = css + '\n' + io.open(_after, encoding='utf-8').read()

rd = lambda n: io.open(P + n, encoding='utf-8').read()
# 2026-08-18：第二部分从「一张长台账 + 6 张另开的准备卡」拆成四段独立 section，
# 名称直接对应求职进度（Bella 的内容规范 §3）。part2.html 已经不存在了——
# 它的 6 张卡按 job_id 拆进 parts/prep/，由 render-applications.py 注进对应那一行。
# today.html 是新的第一屏（今日决策台，2026-08-18），它把 <section id="apply"> 开起来；
# part1-head.html 退化成「其余岗位」那一段的小标题。旧的 top10.html 已删——
# Top 10 和下面 26 张卡是同一批岗的两个排序，同屏出现两次。
nav, today, p1head, part1, arch = (rd('nav.html'), rd('today.html'), rd('part1-head.html'),
                                   rd('part1.html'), rd('archive.html'))
waiting, interviewing, offers, rejected = (rd('pipeline-status.html'), rd('interviewing.html'),
                                           rd('offers.html'), rd('rejected.html'))
# 2026-08-13 新增的三块：第三部分「已面试」、第四部分「被看见」、前端交互。
# board.js 必须放在正文之后（它要现数 DOM），别挪到 head 里。
visible, js = rd('visible.html'), rd('board.js')
overreach = rd('overreach.html')
# 05 猎头渠道：七家 UAE 中介的逐家体检 + 值得投的岗 + 要联系的猎头。
# 放在 visible 之后、归档之前——Bella 要求"放到最下面"，但归档必须永远是最后一块。
# 8-14：这里一度有两份赋值 + 下面拼了两次，页面上出现两个相同的 id="agencies"
# （8-13 从线上合并回来时和本地那行叠加了）。**同一块内容只许出现一次**，
# 而且重复 id 会让侧边栏锚点只跳到第一个——门禁数标签配平，数不出这种重复。
agencies = rd('agencies.html')
# 今天新扫到的那一批，贴在 Top 10 之前——8-14 Bella：「我看到的这些岗位都是历史的了呀」。
newtoday = rd('newtoday.html')

# footer 的值班日志每轮都不一样，只能来自数据：board.json 的 footer_line（一行摘要）
# 和 footer_log（逐条，HTML 片段）。原来写死着某一天的手记，换个人就是一段假话。
_B = json.load(io.open(os.path.join(_WS, 'board.json'), encoding='utf-8'))
_fl = _B.get("footer_line") or ""
_fg = _B.get("footer_log") or ""
FOOTER = ('  <footer>\n'
          + ('    <p class="ft-line">%s</p>\n' % _fl if _fl else '')
          + ('    <details class="fold"><summary>这一轮做了什么 · 逐条</summary>'
             '<div class="fold-body">%s</div></details>\n' % _fg if _fg else '')
          + '    <p class="ft-line"><b>免责</b> 匹配度与优先级是按 JD 明写门槛 + 公司四问算出来的判断，'
            '不是录用概率；人数是抓取当时的快照。</p>\n'
          + '  </footer>\n</div>\n')

out = (head + "<style>\n" + css + "</style>\n\n" + nav + "\n<div class=\"wrap\">\n"
       + today + p1head + newtoday + part1 + overreach + "</section>\n\n"
       + waiting + "\n" + interviewing + "\n" + offers + "\n" + rejected + "\n"
       + visible + "\n" + agencies + "\n"
       + arch + FOOTER
       + "\n<script>\n" + js + "</script>\n")

# 2026-08-19：换皮试版必须能写到别的文件去。原来只会原地写 SRC——
# 想看另一套皮长什么样，就得先把线上那份覆盖掉再改回来，
# 中途任何一步断了，线上那版就是错的皮（R20-4 那条的另一个入口）。
OUT = os.environ.get('OUT') or SRC
# 试版的 <title> 必须自报是试版：Artifact 的名字取自 <title>，
# 两个都叫「UAE 求职看板」的话，她在列表里分不出哪个是每天在看的那份。
LIVE_URL = 'https://claude.ai/code/artifact/37f416a1-8953-40d7-ae81-fd8bd8fb2b53'
# 2026-08-20：<title> 必须每次从常量归一，**不许继承上一版**。
# head 是从上一版产物里剪下来的（见文件开头），所以标题一旦被写脏就永久粘住：
# 试版横幅那次证伪把真板标题写成「· blue 试版」之后，再拼多少次都改不回来——
# 因为替换的锚点 `<title>UAE 求职看板</title>` 已经不存在了。**污染会自我复制。**
# 这跟 R20-4「皮肤参数要有唯一事实源」是同一条：产物的身份不能靠继承。
TITLE = _title      # 从用户 config 归一（display_name / name），不写死地区
import re as _re_t
out = _re_t.sub(r'<title>[^<]*</title>', '<title>%s</title>' % TITLE, out, count=1)
assert '<title>%s</title>' % TITLE in out
if OUT != SRC:
    out = out.replace('<title>求职看板</title>',
                      '<title>%s · %s 试版</title>' % (TITLE, SKIN), 1)
    # 2026-08-20：光改 <title> 不够。Bella 打开 acid 试版（8-19 之后就没动过）
    # 问「今日怎么没更新呢」——**页面正文跟真板一模一样**，标签页那行小字看不见，
    # 而 Artifact 列表里三份都叫「UAE 求职看板…」，两个试版还排在真板前面。
    # 试版必须**在页面上**自报身份 + 给一条回真板的路（R38-1：验入口，不验文件存在；
    # R34：复用一个外观之前先看它在页面上说了什么话）。横幅要在最顶上、点得走。
    banner = (
        '<div style="position:sticky;top:0;z-index:999;background:#B45309;color:#fff;'
        'padding:10px 16px;font:600 13px/1.5 -apple-system,BlinkMacSystemFont,sans-serif;'
        'display:flex;gap:12px;flex-wrap:wrap;align-items:center">'
        '<span>\u26a0\ufe0f 这是 <b>%s 试版</b>，只用来看配色，<b>数据停在拼版那天、不会每天更新</b>。</span>'
        '<a href="%s" target="_blank" rel="noopener" style="color:#fff;text-decoration:underline">'
        '打开每天在更新的那份 \u2192</a></div>\n' % (SKIN, LIVE_URL))
    assert '<body' not in out, '基线现在不带 <body>，横幅直接插在正文最前'
    out = out.replace('<div class="wrap">', banner + '<div class="wrap">', 1)
    assert banner in out, '试版横幅没插进去'
io.open(OUT, 'w', encoding='utf-8').write(out)
print("written", len(out), "bytes ->", OUT, "(skin=%s)" % SKIN)
