#!/usr/bin/env python
"""鲁棒性检查脚本 - 测试边界情况和异常输入"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import parse_instruction

def check_robustness():
    """检查解析器的鲁棒性"""
    print("=" * 60)
    print("鲁棒性检查")
    print("=" * 60)

    issues = []
    test_cases = []

    # 测试1: 空文本
    print("\n【测试 1：空文本】")
    try:
        result = parse_instruction('', use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - role: \"{result.role}\"")
        print(f"  - task: \"{result.task}\"")
        test_cases.append(("空文本", True, None))
    except Exception as e:
        issues.append(f"空文本处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("空文本", False, str(e)))

    # 测试2: 只有标题无内容
    print("\n【测试 2：只有标题无内容】")
    try:
        result = parse_instruction('# Role\n# Task\n# Flow', use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - role: \"{result.role}\"")
        print(f"  - flow_steps: {len(result.flow_steps)}")
        test_cases.append(("只有标题", True, None))
    except Exception as e:
        issues.append(f"只有标题处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("只有标题", False, str(e)))

    # 测试3: 非标准标题格式
    print("\n【测试 3：非标准标题格式】")
    try:
        text = '''## 角色
测试员

### 任务目标
测试系统

#### 开场白
你好
'''
        result = parse_instruction(text, use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - role: \"{result.role}\"")
        print(f"  - task: \"{result.task}\"")
        print(f"  - opening: \"{result.opening}\"")
        test_cases.append(("非标准标题", True, None))
    except Exception as e:
        issues.append(f"非标准标题处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("非标准标题", False, str(e)))

    # 测试4: 混合中英文标题
    print("\n【测试 4：混合中英文标题】")
    try:
        text = '''# Role: 客服
# Task: 解答问题
# Opening Line: 您好
# Call Flow
1. 询问
2. 回答
'''
        result = parse_instruction(text, use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - role: \"{result.role}\"")
        print(f"  - flow_steps: {len(result.flow_steps)}")
        test_cases.append(("混合中英文", True, None))
    except Exception as e:
        issues.append(f"混合中英文处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("混合中英文", False, str(e)))

    # 测试5: 复杂嵌套 Flow
    print("\n【测试 5：复杂嵌套 Flow】")
    try:
        text = '''# Call Flow
## Step 1: 开始
### 1.1 子步骤
#### 1.1.1 更深层级
- 若条件A → 动作1
- 若条件B → 动作2

## Step 2: 结束
'''
        result = parse_instruction(text, use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - flow_steps: {len(result.flow_steps)}")
        for step in result.flow_steps:
            print(f"    [{step.id}] {step.description[:30]}")
        test_cases.append(("复杂嵌套Flow", True, None))
    except Exception as e:
        issues.append(f"复杂嵌套Flow处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("复杂嵌套Flow", False, str(e)))

    # 测试6: 特殊字符和符号
    print("\n【测试 6：特殊字符和符号】")
    try:
        text = '''# Constraints
- 不说"@#$%"、"<>&"
- 每次回复不超过100字
- 若用户说"😀"→挂断
'''
        result = parse_instruction(text, use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - constraints: {len(result.constraints)}")
        for c in result.constraints:
            print(f"    [{c.constraint_type}] {c.raw[:40]}")
        test_cases.append(("特殊字符", True, None))
    except Exception as e:
        issues.append(f"特殊字符处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("特殊字符", False, str(e)))

    # 测试7: 超长文本
    print("\n【测试 7：超长文本】")
    try:
        long_text = '# Role\n' + '这是一个很长的角色描述。' * 100 + '\n# Task\n' + '任务' * 50
        result = parse_instruction(long_text, use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - role 长度: {len(result.role)}")
        print(f"  - task 长度: {len(result.task)}")
        test_cases.append(("超长文本", True, None))
    except Exception as e:
        issues.append(f"超长文本处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("超长文本", False, str(e)))

    # 测试8: 无 Flow 但有其他字段
    print("\n【测试 8：无 Flow 但有其他字段】")
    try:
        text = '''# Role
客服

# Task
回答问题

# Constraints
- 礼貌
'''
        result = parse_instruction(text, use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - role: \"{result.role}\"")
        print(f"  - flow_steps: {len(result.flow_steps)}")
        print(f"  - constraints: {len(result.constraints)}")
        test_cases.append(("无Flow", True, None))
    except Exception as e:
        issues.append(f"无Flow处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("无Flow", False, str(e)))

    # 测试9: 多个同名章节
    print("\n【测试 9：多个同名章节】")
    try:
        text = '''# Role
第一个角色

# Role
第二个角色

# Task
任务
'''
        result = parse_instruction(text, use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - role: \"{result.role}\"")
        test_cases.append(("多个同名章节", True, None))
    except Exception as e:
        issues.append(f"多个同名章节处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("多个同名章节", False, str(e)))

    # 测试10: 变量格式混合
    print("\n【测试 10：变量格式混合】")
    try:
        text = '''# Opening
你好 ${name}，今天需要完成 **X 单**，还有 {Y} 个任务
'''
        result = parse_instruction(text, use_llm_fallback=False)
        print(f"  ✓ 不崩溃")
        print(f"  - variables: {len(result.variables)}")
        for v in result.variables:
            print(f"    {v.name} ({v.var_type})")
        test_cases.append(("变量格式混合", True, None))
    except Exception as e:
        issues.append(f"变量格式混合处理失败: {e}")
        print(f"  ✗ 崩溃: {e}")
        test_cases.append(("变量格式混合", False, str(e)))

    # 汇总
    print("\n" + "=" * 60)
    print(f"测试用例总数: {len(test_cases)}")
    passed = sum(1 for _, success, _ in test_cases if success)
    failed = len(test_cases) - passed
    print(f"通过: {passed}, 失败: {failed}")

    if issues:
        print(f"\n发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"  ✗ {issue}")
        return False
    else:
        print("\n✅ 鲁棒性检查通过")
        return True

if __name__ == '__main__':
    success = check_robustness()
    sys.exit(0 if success else 1)
