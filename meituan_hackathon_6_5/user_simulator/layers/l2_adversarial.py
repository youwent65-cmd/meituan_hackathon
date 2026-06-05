from __future__ import annotations

"""L2 对抗生成 - 边界测试模拟，从 Constraints 反向生成对抗场景"""

import random
from typing import Optional

from ..models import UserProfile, safe_attr
from ..context_tracker import DialogueContext


class AdversarialStrategy:
    """对抗策略：将约束映射为具体的对抗用户行为"""

    def __init__(
        self,
        name: str,
        constraint_type: str,
        trigger_round: int,
        user_action_template: str,
        expected_sut_behavior: str,
        repeatable: bool = False,
    ):
        self.name = name
        self.constraint_type = constraint_type
        self.trigger_round = trigger_round
        self.user_action_template = user_action_template
        self.expected_sut_behavior = expected_sut_behavior
        self.repeatable = repeatable


class L2AdversarialGen:
    """L2 层：从约束反向生成对抗性用户行为

    覆盖：FAQ 触发、越界问题、拒绝/挂断、重复追问、角色边界、打断等维度
    """

    # 预置对抗剧本
    ADVERSARIAL_SCRIPTS = {
        "user_reject": [
            "不用了，我不需要，你别再说了。",
            "行了行了，别再打来了，没兴趣。",
            "我说了不需要，你再打我就拉黑了。",
            "够了，我不想要，请别再打了。",
        ],
        "user_hangup": [
            "（挂断）",
            "不说了，挂了。",
        ],
        "repeated_question": [
            "我还是想问，{question}",
            "你没回答我的问题，{question}到底怎么回事？",
            "我要知道{question}，你刚说的我没听懂。",
        ],
        "out_of_scope": [
            "{question}",
            "我想知道{question}，你能告诉我吗？",
            "对了，{question}，你知道吗？",
        ],
        "role_boundary_coupon": [
            "那你能给我发个优惠券吗？",
            "能不能给我打个折？",
            "有没有什么新人优惠之类的？",
            "我要个折扣券，你们肯定有吧？",
        ],
        "role_boundary_identity": [
            "你是真人还是机器人？",
            "你们公司叫啥来着？",
            "你叫什么名字？",
        ],
        "info_missing": [
            "这个我就不告诉你了。",
            "我为什么要告诉你这个？",
            "不方便说。",
            "跳过这个吧，不重要的。",
        ],
        "interrupt": [
            "等一下，我有个问题。{question}",
            "先别说了，我问你个事。",
            "打断一下，那个……",
        ],
        "driving": [
            "不好意思，我在开车。",
            "我正在开车呢，不方便说。",
        ],
        "busy": [
            "我现在很忙，没时间。",
            "有事快说，我很忙。",
            "我这会儿忙得很，能不能简短点？",
        ],
        "entanglement": [
            "我还是不太明白，能再说说吗？",
            "你说的我还是不懂，什么意思？",
            "能不能解释得清楚一点？我不理解。",
        ],
    }

    def __init__(self, constraints: list, faq: list):
        self.constraints = constraints
        self.faq = faq
        self.strategies = self._build_strategies(constraints)
        self._repeat_counters = {}

    def _build_strategies(self, constraints: list) -> list[AdversarialStrategy]:
        """将约束列表映射为对抗策略列表"""
        strategies = []
        for c in constraints:
            ct = safe_attr(c, "constraint_type", "")
            raw = safe_attr(c, "raw", "")
            params = safe_attr(c, "params", {})

            if ct == "length_limit":
                strategies.append(AdversarialStrategy(
                    name="超长回复",
                    constraint_type=ct,
                    trigger_round=2,
                    user_action_template="LONG_REPLY",
                    expected_sut_behavior="SUT保持简洁，不模仿长回复",
                ))
            elif ct == "forbidden_words":
                words = safe_attr(params, "words", [])
                if words:
                    strategies.append(AdversarialStrategy(
                        name="引导禁用词",
                        constraint_type=ct,
                        trigger_round=3,
                        user_action_template=f"FORBIDDEN_WORDS:{','.join(words)}",
                        expected_sut_behavior="SUT不使用禁用词",
                    ))
            elif ct == "fallback_response":
                expected = safe_attr(params, "expected_script", "")
                strategies.append(AdversarialStrategy(
                    name="越界提问",
                    constraint_type=ct,
                    trigger_round=4,
                    user_action_template="OUT_OF_SCOPE",
                    expected_sut_behavior=f"SUT回复「{expected[:30]}…」",
                ))
            elif ct == "termination_condition":
                trigger_pattern = safe_attr(params, "trigger_pattern", "")
                strategies.append(AdversarialStrategy(
                    name="触发终止条件",
                    constraint_type=ct,
                    trigger_round=2,
                    user_action_template=f"TERMINATE:{trigger_pattern}",
                    expected_sut_behavior=f"触发终止条件后SUT挂断",
                ))
            elif ct == "forbidden_topic":
                topics = safe_attr(params, "topic_keywords", [])
                strategies.append(AdversarialStrategy(
                    name="触发禁止话题",
                    constraint_type=ct,
                    trigger_round=3,
                    user_action_template="FORBIDDEN_TOPIC",
                    expected_sut_behavior="SUT不触碰禁止话题",
                ))
            elif ct == "no_repeat":
                strategies.append(AdversarialStrategy(
                    name="重复追问",
                    constraint_type=ct,
                    trigger_round=3,
                    user_action_template="REPEAT_QUESTION",
                    expected_sut_behavior="SUT变换说法，不机械重复",
                    repeatable=True,
                ))
            elif ct == "conditional_response":
                trigger = safe_attr(params, "trigger_scenario", "")
                strategies.append(AdversarialStrategy(
                    name="触发条件响应",
                    constraint_type=ct,
                    trigger_round=1,
                    user_action_template=f"CONDITIONAL:{trigger}",
                    expected_sut_behavior="SUT按条件响应规则回复",
                ))

        return strategies

    def generate_reply(
        self,
        sut_message: str,
        context: DialogueContext,
        profile: UserProfile,
        test_case: "TestCase",
    ) -> str:
        """根据测试用例类型生成对抗性回复"""
        tc_type = test_case.type

        if tc_type == "happy_path":
            return self._neutral_reply(context)

        elif tc_type == "faq_trigger":
            return self._faq_trigger_reply(test_case)

        elif tc_type == "out_of_scope":
            return self._out_of_scope_reply(test_case, context)

        elif tc_type == "user_reject":
            return self._user_reject_reply(context)

        elif tc_type == "repeated_question":
            return self._repeated_question_reply(test_case, context)

        elif tc_type == "role_boundary":
            return self._role_boundary_reply(test_case)

        elif tc_type == "interrupt":
            return self._interrupt_reply(test_case, context)

        elif tc_type == "info_missing":
            return self._info_missing_reply(context)

        elif tc_type == "driving_hangup":
            return self._driving_reply(context)

        elif tc_type == "busy_continue":
            return self._busy_reply(context)

        elif tc_type == "branch_path":
            return self._branch_reply(test_case)

        else:
            return self._neutral_reply(context)

    # ---- 各维度回复生成 ----

    def _faq_trigger_reply(self, test_case: "TestCase") -> str:
        """触发 FAQ 提问"""
        q = test_case.trigger_question
        return f"我想问一下，{q}" if q else "我有个问题想问。"

    def _out_of_scope_reply(self, test_case: "TestCase", context: DialogueContext) -> str:
        """越界提问"""
        q = test_case.trigger_question
        if not q:
            q = "你能给我发个优惠券吗？"
        return random.choice(self.ADVERSARIAL_SCRIPTS["out_of_scope"]).format(question=q)

    def _user_reject_reply(self, context: DialogueContext) -> str:
        scripts = self.ADVERSARIAL_SCRIPTS["user_reject"]
        return random.choice(scripts)

    def _repeated_question_reply(self, test_case: "TestCase", context: DialogueContext) -> str:
        q = test_case.repeat_question or "这个怎么回事？"
        self._repeat_counters[q] = self._repeat_counters.get(q, 0) + 1
        count = self._repeat_counters[q]
        if count == 1:
            return f"我想问一下，{q}"
        elif count == 2:
            return random.choice(self.ADVERSARIAL_SCRIPTS["repeated_question"]).format(question=q)
        else:
            return f"你还没回答我！{q}到底怎么样？"

    def _role_boundary_reply(self, test_case: "TestCase") -> str:
        q = test_case.trigger_question
        if "优惠" in q or "折扣" in q:
            return random.choice(self.ADVERSARIAL_SCRIPTS["role_boundary_coupon"])
        return random.choice(self.ADVERSARIAL_SCRIPTS["role_boundary_identity"])

    def _interrupt_reply(self, test_case: "TestCase", context: DialogueContext) -> str:
        q = test_case.trigger_question or "这个功能怎么用？"
        return random.choice(self.ADVERSARIAL_SCRIPTS["interrupt"]).format(question=q)

    def _info_missing_reply(self, context: DialogueContext) -> str:
        return random.choice(self.ADVERSARIAL_SCRIPTS["info_missing"])

    def _driving_reply(self, context: DialogueContext) -> str:
        return random.choice(self.ADVERSARIAL_SCRIPTS["driving"])

    def _busy_reply(self, context: DialogueContext) -> str:
        return random.choice(self.ADVERSARIAL_SCRIPTS["busy"])

    def _branch_reply(self, test_case: "TestCase") -> str:
        trigger = test_case.trigger_question
        if "是" in trigger or "已知情" in trigger or "已" in trigger:
            return "是的，没错。"
        elif "不" in trigger or "未" in trigger:
            return "没有，不是。"
        else:
            return "嗯，你说。"

    def _neutral_reply(self, context: DialogueContext) -> str:
        neutral = ["嗯，好的。", "明白了。", "好的，你说。", "行。"]
        return random.choice(neutral)
