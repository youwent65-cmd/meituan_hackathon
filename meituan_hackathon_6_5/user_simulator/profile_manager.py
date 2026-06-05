from __future__ import annotations

"""用户画像管理器 - 生成和管理多种用户画像配置"""

from .models import UserProfile, safe_attr


class ProfileManager:
    """为每条指令生成多样化的用户画像组合"""

    def __init__(self):
        self._default_profiles = [
            UserProfile(
                name="标准用户",
                identity="外卖骑手",
                cooperation_level=0.9,
                emotion="neutral",
                verbosity="normal",
                question_frequency=0.1,
                distraction_level=0.0,
            ),
            UserProfile(
                name="急躁用户",
                identity="外卖骑手",
                cooperation_level=0.5,
                emotion="impatient",
                verbosity="short",
                question_frequency=0.3,
                distraction_level=0.1,
            ),
            UserProfile(
                name="挑剔用户",
                identity="外卖骑手",
                cooperation_level=0.2,
                emotion="angry",
                verbosity="long",
                question_frequency=0.7,
                distraction_level=0.5,
            ),
            UserProfile(
                name="困惑用户",
                identity="外卖骑手",
                cooperation_level=0.6,
                emotion="confused",
                verbosity="normal",
                question_frequency=0.8,
                distraction_level=0.2,
            ),
            UserProfile(
                name="合作的开心用户",
                identity="外卖骑手",
                cooperation_level=0.85,
                emotion="happy",
                verbosity="short",
                question_frequency=0.1,
                distraction_level=0.1,
            ),
            UserProfile(
                name="开车的用户",
                identity="外卖骑手",
                cooperation_level=0.7,
                emotion="neutral",
                verbosity="short",
                question_frequency=0.1,
                distraction_level=0.0,
                is_driving=True,
            ),
            UserProfile(
                name="索要优惠的用户",
                identity="机构负责人",
                cooperation_level=0.4,
                emotion="neutral",
                verbosity="normal",
                question_frequency=0.5,
                distraction_level=0.3,
                has_special_request=True,
            ),
            UserProfile(
                name="拒绝的用户",
                identity="外卖骑手",
                cooperation_level=0.1,
                emotion="angry",
                verbosity="long",
                question_frequency=0.5,
                distraction_level=0.6,
            ),
        ]

    def generate_profiles(
        self,
        instruction: "ParsedInstruction",
        num_profiles: int = 5,
    ) -> list[UserProfile]:
        """根据指令生成合适的用户画像列表

        Args:
            instruction: 解析后的结构化指令
            num_profiles: 需要的画像数量

        Returns:
            画像列表
        """
        profiles = []

        # 从 instruction 提取变量来定制画像身份
        rider_name = "用户"
        identity = "用户"
        for v in instruction.variables:
            v_name = safe_attr(v, "name", "")
            if isinstance(v_name, str) and ("rider" in v_name.lower() or "姓名" in v_name):
                rider_name = v_name

        # 根据 task 内容调整身份描述
        task_lower = instruction.task.lower() if instruction.task else ""
        if "骑" in task_lower or "配送" in task_lower or "飞毛腿" in task_lower:
            identity = "外卖骑手"
        elif "课程" in task_lower or "直播" in task_lower or "培训" in task_lower:
            identity = "机构负责人"
        elif "客服" in task_lower:
            identity = "咨询用户"

        # 1. 标准配合用户 (Happy Path)
        profiles.append(UserProfile(
            name=rider_name if rider_name != "用户" else "标准用户",
            identity=identity,
            cooperation_level=0.9,
            emotion="neutral",
            verbosity="normal",
            question_frequency=0.1,
            distraction_level=0.0,
        ))

        # 2. 急躁用户
        profiles.append(UserProfile(
            name=rider_name if rider_name != "用户" else "急躁用户",
            identity=identity,
            cooperation_level=0.5,
            emotion="impatient",
            verbosity="short",
            question_frequency=0.3,
            distraction_level=0.1,
        ))

        # 3. 低配合/挑剔用户
        profiles.append(UserProfile(
            name="挑剔用户",
            identity=identity,
            cooperation_level=0.2,
            emotion="angry",
            verbosity="long",
            question_frequency=0.7,
            distraction_level=0.5,
        ))

        # 4. 困惑用户
        profiles.append(UserProfile(
            name="困惑用户",
            identity=identity,
            cooperation_level=0.6,
            emotion="confused",
            verbosity="normal",
            question_frequency=0.8,
            distraction_level=0.2,
        ))

        # 5. 特殊场景画像（根据指令约束定制）
        special_profile = self._generate_contextual_profile(instruction)
        if special_profile:
            special_profile.identity = identity
            profiles.append(special_profile)

        return profiles[:max(num_profiles, len(profiles))]

    def _generate_contextual_profile(
        self,
        instruction: "ParsedInstruction",
    ) -> UserProfile:
        """根据指令中的约束条件，生成上下文匹配的特殊画像"""
        has_driving_ct = any(
            "开车" in safe_attr(c, "raw", "") for c in instruction.constraints
        )
        has_quota_ct = any(
            "优惠" in safe_attr(c, "raw", "") or "折扣" in safe_attr(c, "raw", "") or "券" in safe_attr(c, "raw", "")
            for c in instruction.constraints
        )
        has_reject_ct = any(
            "拒绝" in safe_attr(c, "raw", "") or "挂断" in safe_attr(c, "raw", "")
            for c in instruction.constraints
        )

        if has_driving_ct:
            return UserProfile(
                name="开车中的用户",
                cooperation_level=0.6,
                emotion="neutral",
                verbosity="short",
                question_frequency=0.1,
                distraction_level=0.0,
                is_driving=True,
            )
        elif has_quota_ct:
            return UserProfile(
                name="索要优惠的用户",
                cooperation_level=0.4,
                emotion="neutral",
                verbosity="normal",
                question_frequency=0.5,
                distraction_level=0.3,
                has_special_request=True,
            )
        elif has_reject_ct:
            return UserProfile(
                name="拒绝沟通的用户",
                cooperation_level=0.1,
                emotion="angry",
                verbosity="short",
                question_frequency=0.2,
                distraction_level=0.8,
            )
        else:
            return UserProfile(
                name="合作的开朗用户",
                cooperation_level=0.85,
                emotion="happy",
                verbosity="short",
                question_frequency=0.1,
                distraction_level=0.1,
            )
