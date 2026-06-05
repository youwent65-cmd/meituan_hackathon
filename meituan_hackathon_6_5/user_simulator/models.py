from __future__ import annotations

"""数据模型定义 - 用户模拟器的核心数据结构"""

import re
from dataclasses import dataclass, field
from typing import Optional


def safe_attr(obj, key, default=None):
    """安全获取 dict 或 object 的属性值"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


_SENTENCE_BOUNDARY = re.compile(r"[。！？；\n]")

def truncate_at_sentence(text: str, max_chars: int) -> str:
    """在句子边界处截断文本，避免中途截断导致语义不完整。

    在 max_chars 范围内找到最后一个句子边界（。！？；\\n）进行截断。
    如果找不到边界，则退回字符截断。
    """
    if len(text) <= max_chars:
        return text

    # 在 max_chars 范围内找最后一个句子边界
    substring = text[:max_chars]
    matches = list(_SENTENCE_BOUNDARY.finditer(substring))
    if matches:
        last_boundary = matches[-1].end()
        if last_boundary >= max_chars * 0.5:  # 至少保留一半长度
            return text[:last_boundary]

    # 找不到合适边界时，尽量在标点后截断
    for sep in ["；", "，", "、", " ", "…"]:
        idx = substring.rfind(sep)
        if idx > max_chars * 0.5:
            return text[:idx + 1]

    return text[:max_chars]


@dataclass
class UserProfile:
    """用户画像：控制用户行为的多维度参数"""
    name: str = "用户"
    identity: str = "接听电话的用户"

    # 行为参数
    cooperation_level: float = 0.9  # 配合度 0.0 ~ 1.0
    verbosity: str = "normal"       # "short" / "normal" / "long"
    question_frequency: float = 0.1  # 反问/提问概率 0.0 ~ 1.0
    emotion: str = "neutral"        # "neutral" / "happy" / "impatient" / "angry" / "confused"
    distraction_level: float = 0.0  # 跑题概率 0.0 ~ 1.0

    # 场景特殊标记
    is_driving: bool = False
    has_special_request: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "identity": self.identity,
            "cooperation_level": self.cooperation_level,
            "verbosity": self.verbosity,
            "question_frequency": self.question_frequency,
            "emotion": self.emotion,
            "distraction_level": self.distraction_level,
            "is_driving": self.is_driving,
            "has_special_request": self.has_special_request,
        }

    def describe(self) -> str:
        cooperation_label = (
            "高" if self.cooperation_level > 0.7
            else "中" if self.cooperation_level > 0.3
            else "低"
        )
        emotion_cn = {
            "neutral": "平静", "happy": "开心", "impatient": "急躁",
            "angry": "生气", "confused": "困惑"
        }.get(self.emotion, "平静")
        return f"配合度{cooperation_label}/{emotion_cn}/说话{self.verbosity}"


@dataclass
class TestCase:
    """测试用例：用户画像 + 测试维度 + 模拟层次"""
    id: str = ""
    type: str = ""                   # "happy_path" / "faq_trigger" / "out_of_scope" / ...
    layer: str = "L1"               # "L1" / "L2" / "L3"
    profile: Optional[UserProfile] = None
    description: str = ""

    # L2/L3 特定参数
    trigger_turn: int = 0           # 在第几轮触发对抗行为
    trigger_question: str = ""      # 对抗触发的问题（FAQ触发/越界问题）
    expected_answer: str = ""       # 期望的答案
    expected_behavior: str = ""     # 期望的 SUT 行为
    repeat_question: str = ""       # 重复追问的问题
    repeat_count: int = 1           # 重复次数
    max_turns: int = 15             # 最大对话轮次
    user_action: str = ""           # 用户的具体行为描述

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "layer": self.layer,
            "profile": self.profile.to_dict() if self.profile else None,
            "description": self.description,
            "trigger_turn": self.trigger_turn,
            "trigger_question": self.trigger_question,
            "expected_answer": self.expected_answer,
            "expected_behavior": self.expected_behavior,
            "repeat_question": self.repeat_question,
            "repeat_count": self.repeat_count,
            "max_turns": self.max_turns,
            "user_action": self.user_action,
        }


@dataclass
class Turn:
    """单轮对话记录"""
    turn_number: int
    role: str                    # "SUT" | "USER"
    content: str
    timestamp: float = 0.0
    context_step: Optional[str] = None   # 当前处于流程的哪一步
    triggered_constraint: Optional[str] = None  # 此轮触发了哪条约束的检测

    def to_dict(self) -> dict:
        return {
            "turn_number": self.turn_number,
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "context_step": self.context_step,
            "triggered_constraint": self.triggered_constraint,
        }


@dataclass
class DialogueRecord:
    """完整的对话记录"""
    instruction_id: str = ""
    test_case_id: str = ""
    test_dimension: str = ""          # happy_path / faq_trigger / out_of_scope ...
    layer_used: str = ""              # L1 / L2 / L3
    profile: Optional[UserProfile] = None
    turns: list[Turn] = field(default_factory=list)
    end_reason: str = ""              # 结束原因
    total_turns: int = 0
    metadata: dict = field(default_factory=dict)
    created_at: str = ""

    def add_turn(self, role: str, content: str, **kwargs):
        turn_num = len(self.turns)
        self.turns.append(Turn(
            turn_number=turn_num,
            role=role,
            content=content,
            **kwargs
        ))

    def get_sut_messages(self) -> list[str]:
        return [t.content for t in self.turns if t.role == "SUT"]

    def get_user_messages(self) -> list[str]:
        return [t.content for t in self.turns if t.role == "USER"]

    def conversation_text(self) -> str:
        lines = []
        for t in self.turns:
            label = "SUT" if t.role == "SUT" else "用户"
            lines.append(f"[{label}] {t.content}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "instruction_id": self.instruction_id,
            "test_case_id": self.test_case_id,
            "test_dimension": self.test_dimension,
            "layer_used": self.layer_used,
            "profile": self.profile.to_dict() if self.profile else None,
            "turns": [t.to_dict() for t in self.turns],
            "end_reason": self.end_reason,
            "total_turns": self.total_turns,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }


@dataclass
class SimulationConfig:
    """模拟器全局配置"""
    max_turns: int = 15                # 最大对话轮次
    no_progress_limit: int = 3         # 连续无进展轮次上限
    temperature: float = 0.8           # LLM 温度参数

    # SUT 配置
    sut_provider: str = "mock"         # "mock" / "api"
    sut_api_url: str = ""
    sut_api_key: str = ""

    # L3 LLM 配置
    llm_provider: str = "mock"         # "mock" / "anthropic" / "deepseek" / "openai"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str = ""
    llm_base_url: str = ""             # 自定义 API 端点

    # 降级配置
    fallback_enabled: bool = True
    llm_timeout: int = 30

    def to_dict(self) -> dict:
        return {
            "max_turns": self.max_turns,
            "no_progress_limit": self.no_progress_limit,
            "temperature": self.temperature,
            "sut_provider": self.sut_provider,
            "llm_provider": self.llm_provider,
            "llm_model": self.llm_model,
            "fallback_enabled": self.fallback_enabled,
        }
