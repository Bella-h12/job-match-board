# -*- coding: utf-8 -*-
"""抓邮箱里的求职回执 → workspace/<名字>/inbox.json

用法：
    export JMB_EMAIL_PASS='应用专用密码'
    python3 scripts/fetch_inbox.py workspace/<名字> [--days 21]

走 IMAP，Gmail / Outlook / 163 / 企业邮箱通用。**密码只从环境变量读，不落盘、不进仓库。**
Gmail 要先开两步验证再生成「应用专用密码」（普通登录密码 IMAP 用不了）。

两条纪律（踩过才写的）：
· **取到 0 封要判失败，不是「今天没人回」。** 一个天天在投的人不可能一封回执都没有；
  恒空会被下游读成「没人理你」，比报错坏得多。
· **认证失败要指名道姓说是掉登录**，不要压成一句通用错误让人反复重试。
"""
import argparse, email, imaplib, io, json, os, re, sys
from email.header import decode_header, make_header
from datetime import datetime, timedelta

IMAP = {"gmail.com": "imap.gmail.com", "googlemail.com": "imap.gmail.com",
        "outlook.com": "outlook.office365.com", "hotmail.com": "outlook.office365.com",
        "163.com": "imap.163.com", "126.com": "imap.126.com",
        "qq.com": "imap.qq.com", "yahoo.com": "imap.mail.yahoo.com"}
KEYS = ["application", "applying", "applied", "candidate", "interview", "recruit",
        "your application", "thank you for", "position", "role at", "感谢您的申请", "面试"]


def host_for(addr, override):
    if override:
        return override
    d = addr.split("@")[-1].lower()
    if d in IMAP:
        return IMAP[d]
    raise SystemExit("不认识 %s 的 IMAP 服务器，用 --imap-host 指定" % d)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workspace"); ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--imap-host", default="")
    a = ap.parse_args()
    ws = a.workspace.rstrip("/")
    cfg = json.load(io.open(os.path.join(ws, "config.json"), encoding="utf-8"))
    addr = cfg.get("email")
    if not addr:
        raise SystemExit("config.json 里没有 email —— 先补上再跑")
    pw = os.environ.get("JMB_EMAIL_PASS")
    if not pw:
        raise SystemExit("没有 JMB_EMAIL_PASS 环境变量。密码不写进仓库，用：\n"
                         "  export JMB_EMAIL_PASS='应用专用密码'")

    try:
        M = imaplib.IMAP4_SSL(host_for(addr, a.imap_host))
        M.login(addr, pw)
    except imaplib.IMAP4.error as ex:
        raise SystemExit("邮箱登录失败（**是认证问题，不是没有邮件**）：%s\n"
                         "  Gmail 要用「应用专用密码」，不是登录密码。" % ex)
    M.select("INBOX")
    since = (datetime.now() - timedelta(days=a.days)).strftime("%d-%b-%Y")
    typ, data = M.search(None, "(SINCE %s)" % since)
    ids = data[0].split()
    rows = []
    for i in ids[-400:]:
        typ, d = M.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
        if typ != "OK" or not d or not d[0]:
            continue
        msg = email.message_from_bytes(d[0][1])
        subj = str(make_header(decode_header(msg.get("Subject") or "")))
        frm = str(make_header(decode_header(msg.get("From") or "")))
        if any(k in subj.lower() for k in KEYS):
            rows.append(dict(date=msg.get("Date"), frm=frm, subject=subj))
    M.logout()
    json.dump(dict(fetched_at=datetime.now().astimezone().isoformat(timespec="seconds"),
                   account=addr, window_days=a.days, rows=rows),
              io.open(os.path.join(ws, "inbox.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("%s：%d 天窗口，%d 封求职相关" % (addr, a.days, len(rows)))
    if not rows:
        raise SystemExit("一封都没有 —— **判失败**。要么关键词没覆盖到，要么读错了邮箱；"
                         "别把它渲染成「没人回复你」。")


if __name__ == "__main__":
    main()
