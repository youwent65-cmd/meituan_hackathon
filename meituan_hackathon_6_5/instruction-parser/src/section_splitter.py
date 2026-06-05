from __future__ import annotations

"""Markdown 章节分割与字段路由

将原始 Markdown 文本按标题分割为章节，并将每个章节路由到对应的字段解析器。
"""

import re
from dataclasses import dataclass, field


# 字段匹配模式：支持中英文、多种写法
FIELD_PATTERNS: dict[str, list[str]] = {
    "role": [r"role", r"角色"],
    "task": [r"task", r"任务", r"目标"],
    "opening": [r"opening\s*line", r"开场白", r"开场"],
    "flow": [r"call\s*flow", r"conversation\s*flow", r"对话流程", r"流程"],
    "faq": [r"knowledge\s*points?", r"faq", r"知识", r"常见问题"],
    "constraints": [r"constraints?", r"约束", r"限制", r"规则"],
}


@dataclass
class Section:
    """一个 Markdown 章节"""
    title: str  # 原始标题文本
    level: int  # 标题层级 (1-6)
    content: str  # 标题下的内容（不含子标题）
    children: list["Section"] = field(default_factory=list)
    field_type: str = "unknown"  # 路由后的字段类型


def split_sections(markdown_text: str) -> list[Section]:
    """将 Markdown 文本按标题分割为层级化的章节树。"""
    lines = markdown_text.split("\n")
    sections: list[Section] = []
    stack: list[Section] = []  # 用栈维护层级关系

    current_content_lines: list[str] = []
    current_section: Section | None = None

    heading_pattern = re.compile(r"^(#{1,6})\s+(.+)$")

    for line in lines:
        match = heading_pattern.match(line.strip())
        if match:
            # 保存之前积累的内容
            if current_section is not None:
                current_section.content = "\n".join(current_content_lines).strip()
            elif current_content_lines:
                pass  # 标题前的内容忽略

            level = len(match.group(1))
            title = match.group(2).strip()

            new_section = Section(title=title, level=level, content="")
            current_content_lines = []
            current_section = new_section

            # 维护层级关系
            while stack and stack[-1].level >= level:
                stack.pop()

            if stack:
                stack[-1].children.append(new_section)
            else:
                sections.append(new_section)

            stack.append(new_section)
        else:
            current_content_lines.append(line)

    # 保存最后一个章节的内容
    if current_section is not None:
        current_section.content = "\n".join(current_content_lines).strip()

    return sections


def route_field(title: str) -> str:
    """根据标题文本模糊匹配字段类型。"""
    # 去掉标题中的冒号及其后内容（如 "Role: XXX" 只匹配 "Role"）
    title_for_match = re.split(r"[：:]", title)[0].strip()

    for field_name, patterns in FIELD_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, title_for_match, re.IGNORECASE):
                return field_name
    return "unknown"


def parse_sections(markdown_text: str) -> dict[str, list[Section]]:
    """解析 Markdown 并按字段类型分组返回。

    Returns:
        dict: key 为字段类型 (role/task/flow/faq/constraints/unknown)，
              value 为匹配到该类型的 Section 列表
    """
    sections = split_sections(markdown_text)
    result: dict[str, list[Section]] = {}

    def classify(section_list: list[Section]):
        for sec in section_list:
            field_type = route_field(sec.title)
            sec.field_type = field_type
            result.setdefault(field_type, []).append(sec)
            # 递归处理子章节（但如果父章节已经是 flow，子章节归属于 flow）
            if sec.children:
                if field_type == "flow":
                    # flow 的子章节不再独立路由，保留在 children 中
                    for child in sec.children:
                        child.field_type = "flow_child"
                else:
                    classify(sec.children)

    classify(sections)
    return result
