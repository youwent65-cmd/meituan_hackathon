from __future__ import annotations

"""Constraints 规则化解析器

将自然语言约束转化为结构化的可检测规则。
"""

import re

from .models import Constraint
from .section_splitter import Section


# 约束模式匹配规则（按优先级排列）
CONSTRAINT_RULES = [
    # 字数/长度限制
    {
        "pattern": re.compile(
            r"(?:每次回复|回复|每轮).{0,15}?(?:控制在|不超过|最多|约)\s*(?:约\s*)?(\d+)\s*[-~～到至]?\s*(\d+)?\s*(?:个)?(?:字|词|字符)",
            re.IGNORECASE,
        ),
        "type": "length_limit",
        "extract": lambda m: {
            "max_chars": int(m.group(2) or m.group(1)),
            "tolerance": 5 if "约" in m.string else 0,
        },
        "is_hard": True,
    },
    # 禁用词
    {
        "pattern": re.compile(
            r"不[说用讲提](?:出)?(.+)",
        ),
        "type": "forbidden_words",
        "extract": lambda m: {
            "words": re.findall(r'[\u201c\u201d"\']+([^\u201c\u201d"\']+)[\u201c\u201d"\']+', m.group(1)),
        },
        "is_hard": True,
    },
    # 禁止承诺/禁止话题
    {
        "pattern": re.compile(
            r"不[能可](?:以)?(?:承诺|答应|保证|给予?|提供)(.+?)(?:[。；;,，]|$)",
        ),
        "type": "forbidden_topic",
        "extract": lambda m: {
            "topic_keywords": re.findall(r"[\u4e00-\u9fff]+", m.group(1)),
            "topic_desc": m.group(1).strip(),
        },
        "is_hard": True,
    },
    # 终止条件: "若/如果...→...挂断/结束"
    {
        "pattern": re.compile(
            r"[若如]果?\s*(.+?)[，,]\s*(.+?(?:挂断|结束)[^。；]*)",
        ),
        "type": "termination_condition",
        "extract": lambda m: {
            "trigger_pattern": m.group(1).strip(),
            "expected_action": m.group(2).strip(),
        },
        "is_hard": True,
    },
    # 条件响应: "若/如果...→...说/回复..."
    {
        "pattern": re.compile(
            r"[若如]果?\s*(.+?)[，,]\s*(?:说|回复|回答|告知)[""\"'](.+?)[""\"']",
        ),
        "type": "conditional_response",
        "extract": lambda m: {
            "trigger_scenario": m.group(1).strip(),
            "expected_script": m.group(2).strip(),
        },
        "is_hard": True,
    },
    # 越界处理
    {
        "pattern": re.compile(
            r"(?:超出|越界|不在|超过).{0,10}(?:职责|范围|能力).{0,20}(?:回复|回答|说)[：:]?\s*[""\"'](.+?)[""\"']",
        ),
        "type": "fallback_response",
        "extract": lambda m: {
            "trigger_scenario": "用户提问超出职责范围",
            "expected_script": m.group(1).strip(),
        },
        "is_hard": True,
    },
    # 避免重复
    {
        "pattern": re.compile(r"避免重复"),
        "type": "no_repeat",
        "extract": lambda m: {"similarity_threshold": 0.8},
        "is_hard": True,
    },
]

# 软约束关键词（无法程序化精确检测）
SOFT_CONSTRAINT_KEYWORDS = [
    "语气", "自然", "口语", "随意", "简短", "风格", "像打电话",
    "过渡语", "暂停", "等待", "频繁给",
]


def extract_constraints(constraint_sections: list[Section]) -> list[Constraint]:
    """从 Constraints 章节提取并规则化约束。"""
    constraints: list[Constraint] = []

    for sec in constraint_sections:
        content = sec.content
        if not content:
            # 标题中可能直接有内容
            colon_match = re.search(r"[：:]\s*$", sec.title)
            if not colon_match:
                continue

        # 按 bullet 或换行分割为单条约束
        raw_constraints = _split_constraints(content or "")

        for raw in raw_constraints:
            constraint = _classify_constraint(raw)
            constraints.append(constraint)

    return constraints


def _split_constraints(content: str) -> list[str]:
    """将约束内容分割为单条约束文本。"""
    items: list[str] = []

    # 尝试按 bullet 分割
    bullets = re.split(r"\n\s*[-*]\s+", "\n" + content)
    for bullet in bullets:
        bullet = bullet.strip()
        if bullet:
            items.append(bullet)

    # 如果没有 bullet，按换行分割
    if not items:
        for line in content.split("\n"):
            line = line.strip()
            if line:
                items.append(line)

    return items


def _classify_constraint(raw_text: str) -> Constraint:
    """对单条约束进行分类和参数提取。"""
    # 预处理：去掉 Markdown 加粗标记，便于正则匹配
    clean_text = re.sub(r"\*{1,2}", "", raw_text)

    # 先尝试硬约束模式匹配
    for rule in CONSTRAINT_RULES:
        match = rule["pattern"].search(clean_text)
        if match:
            return Constraint(
                raw=raw_text,
                constraint_type=rule["type"],
                params=rule["extract"](match),
                is_hard=rule["is_hard"],
            )

    # 检查是否为软约束
    is_soft = any(kw in raw_text for kw in SOFT_CONSTRAINT_KEYWORDS)
    if is_soft:
        return Constraint(
            raw=raw_text,
            constraint_type="style",
            params={"style_desc": raw_text},
            is_hard=False,
        )

    # 无法分类的约束，标记为 generic
    return Constraint(
        raw=raw_text,
        constraint_type="generic",
        params={"desc": raw_text},
        is_hard=False,
    )
