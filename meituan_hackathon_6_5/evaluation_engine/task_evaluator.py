from __future__ import annotations

"""任务完成度评估器 — 维度五 (权重 10%)

指标：对话结束时是否完成了 Task 定义的总目标
"""

from .models import DimensionScore, Violation, EvalConfig, safe_attr


class TaskEvaluator:
    """评估 SUT 是否完成了指令定义的任务目标"""

    def __init__(self, config: EvalConfig, instruction):
        self.config = config
        self.instruction = instruction

    def evaluate(self, dialogue_records: list) -> DimensionScore:
        score = DimensionScore(
            dimension="task",
            label_cn="任务完成度",
            weight=0.10,
            score=100.0,
        )
        violations = []

        task_text = self.instruction.task if hasattr(self.instruction, "task") else ""

        # 获取流程步骤总数（用于计算部分完成度）
        flow_steps = self.instruction.flow_steps if hasattr(self.instruction, "flow_steps") else []
        total_flow_steps = len(flow_steps) if flow_steps else 0

        completed_count = 0
        partial_count = 0
        total_valid = 0
        completion_scores = []

        for record in dialogue_records:
            end_reason = safe_attr(record, "end_reason", "")
            test_dim = safe_attr(record, "test_dimension", "")
            metadata = safe_attr(record, "metadata", {}) or {}

            # 只评估正常流程和自由对话的完成情况
            if test_dim in ("user_reject", "driving_hangup"):
                continue

            total_valid += 1

            # 判断任务完成度（多级评分）
            flow_complete = metadata.get("flow_complete", False)
            completed_steps = metadata.get("completed_steps", [])
            is_normal_end = end_reason in ("sut_normal_end", "flow_complete", "sut_transfer")

            if flow_complete or is_normal_end:
                completed_count += 1
                completion_scores.append(100)
            elif end_reason == "max_turns":
                # 达到最大轮次但可能部分完成：根据步骤覆盖率给分
                if total_flow_steps > 0 and completed_steps:
                    coverage = len(completed_steps) / total_flow_steps
                    partial_score = coverage * 100
                    completion_scores.append(partial_score)
                    partial_count += 1
                    if coverage < 0.5:
                        violations.append(Violation(
                            dimension="task",
                            violation_type="task_partial",
                            severity="medium",
                            deduction=10.0,
                            test_case_id=safe_attr(record, "test_case_id", ""),
                            expected=f"任务目标: {task_text[:80]}",
                            actual=f"对话达最大轮次，完成{len(completed_steps)}/{total_flow_steps}步骤 (覆盖率{coverage:.0%})",
                            explanation=f"对话达到最大轮次限制，流程部分完成({len(completed_steps)}/{total_flow_steps}步)。",
                        ))
                else:
                    completion_scores.append(0)
                    violations.append(Violation(
                        dimension="task",
                        violation_type="task_incomplete",
                        severity="high",
                        deduction=10.0,
                        test_case_id=safe_attr(record, "test_case_id", ""),
                        expected=f"任务目标: {task_text[:80]}",
                        actual=f"对话达最大轮次({end_reason})，未检测到步骤完成",
                        explanation="对话达到最大轮次限制且未能完成流程步骤。",
                    ))
            elif end_reason == "no_progress":
                # 无进展终止：根据已完成步骤给部分分
                if total_flow_steps > 0 and completed_steps:
                    coverage = len(completed_steps) / total_flow_steps
                    partial_score = coverage * 100 * 0.7  # 无进展终止打折
                    completion_scores.append(partial_score)
                    partial_count += 1
                else:
                    completion_scores.append(0)
                violations.append(Violation(
                    dimension="task",
                    violation_type="task_incomplete",
                    severity="high",
                    deduction=10.0,
                    test_case_id=safe_attr(record, "test_case_id", ""),
                    expected=f"任务目标: {task_text[:80]}…",
                    actual=f"对话因无进展而终止 (reason={end_reason})",
                    explanation="对话未能在正常结束前完成任务目标。",
                ))
            else:
                # 未知结束原因：根据已完成的步骤数估算
                if total_flow_steps > 0 and completed_steps:
                    coverage = len(completed_steps) / total_flow_steps
                    partial_score = coverage * 100 * 0.8
                    completion_scores.append(partial_score)
                    partial_count += 1
                else:
                    completion_scores.append(0)

        if total_valid > 0:
            score.score = sum(completion_scores) / len(completion_scores)
        else:
            score.score = 100.0

        score.score = max(0, min(100, score.score))
        score.raw_metrics = {
            "completed_count": completed_count,
            "partial_count": partial_count,
            "total_valid_cases": total_valid,
            "completion_rate": round(completed_count / max(total_valid, 1), 3),
            "avg_completion_score": round(score.score, 1),
            "total_flow_steps": total_flow_steps,
        }
        score.violations = violations
        score.details = (
            f"在 {total_valid} 条有效用例中，{completed_count} 条完全完成"
            f"{f'，{partial_count} 条部分完成' if partial_count > 0 else ''}，"
            f"平均完成度 {score.score:.1f}%。"
        )
        return score
