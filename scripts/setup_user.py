# -*- coding: utf-8 -*-
"""接入一个新用户：简历 + 感兴趣的岗位 + LinkedIn + 邮箱 → 一份 config。

用法
    python3 scripts/setup_user.py --name <标识> --resume <简历路径> \
        [--roles "AI Product Manager, Data Scientist"] [--email you@gmail.com] \
        [--linkedin-url "https://www.linkedin.com/jobs/collections/recommended/"]

产出 workspace/<标识>/：
    CV.txt         简历正文
    facts.json     事实清单草稿 —— **本人确认前不出分**
    config.json    岗位方向 / 邮箱 / LinkedIn 入口
"""
import argparse, io, json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

DEFAULT_LINKEDIN = "https://www.linkedin.com/jobs/collections/recommended/"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="工作区标识，英文，例如 alex")
    ap.add_argument("--resume", required=True, help="简历 .pdf / .docx / .txt")
    ap.add_argument("--roles", default="", help="感兴趣的岗位，逗号分隔")
    ap.add_argument("--email", default="", help="接收回执的邮箱")
    ap.add_argument("--linkedin-url", default=DEFAULT_LINKEDIN,
                    help="LinkedIn 岗位入口页。默认用 Recommended；"
                         "想用「你最可能被选中」那一页就把它的完整 URL 贴进来")
    ap.add_argument("--location", default="", help="目标城市/地区，例如 Dubai")
    a = ap.parse_args()

    ws = os.path.join(ROOT, "workspace", a.name)
    os.makedirs(ws, exist_ok=True)

    # ① 简历 → 事实清单草稿
    r = subprocess.run([sys.executable, os.path.join(HERE, "make_facts.py"), a.resume, ws],
                       capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit("简历解析失败，先把它转成 .txt 再试")

    # ② 岗位方向 / 邮箱 / LinkedIn 入口
    roles = [x.strip() for x in a.roles.split(",") if x.strip()]
    if not roles:                       # 没指定就用简历推出来的方向
        fj = json.load(io.open(os.path.join(ws, "facts.json"), encoding="utf-8"))
        roles = fj.get("suggested_roles") or []
    cfg = dict(
        name=a.name,
        roles=roles,
        location=a.location,
        email=a.email,
        linkedin_url=a.linkedin_url,
        # 邮箱怎么连：不存密码，走各家自己的授权
        email_note="Gmail 走 OAuth 或应用专用密码；其他邮箱走 IMAP。"
                   "凭据不落在这个仓库里，见 README「连接邮箱」。",
    )
    json.dump(cfg, io.open(os.path.join(ws, "config.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print()
    print("工作区：%s" % ws)
    print("下一步（这一步不能省）：")
    print("  1. 打开 %s/facts.json" % ws)
    print("     核两处：title_years（每个职位各做了几年）和 lacks（简历上没找到的能力）")
    print("     lacks 的意思是「这份简历里没写」，不是「你一定不会」——不对就改")
    print("  2. 改完把 confirmed 改成 true")
    print("  3. python3 scripts/run.py workspace/%s" % a.name)


if __name__ == "__main__":
    main()
