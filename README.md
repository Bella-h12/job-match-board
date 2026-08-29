# job-match-board

上传简历 → 系统从简历推出适合的岗位方向 → 去 LinkedIn 抓这些岗 → 逐条对着 JD 原文算匹配 →
生成一张**每天原地更新的求职看板**。一人一个工作区，格式完全一样，内容全是自己的。

**每个分数都能点开看它是从 JD 哪句话来的。** 这是它跟别的匹配工具唯一的区别。

## 接入（四样东西）

```bash
git clone https://github.com/Bella-h12/job-match-board && cd job-match-board

# 1  简历（.pdf / .docx / .txt）。方向不用填，脚本从简历推；要改就 --roles 指定
python3 scripts/setup_user.py --name alex --resume ~/Desktop/resume.pdf --location "United States"

# 2  ⚠ 本人过一遍 workspace/alex/facts.json，把 confirmed 改成 true（理由见下）

# 3  LinkedIn —— 用你自己已登录的浏览器（装 uv，脚本自己起 mcp-server-linkedin）
python3 scripts/fetch_jobs.py workspace/alex

# 4  邮箱（可选）—— IMAP，Gmail 要「应用专用密码」；密码只走环境变量
export JMB_EMAIL_PASS='...'
python3 scripts/fetch_inbox.py workspace/alex

# 5  你自己的模型（可选，只用来写每岗的点评；不给就跳过，看板照出但决策台为空）
export JMB_MODEL_KEY=...  JMB_MODEL_PROVIDER=openai  JMB_MODEL_BASE=https://api.deepseek.com/v1  JMB_MODEL=deepseek-v4-flash

# 6  出看板
bash scripts/build.sh workspace/alex      # → workspace/alex/board.html
```

## 为什么第 2 步不能省

`facts.json` 是之后**每一个**岗位匹配度的基准，脚本从简历生成的只是草稿。拿三份真实简历跑过，每份都抓到不同的错：

| 简历 | 草稿的错 |
|---|---|
| 英文，数据分析 | `A/B-tested` 被判成「没有 A/B 经验」 |
| 中文，增长 | `2024.03 - 2026.04` 一条日期没认出来，**6 年经验算成 0 年** |
| 中文，测试工程师 | 职位名和日期不在同一行 → 专项年限全空；重叠区间被相加 → 总年限虚高成 6.7（真值 4.8）；「2025.09 至今」解析不出来 |

这些都修了，但同类问题一定还会有。所以 `confirmed` 不是 `true` 时打分脚本直接退出——**宁可不出分，也不拿猜的基准去判你的岗位。**

## 分数怎么算（全是确定性代码，零模型调用）

- **适配度 = 这份 JD 的硬性要求里你命中几条 ÷ 一共几条**。分母只能来自 JD 正文逐条抽取，不许手填。
- must / nice 由 **JD 自己的段标题**决定；nice 只加分不扣分（JD 多列几条 preferred 反而让你掉分，方向就是反的）。
- **没有硬门槛的岗不给百分数**，单独标出来——「没门槛」和「门槛全中」是两件事。
- 抄出的清单少于 4 条不算清单，判「未核」；**空着比编一个数诚实**。
- 专项年限不拿总年限顶（「5 年 PM」和「5 年总工龄」是两回事），也不许被「或列表」豁免。

模型只在一处：给每个岗写「公司发展四问 + 行动建议 + 触达路径 + 弹药/缺口」。用哪家、什么 key，你自己接（Anthropic 格式或 OpenAI 兼容格式都行）。没有 key 就跳过，**不编**。

## 这东西为什么不能做成网站

LinkedIn 的岗位推荐页在登录墙后面。代登录违反平台条款，封的是**你的**号。所以它只能跑在你自己的电脑上，用你自己已登录的浏览器。

## 明确不做

不代投（表单签的是你名下的条款）· 不估薪资（JD 里写薪酬数字的极少，估的你没法验）· 不改简历。

## 测试

```bash
python3 tests/test_pipeline.py     # 零网络，21 条，守上面每一条规则
```

## 目录

```
scripts/
  setup_user.py      简历 → 工作区 + 事实清单草稿 + 方向
  make_facts.py      简历解析（中英文日期、职位、能力）
  fetch_jobs.py      LinkedIn 两段式搜索 + 抓 JD
  fetch_inbox.py     邮箱回执（IMAP）
  run.py             打分
  enrich.py          模型点评（可选）
  board/             看板渲染（从原版看板原样抽出的模板）
  build.sh           一条命令跑完
workspace/<名字>/    你的工作区（不进 git）
```
