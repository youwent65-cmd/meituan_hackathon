from __future__ import annotations

"""Call Flow DAG 解析器

将对话流程文本解析为有向图结构，支持：
- 线性步骤序列
- 条件分支 (若...→...)
- 子步骤嵌套
- 隐式/显式跳转
"""

import re

from .models import FlowNode, Condition
from .section_splitter import Section


# 条件分支模式
CONDITION_PATTERNS = [
    # "若/如果 + 条件 → 动作/跳转"
    re.compile(r"[若如]果?\s*(.+?)\s*[→➜➡]\s*(.+)"),
    # "- 条件 → 动作" (无若字，在 bullet 中)
    re.compile(r"^(.+?)\s*[→➜➡]\s*(.+)"),
]

# 跳转模式: "进入第N步" / "进入Step N"
JUMP_PATTERN = re.compile(r"进入第?\s*(\d+)\s*步|进入\s*Step\s*(\d+)", re.IGNORECASE)

# 步骤编号模式
STEP_NUMBER_PATTERN = re.compile(r"^(?:Step\s*)?(\d+(?:\.\d+)?)[.、:：)\s]\s*(.+)", re.IGNORECASE)


def parse_flow(flow_sections: list[Section]) -> list[FlowNode]:
    """解析 Call Flow 章节为 FlowNode 列表。"""
    if not flow_sections:
        return []

    main_section = flow_sections[0]
    nodes: list[FlowNode] = []

    # 策略：先尝试从子章节解析（指令2的结构），再尝试从内容解析（指令1的结构）
    if main_section.children:
        nodes = _parse_from_children(main_section)
    elif main_section.content:
        nodes = _parse_from_content(main_section.content)

    # 后处理：建立默认跳转关系
    _build_default_transitions(nodes)

    return nodes


def _parse_from_content(content: str) -> list[FlowNode]:
    """从纯文本内容解析步骤（适用于指令1的扁平列表格式）。"""
    nodes: list[FlowNode] = []
    lines = content.split("\n")

    current_step_lines: list[str] = []
    current_id: str | None = None
    current_desc: str = ""

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # 尝试匹配步骤编号
        step_match = STEP_NUMBER_PATTERN.match(stripped)
        if step_match:
            # 保存之前的步骤
            if current_id is not None:
                node = _build_node_from_lines(current_id, current_desc, current_step_lines)
                nodes.append(node)

            current_id = step_match.group(1)
            current_desc = step_match.group(2).strip()
            current_step_lines = []
        else:
            current_step_lines.append(stripped)

    # 保存最后一个步骤
    if current_id is not None:
        node = _build_node_from_lines(current_id, current_desc, current_step_lines)
        nodes.append(node)

    return nodes


def _parse_from_children(main_section: Section) -> list[FlowNode]:
    """从子章节结构解析步骤（适用于指令2的层级结构）。"""
    nodes: list[FlowNode] = []

    for child in main_section.children:
        # 从标题提取步骤编号和描述
        title = child.title
        step_match = STEP_NUMBER_PATTERN.match(title)
        if step_match:
            step_id = step_match.group(1)
            step_desc = step_match.group(2).strip()
        else:
            # 标题没有编号，用序号
            step_id = str(len(nodes) + 1)
            step_desc = title

        # 解析内容中的条件分支和参考话术
        conditions = []
        reference_script = None
        sub_content_lines = []

        if child.content:
            conditions, reference_script, sub_content_lines = _parse_step_content(
                child.content
            )

        # 确定节点类型
        node_type = _determine_node_type(step_desc, conditions, child)

        node = FlowNode(
            id=step_id,
            description=step_desc,
            node_type=node_type,
            reference_script=reference_script,
            conditions=conditions,
            detection_hint=_generate_detection_hint(step_desc, reference_script),
        )
        nodes.append(node)

        # 处理子步骤
        if child.children:
            for sub_child in child.children:
                sub_node = _parse_sub_step(sub_child, parent_id=step_id)
                if sub_node:
                    nodes.append(sub_node)

    return nodes


def _parse_sub_step(section: Section, parent_id: str) -> FlowNode | None:
    """解析子步骤章节。"""
    title = section.title
    step_match = STEP_NUMBER_PATTERN.match(title)
    if step_match:
        step_id = step_match.group(1)
        step_desc = step_match.group(2).strip()
    else:
        step_id = f"{parent_id}.x"
        step_desc = title

    conditions = []
    reference_script = None
    if section.content:
        conditions, reference_script, _ = _parse_step_content(section.content)

    node_type = _determine_node_type(step_desc, conditions, section)

    return FlowNode(
        id=step_id,
        description=step_desc,
        node_type=node_type,
        parent_id=parent_id,
        reference_script=reference_script,
        conditions=conditions,
        detection_hint=_generate_detection_hint(step_desc, reference_script),
        is_required=not bool(conditions),  # 有条件分支的子步骤可能不是必经
    )


def _parse_step_content(content: str) -> tuple[list[Condition], str | None, list[str]]:
    """解析步骤内容，提取条件分支和参考话术。

    Returns:
        (conditions, reference_script, remaining_lines)
    """
    conditions: list[Condition] = []
    reference_script: str | None = None
    remaining_lines: list[str] = []

    lines = content.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 检测参考话术
        script_match = re.match(r"\*\*参考话术[：:]\*\*\s*(.*)", line)
        if script_match:
            script_text = script_match.group(1).strip()
            # 可能跨多行
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(("**", "##", "#", "- ")):
                script_text += " " + lines[i].strip()
                i += 1
            reference_script = script_text
            continue

        # 检测询问话术
        ask_match = re.match(r"\*\*询问[：:]\*\*\s*(.*)", line)
        if ask_match:
            if reference_script is None:
                reference_script = ask_match.group(1).strip()
            i += 1
            continue

        # 检测条件分支 (bullet 格式)
        bullet_match = re.match(r"^[-*]\s+(.*)", line)
        if bullet_match:
            bullet_content = bullet_match.group(1)
            condition = _try_parse_condition(bullet_content)
            if condition:
                conditions.append(condition)
                i += 1
                continue

        # 非 bullet 行也尝试条件匹配
        if "→" in line or "➜" in line or "➡" in line:
            condition = _try_parse_condition(line)
            if condition:
                conditions.append(condition)
                i += 1
                continue

        remaining_lines.append(line)
        i += 1

    return conditions, reference_script, remaining_lines


def _try_parse_condition(text: str) -> Condition | None:
    """尝试从文本中解析条件分支。"""
    for pattern in CONDITION_PATTERNS:
        match = pattern.match(text)
        if match:
            trigger = match.group(1).strip()
            action_text = match.group(2).strip()

            # 检查是否包含跳转
            jump_match = JUMP_PATTERN.search(action_text)
            next_step = None
            if jump_match:
                next_step = jump_match.group(1) or jump_match.group(2)

            # 检查是否为终止条件
            is_terminal = any(kw in action_text for kw in ["挂断", "结束通话", "结束对话"])

            return Condition(
                trigger=trigger,
                action=action_text if not jump_match else action_text,
                next_step=next_step,
                is_terminal=is_terminal,
            )
    return None


def _build_node_from_lines(step_id: str, desc: str, extra_lines: list[str]) -> FlowNode:
    """从步骤描述和附加行构建 FlowNode。"""
    conditions = []
    for line in extra_lines:
        stripped = line.strip()
        if stripped.startswith(("-", "*")):
            bullet_content = re.sub(r"^[-*]\s+", "", stripped)
            cond = _try_parse_condition(bullet_content)
            if cond:
                conditions.append(cond)

    node_type = "branch" if conditions else "action"
    is_terminal = any(c.is_terminal for c in conditions)
    if is_terminal:
        node_type = "terminal"

    return FlowNode(
        id=step_id,
        description=desc,
        node_type=node_type,
        conditions=conditions,
        detection_hint=_generate_detection_hint(desc, None),
    )


def _determine_node_type(desc: str, conditions: list[Condition], section: Section) -> str:
    """根据步骤特征判断节点类型。"""
    if any(c.is_terminal for c in conditions):
        return "terminal"
    if conditions:
        return "branch"
    # 检查是否为引导操作步骤
    if section.content and re.search(r"^\s*\d+\.\s+", section.content, re.MULTILINE):
        numbered_lines = re.findall(r"^\s*\d+\.\s+", section.content, re.MULTILINE)
        if len(numbered_lines) >= 3:
            return "guide"
    # 检查是否为纯信息节点（如 "3.1 区别"）
    if re.match(r"\d+\.\d+", section.title if hasattr(section, "title") else ""):
        return "info"
    return "action"


def _generate_detection_hint(desc: str, reference_script: str | None) -> str:
    """为步骤生成检测提示，帮助评测引擎判断步骤是否被执行。"""
    # 提取描述中的关键词作为检测线索
    keywords = []
    # 提取引号内的内容
    quoted = re.findall(r"[""\"'](.+?)[""\"']", desc)
    keywords.extend(quoted)
    # 提取【】内的内容
    bracketed = re.findall(r"【(.+?)】", desc)
    keywords.extend(bracketed)

    if reference_script:
        # 从参考话术中提取关键短语
        script_keywords = re.findall(r"[""\"'](.+?)[""\"']", reference_script)
        keywords.extend(script_keywords)

    if keywords:
        return f"关键词检测: {', '.join(keywords[:5])}"
    return f"语义匹配: {desc[:50]}"


def _build_default_transitions(nodes: list[FlowNode]):
    """为没有显式跳转的节点建立默认顺序跳转。"""
    # 只处理顶级节点（无 parent_id 的）
    top_nodes = [n for n in nodes if n.parent_id is None]

    for i, node in enumerate(top_nodes):
        if node.node_type == "terminal":
            continue

        # 如果条件分支中已经有 next_step，不设置 default_next
        has_explicit_jump = any(c.next_step for c in node.conditions)

        if not has_explicit_jump and i + 1 < len(top_nodes):
            node.default_next = top_nodes[i + 1].id
