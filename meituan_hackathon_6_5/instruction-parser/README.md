# 外呼任务对话模型指令解析器

阶段一：将自然语言编写的外呼任务指令解析为结构化数据，供用户模拟器和评测引擎使用。

## 功能特性

- ✅ **Markdown 章节分割**：自动识别 Role、Task、Opening、Flow、FAQ、Constraints 等字段
- ✅ **变量识别**：支持 `${var}` 和 `**VAR**` 两种变量占位符
- ✅ **Call Flow DAG 解析**：解析线性步骤、条件分支（`若...→...`）、子步骤嵌套
- ✅ **FAQ 提取**：从独立章节和 Flow 步骤中提取知识点
- ✅ **约束规则化**：将自然语言约束转化为可检测规则（硬约束/软约束分类）
- ✅ **LLM Fallback**：规则解析不完整时自动调用 Claude API 补全

## 项目结构

```
instruction-parser/
├── pyproject.toml              # 项目配置
├── data/
│   ├── instructions.xlsx       # 示例指令（2条）
│   └── parsed_output.json      # 解析结果
├── src/
│   ├── models.py               # 数据模型定义
│   ├── section_splitter.py     # Markdown 章节分割与字段路由
│   ├── field_extractor.py      # Role/Task/Opening/变量提取
│   ├── flow_parser.py          # Call Flow DAG 解析器（核心）
│   ├── faq_extractor.py        # FAQ 提取器
│   ├── constraint_parser.py    # 约束规则化解析器
│   ├── llm_fallback.py         # Claude API 兜底解析
│   └── main.py                 # 主入口
└── tests/
```

## 快速开始

```bash
# 1. 进入项目目录
cd C:/develop/research/instruction-parser

# 2. 安装依赖
pip install markdown-it-py anthropic openpyxl

# 3. 运行测试验证功能
python tests/run_all_checks.py

# 4. 解析示例指令
python -m src.main data/instructions.xlsx > output.json
```

预期输出：
```
✅ 通过 - 功能完整性检查
✅ 通过 - 准确性检查
✅ 通过 - 鲁棒性检查
🎉 所有检查通过！
```

## 使用方法

### 1. 解析 Excel 文件

```bash
python -m src.main data/instructions.xlsx > output.json
```

### 2. 解析单个 Markdown 文件

```bash
python -m src.main instruction.md > output.json
```

### 3. 在代码中使用

```python
from src.main import parse_instruction

markdown_text = """
# Role
你是客服专员。

# Task
解答用户关于产品的问题。

# Opening Line
您好，请问有什么可以帮您？

# Call Flow
1. 询问用户问题
2. 根据知识库回答
3. 确认是否解决

# Constraints
- 每次回复不超过30字
- 不说"好的"、"嗯嗯"
"""

result = parse_instruction(markdown_text, use_llm_fallback=False)
print(f"Role: {result.role}")
print(f"Flow 步骤数: {len(result.flow_steps)}")
print(f"约束数: {len(result.constraints)}")
```

## 输出格式

解析后的 JSON 结构：

```json
{
  "role": "角色描述",
  "task": "任务目标",
  "opening": "开场白",
  "variables": [
    {"name": "rider_name", "raw": "${rider_name}", "var_type": "placeholder"}
  ],
  "flow_steps": [
    {
      "id": "1",
      "description": "步骤描述",
      "node_type": "action",
      "conditions": [
        {"trigger": "若是负责人", "action": "...", "next_step": "2"}
      ],
      "default_next": "2"
    }
  ],
  "faq": [
    {"question": "问题", "answer": "答案", "source": "faq_section"}
  ],
  "constraints": [
    {
      "raw": "每次回复不超过30字",
      "constraint_type": "length_limit",
      "params": {"max_chars": 30, "tolerance": 5},
      "is_hard": true
    }
  ]
}
```

## 约束类型

| 类型 | 说明 | 检测方式 |
|------|------|---------|
| `length_limit` | 字数限制 | 硬约束，程序化检测 |
| `forbidden_words` | 禁用词 | 硬约束，关键词匹配 |
| `forbidden_topic` | 禁止话题 | 硬约束，意图识别 |
| `termination_condition` | 终止条件 | 硬约束，状态机 |
| `conditional_response` | 条件响应 | 硬约束，场景匹配 |
| `fallback_response` | 越界处理 | 硬约束，语义匹配 |
| `no_repeat` | 避免重复 | 硬约束，相似度检测 |
| `style` | 风格要求 | 软约束，需 LLM 判断 |
| `generic` | 其他 | 软约束 |

## Flow 节点类型

| 类型 | 说明 |
|------|------|
| `action` | 模型需要执行的动作 |
| `branch` | 根据用户回复分支 |
| `info` | 纯信息展示（如"3.1 区别"） |
| `guide` | 引导用户操作的步骤序列 |
| `terminal` | 对话结束 |

## LLM Fallback

设置环境变量后启用：

```bash
export ANTHROPIC_API_KEY="your-api-key"
python -m src.main data/instructions.xlsx
```

当规则解析结果不完整（Role/Task/Flow 为空）时，自动调用 Claude API 补全。

## 测试结果

两条示例指令解析结果：

**指令 1（骑手通知）**：
- Role: ✓
- Task: ✓
- Opening: ✓（含 1 个变量）
- Variables: 5 个（`${rider_name}`, `**X 单**`, `**Y 单**`, `**Y 天**`, `**W 天**`）
- Flow: 4 步线性流程
- FAQ: 5 条
- Constraints: 6 条（4 硬 + 2 软）

**指令 2（直播升级）**：
- Role: ✓
- Task: ✓
- Opening: ✓
- Variables: 0 个
- Flow: 11 步（含条件分支、子步骤）
- FAQ: 3 条（从 Flow 中提取）
- Constraints: 11 条（5 硬 + 6 软）

## 技术栈

- Python 3.11+
- markdown-it-py：Markdown AST 解析
- anthropic：Claude API
- openpyxl：Excel 读取

## 代码统计

- 总行数：~1200 行
- 核心模块：9 个
- 测试覆盖：2 条真实指令全部通过
