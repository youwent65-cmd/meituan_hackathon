from __future__ import annotations

"""L1 规则引擎 - 流程驱动模拟，基于 Call Flow 状态机"""

import random
from typing import Optional

from ..models import UserProfile
from ..context_tracker import DialogueContext


class FlowGraph:
    """将 Call Flow 解析为有向状态图"""

    def __init__(self, flow_steps: list):
        self.steps = {}
        self.entry_step = None
        self.exit_steps = []
        self._build(flow_steps)

    def _build(self, flow_steps: list):
        if not flow_steps:
            return
        for step in flow_steps:
            step_id = step.get("id", str(step.id) if hasattr(step, "id") else "")
            desc = step.get("description", str(step) if hasattr(step, "description") else str(step))
            conditions = step.get("conditions", []) if isinstance(step, dict) else (
                step.conditions if hasattr(step, "conditions") else []
            )
            default_next = step.get("default_next") if isinstance(step, dict) else (
                step.default_next if hasattr(step, "default_next") else None
            )
            node_type = step.get("node_type", "action") if isinstance(step, dict) else (
                step.node_type if hasattr(step, "node_type") else "action"
            )

            self.steps[step_id] = {
                "id": step_id,
                "description": desc,
                "node_type": node_type,
                "conditions": conditions,
                "default_next": default_next,
                "is_required": step.get("is_required", True) if isinstance(step, dict) else (
                    step.is_required if hasattr(step, "is_required") else True
                ),
            }

            # 入口/出口判断
            if self.entry_step is None:
                self.entry_step = step_id
            if not default_next and not conditions:
                self.exit_steps.append(step_id)

    def get_step(self, step_id: str) -> Optional[dict]:
        return self.steps.get(step_id)

    def get_next_step(self, current_id: str, condition_index: int = 0) -> Optional[str]:
        """获取下一步的ID"""
        step = self.steps.get(current_id)
        if not step:
            return None

        conditions = step["conditions"]
        if conditions and condition_index < len(conditions):
            cond = conditions[condition_index]
            return cond.get("next_step") if isinstance(cond, dict) else (
                cond.next_step if hasattr(cond, "next_step") else None
            )

        return step["default_next"]

    def get_required_steps(self) -> list[str]:
        return [sid for sid, s in self.steps.items() if s["is_required"] and s["node_type"] not in ("info",)]


class L1RuleEngine:
    """L1 层：基于规则引擎的流程驱动模拟

    严格按 Call Flow 步骤生成符合预期的用户回复。
    覆盖 Happy Path 和分支路径。
    """

    # 预置回复模板库 — 每组6-8条，避免机械重复
    REPLY_TEMPLATES = {
        "confirm_identity": [
            "对，是我。",
            "嗯，我就是，有什么事吗？",
            "是的，你说吧。",
            "没错，我是。",
            "对的对的，您请讲。",
            "是我本人，怎么啦？",
            "嗯嗯我就是，您是哪位？",
            "对，有什么事直接说吧。",
        ],
        "agree_continue": [
            "好的，你继续说吧。",
            "行，你说。",
            "嗯嗯，然后呢？",
            "知道了，接着说。",
            "好嘞，您讲。",
            "嗯可以，往下说吧。",
            "行吧，我听着呢。",
            "哦这样啊，那你继续。",
        ],
        "understand": [
            "明白了。",
            "了解了。",
            "这样啊，知道了。",
            "好的，清楚了。",
            "哦原来是这么回事。",
            "懂了懂了。",
            "嗯我大概明白了。",
            "行，我清楚了。",
        ],
        "ask_question": [
            "我有个问题想问你，{question}",
            "那{question}怎么办呢？",
            "对了，{question}是什么情况？",
            "我想了解一下，{question}",
            "还有个事，{question}",
            "那我想问一下，{question}？",
            "对了，你刚才说的{question}能再解释下吗？",
        ],
        "positive_response": [
            "好的，没问题。",
            "可以，我会注意的。",
            "谢谢提醒。",
            "嗯，我会的。",
            "行，就按你说的来。",
            "没问题，我记下了。",
            "好的好的，知道了。",
            "行，这样安排我没意见。",
        ],
        "confirm_end": [
            "好的，没有其他问题了。",
            "明白了，谢谢。",
            "嗯嗯，再见。",
            "好，那就这样，拜拜。",
            "行，谢谢您啊，再见。",
            "没问题了，辛苦啦。",
            "好了好了，就这样吧。",
            "嗯，您忙吧，我挂了。",
        ],
        "brief_ack": [
            "嗯。",
            "好。",
            "行。",
            "哦。",
            "嗯嗯。",
            "是。",
            "对。",
            "呃。",
        ],
        "confused": [
            "什么意思？没太听懂。",
            "你能再说一遍吗？",
            "等一下，我不太明白。",
            "这个……是什么意思？",
            "诶？我没听清楚。",
            "啊？你说的我没跟上。",
            "慢点说，我没反应过来。",
            "啥意思？能换个说法吗？",
        ],
    }

    def __init__(self, flow_graph: FlowGraph):
        self.graph = flow_graph
        self.current_step = flow_graph.entry_step
        self.completed_steps: set = set()
        self.step_turn_count: dict = {}

    def generate_reply(
        self,
        sut_message: str,
        context: DialogueContext,
        profile: UserProfile,
    ) -> str:
        """根据当前步骤和上下文生成用户回复"""
        step = self.graph.get_step(self.current_step)
        if not step:
            return self._fallback_reply(context)

        step_id = step["id"]
        self.step_turn_count[step_id] = self.step_turn_count.get(step_id, 0) + 1

        # 判断应回复的模板类型
        node_type = step["node_type"]

        if node_type == "branch":
            reply = self._handle_branch_step(step, context, profile)
        elif node_type in ("action", "guide"):
            reply = self._handle_action_step(step, context, profile)
        elif node_type == "info":
            reply = self._random_pick("brief_ack")
        elif node_type == "terminal":
            reply = self._random_pick("confirm_end")
        else:
            reply = self._random_pick("agree_continue")

        # 检查是否应前进到下一步
        self._maybe_advance_step(step, context)

        # 根据画像调整
        reply = self._apply_profile_modifiers(reply, profile)

        return reply

    def _handle_branch_step(
        self,
        step: dict,
        context: DialogueContext,
        profile: UserProfile,
    ) -> str:
        """处理分支步骤：选择一条分支路径的回复"""
        conditions = step["conditions"]
        if not conditions:
            return self._random_pick("agree_continue")

        # 高配合度用户 → 选择第一个匹配条件（通常是最佳路径）
        if profile.cooperation_level > 0.5:
            cond = conditions[0]
            trigger = cond.get("trigger", "") if isinstance(cond, dict) else str(cond)
            if "是" in trigger or "已知情" in trigger or "已显示" in trigger:
                return self._random_pick("agree_continue")
            elif "不" in trigger or "未" in trigger:
                return f"不是，{trigger}。"
            else:
                return self._random_pick("agree_continue")
        else:
            # 低配合度 → 选负面/对抗分支
            cond = conditions[-1]
            trigger = cond.get("trigger", "") if isinstance(cond, dict) else str(cond)
            return f"不太清楚，你说的是什么？"

    def _handle_action_step(
        self,
        step: dict,
        context: DialogueContext,
        profile: UserProfile,
    ) -> str:
        """处理 action 步骤"""
        desc = step["description"]
        turn_count = self.step_turn_count.get(step["id"], 1)

        # 第一轮：给确认/同意的回复推进流程
        if turn_count <= 1:
            return self._random_pick("agree_continue")
        elif profile.emotion == "confused" and "问" in desc:
            # 困惑用户在提问步骤可能卡住
            return self._random_pick("confused")
        else:
            return self._random_pick("positive_response")

    def _maybe_advance_step(self, step: dict, context: DialogueContext):
        """判断是否推进到下一步"""
        step_id = step["id"]
        turns_here = self.step_turn_count.get(step_id, 0)

        # action/info 步骤：1-2 轮后自动前进
        if step["node_type"] in ("action", "info", "guide") and turns_here >= 2:
            self._advance(step)

        # branch 步骤：1 轮后前进
        if step["node_type"] == "branch" and turns_here >= 1:
            self._advance(step)

    def _advance(self, current_step: dict):
        """前进到下一步（按 default_next 或第一个条件分支）"""
        self.completed_steps.add(current_step["id"])
        next_id = self.graph.get_next_step(current_step["id"], condition_index=0)
        if next_id and next_id in self.graph.steps:
            self.current_step = next_id
        elif current_step["default_next"]:
            self.current_step = current_step["default_next"]

    def _fallback_reply(self, context: DialogueContext) -> str:
        return self._random_pick("brief_ack")

    def _apply_profile_modifiers(self, reply: str, profile: UserProfile) -> str:
        if profile.verbosity == "short":
            from ..models import truncate_at_sentence
            reply = truncate_at_sentence(reply, 15)
        if profile.emotion == "angry":
            prefixes = ["哎，", "啧，", "我说，", ""]
            reply = random.choice(prefixes) + reply
        if profile.emotion == "impatient":
            if random.random() < 0.4:
                reply = "快点说吧，" + reply
        return reply

    @staticmethod
    def _random_pick(template_key: str) -> str:
        templates = L1RuleEngine.REPLY_TEMPLATES.get(template_key, ["嗯。"])
        return random.choice(templates)

    def is_complete(self) -> bool:
        return self.current_step in self.graph.exit_steps

    def reset(self):
        self.current_step = self.graph.entry_step
        self.completed_steps.clear()
        self.step_turn_count.clear()
