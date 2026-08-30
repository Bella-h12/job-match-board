---
name: job-match-board
description: 把你的简历和一页 LinkedIn 岗位，变成一张按「你的简历逐条对上 JD 原文」算出来的求职看板——每个分数都能点开看它是从哪句话来的。接入需要四样：简历、感兴趣的岗位方向、你自己的 LinkedIn 登录态、一个用来收回执的邮箱。触发词：求职看板、岗位匹配、job match board、帮我看这些岗位、分析这页岗位。
---

# 求职看板

## 它跟别的匹配工具差在哪

大多数工具给你一个说不清来处的匹配度。这套东西的**唯一卖点是可证伪**：

- 分数 = **这份 JD 的硬性要求里你命中几条 ÷ 一共几条**，分母只能来自 JD 正文逐条抽取，**不许手填**
- must / nice 由 **JD 自己的段标题**决定；nice 只加分不扣分（JD 多列 preferred 反而让你掉分，方向就是反的）
- **没有硬门槛的岗不给百分数**，单独标出来——「没门槛」和「门槛全中」是两件事
- 抄不出要求清单就写「未核」，不给分、不参与排名。**空着比编一个数诚实**

核心是**确定性 Python，不调模型**——分数和排名不需要 API key。模型只用来联网查公司事实和写点评，默认走本机的 Claude Code / Codex（用你已有的订阅），两个都没装才会问你要 key。

## 接入（四样东西）

```bash
# 1) 简历 + 想投的方向 + 邮箱 + LinkedIn 入口
python3 scripts/setup_user.py --name alex \
    --resume ~/Desktop/resume.pdf \
    --roles "Data Scientist, AI Product Manager" \
    --location Dubai \
    --email alex@gmail.com

# 2) ⚠ 打开 workspace/alex/facts.json，本人过一遍，改完把 confirmed 改成 true
#    这一步不能省，理由见下面

# 3) 抓岗位（用你自己已登录的浏览器）
python3 scripts/fetch_jobs.py workspace/alex

# 4) 抓邮箱回执（可选）
export JMB_EMAIL_PASS='应用专用密码'
python3 scripts/fetch_inbox.py workspace/alex

# 5) 打分 + 出看板
python3 scripts/run.py workspace/alex
python3 scripts/render_board.py workspace/alex     # → workspace/alex/board.html
```

## 为什么第 2 步不能省

`facts.json` 是之后**每一个**岗位匹配度的基准。脚本从简历生成的是**草稿，必然有小错**：

- 实测把 `A/B-tested` 判成「没有 A/B 经验」（正则写的是 `a/b test`）
- 实测一份中文简历里 `2024.03 - 2026.04` 一条日期都没认出来，6 年经验被算成 0 年（已修，但同类问题还会有）
- 脚本按日期区间算出 5.4 年，本人简历自述 6 年 —— 这个差只有本人能拍

所以 `confirmed` 不是 `true` 时，打分脚本**直接退出**。宁可不出分，也不拿猜的基准去判他的岗位。

`lacks` 那一栏的意思是「**这份简历里没找到**」，不是「他一定不会」——不对就改。

## 连接 LinkedIn

用的是**你自己机器上已登录的浏览器会话**（`mcp-server-linkedin` 驱动本机 Chrome）。
不代登录、不存密码。个性化推荐页在登录墙后面，关键词搜索复现不了它；
而代登录违反平台条款，封的是**你的**号。**这决定了它只能跑在你自己电脑上，不能做成一个网站。**

## 连接邮箱

走 IMAP，Gmail / Outlook / 163 / 企业邮箱通用。密码只从环境变量 `JMB_EMAIL_PASS` 读，
不落盘、不进仓库。Gmail 要先开两步验证再生成「应用专用密码」。

**取到 0 封会判失败**，不会渲染成「没人回复你」——「查过了没人回」和「根本没查」是两件事。

## 换成你自己的模型

分数、排序、逐条判据全是确定性 Python，**零模型调用**。
模型只用来联网查公司事实（融资 / Glassdoor）和写点评、触达草稿，默认走本机 `claude` / `codex`，不需要 key。

## 明确不做

- **不代投 / 不代填表单**——签的是你名下的条款
- **不估薪资**——实测 30 份 JD 里写薪酬数字的是 0 份，可得率为 0 的维度进了分数只能靠编
- **不改简历**——那是另一件事

## 测试

```bash
python3 tests/test_pipeline.py     # 零网络，守上面每一条规则
```
