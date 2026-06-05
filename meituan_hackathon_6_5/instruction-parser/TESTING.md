# 阶段一指令解析器 - 检查指南

本文档提供系统化的检查方法，确保指令解析器的质量。

## 快速检查

运行所有检查：

```bash
cd C:/develop/research/instruction-parser
python tests/run_all_checks.py
```

## 检查维度

### 1. 功能完整性检查

**目的**：验证所有需求的字段是否都能正确解析。

**运行方法**：
```bash
python tests/test_completeness.py
```

**检查内容**：
- ✓ 所有必需字段存在（role, task, opening, variables, flow_steps, faq, constraints）
- ✓ Role/Task/Opening 非空
- ✓ Flow 步骤结构完整（id, description, node_type, conditions, default_next）
- ✓ Constraints 结构完整（raw, constraint_type, params, is_hard）
- ✓ 硬约束/软约束分类正确

**预期结果**：
- 指令 1：4 步 Flow、5 条 FAQ、6 条约束（4 硬 + 2 软）
- 指令 2：11 步 Flow、3 条 FAQ、11 条约束（5 硬 + 6 软）

---

### 2. 准确性检查

**目的**：验证解析结果是否符合原始指令的语义。

**运行方法**：
```bash
python tests/test_accuracy.py
```

**检查内容**：

**指令 1（骑手通知）**：
- ✓ Role 包含"站长"
- ✓ Task 包含"飞毛腿"
- ✓ Opening 包含 `${rider_name}` 变量
- ✓ 5 个变量全部识别（rider_name, X 单, Y 单, Y 天, W 天）
- ✓ Flow 为 4 步线性结构（无条件分支）
- ✓ 约束类型完整（length_limit=30, fallback_response, termination_condition, no_repeat）

**指令 2（直播升级）**：
- ✓ Role 包含"Customer Support"
- ✓ Task 包含"标准直播"和"低延迟直播"
- ✓ Opening 包含"负责人"
- ✓ Flow >= 7 步，含条件分支
- ✓ Step 1 为 branch 类型，有 >= 2 个条件
- ✓ 子步骤 3.1、3.2 存在且为 info 类型
- ✓ 约束类型完整（length_limit=20, forbidden_words, forbidden_topic, termination_condition, conditional_response）
- ✓ forbidden_words 包含"好的"、"哈哈"、"嘿嘿"、"嘻嘻"

**预期结果**：所有关键词、变量、步骤、约束都正确提取。

---

### 3. 鲁棒性检查

**目的**：测试边界情况和异常输入，确保不崩溃。

**运行方法**：
```bash
python tests/test_robustness.py
```

**测试用例**：

| 测试 | 输入 | 预期 |
|------|------|------|
| 1. 空文本 | `''` | 不崩溃，返回空字段 |
| 2. 只有标题无内容 | `# Role\n# Task` | 不崩溃，字段为空 |
| 3. 非标准标题格式 | `## 角色\n### 任务目标` | 正确识别中文标题 |
| 4. 混合中英文标题 | `# Role: 客服\n# Task: 解答` | 正确解析 |
| 5. 复杂嵌套 Flow | 多层级子步骤 | 正确解析层级 |
| 6. 特殊字符和符号 | `@#$%`, `<>&`, `😀` | 不崩溃 |
| 7. 超长文本 | 1000+ 字符 | 不崩溃 |
| 8. 无 Flow 但有其他字段 | 只有 Role/Task/Constraints | 不崩溃 |
| 9. 多个同名章节 | 两个 `# Role` | 取第一个 |
| 10. 变量格式混合 | `${name}`, `**X 单**`, `{Y}` | 识别前两种 |

**预期结果**：10/10 测试通过，无崩溃。

---

## 手动检查清单

除了自动化测试，还可以手动检查以下方面：

### 4. 代码质量检查

```bash
# 语法检查
python -m py_compile src/*.py

# 导入检查
python -c "from src.main import parse_instruction; print('✓ 导入成功')"

# 无警告运行
python -W all -m src.main data/instructions.xlsx > /dev/null
```

### 5. 输出格式检查

```bash
# 生成输出
python -m src.main data/instructions.xlsx > output.json

# 验证 JSON 格式
python -c "import json; json.load(open('output.json')); print('✓ JSON 格式正确')"

# 检查字段完整性
python -c "
import json
data = json.load(open('output.json'))
required = ['role', 'task', 'opening', 'variables', 'flow_steps', 'faq', 'constraints', 'raw_text']
for inst in data:
    missing = [f for f in required if f not in inst]
    if missing:
        print(f'✗ 缺少字段: {missing}')
    else:
        print('✓ 字段完整')
"
```

### 6. 性能检查

```bash
# 测试解析速度
time python -m src.main data/instructions.xlsx > /dev/null

# 预期：< 2 秒
```

### 7. 文档检查

- ✓ README.md 存在且完整
- ✓ 使用示例清晰
- ✓ 输出格式有文档说明
- ✓ 依赖列表准确

---

## 检查结果判定标准

### ✅ 合格标准

- 功能完整性检查：100% 通过
- 准确性检查：100% 通过
- 鲁棒性检查：>= 90% 通过（10/10 或 9/10）
- 代码无语法错误
- 输出 JSON 格式正确

### ⚠️ 需改进

- 鲁棒性检查：70-89% 通过（7-8/10）
- 部分边界情况处理不当

### ❌ 不合格

- 功能完整性或准确性检查失败
- 鲁棒性检查：< 70% 通过
- 代码有语法错误或崩溃

---

## 常见问题排查

### 问题 1：字段为空

**症状**：role/task/opening 为空

**排查**：
```bash
python -c "
from src.section_splitter import parse_sections
text = open('data/instructions.xlsx', 'rb').read()  # 读取原始文本
sections = parse_sections(text.decode('utf-8'))
print(sections.keys())
"
```

**可能原因**：
- 标题格式不匹配
- 章节分割失败

### 问题 2：Flow 步骤缺失

**症状**：flow_steps 为空或数量不对

**排查**：
```bash
python -c "
from src.main import parse_instruction
text = '''# Call Flow
1. 步骤1
2. 步骤2
'''
result = parse_instruction(text, use_llm_fallback=False)
print(f'flow_steps: {len(result.flow_steps)}')
for s in result.flow_steps:
    print(f'  [{s.id}] {s.description}')
"
```

**可能原因**：
- 步骤编号格式不匹配
- 章节标题未识别为 flow

### 问题 3：约束分类错误

**症状**：硬约束被分类为软约束

**排查**：
```bash
python -c "
from src.constraint_parser import _classify_constraint
raw = '每次回复不超过30字'
c = _classify_constraint(raw)
print(f'type: {c.constraint_type}, is_hard: {c.is_hard}, params: {c.params}')
"
```

**可能原因**：
- 正则模式未匹配
- 预处理（去 `**`）失败

---

## 提交前最终检查

运行以下命令确保一切正常：

```bash
cd C:/develop/research/instruction-parser

# 1. 运行所有自动化检查
python tests/run_all_checks.py

# 2. 重新生成输出
python -m src.main data/instructions.xlsx > data/parsed_output.json

# 3. 验证输出
python -c "
import json
data = json.load(open('data/parsed_output.json'))
print(f'✓ 成功解析 {len(data)} 条指令')
"

# 4. 检查代码质量
python -m py_compile src/*.py && echo '✓ 代码无语法错误'

# 5. 检查文档
test -f README.md && echo '✓ README 存在'
```

**预期输出**：
```
✅ 通过 - 功能完整性检查
✅ 通过 - 准确性检查
✅ 通过 - 鲁棒性检查
🎉 所有检查通过！阶段一指令解析器质量合格。
✓ 成功解析 2 条指令
✓ 代码无语法错误
✓ README 存在
```

---

## 总结

本检查体系覆盖：
- **功能完整性**：所有字段都能解析
- **准确性**：解析结果符合原始语义
- **鲁棒性**：边界情况不崩溃
- **代码质量**：无语法错误、可导入
- **输出格式**：JSON 结构正确

通过这些检查，可以确保阶段一指令解析器达到交付标准。
