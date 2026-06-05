#!/usr/bin/env python
"""功能完整性检查脚本"""

import json
import sys
from pathlib import Path

def check_completeness():
    """检查解析结果的完整性"""
    data_path = Path(__file__).parent.parent / 'data' / 'parsed_output.json'
    with open(data_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    print("=" * 60)
    print("功能完整性检查")
    print("=" * 60)

    issues = []

    for i, inst in enumerate(data, 1):
        print(f"\n【指令 {i}】")

        # 1. 必需字段检查
        required = ['role', 'task', 'opening', 'variables', 'flow_steps', 'faq', 'constraints']
        for field in required:
            if field not in inst:
                issues.append(f"指令{i}: 缺少字段 {field}")
                print(f"  ✗ 缺少字段: {field}")
            else:
                print(f"  ✓ {field}: 存在")

        # 2. Role/Task/Opening 非空检查
        if not inst.get('role'):
            issues.append(f"指令{i}: role 为空")
            print(f"  ✗ role 为空")
        else:
            print(f"  ✓ role: \"{inst['role'][:30]}...\"")

        if not inst.get('task'):
            issues.append(f"指令{i}: task 为空")
            print(f"  ✗ task 为空")
        else:
            print(f"  ✓ task: \"{inst['task'][:30]}...\"")

        # 3. Flow 步骤检查
        if not inst.get('flow_steps'):
            issues.append(f"指令{i}: flow_steps 为空")
            print(f"  ✗ flow_steps 为空")
        else:
            print(f"  ✓ flow_steps: {len(inst['flow_steps'])} 步")
            # 检查步骤结构
            for step in inst['flow_steps']:
                if 'id' not in step or 'description' not in step:
                    issues.append(f"指令{i}: flow_step 缺少 id 或 description")

        # 4. 约束检查
        if inst.get('constraints'):
            print(f"  ✓ constraints: {len(inst['constraints'])} 条")
            hard = sum(1 for c in inst['constraints'] if c.get('is_hard'))
            soft = len(inst['constraints']) - hard
            print(f"    - 硬约束: {hard}, 软约束: {soft}")
        else:
            print(f"  ⚠ constraints: 0 条（可能正常）")

    print("\n" + "=" * 60)
    if issues:
        print(f"发现 {len(issues)} 个问题:")
        for issue in issues:
            print(f"  ✗ {issue}")
        return False
    else:
        print("✅ 功能完整性检查通过")
        return True

if __name__ == '__main__':
    success = check_completeness()
    sys.exit(0 if success else 1)
