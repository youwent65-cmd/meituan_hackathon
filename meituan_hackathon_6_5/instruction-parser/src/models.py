"""数据模型定义 - 指令解析器的输入输出结构"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Variable:
    name: str
    raw: str  # 原始文本形式，如 ${rider_name} 或 **X 单**
    var_type: str  # "placeholder" | "bold_marker"


@dataclass
class Condition:
    trigger: str  # 触发条件的自然语言描述
    action: Optional[str] = None  # 满足条件时模型应执行的动作
    next_step: Optional[str] = None  # 满足条件时跳转到哪一步
    is_terminal: bool = False  # 是否导致对话结束


@dataclass
class FlowNode:
    id: str  # "1", "2", "3.1", "4.1"
    description: str  # 步骤描述
    node_type: str = "action"  # action / branch / info / guide / terminal
    parent_id: Optional[str] = None  # 子步骤的父节点
    reference_script: Optional[str] = None  # 参考话术
    conditions: list[Condition] = field(default_factory=list)
    default_next: Optional[str] = None  # 无条件时的默认下一步
    detection_hint: Optional[str] = None  # 评测引擎用：如何判断此步骤被执行
    is_required: bool = True  # 是否为必经步骤


@dataclass
class FAQItem:
    question: str
    answer: str
    source: str = "faq_section"  # "faq_section" | "flow_embedded"


@dataclass
class Constraint:
    raw: str  # 原始自然语言文本
    constraint_type: str  # length_limit / forbidden_words / forbidden_topic / ...
    params: dict = field(default_factory=dict)
    is_hard: bool = True  # 硬约束(可程序化检测) vs 软约束(需LLM判断)
    scope: str = "global"  # global / step_specific


@dataclass
class ParsedInstruction:
    """解析后的结构化指令对象"""
    role: str = ""
    task: str = ""
    opening: str = ""
    variables: list[Variable] = field(default_factory=list)
    flow_steps: list[FlowNode] = field(default_factory=list)
    faq: list[FAQItem] = field(default_factory=list)
    constraints: list[Constraint] = field(default_factory=list)
    raw_text: str = ""  # 保留原始文本

    def to_dict(self) -> dict:
        """转为可序列化的字典"""
        from dataclasses import asdict
        return asdict(self)
