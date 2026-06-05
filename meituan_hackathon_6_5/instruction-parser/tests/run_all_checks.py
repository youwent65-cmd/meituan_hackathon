#!/usr/bin/env python
"""总检查脚本 - 运行所有测试"""

import subprocess
import sys
from pathlib import Path

def run_check(script_name, description):
    """运行单个检查脚本"""
    print(f"\n{'=' * 70}")
    print(f"运行: {description}")
    print('=' * 70)

    script_path = Path(__file__).parent / script_name
    result = subprocess.run(
        [sys.executable, str(script_path)],
        capture_output=False,
        text=True
    )

    return result.returncode == 0

def main():
    """运行所有检查"""
    print("=" * 70)
    print("阶段一指令解析器 - 完整检查")
    print("=" * 70)

    checks = [
        ('test_completeness.py', '功能完整性检查'),
        ('test_accuracy.py', '准确性检查'),
        ('test_robustness.py', '鲁棒性检查'),
    ]

    results = []
    for script, desc in checks:
        success = run_check(script, desc)
        results.append((desc, success))

    # 汇总结果
    print("\n" + "=" * 70)
    print("检查结果汇总")
    print("=" * 70)

    for desc, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status} - {desc}")

    all_passed = all(success for _, success in results)

    print("\n" + "=" * 70)
    if all_passed:
        print("🎉 所有检查通过！阶段一指令解析器质量合格。")
    else:
        print("⚠️  部分检查未通过，请查看上方详细信息。")
    print("=" * 70)

    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
