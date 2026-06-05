from __future__ import annotations

"""约束遵循度评估器 — 维度二 (权重 30%)

检测所有硬约束/软约束在实际对话中的遵循情况。
"""

import re
from collections import Counter

from .models import DimensionScore, Violation, EvalConfig, safe_attr


class ConstraintEvaluator:
    """评估 SUT 是否遵循了所有约束条件"""

    def __init__(self, config: EvalConfig, instruction):
        self.config = config
        self.instruction = instruction

    def evaluate(self, dialogue_records: list) -> DimensionScore:
        score = DimensionScore(
            dimension="constraint",
            label_cn="约束遵循度",
            weight=0.30,
            score=100.0,
        )
        violations = []
        constraints = self.instruction.constraints if hasattr(self.instruction, "constraints") else []

        if not constraints:
            score.details = "无约束条件，跳过评估。"
            return score

        constraint_stats = {}  # constraint_raw → violation_count

        for record in dialogue_records:
            turns = record.turns if hasattr(record, "turns") else record.get("turns", [])
            sut_turns = [(i, t) for i, t in enumerate(turns) if safe_attr(t, "role", "") == "SUT"]

            for c in constraints:
                ct = safe_attr(c, "constraint_type", "generic")
                raw = safe_attr(c, "raw", "")
                params = safe_attr(c, "params", {})
                is_hard = safe_attr(c, "is_hard", True)

                # 根据约束类型选择检测方法
                if ct == "length_limit":
                    vs = self._check_length(sut_turns, c, record)
                elif ct == "forbidden_words":
                    vs = self._check_forbidden_words(sut_turns, c, record)
                elif ct == "forbidden_topic":
                    vs = self._check_forbidden_topic(sut_turns, c, record)
                elif ct == "termination_condition":
                    vs = self._check_termination(sut_turns, c, record, dialogue_records)
                elif ct == "no_repeat":
                    vs = self._check_repeat(sut_turns, c, record)
                elif ct in ("style", "generic"):
                    # 软约束：抽样检测
                    vs = self._check_style(sut_turns, c, record)
                else:
                    vs = []

                violations.extend(vs)
                if vs:
                    constraint_stats[raw] = constraint_stats.get(raw, 0) + len(vs)

        # 计算得分
        total_deduction = sum(v.deduction for v in violations)
        max_possible = len(constraints) * self.config.hard_constraint_deduction * max(len(dialogue_records), 1)
        if max_possible > 0:
            score.score = max(0, 100 - (total_deduction / max_possible) * 100)
        else:
            score.score = 100

        score.raw_metrics = {
            "total_constraints": len(constraints),
            "hard_constraints": sum(1 for c in constraints if safe_attr(c, "is_hard", True)),
            "soft_constraints": sum(1 for c in constraints if not safe_attr(c, "is_hard", True)),
            "total_violations": len(violations),
            "violation_by_type": dict(Counter(v.violation_type for v in violations)),
            "constraint_stats": {
                raw[:50]: cnt for raw, cnt in constraint_stats.items()
            },
        }
        score.violations = violations
        n_constraints_with_issues = len(constraint_stats)
        score.details = (
            f"{len(constraints)} 条约束中 {n_constraints_with_issues} 条被违反，"
            f"共 {len(violations)} 处违规。"
        )
        return score

    # ---- 各约束类型检测 ----

    def _check_length(self, sut_turns: list, constraint, record) -> list[Violation]:
        violations = []
        max_chars = safe_attr(safe_attr(constraint, "params", {}), "max_chars", 30)
        tolerance = safe_attr(safe_attr(constraint, "params", {}), "tolerance", 5)
        limit = max_chars + tolerance
        raw = safe_attr(constraint, "raw", "")
        deduction = self.config.hard_constraint_deduction

        for idx, turn in sut_turns:
            content = safe_attr(turn, "content", "")
            if len(content) > limit:
                violations.append(Violation(
                    dimension="constraint",
                    violation_type="length_limit",
                    severity="medium",
                    deduction=deduction * 0.3,
                    test_case_id=safe_attr(record, "test_case_id", ""),
                    turn_number=idx,
                    sut_message=content[:80],
                    expected=f"≤{max_chars}字(容差{tolerance})",
                    actual=f"{len(content)}字",
                    constraint_raw=raw,
                    explanation=f"第{idx}轮回复{len(content)}字，超过限制{max_chars}+{tolerance}字。",
                ))
        return violations

    def _check_forbidden_words(self, sut_turns: list, constraint, record) -> list[Violation]:
        violations = []
        words = safe_attr(safe_attr(constraint, "params", {}), "words", [])
        raw = safe_attr(constraint, "raw", "")

        for idx, turn in sut_turns:
            content = safe_attr(turn, "content", "")
            found = [w for w in words if w in content]
            if found:
                violations.append(Violation(
                    dimension="constraint",
                    violation_type="forbidden_words",
                    severity="medium",
                    deduction=self.config.hard_constraint_deduction * 0.5,
                    test_case_id=safe_attr(record, "test_case_id", ""),
                    turn_number=idx,
                    sut_message=content[:80],
                    expected=f"不应使用: {', '.join(words)}",
                    actual=f"使用了: {', '.join(found)}",
                    constraint_raw=raw,
                    explanation=f"回复中包含了禁用的词汇: {', '.join(found)}",
                ))
        return violations

    def _check_forbidden_topic(self, sut_turns: list, constraint, record) -> list[Violation]:
        violations = []
        keywords = safe_attr(safe_attr(constraint, "params", {}), "topic_keywords", [])
        raw = safe_attr(constraint, "raw", "")

        for idx, turn in sut_turns:
            content = safe_attr(turn, "content", "")
            detected = [kw for kw in keywords if kw in content]
            if detected:
                violations.append(Violation(
                    dimension="constraint",
                    violation_type="forbidden_topic",
                    severity="high",
                    deduction=self.config.hard_constraint_deduction,
                    test_case_id=safe_attr(record, "test_case_id", ""),
                    turn_number=idx,
                    sut_message=content[:80],
                    expected="不应涉及禁止话题",
                    actual=f"涉及: {', '.join(detected)}",
                    constraint_raw=raw,
                    explanation="SUT 在回复中触及了禁止讨论的话题。",
                ))
        return violations

    def _check_termination(self, sut_turns: list, constraint, record, all_records) -> list[Violation]:
        """检查终止条件是否正确触发"""
        violations = []
        trigger_pattern = safe_attr(safe_attr(constraint, "params", {}), "trigger_pattern", "")
        expected_action = safe_attr(safe_attr(constraint, "params", {}), "expected_action", "")
        raw = safe_attr(constraint, "raw", "")

        # 找到触发终止条件的用例（通过用例类型匹配）
        test_type = safe_attr(record, "test_dimension", "")
        if test_type in ("driving_hangup", "user_reject"):
            # 检查 SUT 是否正确执行了终止动作
            sut_texts = [safe_attr(t, "content", "") for _, t in sut_turns]
            all_sut_text = " ".join(sut_texts)

            terminated = any(kw in all_sut_text for kw in ["稍后再打", "再见", "挂断", "回电"])
            if not terminated:
                violations.append(Violation(
                    dimension="constraint",
                    violation_type="termination_fail",
                    severity="high",
                    deduction=self.config.hard_constraint_deduction,
                    test_case_id=safe_attr(record, "test_case_id", ""),
                    expected=expected_action or "SUT应正确终止对话",
                    actual="SUT未执行终止动作",
                    constraint_raw=raw,
                    explanation=f"触发条件 [{trigger_pattern}] 出现但 SUT 未正确终止对话。",
                ))
        return violations

    def _check_repeat(self, sut_turns: list, constraint, record) -> list[Violation]:
        violations = []
        threshold = safe_attr(safe_attr(constraint, "params", {}), "similarity_threshold", 0.8)
        raw = safe_attr(constraint, "raw", "")
        texts = [safe_attr(t, "content", "") for _, t in sut_turns]

        for i in range(len(texts) - 1):
            for j in range(i + 1, min(i + 3, len(texts))):
                sim = self._simple_similarity(texts[i], texts[j])
                if sim > threshold:
                    violations.append(Violation(
                        dimension="constraint",
                        violation_type="no_repeat",
                        severity="low",
                        deduction=self.config.hard_constraint_deduction * 0.3,
                        test_case_id=safe_attr(record, "test_case_id", ""),
                        turn_number=j,
                        sut_message=texts[j][:80],
                        expected="不应机械重复",
                        actual=f"与第{i}轮相似度 {sim:.1%}",
                        constraint_raw=raw,
                        explanation=f"回复与之前轮次高度相似 ({sim:.1%})，缺乏多样性。",
                    ))
        return violations

    def _check_style(self, sut_turns: list, constraint, record) -> list[Violation]:
        """软约束抽样检测（简化版）"""
        # 软约束使用 LLM-as-Judge，此处仅做基本检测
        violations = []
        raw = safe_attr(constraint, "raw", "")
        # 抽样：只检测第一条记录，避免过多 LLM 调用
        if safe_attr(record, "test_case_id", "").endswith("TC001"):
            # 基本检查：SUT 回复是否为空或过短
            for idx, turn in sut_turns[:5]:
                content = safe_attr(turn, "content", "")
                if len(content) < 2:
                    violations.append(Violation(
                        dimension="constraint",
                        violation_type="style",
                        severity="low",
                        deduction=self.config.soft_constraint_deduction * 0.3,
                        test_case_id=safe_attr(record, "test_case_id", ""),
                        turn_number=idx,
                        sut_message="(空)",
                        constraint_raw=raw,
                        explanation="SUT 回复过短或为空。",
                    ))
        return violations

    @staticmethod
    def _simple_similarity(a: str, b: str) -> float:
        """基于字符集的简单文本相似度"""
        if not a or not b:
            return 0.0
        set_a, set_b = set(a), set(b)
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union)
