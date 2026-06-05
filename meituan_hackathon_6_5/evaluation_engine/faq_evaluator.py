from __future__ import annotations

"""FAQ 准确性评估器 — 维度三 (权重 20%)

指标：知识召回率 / 知识精确度 / 幻觉检测
"""

from collections import Counter

from .models import DimensionScore, Violation, EvalConfig, safe_attr


class FAQEvaluator:
    """评估 SUT 在 FAQ 触发时的回答准确性"""

    def __init__(self, config: EvalConfig, instruction):
        self.config = config
        self.instruction = instruction
        self.faq_items = instruction.faq if hasattr(instruction, "faq") else []

    def evaluate(self, dialogue_records: list) -> DimensionScore:
        score = DimensionScore(
            dimension="faq",
            label_cn="FAQ准确性",
            weight=0.20,
            score=0.0,
        )
        violations = []

        if not self.faq_items:
            score.weight = 0.0
            score.details = "无知识库条目，该维度不适用(N/A)。"
            return score

        # 筛选 FAQ 触发类用例
        faq_records = [
            r for r in dialogue_records
            if safe_attr(r, "test_dimension", "") in ("faq_trigger", "free_form")
        ]

        if not faq_records:
            score.weight = 0.0
            score.details = f"共{len(self.faq_items)}条FAQ但无FAQ触发类测试用例，该维度无法评估(N/A)。"
            return score

        total_recall = 0.0
        total_precision = 0.0
        evaluated_count = 0
        hallucination_count = 0

        for record in faq_records:
            turns = record.turns if hasattr(record, "turns") else record.get("turns", [])
            sut_turns = [t for t in turns if safe_attr(t, "role", "") == "SUT"]
            sut_texts = [safe_attr(t, "content", "") for t in sut_turns]

            record_meta = safe_attr(record, "metadata", {}) or {}

            # 检查 metadata 中的 expected_faq_answers
            expected_faq = record_meta.get("expected_faq_answers", {})

            if not expected_faq:
                # 尝试从 trigger_question 匹配 FAQ
                trigger_q = safe_attr(record, "trigger_question", "")
                for faq in self.faq_items:
                    faq_q = safe_attr(faq, "question", "")
                    if trigger_q and self._overlap(trigger_q, faq_q):
                        expected_faq[faq_q] = safe_attr(faq, "answer", "")

            for faq_q, expected_answer in expected_faq.items():
                evaluated_count += 1
                best_match = ""
                best_sim = 0.0

                for text in sut_texts:
                    # 剥离 SUT 的 FAQ 应答前缀后再比较
                    clean_text = self._strip_sut_prefix(text)
                    sim = self._text_similarity(expected_answer, clean_text)
                    if sim > best_sim:
                        best_sim = sim
                        best_match = text

                threshold = self.config.similarity_threshold
                if best_sim >= threshold:
                    total_recall += 1.0
                    total_precision += best_sim
                else:
                    violations.append(Violation(
                        dimension="faq",
                        violation_type="faq_miss",
                        severity="medium",
                        deduction=self.config.faq_miss_deduction,
                        test_case_id=safe_attr(record, "test_case_id", ""),
                        expected=expected_answer[:100],
                        actual=best_match[:100] if best_match else "(未匹配到)",
                        explanation=(
                            f"FAQ「{faq_q[:40]}…」未得到准确回答"
                            f"(最佳相似度 {best_sim:.1%} < 阈值 {threshold:.1%})。"
                        ),
                    ))

                # 幻觉检测：回答内容包含无关知识
                if best_sim < 0.3 and best_match:
                    hallucination_count += 1
                    violations.append(Violation(
                        dimension="faq",
                        violation_type="hallucination",
                        severity="high",
                        deduction=self.config.hallucination_deduction,
                        test_case_id=safe_attr(record, "test_case_id", ""),
                        expected=expected_answer[:100],
                        actual=best_match[:100],
                        explanation="SUT 似乎编造了知识库中不存在的回答内容。",
                    ))

        # 计算得分
        if evaluated_count > 0:
            recall_rate = total_recall / evaluated_count
            precision_avg = total_precision / max(evaluated_count, 1)
            score.score = max(0, recall_rate * 0.6 * 100 + precision_avg * 0.4 * 100)
            score.score = max(0, score.score - sum(v.deduction for v in violations))
        else:
            score.weight = 0.0
            score.score = 0.0
            score.details = f"共{len(self.faq_items)}条FAQ存在但未被任何测试用例实际触发，该维度无法评估(N/A)。"
            return score

        score.raw_metrics = {
            "faq_items_total": len(self.faq_items),
            "faq_triggered_count": evaluated_count,
            "recall_rate": round(total_recall / max(evaluated_count, 1), 3),
            "avg_precision": round(total_precision / max(evaluated_count, 1), 3),
            "hallucination_count": hallucination_count,
        }
        score.violations = violations
        score.details = (
            f"已评估 {evaluated_count} 次 FAQ 触发，"
            f"召回率 {score.raw_metrics['recall_rate']:.1%}，"
            f"精确度均值 {score.raw_metrics['avg_precision']:.1%}，"
            f"疑似幻觉 {hallucination_count} 次。"
        )
        return score

    @staticmethod
    def _strip_sut_prefix(text: str) -> str:
        """移除 SUT 回复中的 FAQ 应答前缀，使相似度比较更准确"""
        prefixes = [
            "好的，关于您问的这个问题——",
            "嗯，这个问题是这样的——",
            "了解，您问的是——",
            "好的，我给您解释一下——",
            "关于这个问题——",
            "好的，关于这个问题——",
            "嗯，关于这个问题——",
        ]
        for prefix in prefixes:
            if text.startswith(prefix):
                return text[len(prefix):]
        return text

    @staticmethod
    def _text_similarity(a: str, b: str) -> float:
        """基于字符 n-gram 的文本相似度"""
        if not a or not b:
            return 0.0

        def _ngrams(s, n=3):
            s = s.replace(" ", "")
            return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}

        ngrams_a = _ngrams(a)
        ngrams_b = _ngrams(b)
        if not ngrams_a or not ngrams_b:
            return 0.0
        intersection = ngrams_a & ngrams_b
        union = ngrams_a | ngrams_b
        return len(intersection) / len(union) if union else 0.0

    @staticmethod
    def _overlap(a: str, b: str) -> bool:
        """简单重叠检测"""
        a_words = set(a[:30].replace("？", "").replace("，", " ").split())
        b_words = set(b[:30].replace("？", "").replace("，", " ").split())
        if not a_words or not b_words:
            return False
        return len(a_words & b_words) / len(a_words | b_words) > 0.3
