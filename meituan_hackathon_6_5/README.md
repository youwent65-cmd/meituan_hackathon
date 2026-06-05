# 外呼任务对话模型 — 指令遵循能力自动评估系统

对 AI 对话模型（SUT）进行五维度量化评估，判断其是否严格遵循预设的 Call Flow 指令。系统通过模拟用户与 SUT 进行多轮对话，自动生成测试用例并输出可解释的评测报告。

## 架构概览

```
┌─────────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  指令解析器          │ ──> │  用户模拟器        │ ──> │  评测引擎          │
│  Instruction Parser │     │  User Simulator   │     │  Evaluation Engine│
│                     │     │                   │     │                   │
│  Excel/MD → 结构化   │     │  L1 规则引擎      │     │  流程完整度 (30%)  │
│  JSON 指令          │     │  L2 对抗生成      │     │  约束遵循度 (30%)  │
│                     │     │  L3 LLM Agent    │     │  FAQ准确性 (20%)  │
│                     │     │                   │     │  对话自然度 (10%)  │
│                     │     │                   │     │  任务完成度 (10%)  │
└─────────────────────┘     └──────────────────┘     └──────────────────┘
         ↓                         ↓                        ↓
  parsed_output.json      dialogue_records.json      evaluation_report.md
```

## 目录结构

```
meituan_hackathon_6_2_2/
├── main.py                          # 全管线编排入口
├── app.py                           # Web UI (Flask)
├── config.py                        # 全局配置
├── README.md
│
├── instruction-parser/              # 模块一：指令解析器
│   ├── src/
│   │   ├── main.py                  #   解析器主入口
│   │   ├── models.py                #   数据模型
│   │   ├── section_splitter.py      #   章节分割
│   │   ├── field_extractor.py       #   字段提取（含变量识别）
│   │   ├── flow_parser.py           #   Call Flow 解析
│   │   ├── constraint_parser.py     #   约束解析
│   │   ├── faq_extractor.py         #   FAQ 抽取
│   │   └── llm_fallback.py          #   LLM 补全（支持多 provider）
│   ├── tests/
│   │   ├── test_completeness.py     #   完整性检查
│   │   ├── test_accuracy.py         #   准确性检查
│   │   ├── test_robustness.py       #   鲁棒性检查
│   │   └── run_all_checks.py        #   总检查脚本
│   └── data/
│       └── parsed_output.json       #   解析结果样例
│
├── user_simulator/                  # 模块二：用户模拟器
│   ├── main.py                      #   模拟器主入口
│   ├── models.py                    #   数据模型
│   ├── profile_manager.py           #   用户画像管理
│   ├── test_case_generator.py       #   测试用例生成
│   ├── dialogue_driver.py           #   对话驱动器（信号检测+FAQ处理）
│   ├── mock_sut_v2.py               #   Mock SUT（步骤感知+口语化回复）
│   ├── context_tracker.py           #   上下文追踪
│   ├── recorder.py                  #   对话记录器
│   └── layers/
│       ├── l1_rule_engine.py        #   L1 规则引擎
│       ├── l2_adversarial.py        #   L2 对抗生成
│       └── l3_llm_agent.py          #   L3 LLM Agent（多 provider 支持）
│
├── evaluation_engine/               # 模块三：评测引擎
│   ├── main.py                      #   评测器主入口
│   ├── models.py                    #   数据模型
│   ├── scorer.py                    #   加权评分器
│   ├── flow_evaluator.py            #   流程完整度评估（多策略匹配）
│   ├── constraint_evaluator.py      #   约束遵循度评估
│   ├── faq_evaluator.py             #   FAQ 准确性评估（前缀剥离+ngram匹配）
│   ├── naturalness_evaluator.py     #   对话自然度评估（规则+LLM-as-Judge）
│   ├── task_evaluator.py            #   任务完成度评估（递进评分）
│   └── report_generator.py          #   报告生成器
│
├── static/                          # Web UI 前端资源
│   ├── css/style.css
│   └── js/app.js
├── templates/                       # Web UI 模板
│   └── index.html
├── output/                          # 对话记录输出目录
├── reports/                         # 评测报告输出目录
├── uploads/                         # 上传文件暂存
└── archive/                         # 报告归档
```

## 环境准备

- Python 3.8+
- pip

## 安装

```bash
# 1. 进入项目目录
cd meituan_hackathon_6_2_2

# 2. 安装基础依赖
pip install flask openpyxl

# 3. 如需启用 LLM 增强（L3 Agent + LLM-as-Judge）
# Anthropic Claude:
pip install anthropic

# DeepSeek / OpenAI:
pip install openai
```

## 快速开始

### 方式一：Web UI（推荐）

```bash
python app.py
```

浏览器访问 `http://127.0.0.1:5000`，上传指令文件（Excel/JSON/Markdown）或使用内置样例，点击"开始评估"即可。

**启用 LLM 增强**：在 Web UI 中勾选"LLM 增强评测"→ 选择提供商（DeepSeek/Anthropic/OpenAI）→ 填入 API Key → 开始评估。

Web UI 会实时显示评估进度、结果图表、LLM 运行状态和 API 错误提示。

### 方式二：命令行一键评估

```bash
# 从 Excel 文件评估（Mock 模式）
python main.py --input "命题二：外呼任务对话模型指令示例 (1).xlsx"

# 从已解析的 JSON 评估
python main.py --parsed instruction-parser/data/parsed_output.json

# 自定义参数
python main.py --parsed instruction-parser/data/parsed_output.json \
    --profiles 8 --max-turns 20 --output-dir output --report-dir reports

# 启用 LLM 增强 — Anthropic Claude
python main.py --input data.xlsx --llm --llm-provider anthropic --llm-key "sk-ant-..."

# 启用 LLM 增强 — DeepSeek
python main.py --input data.xlsx --llm --llm-provider deepseek --llm-key "sk-..."

# 启用 LLM 增强 — OpenAI
python main.py --input data.xlsx --llm --llm-provider openai --llm-key "sk-..."

# 自定义 API 端点（Ollama / vLLM 等兼容服务）
python main.py --input data.xlsx --llm --llm-provider openai \
    --llm-key "ollama" --llm-base-url "http://localhost:11434/v1" --llm-model "qwen2.5"
```

### 方式三：分步运行

```bash
# Step 1: 指令解析
cd instruction-parser
python -m src.main "命题二：外呼任务对话模型指令示例 (1).xlsx" > data/parsed_output.json
cd ..

# Step 2: 用户模拟
python -m user_simulator.main instruction-parser/data/parsed_output.json

# Step 3: 评测
python -m evaluation_engine.main output/all_dialogue_records_*.json \
    --instruction instruction-parser/data/parsed_output.json

# Step 3 (启用 LLM-as-Judge):
python -m evaluation_engine.main output/all_dialogue_records_*.json \
    --instruction instruction-parser/data/parsed_output.json --llm --llm-key "sk-..."
```

### 方式四：Python API

```python
from main import InstructionFollowEvaluator
from config import PipelineConfig

config = PipelineConfig(
    num_profiles=6,
    max_turns=15,
    # 启用 LLM（可选）
    # llm_provider="deepseek",
    # llm_api_key="sk-...",
)
evaluator = InstructionFollowEvaluator(config)
result = evaluator.run("instruction-parser/data/parsed_output.json")
```

## LLM 增强模式

系统支持两种运行模式，可在 Web UI 或 CLI 中切换：

### Mock 模式（默认）

- L3 用户模拟使用预置模板库（8 类共 50+ 条口语化回复）
- 评测全部基于规则（ngram 匹配、正则检测、启发式算法）
- 无需 API Key，开箱即用
- 适合：快速验证评估管线、测试结构化维度（流程/约束/FAQ/任务）

### LLM 增强模式

- L3 用户模拟调用 LLM API 实时生成自然对话
- 自然度评估启用 LLM-as-Judge（抽样对话由 LLM 评分，规则 40% + LLM 60%）
- 指令解析不完整时触发 LLM Fallback 补全
- 前端显示运行模式徽章、LLM-as-Judge 状态、API 错误提示
- 适合：真实对话压力测试、自然度敏感场景

### 支持的 LLM 提供商

| 提供商 | `--llm-provider` | 默认模型 | 默认端点 | 所需 pip 包 |
|--------|-------------------|----------|----------|-------------|
| Anthropic Claude | `anthropic` | `claude-sonnet-4-6` | 标准 | `anthropic` |
| DeepSeek | `deepseek` | `deepseek-chat` | `https://api.deepseek.com` | `openai` |
| OpenAI | `openai` | `gpt-4o` | 标准 | `openai` |
| 自定义兼容 | `openai` + `--llm-base-url` | 需指定 `--llm-model` | 自定义 | `openai` |

## 评测维度

| 维度 | 权重 | 评估内容 |
|------|------|----------|
| 流程完整度 | 30% | 是否按 Call Flow 执行所有必要步骤、步骤顺序是否正确 |
| 约束遵循度 | 30% | 字数限制、禁用词、越界处理、终止条件等约束是否满足 |
| FAQ 准确性 | 20% | FAQ 回答是否准确、是否存在幻觉信息 |
| 对话自然度 | 10% | 回应多样性、过渡自然度、口语化程度（可选 LLM-as-Judge） |
| 任务完成度 | 10% | 对话是否达成预设任务目标（递进评分：正常结束100/超轮次覆盖分/无进展覆盖×0.7） |

> N/A 维度的权重会按比例重新分配给活跃维度，不会被计入总分。报告中对 N/A 维度显示 "N/A" 而非 100 分。

### 等级划分

| 等级 | 分数区间 | 含义 |
|------|----------|------|
| A | ≥ 90 | 优秀 |
| B | ≥ 75 | 良好 |
| C | ≥ 60 | 合格 |
| D | ≥ 40 | 待改进 |
| F | < 40 | 不合格 |

## 配置参数

编辑 `config.py` 或通过 CLI 参数调整：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| max_turns | 15 | 最大对话轮次 |
| num_profiles | 6 | 用户画像数量 |
| llm_provider | mock | LLM 提供商: mock / anthropic / deepseek / openai |
| llm_model | (自动) | LLM 模型名，不指定则按 provider 自动选择 |
| llm_api_key | (空) | LLM API Key |
| llm_base_url | (空) | 自定义 API 端点（OpenAI 兼容） |
| llm_temperature | 0.8 | LLM 温度参数 |
| use_llm_fallback | False | 指令解析不完整时启用 LLM 补全 |
| llm_judge_enabled | False | 启用 LLM-as-Judge 自然度评估 |
| length_tolerance | 5 | 字数限制容差 |
| hard_constraint_deduction | 10.0 | 硬约束违规单次扣分 |
| soft_constraint_deduction | 3.0 | 软约束违规单次扣分 |
| step_miss_deduction | 8.0 | 步骤遗漏扣分 |
| hallucination_deduction | 15.0 | 幻觉严重扣分 |
| faq_similarity_threshold | 0.7 | FAQ 相似度阈值 |
| output_dir | output | 对话记录输出目录 |
| report_dir | reports | 评测报告输出目录 |

## 用户模拟器三层体系

| 层次 | 名称 | 说明 |
|------|------|------|
| L1 | 流程驱动模拟 | 严格按 Call Flow 步骤给出预期用户回复（模板 + 状态机） |
| L2 | 边界测试模拟 | 模拟偏离流程、拒绝、越界、打断、重复追问等对抗场景 |
| L3 | 自由对话模拟 | 基于 LLM 扮演用户角色进行开放式对话，支持 Anthropic/DeepSeek/OpenAI |

### Mock SUT 特性

内置的 `mock_sut_v2` 实现了以下能力：
- **步骤感知回复**：按 Flow 步骤逐一推进，描述文本自动转换为自然口语
- **用户信号检测**：识别打断、不耐烦、拒绝、困惑四类信号并给出对应回应
- **FAQ 匹配**：基于 2-gram Jaccard 重叠度匹配 FAQ 问题（阈值 0.25）
- **防死循环**：连续 3 次同类型信号强制推进步骤

### L3 Mock 回复

Mock 模式下 L3 使用结构化回复库（8 类场景，去重追踪），根据用户画像（配合度/情绪/跑题概率）和对话上下文选择单条完整回复，不再随机拼接片段。

## 测试维度覆盖

每条指令自动生成多种测试用例，覆盖：Happy Path、分支路径、FAQ 触发、越界问题、拒绝/挂断、重复追问、角色边界、打断、信息缺失、开车挂断、繁忙继续、自由对话等场景。共约 20-30 条测试用例/指令。

## FAQ 评估机制

FAQ 准确性评估采用以下流程：

1. **问题匹配**：用户消息与 FAQ 条目做 2-gram Jaccard 重叠度匹配（阈值 0.25），触发最匹配的 FAQ
2. **答案比对**：Mock SUT 生成 FAQ 回答后，评测引擎剥离 SUT 应答前缀（如"好的，关于您问的这个问题——"），对纯答案文本与期望答案做 3-gram Jaccard 相似度计算
3. **幻觉检测**：相似度 < 0.3 且非空时判定为幻觉（严重违规，扣 15 分）
4. **评分公式**：`召回率 × 60 + 精确度均值 × 40 - 违规扣分`

## 输入格式

### Excel 指令文件

支持含 `Role`、`Task`、`Opening Line`、`Call Flow`、`FAQ`、`Constraints` 等章节的 Markdown 格式文本，可存放在 Excel 单元格中。

### JSON 指令文件

```json
[{
  "role": "角色描述",
  "task": "任务目标",
  "opening": "开场白",
  "variables": [{"name": "rider_name", "raw": "${rider_name}", "var_type": "placeholder"}],
  "flow_steps": [
    {"id": "1", "description": "步骤描述", "node_type": "action", "is_required": true}
  ],
  "faq": [{"question": "问题", "answer": "答案"}],
  "constraints": [
    {"raw": "每次回复不超过30字", "constraint_type": "length_limit", "params": {"max_chars": 30}, "is_hard": true}
  ]
}]
```

## 输出

### 对话记录 (`output/`)

- `all_dialogue_records_YYYYMMDD_HHMMSS.json` — 完整对话记录
- `evaluation_summary_YYYYMMDD_HHMMSS.md` — 评估汇总报告

### 评测报告 (`reports/`)

- `evaluation_report_*.md` — 结构化 Markdown 报告（概览、分维度得分、违规详情、改进建议、LLM 状态）
- `evaluation_report_*.json` — 机器可读 JSON 报告

### 报告归档 (`archive/`)

每次 Web UI 评估完成后自动归档到 `archive/YYYY-MM-DD/` 目录。

## 运行测试

```bash
cd instruction-parser/tests
python run_all_checks.py
```

包含三个检查：
- **完整性检查** (`test_completeness.py`)：验证解析结果字段完整性
- **准确性检查** (`test_accuracy.py`)：验证解析结果与原始指令一致性
- **鲁棒性检查** (`test_robustness.py`)：边界情况和异常输入测试

## 常见问题

**Q: 如何接入真实的 SUT（被评测对话模型）？**

```python
def my_sut(user_msg: str) -> str:
    response = your_model_api.chat(user_msg)
    return response.text

evaluator = InstructionFollowEvaluator(config, sut_callback=my_sut)
evaluator.run("data.xlsx")
```

**Q: Mock 模式和真实 SUT 模式有什么区别？**

Mock 模式使用内置的 `mock_sut_v2` 模拟一个"基本合格"的 SUT，用于快速验证评估管线是否正常工作。真实评估时应接入实际的 SUT。

**Q: Mock 模式和 LLM 增强模式有什么区别？**

Mock 模式下 L3 用户模拟使用预置模板，自然度评估纯规则评分。LLM 增强模式调用真实 LLM API 生成用户回复（更自然多样），并启用 LLM-as-Judge 从连贯性/人性化/应变能力/简洁度四个维度评估对话质量。开启方式：Web UI 勾选"LLM 增强评测"或 CLI 加 `--llm --llm-provider deepseek --llm-key xxx`。

**Q: 为什么 LLM 增强模式显示"未生效"？**

常见原因：1) 未配置 API Key；2) `llm_provider` 未正确设置（Web UI 需选择提供商，CLI 需加 `--llm-provider`）；3) API Key 无效或网络不通。前端报告预览中的"系统状态"区域会显示具体错误原因。

**Q: 评估结果中某些维度显示 N/A 是什么意思？**

表示该维度不适用（如无 FAQ 条目时 FAQ 准确性为 N/A）。N/A 维度的权重会自动按比例分配给其他活跃维度，不会被计为 0 分或 100 分。

**Q: 评估结果的可靠性如何？**

规则引擎（L1/L2）的评估结果具有确定性和可解释性，每个扣分都附带违规证据和原始约束引用。LLM-as-Judge 仅作为可选的增强手段，最终得分为规则分 40% + LLM 分 60%。

**Q: 支持哪些指令文件格式？**

输入支持 Excel (.xlsx/.xls)、JSON (.json) 和 Markdown (.md) 三种格式。

**Q: 项目是否依赖特定的工作目录？**

不依赖。所有路径均使用 `Path(__file__).parent` 相对路径，可从任意目录运行。
