from __future__ import annotations

"""上下文追踪器 - 维护对话状态和执行栈"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DialogueContext:
    """对话上下文：跟踪当前状态、历史步骤等"""
    instruction_id: str = ""
    current_step_id: Optional[str] = None
    completed_steps: set = field(default_factory=set)
    attempted_steps: set = field(default_factory=set)
    conversation_history: list[dict] = field(default_factory=list)
    user_profile_desc: str = ""
    task: str = ""
    role: str = ""
    opening: str = ""

    # 统计
    total_user_turns: int = 0
    total_sut_turns: int = 0
    consecutive_no_progress: int = 0
    faq_triggered: list[str] = field(default_factory=list)
    constraints_violated: list[str] = field(default_factory=list)

    # 对抗行为追踪
    adversarial_triggered: bool = False
    current_strategy: str = ""

    def update(self, user_msg: str, sut_msg: str, current_step: Optional[str] = None):
        """每轮对话后更新上下文"""
        self.conversation_history.append({"role": "user", "content": user_msg})
        self.conversation_history.append({"role": "sut", "content": sut_msg})
        self.total_user_turns += 1
        self.total_sut_turns += 1

        # 步骤进展跟踪
        if current_step and current_step != self.current_step_id:
            self.completed_steps.add(self.current_step_id)
            self.current_step_id = current_step
            self.consecutive_no_progress = 0
        else:
            self.consecutive_no_progress += 1

        self.attempted_steps.add(current_step)

    def get_last_sut_msg(self) -> str:
        for h in reversed(self.conversation_history):
            if h["role"] == "sut":
                return h["content"]
        return ""

    def get_last_user_msg(self) -> str:
        for h in reversed(self.conversation_history):
            if h["role"] == "user":
                return h["content"]
        return ""

    def get_history_text(self, max_turns: int = 10) -> str:
        """获取最近 N 轮对话历史的文本表示"""
        recent = self.conversation_history[-(max_turns * 2):]
        lines = []
        for h in recent:
            role = "客服" if h["role"] == "sut" else "用户"
            lines.append(f"{role}: {h['content']}")
        return "\n".join(lines)

    def is_no_progress(self) -> bool:
        return self.consecutive_no_progress >= 3
