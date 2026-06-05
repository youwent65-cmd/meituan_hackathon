from __future__ import annotations

"""简单字段提取器 - Role / Task / Opening / 变量识别"""

import re

from .models import Variable
from .section_splitter import Section


def extract_role(sections: list[Section]) -> str:
    """从 Role 章节提取角色描述。"""
    if not sections:
        return ""
    sec = sections[0]
    # 情况1: 标题中直接包含内容 "# Role: XXX"
    colon_match = re.search(r"[：:]\s*(.+)", sec.title)
    if colon_match:
        role_text = colon_match.group(1).strip()
        # 如果 content 也有内容，拼接
        if sec.content:
            role_text += "\n" + sec.content
        return role_text.strip()
    # 情况2: 内容在下一行
    return sec.content.strip()


def extract_task(sections: list[Section]) -> str:
    """从 Task 章节提取任务目标。"""
    if not sections:
        return ""
    sec = sections[0]
    colon_match = re.search(r"[：:]\s*(.+)", sec.title)
    if colon_match:
        task_text = colon_match.group(1).strip()
        if sec.content:
            task_text += "\n" + sec.content
        return task_text.strip()
    return sec.content.strip()


def extract_opening(sections: list[Section]) -> str:
    """从 Opening Line 章节提取开场白。"""
    if not sections:
        return ""
    sec = sections[0]
    colon_match = re.search(r"[：:]\s*(.+)", sec.title)
    if colon_match:
        return colon_match.group(1).strip()
    return sec.content.strip()


def extract_variables(text: str) -> list[Variable]:
    """从文本中识别所有变量占位符。

    支持三种形式:
    1. ${var_name} - 显式占位符
    2. **X 单** 等 - 简单加粗标记的变量（单个大写字母/短词 + 量词单位）
    3. **连续 Y 天** 等 - 复合加粗变量（中文上下文 + 字母变量 + 量词单位）
    """
    variables: list[Variable] = []
    seen_raw = set()
    seen_names = set()

    # 模式1: ${...} 占位符
    for match in re.finditer(r"\$\{([^}]+)\}", text):
        raw = match.group(0)
        name = match.group(1)
        if raw not in seen_raw:
            variables.append(Variable(name=name, raw=raw, var_type="placeholder"))
            seen_raw.add(raw)
            seen_names.add(name)

    # 模式2: **X 单** 简单加粗变量（仅有变量字母+单位，无其他文字）
    # 匹配: 1-3个大写字母/数字 + 可选空格 + 量词单位
    units = r"[单天点元个日次条步分秒]"
    simple_pattern = rf"\*\*([A-Z\d]{{1,3}}\s*{units}+)\*\*"
    for match in re.finditer(simple_pattern, text):
        raw = match.group(0)
        name = match.group(1).strip()
        if raw not in seen_raw:
            variables.append(Variable(name=name, raw=raw, var_type="bold_marker"))
            seen_raw.add(raw)
            seen_names.add(name)

    # 模式3: **中文上下文 + 变量字母 + 单位** 复合加粗标记
    # 如 **连续 Y 天**、**每天 X 单** — 变量字母被中文文本包围
    # 用负向前瞻确保不跨越 ** 边界
    compound_pattern = rf"\*\*((?:(?!\*\*).)*?[A-Z\d]{{1,3}}\s*{units}+(?:(?!\*\*).)*?)\*\*"
    for match in re.finditer(compound_pattern, text):
        raw = match.group(0)
        if raw in seen_raw:
            continue
        inner = match.group(1)
        # 提取核心变量名（字母+单位部分）
        var_match = re.search(rf"([A-Z\d]{{1,3}}\s*{units}+)", inner)
        if not var_match:
            continue
        name = var_match.group(1).strip()
        # 如果内部全是变量（无额外中文文本），则已被模式2覆盖，跳过
        if inner.strip() == name:
            continue
        if name not in seen_names:
            variables.append(Variable(name=name, raw=raw, var_type="bold_marker_compound"))
            seen_raw.add(raw)
            seen_names.add(name)

    return variables
