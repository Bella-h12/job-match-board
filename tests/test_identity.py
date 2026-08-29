# -*- coding: utf-8 -*-
"""门禁：产物里不许出现原版看板的地区/身份字样。

2026-08-29 Bella 截图指出：一个找美国 QA 岗的人打开看板，标签页写「UAE 求职看板」、
侧栏写「UAE 求职作战板 8-29」。两处都是从原版模板原样拷来的常量。
身份字段（标题 / 品牌行 / 日期）必须每次从该用户的 config 归一。
"""
import io, os, re, sys, glob
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
FAIL = []
BAD = re.compile(r"\bUAE\b|阿联酋|UAE 求职|求职作战板 8-2\d")
# 模板层：常量里不许有
for f in glob.glob(os.path.join(ROOT, "assets/board/*")) + glob.glob(os.path.join(ROOT, "scripts/board/*.py")):
    src = io.open(f, encoding="utf-8", errors="replace").read()
    code = "\n".join(l for l in re.sub(r'"""(?:.|\n)*?"""', "", src).split("\n") if not l.lstrip().startswith(("#", "/*", "*", "//")))
    hits = [l.strip()[:80] for l in code.split("\n") if BAD.search(l) and "{{" not in l]
    if hits:
        FAIL.append(f); print("❌ %s：%s" % (os.path.relpath(f, ROOT), hits[0]))
# 产物层：任何 workspace 里已生成的 board.html 都不许有
for f in glob.glob(os.path.join(ROOT, "workspace/*/board.html")):
    s = io.open(f, encoding="utf-8").read()
    t = re.sub(r"<script[\s\S]*?</script>", "", s); t = re.sub(r"<[^>]+>", " ", t)
    title = re.search(r"<title>([^<]*)</title>", s).group(1)
    if BAD.search(title) or BAD.search(re.search(r'class="side-brand"[^>]*>(.*?)</a>', s).group(1)):
        FAIL.append(f); print("❌ %s：标题/品牌行还是原版的「%s」" % (os.path.relpath(f, ROOT), title))
print("全绿：模板和产物都没有原版身份字样" if not FAIL else "变红")
sys.exit(1 if FAIL else 0)
