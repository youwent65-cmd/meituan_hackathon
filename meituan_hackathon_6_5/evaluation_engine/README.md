# 评测引擎 (Evaluation Engine) 使用说明

## 概述

评测引擎是"外呼任务对话模型指令遵循能力自动评估系统"的第三核心模块。它接收指令解析器输出的结构化指令和用户模拟器生成的对话记录，对 SUT（被评估对话模型）进行五维度量化评分，并输出可解释的评测报告。

## 评测维度体系

| 维度 | 权重 | 核心指标 | 检测方法 |
|------|------|----------|----------|
| 流程完整度 | 30% | 步骤覆盖率、顺序正确率、触发准确性 | 关键词匹配 + 流程 DAG 比对 |
| 约束遵循度 | 30% | 字数限制、禁用词、越界处理、终止条件 | 规则引擎 + 正则表达式 |
| FAQ 准确性 | 20% | 知识召回率、精确度、幻觉检测 | n-gram 相似度 + NLI |
| 对话自然度 | 10% | 回应多样性、过渡自然度、口语化程度 | 文本特征统计 |
| 任务完成度 | 10% | 任务目标达成率 | 结束状态判断 |

## 项目结构

```
evaluation_engine/
├── __init__.py
├── models.py                   # 数据模型定义
├── flow_evaluator.py           # 流程完整度评估器
├── constraint_evaluator.py     # 约束遵循度评估器
├── faq_evaluator.py            # FAQ 准确性评估器
├── naturalness_evaluator.py    # 对话自然度评估器
├── task_evaluator.py           # 任务完成度评估器
├── scorer.py                   # 加权评分器
├── report_generator.py         # Markdown + JSON 报告生成器
├── main.py                     # 主入口
└── README.md
```

## 快速开始

### 1. 全链路一键运行

```bash
# 在项目根目录下运行

# Step 1: 指令解析
cd instruction-parser
python -m src.main data/instructions.xlsx > data/parsed_output.json
cd ..

# Step 2: 用户模拟
python -m user_simulator.main instruction-parser/data/parsed_output.json

# Step 3: 评测
python -c "
from evaluation_engine.main import EvaluationEngine
from evaluation_engine.models import EvalConfig
import json
from pathlib import Path

def read_json(p):
    try: return json.loads(Path(p).read_text(encoding='utf-8'))
    except: return json.loads(Path(p).read_text(encoding='gbk'))

inst = read_json('instruction-parser/data/parsed_output.json')[0]
records = read_json('output/all_dialogue_records_*.json')

engine = EvaluationEngine(inst, EvalConfig())
result = engine.evaluate(records)
engine.generate_report(result)
EvaluationEngine.print_result(result)
"
```

### 2. 在 Python 代码中使用

```python
from evaluation_engine import EvaluationEngine
from evaluation_engine.models import EvalConfig

# 配置
config = EvalConfig(
    length_tolerance=5,
    hard_constraint_deduction=10.0,
    soft_constraint_deduction=3.0,
)

# 创建评测引擎
engine = EvaluationEngine(parsed_instruction, config)

# 评测
result = engine.evaluate(dialogue_records)

# 查看结果
print(f"综合得分: {result.overall_score:.1f} / 100")
print(f"等级: {result.grade}")
print(f"流程完整度: {result.flow_score.score:.1f}")
print(f"约束遵循度: {result.constraint_score.score:.1f}")

# 生成报告
report_path = engine.generate_report(result)
```

### 3. 仅使用某个维度评估器

```python
from evaluation_engine.flow_evaluator import FlowEvaluator
from evaluation_engine.models import EvalConfig

config = EvalConfig()
evaluator = FlowEvaluator(config, instruction)
dimension_score = evaluator.evaluate(dialogue_records)

print(f"步骤覆盖率: {dimension_score.raw_metrics['avg_step_coverage']:.1%}")
for v in dimension_score.violations:
    print(f"  - {v.explanation}")
```

## 输入格式

评测引擎接受两个输入：

### (1) 指令 (与指令解析器输出一致)

```json
{
  "role": "角色描述",
  "task": "任务目标",
  "flow_steps": [...],
  "faq": [...],
  "constraints": [
    {"raw": "...", "constraint_type": "length_limit", "params": {...}, "is_hard": true}
  ]
}
```

### (2) 对话记录 (与用户模拟器输出一致)

```json
[{
  "instruction_id": "RIDER_001",
  "test_case_id": "RIDER_001_TC001",
  "test_dimension": "happy_path",
  "layer_used": "L1",
  "turns": [
    {"turn_number": 0, "role": "SUT", "content": "..."},
    {"turn_number": 1, "role": "USER", "content": "..."}
  ],
  "end_reason": "flow_complete",
  "total_turns": 8,
  "metadata": {"completed_steps": [...], "flow_complete": true}
}]
```

## 输出格式

### Markdown 报告 (evaluation_report_*.md)

结构化的可读报告，包含：
- 一、评测概览（综合得分 + 等级）
- 二、分维度得分（表格 + ASCII 柱状图）
- 三、详细分析（每个维度的违规详情和证据）
- 四、典型对话案例（最佳 + 最差）
- 五、改进建议（按优先级排序）

### JSON 报告 (evaluation_report_*.json)

```json
{
  "instruction_id": "RIDER_001",
  "overall_score": 75.3,
  "grade": "B",
  "dimensions": {
    "flow": {
      "score": 80.0,
      "violations": [{"violation_type": "step_miss", "explanation": "..."}],
      "raw_metrics": {"avg_step_coverage": 0.8, ...}
    }
  },
  "best_case": {...},
  "worst_case": {...},
  "improvement_items": [...]
}
```

## 可解释性保障

每条扣分都附带：
- **具体对话片段引用**：哪条测试用例、第几轮、SUT 说了什么
- **期望 vs 实际对比**：标准答案 vs 实际回答
- **违规的原始约束文本**：违反的是哪条约束
- **人类可读的解释**：通俗说明扣分原因

## 配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| length_tolerance | 5 | 字数限制容差 |
| similarity_threshold | 0.7 | FAQ 回答相似度阈值 |
| hard_constraint_deduction | 10.0 | 硬约束违规单次扣分 |
| soft_constraint_deduction | 3.0 | 软约束违规单次扣分 |
| step_miss_deduction | 8.0 | 步骤遗漏扣分 |
| hallucination_deduction | 15.0 | 幻觉严重扣分 |

## 扣分与评分逻辑

```
每个维度初始得分 = 100
每个维度最终得分 = 初始分 - sum(违规扣分)

综合得分 = SUM(维度得分 * 维度权重)

等级划分:
  A (≥90): 优秀
  B (≥75): 良好
  C (≥60): 合格
  D (≥40): 待改进
  F (<40): 不合格
```
