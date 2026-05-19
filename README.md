# WeRead Deep Insights

微信读书深度阅读画像工具。它通过 WeRead Agent Gateway 导出个人书架、阅读进度、阅读统计、笔记、划线和个人点评，使用本地规则、统计和模板生成可离线查看的 Markdown 与 HTML 报告。

当前版本是本地规则分析版：不调用大模型，结果具有可复现、低成本、隐私边界清晰的特点；如果需要更接近“读过全部笔记后的深度访谈式画像”，可以在本工具导出的证据基础上接入可选的大模型增强分析。

## 功能

- 汇总累计阅读时长、读书天数、读过/读完书籍、书架结构和笔记覆盖情况。
- 分析阅读主题、常见问题意识、思维风格、价值信号、焦虑来源和长期兴趣方向。
- 基于个人笔记和点评抽取证据片段，避免只靠关键词做空泛判断。
- 评估信息茧房风险，并给出基于数据的阅读、写作、思考和行动建议。
- 输出自包含 HTML 报告和 Markdown 报告。

## 使用方式

### 1. 克隆仓库

```bash
git clone https://github.com/SpaceTrave1/weread-deep-insights.git
cd weread-deep-insights
```

先设置 `WEREAD_API_KEY` 环境变量，或在项目根目录创建本地 `.env` 文件：

```bash
WEREAD_API_KEY=your_api_key
```

### 2. 本地运行

本工具只依赖 Python 标准库，不需要安装第三方 Python 包。配置好 `WEREAD_API_KEY` 后，直接运行生成器：

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

### 3. 在 AI Agent 应用中运行

这个仓库包含 `SKILL.md` 和 `agents/openai.yaml`，可以作为本地 skill/工具项目被支持本地仓库、文件读写和命令执行的 AI Agent 应用使用，例如 WorkBuddy、OpenClaw、Codex，以及其他兼容本地 skill 或可执行 shell 命令的应用。

如果应用支持读取本地 skill，可以让它使用本仓库执行微信读书数据分析；如果应用不支持 `SKILL.md`，也可以让它在仓库根目录直接运行：

```bash
python scripts/generate_deep_report.py --format both --output-dir ./weread-reports
```

不同应用的 skill 自动发现机制可能不同，但本项目的核心能力不依赖特定客户端。只要应用能访问仓库文件、读取环境变量并执行 Python 命令，就可以调用本工具。

### 4. 是否需要大模型

直接运行 `scripts/generate_deep_report.py` 不需要调用大模型，也不需要 OpenAI API Key。脚本会通过 `WEREAD_API_KEY` 拉取微信读书个人数据，然后使用本地规则、统计和模板生成 Markdown/HTML 报告。

这意味着当前报告的个性化主要来自真实阅读数据本身，例如阅读时长、类别分布、书架结构、笔记密度、划线和个人点评，而不是来自大模型对全部文本的实时语义推理。

当前本地规则分析版的优点：

- 不需要模型 API Key，也没有模型调用成本。
- 分析过程更稳定，同一批数据生成结果基本一致。
- 默认不把个人笔记发送给第三方模型服务。
- 幻觉风险较低，报告更依赖可追溯的数据和证据片段。

当前版本的限制：

- 深层语义理解、隐含动机归纳和文风定制能力有限。
- 对个人经历、长期变化和复杂价值冲突的解释会偏模板化。
- 书单建议和成长建议更偏规则推断，不等同于大模型深度阅读后的定制建议。

推荐的增强方案是混合模式：先由本工具本地完成数据导出、清洗、统计和证据提取，再可选调用大模型生成增强版画像、盲区诊断、长期兴趣主线和更自然的个性化建议。这样可以同时保留本地分析的隐私与可复现性，以及大模型的语义理解和表达能力。

大模型应用可以用来更方便地触发脚本、解释报告或二次编辑报告；当前脚本本身的数据分析过程仍是本地确定性逻辑。

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
