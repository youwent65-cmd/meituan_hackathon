from __future__ import annotations

"""加权评分器 - 汇总五个维度得分，生成综合评分"""

from .models import (
    EvaluationResult, DimensionScore, EvalConfig, safe_attr,
)
from .flow_evaluator import FlowEvaluator
from .constraint_evaluator import ConstraintEvaluator
from .faq_evaluator import FAQEvaluator
from .naturalness_evaluator import NaturalnessEvaluator
from .task_evaluator import TaskEvaluator


class Scorer:
    """五个维度的加权评分器"""

    DIMENSION_WEIGHTS = {
        "flow": 0.30,
        "constraint": 0.30,
        "faq": 0.20,
        "naturalness": 0.10,
        "task": 0.10,
    }

    def __init__(self, config: EvalConfig, instruction):
        self.config = config
        self.instruction = instruction

        # 初始化五个维度评估器
        self.flow_eval = FlowEvaluator(config, instruction)
        self.constraint_eval = ConstraintEvaluator(config, instruction)
        self.faq_eval = FAQEvaluator(config, instruction)
        self.naturalness_eval = NaturalnessEvaluator(config, instruction)
        self.task_eval = TaskEvaluator(config, instruction)

    def evaluate(self, dialogue_records: list) -> EvaluationResult:
        """运行全部五个维度的评估，返回综合结果"""
        result = EvaluationResult(
            instruction_id=self._extract_instruction_id(),
            instruction_role=self.instruction.role if hasattr(self.instruction, "role") else "",
            instruction_task=self.instruction.task if hasattr(self.instruction, "task") else "",
            total_cases=len(dialogue_records),
        )

        # 维度一：流程完整度 (30%)
        result.flow_score = self.flow_eval.evaluate(dialogue_records)

        # 维度二：约束遵循度 (30%)
        result.constraint_score = self.constraint_eval.evaluate(dialogue_records)

        # 维度三：FAQ 准确性 (20%)
        result.faq_score = self.faq_eval.evaluate(dialogue_records)

        # 维度四：对话自然度 (10%)
        result.naturalness_score = self.naturalness_eval.evaluate(dialogue_records)

        # 维度五：任务完成度 (10%)
        result.task_score = self.task_eval.evaluate(dialogue_records)

        # 计算加权总分
        result.compute_overall()

        # 记录 LLM 状态
        result.llm_status = {
            "judge_enabled": self.config.llm_enabled,
            "judge_used": "llm_judge_score" in result.naturalness_score.raw_metrics,
            "judge_error": None,
        }
        if self.config.llm_enabled and not result.llm_status["judge_used"]:
            if not self.config.llm_api_key:
                result.llm_status["judge_error"] = "未配置 API Key，LLM-as-Judge 未执行"
            else:
                result.llm_status["judge_error"] = "API 调用失败，已降级为规则评分"

        # 识别最佳/最差案例
        result.best_case, result.worst_case = self._extract_cases(dialogue_records)

        # 生成改进建议
        result.improvement_items = self._generate_improvements(result)

        return result

    def _extract_instruction_id(self) -> str:
        role = getattr(self.instruction, "role", "") or ""
        if "骑" in role:
            return "RIDER_001"
        elif "直播" in role or "Course" in role:
            return "COURSE_001"
        return "INST_001"

    @staticmethod
    def _extract_cases(dialogue_records: list) -> tuple[dict, dict]:
        """找出最佳和最差的对话案例"""
        if not dialogue_records:
            return {}, {}

        scored = []
        for r in dialogue_records:
            end_reason = safe_attr(r, "end_reason", "")
            total_turns = safe_attr(r, "total_turns", 0)
            test_dim = safe_attr(r, "test_dimension", "")

            scan_score = 100
            if end_reason == "no_progress":
                scan_score = 40
            elif end_reason == "max_turns":
                scan_score = 50
            elif end_reason == "sut_normal_end":
                scan_score = 90
            elif end_reason == "flow_complete":
                scan_score = 95

            # 根据测试维度调整
            if test_dim in ("user_reject", "driving_hangup", "info_missing"):
                scan_score = min(scan_score, 70)  # 这些场景本身就有挑战

            scored.append((scan_score, r))

        scored.sort(key=lambda x: x[0])
        worst = scored[0][1]
        best = scored[-1][1]

        def _summarize(r) -> dict:
            turns = r.turns if hasattr(r, "turns") else r.get("turns", [])
            conversation = []
            for t in turns[:6]:
                role = safe_attr(t, "role", "SUT")
                content = safe_attr(t, "content", "")
                conversation.append(f"[{role}] {content[:100]}")
            return {
                "test_case_id": safe_attr(r, "test_case_id", ""),
                "test_dimension": safe_attr(r, "test_dimension", ""),
                "total_turns": safe_attr(r, "total_turns", 0),
                "end_reason": safe_attr(r, "end_reason", ""),
                "conversation_snippet": "\n".join(conversation),
            }

        return _summarize(best), _summarize(worst)

    @staticmethod
    def _generate_improvements(result: EvaluationResult) -> list[str]:
        """根据评估结果生成改进建议"""
        items = []

        dims = [
            (result.flow_score, "流程完整度"),
            (result.constraint_score, "约束遵循度"),
            (result.faq_score, "FAQ准确性"),
            (result.naturalness_score, "对话自然度"),
            (result.task_score, "任务完成度"),
        ]

        # 按得分排序，优先改进低分维度（N/A维度排到最后）
        dims.sort(key=lambda x: x[0].score if x[0].weight > 0 else 999)

        for dim_score, label in dims:
            if dim_score.weight == 0:
                items.append(f"[提示] {label}未评估(N/A)，建议补充相关测试用例以覆盖该维度。")
                continue
            if dim_score.score < 60:
                items.append(f"[高优先级] {label}得分较低({dim_score.score:.0f}/100)，建议优先优化。")
                type_counts = {}
                for v in dim_score.violations:
                    type_counts[v.violation_type] = type_counts.get(v.violation_type, 0) + 1
                for vtype, count in sorted(type_counts.items(), key=lambda x: -x[1])[:2]:
                    items.append(f"  - {vtype}: 共 {count} 次违规，需逐一修复。")
            elif dim_score.score < 75:
                items.append(f"[中优先级] {label}得分{dim_score.score:.0f}/100，存在提升空间。")
            elif dim_score.score >= 90:
                items.append(f"[保持] {label}表现良好({dim_score.score:.0f}/100)。")

        return items
