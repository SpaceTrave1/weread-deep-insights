# WeRead Deep Insights

微信读书深度阅读画像工具。它通过 WeRead Agent Gateway 导出个人书架、阅读进度、阅读统计、笔记、划线和个人点评，生成可离线查看的 Markdown 与 HTML 报告。

## 功能

- 汇总累计阅读时长、读书天数、读过/读完书籍、书架结构和笔记覆盖情况。
- 分析阅读主题、常见问题意识、思维风格、价值信号、焦虑来源和长期兴趣方向。
- 基于个人笔记和点评抽取证据片段，避免只靠关键词做空泛判断。
- 评估信息茧房风险，并给出个性化阅读、写作、思考和行动建议。
- 输出自包含 HTML 报告和 Markdown 报告。

## 使用方式

先设置 `WEREAD_API_KEY` 环境变量，或在项目根目录创建本地 `.env` 文件：

```bash
WEREAD_API_KEY=your_api_key
```

运行生成器：

```bash
python scripts/generate_deep_report.py --format both --output-dir ./weread-reports
```

常用参数：

```bash
python scripts/generate_deep_report.py \
  --format html \
  --output-dir ./weread-reports \
  --title "我的微信读书深度画像"
```

## 输出

- `weread_deep_report.md`
- `weread_deep_report.html`

报告内容可能包含个人阅读记录和笔记。默认 `.gitignore` 会排除 `.env`、缓存文件和本地报告输出目录，避免误传隐私数据。

## 目录结构

```text
agents/                 OpenAI/Codex skill metadata
assets/                 HTML report template
references/             分析口径与 API 覆盖说明
scripts/                报告生成脚本
SKILL.md                Codex skill instruction
```

## 依赖

只依赖 Python 标准库，不需要安装第三方 Python 包。
