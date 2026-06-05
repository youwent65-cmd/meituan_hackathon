from __future__ import annotations

"""对话自然度评估器 — 维度四 (权重 10%)

指标：回应多样性 / 过渡自然度 / 口语化程度
"""

import json
import re
from collections import Counter

from .models import DimensionScore, Violation, EvalConfig, safe_attr


class NaturalnessEvaluator:
    """评估 SUT 对话的自然程度。

    支持两种模式：
    - 规则模式（默认）：基于字符多样性、过渡语、书面语检测
    - LLM-as-Judge（config.llm_enabled=True）：调用 Claude 对对话质量评分
    """

    # 过渡语模式
    TRANSITION_PATTERNS = [
        r"您刚才提到[^，。]*",
        r"我刚说到[^，。]*",
        r"回到刚才[^，。]*",
        r"关于您[^，。]*的问题",
    ]

    # 书面语特征
    FORMAL_PATTERNS = [
        (r"的{2,}", "连续'的'字过多"),         # 的的的
        (r"[之乎者也]{2,}", "文言词过多"),
        (r"综上所述|总而言之|首先.*其次.*最后", "过于正式的表达"),
        (r"\b(鉴于|故此|故而|遂|乃)\b", "书面词使用"),
    ]

    LLM_JUDGE_PROMPT = """你是一位对话质量评估专家。请评估以下外呼机器人(SUT)与用户对话的自然度。

从以下维度评分（每项0-100）：
1. **连贯性**: 机器人回复是否与用户上一条消息衔接自然
2. **人性化**: 机器人语气是否自然、不死板，像真人客服而非机械朗读
3. **应变能力**: 面对用户的打断/困惑/拒绝时，机器人是否灵活应对而非机械推进
4. **简洁度**: 回复长度是否合适，不过于冗长也不过于简短

对话记录：
{conversation}

请返回 JSON 格式（只输出 JSON，不要其他文字）：
{{"coherence": 85, "human_likeness": 72, "adaptability": 60, "conciseness": 90, "overall_comment": "简短评语"}}"""

    def __init__(self, config: EvalConfig, instruction):
        self.config = config
        self.instruction = instruction

    def evaluate(self, dialogue_records: list) -> DimensionScore:
        score = DimensionScore(
            dimension="naturalness",
            label_cn="对话自然度",
            weight=0.10,
            score=100.0,
        )
        violations = []

        all_diversity_scores = []
        all_transition_counts = []
        all_formal_counts = []
        total_turns = 0

        for record in dialogue_records:
            turns = record.turns if hasattr(record, "turns") else record.get("turns", [])
            sut_turns = [(i, t) for i, t in enumerate(turns) if safe_attr(t, "role", "") == "SUT"]
            sut_texts = [safe_attr(t, "content", "") for _, t in sut_turns]
            total_turns += len(sut_texts)

            if not sut_texts:
                continue

            # 指标1: 回应多样性
            diversity = self._calc_diversity(sut_texts)
            all_diversity_scores.append(diversity)

            # 指标2: 过渡自然度
            transitions = self._count_transitions(sut_texts)
            all_transition_counts.append(transitions)

            # 指标3: 口语化程度
            formal_issues = self._check_formal_style(sut_texts)
            all_formal_counts.append(formal_issues)

            # 多样性低：生成违规
            if diversity < 0.3:
                violations.append(Violation(
                    dimension="naturalness",
                    violation_type="low_diversity",
                    severity="medium",
                    deduction=5.0,
                    test_case_id=safe_attr(record, "test_case_id", ""),
                    expected="回复应有多样性",
                    actual=f"轮间相似度均值 {diversity:.1%}",
                    explanation="SUT 回复缺乏多样性，可能存在机械重复。",
                ))

        # 综合计算（规则部分）
        avg_diversity = sum(all_diversity_scores) / max(len(all_diversity_scores), 1)
        avg_transitions = sum(all_transition_counts) / max(len(all_transition_counts), 1) if all_transition_counts else 0
        avg_formal = sum(all_formal_counts) / max(len(all_formal_counts), 1) if all_formal_counts else 0

        diversity_score = avg_diversity * 100
        transition_score = min(100, avg_transitions * 50)  # 过渡语加分
        formal_penalty = min(30, avg_formal * 10)           # 书面语扣分

        rule_score = max(0, diversity_score * 0.5 + transition_score * 0.3 + (100 - formal_penalty) * 0.2)
        rule_score = max(0, rule_score - sum(v.deduction for v in violations))

        # LLM-as-Judge（仅在启用且有 API key 时）
        llm_score = None
        llm_metrics = None
        if self.config.llm_enabled:
            llm_score, llm_metrics = self._llm_judge_naturalness(dialogue_records)

        if llm_score is not None:
            # 规则分 40% + LLM 分 60%，LLM 权重更高
            score.score = max(0, rule_score * 0.4 + llm_score * 0.6)
            score.score = min(100, score.score)
            judge_note = " [LLM-as-Judge已启用]"
        else:
            score.score = min(100, rule_score)
            judge_note = ""

        score.raw_metrics = {
            "avg_diversity": round(avg_diversity, 3),
            "avg_transition_phrases": round(avg_transitions, 1),
            "avg_formal_issues": round(avg_formal, 1),
            "total_sut_turns": total_turns,
            "rule_score": round(rule_score, 1),
        }
        if llm_metrics:
            score.raw_metrics.update(llm_metrics)

        score.violations = violations
        score.details = (
            f"回应多样性 {avg_diversity:.1%}，"
            f"平均过渡语 {avg_transitions:.1f} 处/对话，"
            f"书面语问题 {avg_formal:.1f} 处/对话。"
            f"{judge_note}"
        )
        return score

    def _llm_judge_naturalness(self, dialogue_records: list) -> tuple:
        """使用 LLM-as-Judge 评估对话自然度。

        抽样最多3条对话发送给 Claude 评分，返回 (综合分数, 指标dict)。
        失败时返回 (None, None)。
        """
        if not self.config.llm_api_key:
            print("[LLM Judge] WARNING: llm_enabled=True 但未配置 API Key，跳过 LLM 评估。")
            return None, None

        # 抽样：优先选 L3 自由对话，其次选轮次多的
        l3_records = [r for r in dialogue_records
                      if safe_attr(r, "layer_used", "") == "L3"]
        other_records = [r for r in dialogue_records
                         if safe_attr(r, "layer_used", "") != "L3"]
        # 按轮次数排序，取对话最丰富的
        l3_records.sort(key=lambda r: safe_attr(r, "total_turns", 0), reverse=True)
        other_records.sort(key=lambda r: safe_attr(r, "total_turns", 0), reverse=True)
        sampled = (l3_records[:2] + other_records[:1])[:3]

        if not sampled:
            return None, None

        # 初始化 LLM 客户端
        provider = getattr(self.config, "llm_provider", "anthropic")
        try:
            if provider == "anthropic":
                import anthropic
                client = anthropic.Anthropic(api_key=self.config.llm_api_key)
                client_type = "anthropic"
            elif provider in ("deepseek", "openai"):
                import openai
                base_url = self.config.llm_base_url
                if not base_url and provider == "deepseek":
                    base_url = "https://api.deepseek.com"
                kwargs = {"api_key": self.config.llm_api_key}
                if base_url:
                    kwargs["base_url"] = base_url
                client = openai.OpenAI(**kwargs)
                client_type = "openai"
            else:
                print(f"[LLM Judge] WARNING: 不支持的 provider '{provider}'")
                return None, None
        except Exception as e:
            print(f"[LLM Judge] WARNING: 无法初始化 LLM 客户端 ({e})，"
                  "请检查 API Key 是否正确。")
            return None, None

        # 自动选择模型
        model = self.config.llm_model
        if model == "claude-sonnet-4-6":
            if provider == "deepseek":
                model = "deepseek-chat"
            elif provider == "openai":
                model = "gpt-4o"

        all_scores = []
        all_metrics = {}
        success = 0

        for record in sampled:
            conversation = ""
            if hasattr(record, "conversation_text"):
                conversation = record.conversation_text()
            else:
                turns = record.get("turns", []) if isinstance(record, dict) else getattr(record, "turns", [])
                for t in turns:
                    role = safe_attr(t, "role", "SUT")
                    content = safe_attr(t, "content", "")
                    label = "SUT" if role == "SUT" else "用户"
                    conversation += f"[{label}] {content}\n"

            if not conversation.strip():
                continue

            prompt = self.LLM_JUDGE_PROMPT.format(conversation=conversation[:3000])
            try:
                if client_type == "anthropic":
                    response = client.messages.create(
                        model=model,
                        max_tokens=256,
                        temperature=0.3,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    content = response.content[0].text.strip()
                else:
                    response = client.chat.completions.create(
                        model=model,
                        max_tokens=256,
                        temperature=0.3,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    content = response.choices[0].message.content.strip()
                # 提取 JSON
                if "```" in content:
                    import re as _re
                    match = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
                    if match:
                        content = match.group(1)
                result = json.loads(content)

                # 加权计算单条对话分数
                weights = {"coherence": 0.30, "human_likeness": 0.35,
                           "adaptability": 0.25, "conciseness": 0.10}
                record_score = sum(result.get(k, 50) * w for k, w in weights.items())
                all_scores.append(record_score)
                success += 1
            except Exception as e:
                print(f"[LLM Judge] WARNING: 评分请求失败 ({e})，跳过该条对话。")
                continue

        if not all_scores:
            return None, None

        final_score = sum(all_scores) / len(all_scores)
        all_metrics = {
            "llm_judge_score": round(final_score, 1),
            "llm_samples_evaluated": success,
        }
        print(f"[LLM Judge] 成功评估 {success}/{len(sampled)} 条对话，"
              f"LLM 自然度评分: {final_score:.1f}")
        return final_score, all_metrics

    def _calc_diversity(self, texts: list[str]) -> float:
        """计算相邻轮次间的多样性 (1 - 平均相似度)"""
        if len(texts) < 2:
            return 1.0
        similarities = []
        for i in range(len(texts) - 1):
            sim = self._char_similarity(texts[i], texts[i + 1])
            similarities.append(sim)
        avg_sim = sum(similarities) / len(similarities)
        return 1.0 - avg_sim

    @staticmethod
    def _char_similarity(a: str, b: str) -> float:
        if not a or not b:
            return 0.0
        set_a, set_b = set(a), set(b)
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def _count_transitions(self, texts: list[str]) -> int:
        """统计过渡语使用次数"""
        count = 0
        for text in texts:
            for pattern in self.TRANSITION_PATTERNS:
                if re.search(pattern, text):
                    count += 1
        return count

    def _check_formal_style(self, texts: list[str]) -> int:
        """检查书面语特征"""
        count = 0
        for text in texts:
            for pattern, _ in self.FORMAL_PATTERNS:
                if re.search(pattern, text):
                    count += 1
        return count
