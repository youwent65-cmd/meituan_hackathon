from __future__ import annotations

"""流程完整度评估器 — 维度一 (权重 30%)

指标：步骤覆盖率 / 步骤顺序正确率 / 步骤触发准确性
"""

import re

from .models import DimensionScore, Violation, EvalConfig, safe_attr

# 指令前缀模式 — 与 mock_sut_v2 保持一致，用于关键词提取前的文本清理
_INSTR_PREFIX_PATTERNS = [
    r"^告知(?:骑手|站长|用户|对方|他们|您)?[，。,，\s]*",
    r"^通知(?:骑手|站长|用户|对方|他们|您)?[，。,，\s]*",
    r"^说明[：:，。,，\s]*",
    r"^解释[：:，。,，\s]*",
    r"^询问(?:骑手|站长|用户|对方|他们|您)?[，。,，\s]*",
    r"^确认[：:，。,，\s]*",
    r"^提醒(?:骑手|站长|用户|对方|他们|您)?[，。,，\s]*",
    r"^尽量挽留(?:不想配送的)?骑手[，。,，\s]*",
    r"^挽留(?:骑手|用户|对方)?[，。,，\s]*",
    r"^鼓励(?:能配送的)?(?:骑手|用户|对方)?[，。,，\s]*",
    r"^强调[：:，。,，\s]*",
    r"^核实[：:，。,，\s]*",
    r"^了解[：:，。,，\s]*",
    r"^介绍[：:，。,，\s]*",
    r"^提供[：:，。,，\s]*",
    r"^(?:再次|重复)(?:告知|说明|提醒|强调|确认)[：:，。,，\s]*",
    r"^并且[，。,，\s]*",
    r"^而且[，。,，\s]*",
    r"^并(?=[，。,，；;、])[，。,，\s]*",
]


class FlowEvaluator:
    """评估 SUT 是否按 Call Flow 定义完成了所有必要步骤"""

    def __init__(self, config: EvalConfig, instruction):
        self.config = config
        self.instruction = instruction
        self._build_expected_flow()

    def _build_expected_flow(self):
        """从指令中提取预期的流程步骤"""
        steps = self.instruction.flow_steps if hasattr(self.instruction, "flow_steps") else []
        self.required_steps = []
        self.all_steps = []
        self.step_order = {}  # step_id → position

        for i, s in enumerate(steps):
            sid = safe_attr(s, "id", str(i + 1))
            is_req = safe_attr(s, "is_required", True)
            node_type = safe_attr(s, "node_type", "action")
            self.all_steps.append(sid)
            self.step_order[sid] = i
            if is_req and node_type not in ("info",):
                self.required_steps.append(sid)

    def evaluate(self, dialogue_records: list) -> DimensionScore:
        """对所有对话记录进行流程完整度评估"""
        score = DimensionScore(
            dimension="flow",
            label_cn="流程完整度",
            weight=0.30,
            score=100.0,
        )
        violations = []

        total_required = len(self.required_steps)
        if total_required == 0:
            score.score = 100.0
            score.details = "无预设流程步骤，跳过评估。"
            return score

        # 统计各指标
        step_coverage_sum = 0.0          # 步骤覆盖率
        order_correct_count = 0          # 顺序正确数
        total_order_cases = 0
        step_trigger_correct = 0
        step_trigger_total = 0

        for record in dialogue_records:
            turns = record.turns if hasattr(record, "turns") else record.get("turns", [])
            sut_turns = [t for t in turns if safe_attr(t, "role", "") == "SUT"]
            sut_texts = [safe_attr(t, "content", "") for t in sut_turns]

            # 检测步骤覆盖
            completed = set()
            detected_order = []
            for sid in self.all_steps:
                hint = self._get_detection_hint(sid)
                for i, text in enumerate(sut_texts):
                    if self._step_detected(text, hint, sid):
                        completed.add(sid)
                        if sid not in [d[0] for d in detected_order]:
                            detected_order.append((sid, i))
                        break

            # 指标1: 步骤覆盖率
            coverage = len(completed & set(self.required_steps)) / total_required
            step_coverage_sum += coverage

            # 指标2: 步骤顺序
            expected_order = {sid: self.step_order.get(sid, 999) for sid in completed}
            det_ordered = sorted(detected_order, key=lambda x: x[1])
            det_ids = [d[0] for d in det_ordered]
            if len(det_ids) >= 2:
                total_order_cases += 1
                if all(
                    expected_order.get(det_ids[i], 0) <= expected_order.get(det_ids[i + 1], 999)
                    for i in range(len(det_ids) - 1)
                ):
                    order_correct_count += 1
                else:
                    # 顺序错误扣分
                    violations.append(Violation(
                        dimension="flow",
                        violation_type="step_order_error",
                        severity="medium",
                        deduction=self.config.step_order_deduction,
                        test_case_id=safe_attr(record, "test_case_id", ""),
                        expected=f"步骤顺序: {' → '.join(self.required_steps)}",
                        actual=f"检测到顺序: {' → '.join(det_ids)}",
                        explanation=f"对话中步骤执行顺序与预期流程不一致。",
                    ))

            # 指标3: 步骤遗漏
            missing = set(self.required_steps) - completed
            for mid in missing:
                step_desc = self._get_step_desc(mid)
                violations.append(Violation(
                    dimension="flow",
                    violation_type="step_miss",
                    severity="high",
                    deduction=self.config.step_miss_deduction,
                    test_case_id=safe_attr(record, "test_case_id", ""),
                    expected=f"应执行步骤 [{mid}]: {step_desc}",
                    actual="未检测到该步骤被触发",
                    explanation=f"Call Flow 中步骤 [{mid}] ({step_desc}) 未被 SUT 执行。",
                ))

        # 计算分维度得分
        avg_coverage = step_coverage_sum / max(len(dialogue_records), 1)
        order_rate = order_correct_count / max(total_order_cases, 1) if total_order_cases > 0 else 1.0

        # 覆盖率为主 (80%)，顺序正确率为辅 (20%)
        coverage_score = avg_coverage * 100
        order_penalty = max(0, (1 - order_rate) * 20)
        score.score = max(0, min(100, coverage_score - order_penalty))

        score.raw_metrics = {
            "avg_step_coverage": round(avg_coverage, 3),
            "order_correctness_rate": round(order_rate, 3),
            "total_required_steps": total_required,
            "total_misses": len([v for v in violations if v.violation_type == "step_miss"]),
            "total_order_errors": len([v for v in violations if v.violation_type == "step_order_error"]),
        }
        score.violations = violations
        score.details = (
            f"步骤覆盖率 {avg_coverage:.1%}，顺序正确率 {order_rate:.1%}，"
            f"发现 {len(violations)} 处流程问题。"
        )
        return score

    def _get_detection_hint(self, step_id: str) -> str:
        for s in (self.instruction.flow_steps if hasattr(self.instruction, "flow_steps") else []):
            if safe_attr(s, "id", "") == step_id:
                return safe_attr(s, "detection_hint", "")
        return ""

    def _get_step_desc(self, step_id: str) -> str:
        for s in (self.instruction.flow_steps if hasattr(self.instruction, "flow_steps") else []):
            if safe_attr(s, "id", "") == step_id:
                return safe_attr(s, "description", step_id)
        return step_id

    def _strip_instruction_prefixes(self, text: str) -> str:
        """移除指令前缀动词，提取纯内容关键词（与 mock_sut_v2 的转换保持一致）"""
        for pattern in _INSTR_PREFIX_PATTERNS:
            text = re.sub(pattern, "", text)
        return text

    def _step_detected(self, sut_text: str, hint: str, step_id: str) -> bool:
        """基于 hint、关键词和 trigram 重叠检测步骤是否被触发。

        检测策略（按优先级）：
        1. detection_hint 精确/子串匹配（最可靠）
        2. 关键词匹配（从清理后的步骤描述中提取）
        3. 字符 trigram 重叠（兜底，处理自然口语化变体）
        """
        if not sut_text.strip():
            return False

        # 策略1: detection_hint 匹配
        if hint and hint.strip():
            if hint in sut_text:
                return True
            # hint 子串匹配（取 hint 中最长的非标点片段）
            hint_parts = re.split(r"[，。；;,、\s]+", hint)
            for part in hint_parts:
                if len(part) >= 3 and part in sut_text:
                    return True

        desc = self._get_step_desc(step_id)

        # 剥离指令前缀后再提取关键词
        clean_desc = self._strip_instruction_prefixes(desc)
        # 代词转换：第三人称→第二人称（与mock_sut_v2保持一致）
        clean_desc = clean_desc.replace("骑手", "您").replace("他们", "您")

        # 从清理后的描述中提取有意义的2-4字片段作为关键词
        keywords = []
        # 按标点分割为语义片段
        segments = re.split(r"[，。；;,、\s]+", clean_desc)
        for seg in segments:
            seg = seg.strip()
            # 移除段首的过渡/连接词，避免生成无效关键词
            seg = re.sub(r"^(并且|而且|以及|同时|另外|此外|并|且)[，。,，\s]*", "", seg)
            seg = re.sub(r"^(是否可以|是否|是不是|能不能|可不可以)", "", seg)
            if len(seg) >= 2:
                keywords.append(seg)
                # 对较短的片段（<=5字）生成2字滑动窗口，对长片段生成3字窗口
                if 2 <= len(seg) <= 5:
                    for i in range(len(seg) - 1):
                        sub = seg[i:i + 2]
                        if sub not in keywords:
                            keywords.append(sub)
                elif len(seg) >= 6:
                    for i in range(len(seg) - 2):
                        sub = seg[i:i + 3]
                        if sub not in keywords:
                            keywords.append(sub)

        # 策略2: 关键词匹配（至少需要 max(1, round(len(keywords) * 0.2)) 个匹配）
        if keywords:
            matched = sum(1 for kw in keywords if kw in sut_text)
            required = max(1, round(len(keywords) * 0.2))
            if matched >= required:
                return True

        # 策略3: 字符 trigram 重叠兜底
        trigram_overlap = self._trigram_overlap(clean_desc, sut_text)
        return trigram_overlap >= 0.25

    @staticmethod
    def _trigram_overlap(text_a: str, text_b: str) -> float:
        """计算两个文本的字符 trigram Jaccard 相似度"""
        def _trigrams(s):
            s = s.replace(" ", "").replace("\n", "")
            return {s[i:i + 3] for i in range(max(0, len(s) - 2))}

        tri_a = _trigrams(text_a)
        tri_b = _trigrams(text_b)
        if not tri_a or not tri_b:
            return 0.0
        return len(tri_a & tri_b) / len(tri_a | tri_b)
