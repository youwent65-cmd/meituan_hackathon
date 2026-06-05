#!/usr/bin/env python3
"""外呼任务对话模型指令遵循能力自动评估系统 — 统一入口

将三个模块串联为完整的端到端评估管线：
  指令解析器 (Instruction Parser)
    -> 用户模拟器 (User Simulator)
      -> 评测引擎 (Evaluation Engine)
        -> 评测报告 (Markdown + JSON)

用法:
  # 一键评估 Excel 中的指令
  python main.py --input "命题二：外呼任务对话模型指令示例 (1).xlsx"

  # 从已解析的 JSON 运行
  python main.py --parsed instruction-parser/data/parsed_output.json

  # 使用真实 SUT 回调
  python main.py --input data.xlsx --sut my_sut_module.py
"""

from __future__ import annotations
import sys
import os
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

# 确保项目根目录在 path 中
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import PipelineConfig


class InstructionFollowEvaluator:
    """指令遵循能力自动评估系统 — 全管线编排器"""

    def __init__(self, config: PipelineConfig = None, sut_callback: Callable = None):
        self.config = config or PipelineConfig()
        self.sut_callback = sut_callback
        self.pipeline_log = []

    def run(self, input_path: str) -> dict:
        """运行完整的端到端评估管线

        Args:
            input_path: Excel (.xlsx) 或已解析的 JSON (.json) 文件路径

        Returns:
            包含所有结果的汇总 dict
        """
        started_at = time.time()
        input_file = Path(input_path)

        print(f"\n{'=' * 60}")
        print(f"  外呼任务对话模型 — 指令遵循能力自动评估系统")
        print(f"  启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'=' * 60}")

        # ================================================
        # 阶段一：指令解析
        # ================================================
        print(f"\n[阶段 1/3] 指令解析器")
        print(f"{'-' * 40}")

        if input_file.suffix == ".json":
            instructions = self._load_parsed_instructions(str(input_file))
        elif input_file.suffix in (".xlsx", ".xls"):
            instructions = self._run_parser(str(input_file))
        elif input_file.suffix == ".md":
            instructions = [self._parse_single_md(str(input_file))]
        else:
            raise ValueError(f"不支持的输入格式: {input_file.suffix}")

        print(f"  [OK] 解析完成: {len(instructions)} 条指令")

        for i, inst in enumerate(instructions):
            role = inst.get("role", "") if isinstance(inst, dict) else getattr(inst, "role", "")
            task = inst.get("task", "") if isinstance(inst, dict) else getattr(inst, "task", "")
            flow_n = len(inst.get("flow_steps", []) if isinstance(inst, dict) else getattr(inst, "flow_steps", []))
            faq_n = len(inst.get("faq", []) if isinstance(inst, dict) else getattr(inst, "faq", []))
            const_n = len(inst.get("constraints", []) if isinstance(inst, dict) else getattr(inst, "constraints", []))
            print(f"    指令{i+1}: Role={role[:30]}… | Flow={flow_n}步 | FAQ={faq_n}条 | 约束={const_n}条")

        # ================================================
        # 阶段二：用户模拟
        # ================================================
        print(f"\n[阶段 2/3] 用户模拟器")
        print(f"{'-' * 40}")

        all_records = []
        for i, inst in enumerate(instructions):
            inst_id = f"INST_{i + 1:03d}"
            profile_count = self.config.num_profiles

            records = self._run_simulator(inst, inst_id)
            all_records.extend(records)

            dims = set()
            for r in records:
                d = r.test_dimension if hasattr(r, "test_dimension") else r.get("test_dimension", "")
                dims.add(d)

            print(f"  指令 {inst_id}: {len(records)} 条对话 | {profile_count} 种画像 | {len(dims)} 个测试维度")

        print(f"  [OK] 模拟完成: 共生成 {len(all_records)} 条对话记录")

        # 保存对话记录
        output_dir = Path(self.config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        records_path = output_dir / f"all_dialogue_records_{ts}.json"
        records_json = []
        for r in all_records:
            if hasattr(r, "to_dict"):
                records_json.append(r.to_dict())
            else:
                records_json.append(r)
        records_path.write_text(
            json.dumps(records_json, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"    对话记录: {records_path}")

        # ================================================
        # 阶段三：评测引擎
        # ================================================
        print(f"\n[阶段 3/3] 评测引擎")
        print(f"{'-' * 40}")

        all_results = []
        for i, inst in enumerate(instructions):
            inst_id = f"INST_{i + 1:03d}"
            inst_records = [
                r for r in all_records
                if (getattr(r, "instruction_id", "") if hasattr(r, "instruction_id") else r.get("instruction_id", "")) == inst_id
            ]
            if not inst_records:
                inst_records = all_records  # fallback

            result = self._run_evaluator(inst, inst_records)
            all_results.append(result)

            print(f"  指令 {inst_id}: {result.overall_score:.1f}/100 [{result.grade}级] | "
                  f"流程{result.flow_score.score:.0f} "
                  f"约束{result.constraint_score.score:.0f} "
                  f"FAQ{result.faq_score.score:.0f} "
                  f"自然度{result.naturalness_score.score:.0f} "
                  f"任务{result.task_score.score:.0f}")

        # ================================================
        # 汇总
        # ================================================
        elapsed = time.time() - started_at

        # 生成汇总报告
        summary = self._generate_summary(all_results, all_records, elapsed)
        summary_path = output_dir / f"evaluation_summary_{ts}.md"
        summary_path.write_text(summary, encoding="utf-8")

        print(f"\n{'=' * 60}")
        print(f"  评估完成! 耗时 {elapsed:.1f}s")
        print(f"  指令数: {len(instructions)}")
        print(f"  对话数: {len(all_records)}")
        if all_results:
            avg_score = sum(r.overall_score for r in all_results) / len(all_results)
            print(f"  平均得分: {avg_score:.1f} / 100")
        print(f"  汇总报告: {summary_path}")
        print(f"  详细报告: {self.config.report_dir}/")
        print(f"{'=' * 60}")

        return {
            "instructions": len(instructions),
            "total_records": len(all_records),
            "results": all_results,
            "elapsed": elapsed,
        }

    # ============================================================
    # 私有方法 — 各阶段实现
    # ============================================================

    @staticmethod
    def _read_json(path: str) -> list:
        """读取 JSON 文件，兼容 UTF-8 和 GBK 编码"""
        p = Path(path)
        try:
            raw = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = p.read_text(encoding="gbk")
        return json.loads(raw)

    def _load_parsed_instructions(self, json_path: str) -> list[dict]:
        """从 JSON 文件加载已解析的指令"""
        data = self._read_json(json_path)
        return data if isinstance(data, list) else [data]

    def _run_parser(self, excel_path: str) -> list[dict]:
        """运行指令解析器"""
        import importlib
        parser_path = str(PROJECT_ROOT / "instruction-parser")
        if parser_path not in sys.path:
            sys.path.insert(0, parser_path)
        ip_main = importlib.import_module("src.main")
        parse_from_excel = ip_main.parse_from_excel

        parsed = parse_from_excel(excel_path, use_llm_fallback=self.config.use_llm_fallback,
                                  llm_api_key=self.config.llm_api_key,
                                  llm_provider=self.config.llm_provider,
                                  llm_base_url=self.config.llm_base_url)
        return [p.to_dict() if hasattr(p, "to_dict") else p for p in parsed]

    def _parse_single_md(self, md_path: str) -> dict:
        """解析单个 Markdown 指令文件"""
        import importlib
        parser_path = str(PROJECT_ROOT / "instruction-parser")
        if parser_path not in sys.path:
            sys.path.insert(0, parser_path)
        ip_main = importlib.import_module("src.main")
        parse_instruction = ip_main.parse_instruction

        text = Path(md_path).read_text(encoding="utf-8")
        result = parse_instruction(text, use_llm_fallback=self.config.use_llm_fallback,
                                   llm_api_key=self.config.llm_api_key,
                                   llm_provider=self.config.llm_provider,
                                   llm_base_url=self.config.llm_base_url)
        return result.to_dict() if hasattr(result, "to_dict") else result

    def _run_simulator(self, instruction: dict, inst_id: str):
        """运行用户模拟器"""
        from user_simulator.main import UserSimulator
        from user_simulator.models import SimulationConfig

        sim_config = SimulationConfig(
            max_turns=self.config.max_turns,
            sut_provider=self.config.sut_provider if not self.sut_callback else "api",
            llm_provider=self.config.llm_provider,
            llm_model=self.config.llm_model,
            llm_api_key=self.config.llm_api_key,
            llm_base_url=self.config.llm_base_url,
            temperature=self.config.llm_temperature,
        )

        simulator = UserSimulator(sim_config, sut_callback=self.sut_callback)

        # 生成画像 -> 测试用例 -> 执行对话
        if isinstance(instruction, dict):
            inst_obj = simulator._dict_to_obj(instruction)
        else:
            inst_obj = instruction

        profiles = simulator.profile_manager.generate_profiles(inst_obj, self.config.num_profiles)
        test_cases = simulator.test_gen.generate(inst_obj, profiles)

        from user_simulator.dialogue_driver import DialogueDriver
        driver = DialogueDriver(sim_config, inst_obj, self.sut_callback)

        records = []
        for tc in test_cases:
            profile = tc.profile or profiles[0]
            record = driver.run_dialogue(inst_id, profile, tc)
            simulator.recorder.record(record)
            records.append(record)

        return records

    def _run_evaluator(self, instruction: dict, records: list):
        """运行评测引擎"""
        from evaluation_engine.main import EvaluationEngine
        from evaluation_engine.models import EvalConfig

        eval_config = EvalConfig(
            length_tolerance=self.config.length_tolerance,
            similarity_threshold=self.config.faq_similarity_threshold,
            hard_constraint_deduction=self.config.hard_constraint_deduction,
            soft_constraint_deduction=self.config.soft_constraint_deduction,
            step_miss_deduction=self.config.step_miss_deduction,
            hallucination_deduction=self.config.hallucination_deduction,
            llm_enabled=self.config.llm_judge_enabled,
            llm_provider=self.config.llm_provider,
            llm_api_key=self.config.llm_api_key,
            llm_model=self.config.llm_model,
            llm_base_url=self.config.llm_base_url,
        )

        engine = EvaluationEngine(instruction, eval_config)
        result = engine.evaluate(records)
        result.simulation_mode = "llm" if self.config.llm_provider != "mock" else "mock"
        engine.reporter.output_dir = self.config.report_dir
        engine.generate_report(result)
        return result

    @staticmethod
    def _generate_summary(results: list, all_records: list, elapsed: float) -> str:
        """生成汇总 Markdown 报告"""
        lines = []
        lines.append("# 外呼任务对话模型 — 指令遵循能力评估汇总报告")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**评估耗时**: {elapsed:.1f} 秒")
        lines.append(f"**测试指令数**: {len(results)}")
        lines.append(f"**总对话数**: {len(all_records)}")
        lines.append("")

        lines.append("## 各指令评估结果")
        lines.append("")
        lines.append("| 指令 ID | 角色 | 综合得分 | 等级 | 流程 | 约束 | FAQ | 自然度 | 任务 |")
        lines.append("|---------|------|----------|------|------|------|-----|--------|------|")

        for r in results:
            role_short = r.instruction_role[:20] if r.instruction_role else "N/A"
            lines.append(
                f"| {r.instruction_id} | {role_short} | "
                f"{r.overall_score:.1f} | {r.grade} | "
                f"{r.flow_score.score:.0f} | {r.constraint_score.score:.0f} | "
                f"{r.faq_score.score:.0f} | {r.naturalness_score.score:.0f} | "
                f"{r.task_score.score:.0f} |"
            )

        lines.append("")
        lines.append("## 统计概览")
        lines.append("")

        # 维度统计
        dim_names = ["流程完整度", "约束遵循度", "FAQ准确性", "对话自然度", "任务完成度"]
        dim_accessors = ["flow_score", "constraint_score", "faq_score", "naturalness_score", "task_score"]

        for name, acc in zip(dim_names, dim_accessors):
            scores = [getattr(r, acc).score for r in results]
            avg = sum(scores) / len(scores) if scores else 0
            lines.append(f"- **{name}**: 平均 {avg:.1f}/100")

        # 总体
        overalls = [r.overall_score for r in results]
        avg_overall = sum(overalls) / len(overalls) if overalls else 0
        lines.append(f"- **综合得分**: 平均 {avg_overall:.1f}/100")
        lines.append("")

        # 改进建议汇总
        lines.append("## 改进建议汇总")
        lines.append("")
        all_items = []
        for r in results:
            all_items.extend(r.improvement_items[:3])
        for item in all_items[:10]:
            lines.append(f"- {item}")
        lines.append("")

        lines.append("---")
        lines.append(f"*报告由指令遵循能力自动评估系统生成 | v1.0*")

        return "\n".join(lines)


# ============================================================
# CLI 入口
# ============================================================

def main():
    """命令行主入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="外呼任务对话模型 — 指令遵循能力自动评估系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python main.py --input "命题二：外呼任务对话模型指令示例 (1).xlsx"
  python main.py --parsed instruction-parser/data/parsed_output.json
  python main.py --input data.xlsx --profiles 8 --max-turns 20
        """,
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", "-i", help="Excel (.xlsx) 或 Markdown (.md) 指令文件")
    group.add_argument("--parsed", "-p", help="已解析的 JSON 指令文件")

    parser.add_argument("--profiles", type=int, default=6, help="用户画像数量 (默认: 6)")
    parser.add_argument("--max-turns", type=int, default=15, help="最大对话轮次 (默认: 15)")
    parser.add_argument("--llm", action="store_true", help="启用 LLM（L3 Agent + LLM-as-Judge）")
    parser.add_argument("--llm-provider", default="anthropic",
                        choices=["anthropic", "deepseek", "openai"],
                        help="LLM 提供商 (默认: anthropic)")
    parser.add_argument("--llm-key", default="", help="LLM API Key")
    parser.add_argument("--llm-model", default="", help="LLM 模型名（默认按 provider 自动选择）")
    parser.add_argument("--llm-base-url", default="",
                        help="自定义 API 端点（DeepSeek/OpenAI 兼容）")
    parser.add_argument("--output-dir", default="output", help="输出目录 (默认: output/)")
    parser.add_argument("--report-dir", default="reports", help="报告目录 (默认: reports/)")

    args = parser.parse_args()

    # 构建配置
    # 自动选择默认模型
    llm_model = args.llm_model
    if not llm_model:
        if args.llm_provider == "deepseek":
            llm_model = "deepseek-chat"
        elif args.llm_provider == "openai":
            llm_model = "gpt-4o"
        else:
            llm_model = "claude-sonnet-4-6"

    config = PipelineConfig(
        num_profiles=args.profiles,
        max_turns=args.max_turns,
        output_dir=args.output_dir,
        report_dir=args.report_dir,
        use_llm_fallback=args.llm,
        llm_provider=args.llm_provider if args.llm else "mock",
        llm_model=llm_model,
        llm_judge_enabled=args.llm,
        llm_api_key=args.llm_key,
        llm_base_url=args.llm_base_url,
    )

    input_path = args.input or args.parsed

    # 运行管线
    evaluator = InstructionFollowEvaluator(config)
    result = evaluator.run(input_path)

    return result


if __name__ == "__main__":
    main()
