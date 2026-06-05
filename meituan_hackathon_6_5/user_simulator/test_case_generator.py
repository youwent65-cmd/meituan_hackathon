from __future__ import annotations

"""测试用例生成器 - 根据指令和用户画像生成测试用例矩阵"""

from .models import TestCase, UserProfile, safe_attr


class TestCaseGenerator:
    """画像 × 测试维度 × 模拟层次 → 测试用例矩阵"""

    TEST_DIMENSIONS = [
        "happy_path",         # 正常路径
        "faq_trigger",        # FAQ 触发
        "out_of_scope",       # 越界问题
        "user_reject",        # 用户拒绝
        "repeated_question",  # 重复追问
        "role_boundary",      # 角色边界（索要优惠券等）
        "interrupt",          # 打断场景
        "info_missing",       # 信息缺失
        "free_form",          # 自由对话
        "driving_hangup",     # 开车挂断
        "busy_continue",      # 繁忙继续
    ]

    def __init__(self):
        pass

    def generate(
        self,
        instruction: "ParsedInstruction",
        profiles: list[UserProfile],
    ) -> list[TestCase]:
        """生成完整的测试用例矩阵

        Args:
            instruction: 解析后的结构化指令
            profiles: 用户画像列表

        Returns:
            测试用例列表（约 20-30 条）
        """
        cases = []
        case_id = 0
        inst_id = getattr(instruction, "role", "")[:10]

        # --- T01: Happy Path (L1) ---
        happy_profile = next(
            (p for p in profiles if p.cooperation_level > 0.7 and p.emotion == "neutral"),
            profiles[0]
        )
        cases.append(TestCase(
            id=self._cid(inst_id, case_id := case_id + 1),
            type="happy_path",
            layer="L1",
            profile=happy_profile,
            description="正常路径：用户按预期走完全部流程",
        ))

        # --- T02: 分支路径 (L1) ---
        branch_steps = [s for s in instruction.flow_steps if s.conditions]
        for branch in branch_steps[:3]:
            for cond in branch.conditions[:2]:
                cases.append(TestCase(
                    id=self._cid(inst_id, case_id := case_id + 1),
                    type="branch_path",
                    layer="L1",
                    profile=self._get_cooperative(profiles),
                    description=f"分支路径：步骤{branch.id} → {cond.trigger}",
                    trigger_question=cond.trigger,
                ))

        # --- T03: FAQ 触发 (L2) ---
        confused = next(
            (p for p in profiles if p.emotion == "confused"),
            profiles[3] if len(profiles) > 3 else profiles[-1]
        )
        for faq_item in instruction.faq[:3]:
            cases.append(TestCase(
                id=self._cid(inst_id, case_id := case_id + 1),
                type="faq_trigger",
                layer="L2",
                profile=confused,
                trigger_turn=2,
                trigger_question=faq_item.question,
                expected_answer=faq_item.answer,
                description=f"FAQ触发：用户提问「{faq_item.question[:30]}…」",
            ))

        # --- T04: 越界问题 (L2) ---
        out_of_scope_questions = self._gen_out_of_scope_questions(instruction)
        for q in out_of_scope_questions:
            cases.append(TestCase(
                id=self._cid(inst_id, case_id := case_id + 1),
                type="out_of_scope",
                layer="L2",
                profile=self._get_low_coop(profiles),
                trigger_turn=3,
                trigger_question=q["question"],
                expected_behavior=q["expected"],
                description=f"越界问题：{q['question'][:30]}…",
            ))

        # --- T05: 拒绝/挂断 (L2) ---
        cases.append(TestCase(
            id=self._cid(inst_id, case_id := case_id + 1),
            type="user_reject",
            layer="L2",
            profile=self._get_low_coop(profiles),
            trigger_turn=2,
            user_action="明确表示不需要，请对方不要再打来",
            expected_behavior="SUT安抚后挂断",
            description="拒绝场景：用户明确拒绝",
        ))
        cases.append(TestCase(
            id=self._cid(inst_id, case_id := case_id + 1),
            type="user_reject",
            layer="L2",
            profile=self._get_low_coop(profiles),
            trigger_turn=1,
            user_action="直接挂断电话",
            expected_behavior="SUT不再拨打",
            description="挂断场景：用户直接挂断",
        ))

        # --- T06: 重复追问 (L2) ---
        impatient_p = next(
            (p for p in profiles if p.emotion == "impatient"),
            profiles[1] if len(profiles) > 1 else profiles[0]
        )
        repeat_q = "配送还要多久？" if "骑" in instruction.task else "这个功能什么时候能用？"
        cases.append(TestCase(
            id=self._cid(inst_id, case_id := case_id + 1),
            type="repeated_question",
            layer="L2",
            profile=impatient_p,
            repeat_question=repeat_q,
            repeat_count=3,
            expected_behavior="SUT不机械重复，变换说法回答",
            description=f"重复追问：用户连续3次问「{repeat_q}」",
        ))

        # --- T07: 角色边界 (L2) ---
        boundary_qs = [
            ("你能给我发个优惠券吗？", "SUT不应承诺优惠券"),
            ("能不能给我打个折？", "SUT不应承诺折扣"),
            ("你是机器人还是真人？", "SUT应表明身份"),
        ]
        for q, expected in boundary_qs[:2]:
            cases.append(TestCase(
                id=self._cid(inst_id, case_id := case_id + 1),
                type="role_boundary",
                layer="L2",
                profile=self._get_low_coop(profiles),
                trigger_turn=3,
                trigger_question=q,
                expected_behavior=expected,
                description=f"角色边界：{q}",
            ))

        # --- T08: 打断/信息缺失 (L2) ---
        cases.append(TestCase(
            id=self._cid(inst_id, case_id := case_id + 1),
            type="interrupt",
            layer="L2",
            profile=profiles[2] if len(profiles) > 2 else profiles[-1],
            trigger_turn=2,
            user_action="中途打断对方，岔开话题问别的问题",
            expected_behavior="SUT先回答问题再继续流程",
            description="打断场景：用户中途打断",
        ))
        cases.append(TestCase(
            id=self._cid(inst_id, case_id := case_id + 1),
            type="info_missing",
            layer="L2",
            profile=self._get_low_coop(profiles),
            trigger_turn=2,
            user_action="拒绝提供必要信息（如订单号、姓名等）",
            expected_behavior="SUT解释必要性后再次请求",
            description="信息缺失：用户拒答必要信息",
        ))

        # --- T09: 开车挂断/繁忙继续 (L2) ---
        has_driving = any("开车" in safe_attr(c, "raw", "") for c in instruction.constraints)
        has_busy = any("忙" in safe_attr(c, "raw", "") for c in instruction.constraints)
        if has_driving:
            cases.append(TestCase(
                id=self._cid(inst_id, case_id := case_id + 1),
                type="driving_hangup",
                layer="L2",
                profile=UserProfile(
                    name="开车用户", is_driving=True,
                    cooperation_level=0.5, emotion="neutral",
                    verbosity="short", question_frequency=0.1,
                    distraction_level=0.0,
                ),
                trigger_turn=1,
                user_action="说'我在开车'",
                expected_behavior="SUT说'那我稍后再打'后挂断",
                description="开车挂断：用户在开车",
            ))
        if has_busy:
            cases.append(TestCase(
                id=self._cid(inst_id, case_id := case_id + 1),
                type="busy_continue",
                layer="L2",
                profile=self._get_cooperative(profiles),
                trigger_turn=1,
                user_action="说'我很忙'",
                expected_behavior="SUT说'就1分钟，保证简短'后继续",
                description="繁忙继续：用户说很忙",
            ))

        # --- T10: L3 自由对话 (每个画像一条) ---
        for profile in profiles:
            cases.append(TestCase(
                id=self._cid(inst_id, case_id := case_id + 1),
                type="free_form",
                layer="L3",
                profile=profile,
                max_turns=12,
                description=f"L3自由对话：{profile.describe()}",
            ))

        return cases

    def _gen_out_of_scope_questions(self, instruction) -> list[dict]:
        """生成越界问题列表"""
        faq_topics = {f.question[:20] for f in instruction.faq}
        role_words = set(instruction.role.lower().split())
        task_words = set(instruction.task.lower().split())

        default = []
        if "骑" in instruction.task or "配送" in instruction.task:
            default = [
                {"question": "你能给我发个优惠券吗？", "expected": "表示需向同事确认后回电"},
                {"question": "我想投诉你们平台，怎么投诉？", "expected": "表示需向同事确认后回电"},
                {"question": "你们的算法是怎么分单的？", "expected": "表示需向同事确认后回电"},
            ]
        elif "直播" in instruction.task or "课程" in instruction.task:
            default = [
                {"question": "能给我们机构打折吗？", "expected": "不承诺折扣"},
                {"question": "你们公司有多少员工？", "expected": "表示需向同事确认后回电"},
                {"question": "这个功能为什么要收费？", "expected": "表示需向同事确认后回电"},
            ]
        else:
            default = [
                {"question": "能给我发个优惠券吗？", "expected": "表示需向同事确认后回电"},
                {"question": "我要投诉你们！", "expected": "表示需向同事确认后回电"},
            ]

        return default[:2]  # 取前两个

    # -- helpers --
    def _cid(self, prefix: str, n: int) -> str:
        return f"{prefix}_TC{n:03d}"

    def _get_cooperative(self, profiles: list[UserProfile]) -> UserProfile:
        for p in profiles:
            if p.cooperation_level > 0.7:
                return p
        return profiles[0]

    def _get_low_coop(self, profiles: list[UserProfile]) -> UserProfile:
        for p in profiles:
            if p.cooperation_level < 0.3:
                return p
        return profiles[2] if len(profiles) > 2 else profiles[-1]
