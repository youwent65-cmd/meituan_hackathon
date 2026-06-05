# 用户模拟器 (User Simulator) 使用说明

## 概述

用户模拟器是"外呼任务对话模型指令遵循能力自动评估系统"的核心模块之一。它接收指令解析器输出的结构化指令，自动生成多样化、逼真的模拟用户回复，驱动与被测试对话模型 (SUT) 的多轮对话。

## 项目结构

```
user_simulator/
├── __init__.py
├── models.py                 # 数据模型定义
├── profile_manager.py        # 用户画像管理器
├── test_case_generator.py    # 测试用例生成器
├── dialogue_driver.py        # 对话驱动器（核心调度）
├── context_tracker.py        # 上下文追踪器
├── recorder.py              # 对话记录器
├── main.py                  # 主入口
├── layers/
│   ├── __init__.py
│   ├── l1_rule_engine.py     # L1 规则引擎
│   ├── l2_adversarial.py     # L2 对抗生成
│   └── l3_llm_agent.py       # L3 LLM Agent
└── README.md
```

## 三层模拟体系

| 层次 | 名称 | 说明 | 生成方式 |
|------|------|------|----------|
| L1 | 流程驱动模拟 | 严格按 Call Flow 步骤给出预期回复 | 模板 + 状态机 |
| L2 | 边界测试模拟 | 模拟偏离流程、拒绝、越界等情况 | 对抗性剧本 |
| L3 | 自由对话模拟 | 基于 LLM 扮演用户角色 | LLM Agent (可选) |

## 输入格式

用户模拟器接受与指令解析器 `parsed_output.json` 相同的格式：

```json
{
  "role": "角色描述",
  "task": "任务目标",
  "opening": "开场白文本",
  "variables": [{"name": "rider_name", "raw": "${rider_name}", "var_type": "placeholder"}],
  "flow_steps": [
    {"id": "1", "description": "步骤描述", "node_type": "action", "conditions": [], "default_next": "2", "is_required": true}
  ],
  "faq": [{"question": "问题", "answer": "答案", "source": "faq_section"}],
  "constraints": [
    {"raw": "每次回复不超过30字", "constraint_type": "length_limit", "params": {"max_chars": 30}, "is_hard": true}
  ]
}
```

**重要**: 输入格式与指令解析器 `src/main.py` 中 `ParsedInstruction.to_dict()` 的输出完全一致。

## 快速开始

### 1. 安装依赖

```bash
# 进入项目根目录
cd mietuan_hackathon_6_2_2

# 安装依赖
pip install -r requirements.txt
```

### 2. 从指令解析器输出运行

```bash
# 先用指令解析器生成 JSON
cd instruction-parser
python -m src.main data/instructions.xlsx > data/parsed_output.json

# 再运行用户模拟器
cd ../user_simulator
python -m user_simulator.main ../instruction-parser/data/parsed_output.json
```

### 3. 在代码中使用

```python
import json
from pathlib import Path

from user_simulator import UserSimulator, SimulationConfig

# 配置
config = SimulationConfig(
    max_turns=15,           # 最大对话轮次
    llm_provider="mock",    # "mock" | "anthropic" | "openai"
    temperature=0.8,        # LLM 温度
)

# 创建模拟器
simulator = UserSimulator(config)

# 从指令解析器的 JSON 文件加载
records = simulator.run_from_json("instruction-parser/data/parsed_output.json")

# 查看摘要
UserSimulator.print_records(records)

print(f"生成了 {len(records)} 条对话记录")
```

### 4. 连接真实对话模型 (SUT)

```python
from user_simulator import UserSimulator, SimulationConfig
import anthropic

# 定义 SUT 回调函数
def my_sut(user_message: str) -> str:
    client = anthropic.Anthropic(api_key="your-key")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=100,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text

# 连接真实 SUT
config = SimulationConfig(sut_provider="api")
simulator = UserSimulator(config, sut_callback=my_sut)
records = simulator.run_from_json("parsed_output.json")
```

### 5. 启用 L3 LLM Agent

```python
config = SimulationConfig(
    llm_provider="anthropic",     # 使用 Anthropic API
    llm_model="claude-sonnet-4-6",
    llm_api_key="your-api-key",   # 设置 API Key
    temperature=0.9,
)
```

## 测试维度覆盖

每条指令自动生成 **20-30 条测试用例**，覆盖以下维度：

| 编号 | 测试维度 | 模拟层 | 说明 |
|------|----------|--------|------|
| T01 | Happy Path | L1 | 标准流程全路径 |
| T02 | 分支路径 | L1 | Call Flow 每条分支 |
| T03 | FAQ 触发 | L2 | 每条 FAQ 至少触发一次 |
| T04 | 越界问题 | L2 | 超出 FAQ 范围的提问 |
| T05 | 拒绝/挂断 | L2 | 用户拒绝 + 挂断 |
| T06 | 重复追问 | L2 | 同一问题反复追问 |
| T07 | 角色边界 | L2 | 索要优惠券、质疑身份 |
| T08 | 打断/信息缺失 | L2 | 中途打断、拒答 |
| T09 | 特殊约束触发 | L2 | 开车挂断、繁忙继续 |
| T10 | 自由对话 | L3 | 多画像开放式对话 |

## 用户画像配置

每条指令生成 5-6 种用户画像：

| 画像 | 配合度 | 情绪 | 用途 |
|------|--------|------|------|
| 标准用户 | 0.9 | 平静 | Happy Path |
| 急躁用户 | 0.5 | 急躁 | 重复追问/边缘场景 |
| 挑剔用户 | 0.2 | 生气 | 拒绝/对抗场景 |
| 困惑用户 | 0.6 | 困惑 | FAQ 触发 |
| 开心用户 | 0.85 | 开心 | 自由对话 |
| 特殊场景 | 可变 | 可变 | 根据指令约束定制 |

## 输出格式

对话记录以 JSON 格式保存，结构如下：

```json
[{
  "instruction_id": "RIDER_001",
  "test_case_id": "RIDER_001_TC001",
  "test_dimension": "happy_path",
  "layer_used": "L1",
  "profile": {
    "name": "标准用户",
    "cooperation_level": 0.9,
    "emotion": "neutral",
    ...
  },
  "turns": [
    {"turn_number": 0, "role": "SUT", "content": "你好，请问是张三吗？..."},
    {"turn_number": 1, "role": "USER", "content": "对，是我。"},
    {"turn_number": 2, "role": "SUT", "content": "好的，我了解了。..."},
    ...
  ],
  "end_reason": "flow_complete",
  "total_turns": 8,
  "metadata": {
    "completed_steps": ["1", "2", "3", "4"],
    "flow_complete": true,
    "variables_used": {"rider_name": "张三", "X 单": "8"}
  }
}]
```

输出文件保存在 `output/` 目录下：
- `dialogue_records_*.json` - 完整对话记录
- `simulation_summary_*.json` - 模拟摘要

## 进阶使用

### 自定义 SUT 回调

```python
def custom_sut(user_msg: str) -> str:
    # 这里接入你的对话模型
    import requests
    resp = requests.post("https://your-model-api/chat", json={"msg": user_msg})
    return resp.json()["reply"]

simulator = UserSimulator(config, sut_callback=custom_sut)
```

### 单独使用某个模块

```python
from user_simulator.layers import L1RuleEngine, L2AdversarialGen
from user_simulator.context_tracker import DialogueContext

# 单独使用 L1
l1 = L1RuleEngine(flow_graph)
reply = l1.generate_reply(sut_msg, context, profile)

# 单独使用 L2
l2 = L2AdversarialGen(constraints, faq)
reply = l2.generate_reply(sut_msg, context, profile, test_case)
```

### 自定义测试用例

```python
from user_simulator.models import TestCase, UserProfile

custom_case = TestCase(
    id="CUSTOM_001",
    type="custom_scenario",
    layer="L2",
    profile=UserProfile(cooperation_level=0.1, emotion="angry"),
    trigger_turn=3,
    trigger_question="我想退款！",
    description="自定义退款场景",
)
```

## 注意事项

1. **Mock 模式默认值**: 不配置 LLM API 时默认使用 mock 回复，适合快速测试
2. **降级策略**: L3 LLM 调用失败时自动降级为 mock 回复，不会中断对话
3. **终止条件**: 对话在以下情况下自动终止：
   - SUT 说出"再见"、"祝您"等结束语
   - SUT 说"稍后再打"（转接/回电场景）
   - 流程所有必要步骤完成
   - 连续 3 轮无流程进展
   - 超过 max_turns 轮次上限
4. **输出目录**: 确保 `output/` 目录可写，首次运行会自动创建

## 与上下游协作

```
指令解析器 (Instruction Parser)
    │
    │  parsed_output.json (结构化指令)
    ▼
用户模拟器 (本模块)
    │
    │  dialogue_records.json (对话记录)
    ▼
评测引擎 (Evaluation Engine)
```
