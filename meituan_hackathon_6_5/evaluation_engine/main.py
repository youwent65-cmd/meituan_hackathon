from __future__ import annotations

"""评测引擎主入口

提供三种使用方式：
1. Python API：代码中直接调用
2. CLI：命令行运行
3. 集成模式：读取对话记录 JSON → 评测 → 生成报告
"""

import json
import sys
from pathlib import Path
from datetime import datetime

from .models import EvaluationResult, EvalConfig, safe_attr
from .scorer import Scorer
from .report_generator import ReportGenerator


def _dict_to_obj(d):
    """将 dict 递归转为嵌套对象，兼容 ParsedInstruction 接口"""
    class Obj:
        pass

    def _convert(val):
        if isinstance(val, dict):
            o = Obj()
            for k, v in val.items():
                setattr(o, k, _convert(v))
            return o
        elif isinstance(val, list):
            return [_convert(item) for item in val]
        return val

    return _convert(d)


class EvaluationEngine:
    """评测引擎主类 — 封装完整的评测管线

    Usage:
        engine = EvaluationEngine(instruction_dict, config)
        result = engine.evaluate(dialogue_records)
        report_path = engine.generate_report(result)
    """

    def __init__(self, instruction, config: EvalConfig = None):
        # 兼容 dict 和 object 输入
        if isinstance(instruction, dict):
            instruction = _dict_to_obj(instruction)
        self.instruction = instruction
        self.config = config or EvalConfig()
        self.scorer = Scorer(self.config, instruction)
        self.reporter = ReportGenerator()

    def evaluate(self, dialogue_records: list) -> EvaluationResult:
        """对所有对话记录执行五维度评测

        Args:
            dialogue_records: 用户模拟器输出的对话记录列表

        Returns:
            完整的评测结果
        """
        result = self.scorer.evaluate(dialogue_records)
        result.test_time = datetime.now().isoformat()
        return result

    def evaluate_from_json(self, records_json_path: str) -> EvaluationResult:
        """从对话记录 JSON 文件加载并评测"""
        raw = Path(records_json_path).read_text(encoding="utf-8")
        records = json.loads(raw)
        return self.evaluate(records)

    def generate_report(self, result: EvaluationResult) -> str:
        """生成评测报告（Markdown + JSON）"""
        return self.reporter.generate(result)

    def run_full_pipeline(
        self, records_json_path: str, output_report: bool = True
    ) -> EvaluationResult:
        """一键评测：加载对话记录 → 评测 → 生成报告"""
        result = self.evaluate_from_json(records_json_path)
        if output_report:
            self.generate_report(result)
        return result

    @staticmethod
    def print_result(result: EvaluationResult):
        """打印评测结果摘要"""
        print(f"\n{'=' * 60}")
        print(f"  评测引擎 - 指令遵循能力评测结果")
        print(f"{'=' * 60}")

        print(f"\n  指令 ID: {result.instruction_id}")
        print(f"  角色: {result.instruction_role[:50]}…" if len(result.instruction_role) > 50 else f"  角色: {result.instruction_role}")
        print(f"  测试用例数: {result.total_cases}")
        print(f"  综合得分: {result.overall_score:.1f} / 100  [{result.grade}级]")

        print(f"\n  {'维度':　<6s} {'权重':>6s} {'得分':>8s} {'状态'}")
        print(f"  {'-' * 32}")
        for dim in ("流程完整度", "约束遵循度", "FAQ准确性", "对话自然度", "任务完成度"):
            if dim == "流程完整度":
                d = result.flow_score
            elif dim == "约束遵循度":
                d = result.constraint_score
            elif dim == "FAQ准确性":
                d = result.faq_score
            elif dim == "对话自然度":
                d = result.naturalness_score
            else:
                d = result.task_score
            status = "[OK]" if d.score >= 80 else ("[!!]" if d.score >= 60 else "[XX]")
            print(f"  {dim:　<6s} {d.weight:>6.0%} {d.score:>8.1f} {status}")

        print(f"\n  改进建议:")
        for item in result.improvement_items[:5]:
            print(f"    - {item}")

        print(f"\n{'=' * 60}")


# ============================================================
# CLI 入口
# ============================================================

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="外呼任务对话模型 -- 指令遵循能力评测引擎"
    )
    parser.add_argument(
        "records_json",
        help="用户模拟器输出的对话记录 JSON 文件路径",
    )
    parser.add_argument(
        "--instruction",
        "-i",
        help="指令解析器输出的 parsed_output.json 路径（需要与 records 对应）",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        default="reports",
        help="报告输出目录 (默认: reports/)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        help="启用 LLM-as-Judge 增强评测",
    )
    parser.add_argument(
        "--llm-key",
        default="",
        help="LLM API Key（启用 --llm 时必需）",
    )
    args = parser.parse_args()

    # 加载对话记录
    records_path = Path(args.records_json)
    records_data = json.loads(records_path.read_text(encoding="utf-8"))

    # 自动寻找对应的指令 JSON
    if args.instruction:
        inst_path = Path(args.instruction)
    else:
        # 尝试从 records 同目录找 parsed_output.json
        inst_candidates = [
            records_path.parent / "parsed_output.json",
            Path(__file__).parent.parent / "instruction-parser" / "data" / "parsed_output.json",
        ]
        inst_path = None
        for c in inst_candidates:
            if c.exists():
                inst_path = c
                break

    if inst_path and inst_path.exists():
        inst_data = json.loads(inst_path.read_text(encoding="utf-8"))
        instructions = inst_data if isinstance(inst_data, list) else [inst_data]
    else:
        print("[WARN] 未找到指令 JSON，使用最小化指令进行评测。")
        instructions = [{"role": "", "task": "", "flow_steps": [], "faq": [], "constraints": []}]

    config = EvalConfig(llm_enabled=args.llm, llm_api_key=args.llm_key)

    # 对每条指令分别评测
    for i, inst in enumerate(instructions):
        # 筛选属于该指令的对话记录
        inst_id = f"INST_{i + 1:03d}"

        engine = EvaluationEngine(inst, config)
        result = engine.evaluate(records_data)

        report_path = engine.generate_report(result)
        EvaluationEngine.print_result(result)
        print(f"\n[OK] 评测报告已保存到: {report_path}")


if __name__ == "__main__":
    main()
