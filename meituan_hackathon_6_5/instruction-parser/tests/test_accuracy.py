#!/usr/bin/env python
"""准确性检查脚本 - 验证解析结果与原始指令的一致性"""

import json
import sys
from pathlib import Path

def check_accuracy():
    """检查解析结果的准确性"""
    data_path = Path(__file__).parent.parent / 'data' / 'parsed_output.json'
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("=" * 60)
    print("准确性检查")
    print("=" * 60)

    issues = []

    # ===== 指令 1 检查 =====
    print("\n【指令 1：骑手通知】")
    inst1 = data[0]

    # 检查关键词
    checks = [
        ('role', '站长', inst1.get('role', '')),
        ('task', '飞毛腿', inst1.get('task', '')),
        ('opening', '${rider_name}', inst1.get('opening', '')),
    ]
    for field, keyword, content in checks:
        if keyword in content:
            print(f"  ✓ {field} 包含关键词 \"{keyword}\"")
        else:
            issues.append(f"指令1 {field} 缺少关键词 \"{keyword}\"")
            print(f"  ✗ {field} 缺少关键词 \"{keyword}\"")

    # 检查变量
    var_names = [v['name'] for v in inst1.get('variables', [])]
    expected_vars = ['rider_name', 'X 单', 'Y 单', 'Y 天', 'W 天']
    for var in expected_vars:
        if var in var_names:
            print(f"  ✓ 变量 \"{var}\" 已识别")
        else:
            issues.append(f"指令1 缺少变量 \"{var}\"")
            print(f"  ✗ 缺少变量 \"{var}\"")

    # 检查 Flow 步骤数
    if len(inst1.get('flow_steps', [])) == 4:
        print(f"  ✓ Flow 步骤数正确: 4")
    else:
        issues.append(f"指令1 Flow 步骤数错误: {len(inst1.get('flow_steps', []))}")
        print(f"  ✗ Flow 步骤数错误: {len(inst1.get('flow_steps', []))}")

    # 检查 Flow 是否线性（无条件分支）
    has_conditions = any(step.get('conditions') for step in inst1.get('flow_steps', []))
    if not has_conditions:
        print(f"  ✓ Flow 为线性结构（无条件分支）")
    else:
        issues.append(f"指令1 Flow 不应有条件分支")
        print(f"  ✗ Flow 不应有条件分支")

    # 检查约束类型
    constraint_types = [c['constraint_type'] for c in inst1.get('constraints', [])]
    expected_constraints = ['length_limit', 'fallback_response', 'termination_condition', 'no_repeat']
    for ct in expected_constraints:
        if ct in constraint_types:
            print(f"  ✓ 约束类型 \"{ct}\" 已识别")
        else:
            issues.append(f"指令1 缺少约束类型 \"{ct}\"")
            print(f"  ✗ 缺少约束类型 \"{ct}\"")

    # 检查 length_limit 的值
    for c in inst1.get('constraints', []):
        if c['constraint_type'] == 'length_limit':
            max_chars = c['params'].get('max_chars')
            if max_chars == 30:
                print(f"  ✓ length_limit max_chars = 30")
            else:
                issues.append(f"指令1 length_limit max_chars 应为 30，实际 {max_chars}")
                print(f"  ✗ length_limit max_chars 应为 30，实际 {max_chars}")

    # ===== 指令 2 检查 =====
    print("\n【指令 2：直播升级】")
    inst2 = data[1]

    # 检查关键词
    checks2 = [
        ('role', 'Customer Support', inst2.get('role', '')),
        ('task', '标准直播', inst2.get('task', '')),
        ('task', '低延迟直播', inst2.get('task', '')),
        ('opening', '负责人', inst2.get('opening', '')),
    ]
    for field, keyword, content in checks2:
        if keyword in content:
            print(f"  ✓ {field} 包含关键词 \"{keyword}\"")
        else:
            issues.append(f"指令2 {field} 缺少关键词 \"{keyword}\"")
            print(f"  ✗ {field} 缺少关键词 \"{keyword}\"")

    # 检查 Flow 步骤数（应该 >= 7）
    flow_count = len(inst2.get('flow_steps', []))
    if flow_count >= 7:
        print(f"  ✓ Flow 步骤数: {flow_count} (>= 7)")
    else:
        issues.append(f"指令2 Flow 步骤数不足: {flow_count}")
        print(f"  ✗ Flow 步骤数不足: {flow_count}")

    # 检查条件分支
    step1 = next((s for s in inst2.get('flow_steps', []) if s['id'] == '1'), None)
    if step1:
        if len(step1.get('conditions', [])) >= 2:
            print(f"  ✓ Step 1 有条件分支: {len(step1['conditions'])} 个")
        else:
            issues.append(f"指令2 Step 1 条件分支不足")
            print(f"  ✗ Step 1 条件分支不足")
        if step1.get('node_type') == 'branch':
            print(f"  ✓ Step 1 类型为 branch")
        else:
            issues.append(f"指令2 Step 1 类型应为 branch")
            print(f"  ✗ Step 1 类型应为 branch，实际 {step1.get('node_type')}")

    # 检查子步骤
    for sub_id in ['3.1', '3.2']:
        sub = next((s for s in inst2.get('flow_steps', []) if s['id'] == sub_id), None)
        if sub:
            print(f"  ✓ 子步骤 {sub_id} 存在")
            if sub.get('node_type') == 'info':
                print(f"  ✓ 子步骤 {sub_id} 类型为 info")
            else:
                issues.append(f"指令2 子步骤 {sub_id} 类型应为 info")
                print(f"  ✗ 子步骤 {sub_id} 类型应为 info，实际 {sub.get('node_type')}")
        else:
            issues.append(f"指令2 缺少子步骤 {sub_id}")
            print(f"  ✗ 缺少子步骤 {sub_id}")

    # 检查约束
    constraint_types2 = [c['constraint_type'] for c in inst2.get('constraints', [])]
    expected_constraints2 = ['length_limit', 'forbidden_words', 'forbidden_topic',
                             'termination_condition', 'conditional_response']
    for ct in expected_constraints2:
        if ct in constraint_types2:
            print(f"  ✓ 约束类型 \"{ct}\" 已识别")
        else:
            issues.append(f"指令2 缺少约束类型 \"{ct}\"")
            print(f"  ✗ 缺少约束类型 \"{ct}\"")

    # 检查 forbidden_words 内容
    for c in inst2.get('constraints', []):
        if c['constraint_type'] == 'forbidden_words':
            words = c['params'].get('words', [])
            expected_words = ['好的', '哈哈', '嘿嘿', '嘻嘻']
            for word in expected_words:
                if word in words:
                    print(f"  ✓ forbidden_words 包含 \"{word}\"")
                else:
                    issues.append(f"指令2 forbidden_words 缺少 \"{word}\"")
                    print(f"  ✗ forbidden_words 缺少 \"{word}\"")

    # 检查 length_limit 的值
    for c in inst2.get('constraints', []):
        if c['constraint_type'] == 'length_limit':
            max_chars = c['params'].get('max_chars')
            if max_chars == 20:
                print(f"  ✓ length_limit max_chars = 20")
            else:
                issues.append(f"指令2 length_limit max_chars 应为 20，实际 {max_chars}")
                print(f"  ✗ length_limit max_chars 应为 20，实际 {max_chars}")

    print("\n" + "=" * 60)
    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"  ✗ {issue}")
        return False
    else:
        print("✅ 准确性检查通过")
        return True

if __name__ == '__main__':
    success = check_accuracy()
    sys.exit(0 if success else 1)
