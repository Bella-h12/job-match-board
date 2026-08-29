# -*- coding: utf-8 -*-
"""一条命令跑完整个接入：python3 start.py

按顺序问四件事，每件都要你确认，确认完才往下走：
  1  简历在哪 → 生成事实清单 → 你逐条确认
  2  想在哪个地区找 + LinkedIn 从哪页读
  3  从简历推出的岗位方向 → 你确认或改
  4  邮箱（必填，回执和面试邀约靠它进台账）+ 你自己的模型 key
然后用你自己登录的浏览器抓岗、打分、写点评、出看板。

重跑同一个名字会接着上次的状态走，不会重复问已经确认过的。
"""
import io, json, os, subprocess, sys, getpass

HERE = os.path.dirname(os.path.abspath(__file__))
S = os.path.join(HERE, "scripts")
PY = sys.executable


def ask(q, default=""):
    v = input("%s%s: " % (q, (" [%s]" % default) if default else "")).strip()
    return v or default


def yes(q):
    return input("%s (y/n): " % q).strip().lower() in ("y", "yes", "是")


def run(*cmd, env=None, check=True):
    r = subprocess.run([PY] + list(cmd), cwd=HERE, env=env)
    if check and r.returncode != 0:
        raise SystemExit("上一步失败，停在这里（不往下跑，免得后面全建在错的基础上）")


def main():
    print("=== 求职看板 · 接入 ===\n")
    name = ask("给这个工作区起个英文标识（例如 alex）")
    if not name:
        raise SystemExit("需要一个标识")
    ws = os.path.join(HERE, "workspace", name)
    cfg_p, facts_p = os.path.join(ws, "config.json"), os.path.join(ws, "facts.json")

    # ---------- 1 简历 ----------
    if not os.path.exists(facts_p):
        resume = os.path.expanduser(ask("简历文件路径（.pdf / .docx / .txt）"))
        if not os.path.exists(resume):
            raise SystemExit("找不到这个文件：%s" % resume)
        loc = ask("想在哪个地区找（例如 Dubai / United States / Remote）")
        if not loc:
            raise SystemExit("地区必填：不填没法搜，填错抓到的全是别人的岗")
        li = ask("LinkedIn 从哪页读？有「Jobs where you'd be a top applicant」那页就贴 URL，没有就回车走搜索",
                 "https://www.linkedin.com/jobs/collections/recommended/")
        email = ask("邮箱（必填：投递回执和面试邀约靠它进台账）")
        if "@" not in email:
            raise SystemExit("邮箱必填，而且要是个真地址")
        run(os.path.join(S, "setup_user.py"), "--name", name, "--resume", resume,
            "--location", loc, "--linkedin-url", li, "--email", email, "--yes")
    cfg = json.load(io.open(cfg_p, encoding="utf-8"))
    facts = json.load(io.open(facts_p, encoding="utf-8"))

    # ---------- 1b 事实清单确认 ----------
    if not facts.get("confirmed"):
        print("\n--- 从简历抽出的事实清单（判据的唯一基准，必须你点头）---")
        print("总年限：%s 年" % facts.get("years_total"))
        for k, v in (facts.get("title_years") or {}).items():
            if v:
                print("  %-40s %g 年" % (k.split("|")[0][:40], v))
        print("简历上找到：" + "、".join(list((facts.get("_evidence") or {}).keys())))
        print("简历上没找到（lacks）：%d 项 —— 意思是「这份简历里没写」，不是「你一定不会」" % len(facts.get("lacks") or []))
        print("完整清单在 %s，不对就去改。" % facts_p)
        if not yes("这份清单对吗？（改完再回来按 y）"):
            raise SystemExit("先改 facts.json，改完重跑 python3 start.py")
        facts = json.load(io.open(facts_p, encoding="utf-8"))
        facts["confirmed"] = True
        json.dump(facts, io.open(facts_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------- 3 岗位方向确认 ----------
    if not cfg.get("roles_confirmed"):
        print("\n--- 从简历推出的岗位方向（搜岗就按这几个词搜）---")
        for i, r in enumerate(cfg.get("roles") or [], 1):
            print("  %d. %s" % (i, r))
        v = ask("对就回车；要改就重新输入，逗号分隔")
        if v:
            cfg["roles"] = [x.strip() for x in v.split(",") if x.strip()]
        cfg["roles_confirmed"] = True
        json.dump(cfg, io.open(cfg_p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------- 4 模型 key ----------
    env = dict(os.environ)
    if not env.get("JMB_MODEL_KEY"):
        print("\n--- 你自己的模型（只用来写每岗点评；不给就跳过，看板照出但决策台为空）---")
        k = getpass.getpass("模型 key（回车跳过）: ").strip()
        if k:
            env["JMB_MODEL_KEY"] = k
            env["JMB_MODEL_PROVIDER"] = ask("接口格式 anthropic / openai", "openai")
            env["JMB_MODEL_BASE"] = ask("接口地址", "https://api.openai.com/v1" if env["JMB_MODEL_PROVIDER"] == "openai" else "https://api.anthropic.com")
            env["JMB_MODEL"] = ask("模型名", "gpt-5" if env["JMB_MODEL_PROVIDER"] == "openai" else "claude-sonnet-5")
    if not env.get("JMB_EMAIL_PASS"):
        p = getpass.getpass("邮箱密码/应用专用密码（用来读回执；回车这次先不读）: ").strip()
        if p:
            env["JMB_EMAIL_PASS"] = p

    # ---------- 抓岗 → 打分 → 点评 → 看板 ----------
    print("\n--- 用你登录的浏览器抓岗（LinkedIn 要先在 Chrome 里登录好）---")
    run(os.path.join(S, "fetch_jobs.py"), ws, "--max-per-role", "15")
    if env.get("JMB_EMAIL_PASS"):
        run(os.path.join(S, "fetch_inbox.py"), ws, env=env, check=False)
    run(os.path.join(S, "run.py"), ws)
    run(os.path.join(S, "enrich.py"), ws, env=env)
    run(os.path.join(S, "board", "make_board_json.py"), ws)
    run(os.path.join(S, "board", "render.py"), ws)
    run(os.path.join(S, "board", "assemble.py"), ws)
    print("\n完成 → %s/board.html（用浏览器打开）" % ws)
    print("以后每天重跑：python3 start.py，输同一个标识，只会重抓岗和重打分。")


if __name__ == "__main__":
    main()
