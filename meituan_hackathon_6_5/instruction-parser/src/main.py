"""指令解析器主入口

将自然语言编写的外呼任务指令解析为结构化数据。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .models import ParsedInstruction
from .section_splitter import parse_sections
from .field_extractor import extract_role, extract_task, extract_opening, extract_variables
from .flow_parser import parse_flow
from .faq_extractor import extract_faq
from .constraint_parser import extract_constraints
from .llm_fallback import enhance_with_llm


def parse_instruction(markdown_text: str, use_llm_fallback: bool = True,
                     llm_api_key: str = None, llm_provider: str = "anthropic",
                     llm_base_url: str = "") -> ParsedInstruction:
    """解析单条指令文本为结构化对象。

    Args:
        markdown_text: 原始 Markdown 格式的指令文本
        use_llm_fallback: 是否在规则解析不完整时启用 LLM 补全
        llm_api_key: LLM API Key
        llm_provider: LLM 提供商 ("anthropic" / "deepseek" / "openai")
        llm_base_url: 自定义 API 端点

    Returns:
        ParsedInstruction 结构化对象
    """
    instruction = ParsedInstruction(raw_text=markdown_text)

    # Step 1: 章节分割与字段路由
    sections = parse_sections(markdown_text)

    # Step 2: 提取简单字段
    instruction.role = extract_role(sections.get("role", []))
    instruction.task = extract_task(sections.get("task", []))
    instruction.opening = extract_opening(sections.get("opening", []))

    # Step 3: 提取变量
    instruction.variables = extract_variables(markdown_text)

    # Step 4: 解析 Call Flow
    instruction.flow_steps = parse_flow(sections.get("flow", []))

    # Step 5: 提取 FAQ
    instruction.faq = extract_faq(
        sections.get("faq", []),
        sections.get("flow", []),
    )

    # Step 6: 解析约束
    instruction.constraints = extract_constraints(sections.get("constraints", []))

    # Step 7: LLM Fallback（如果规则解析结果不完整）
    if use_llm_fallback:
        instruction = enhance_with_llm(instruction, llm_api_key, llm_provider, llm_base_url)

    return instruction


def parse_from_excel(excel_path: str, use_llm_fallback: bool = False,
                     llm_api_key: str = None, llm_provider: str = "anthropic",
                     llm_base_url: str = "") -> list[ParsedInstruction]:
    """从 Excel 文件读取并解析所有指令。"""
    import openpyxl

    wb = openpyxl.load_workbook(excel_path)
    ws = wb.active
    instructions = []

    for row in ws.iter_rows(min_row=2, values_only=True):
        if len(row) >= 2 and row[1]:
            text = str(row[1])
            inst = parse_instruction(text, use_llm_fallback=use_llm_fallback,
                                     llm_api_key=llm_api_key,
                                     llm_provider=llm_provider,
                                     llm_base_url=llm_base_url)
            instructions.append(inst)

    return instructions


def main():
    """CLI 入口点。"""
    if len(sys.argv) < 2:
        print("用法: python -m src.main <excel_path_or_markdown_file>")
        print("  解析指令文件并输出结构化 JSON")
        sys.exit(1)

    input_path = Path(sys.argv[1])

    if input_path.suffix == ".xlsx":
        instructions = parse_from_excel(str(input_path))
        output = [inst.to_dict() for inst in instructions]
    elif input_path.suffix in (".md", ".txt"):
        text = input_path.read_text(encoding="utf-8")
        inst = parse_instruction(text)
        output = inst.to_dict()
    else:
        print(f"不支持的文件格式: {input_path.suffix}")
        sys.exit(1)

    # 输出 JSON
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
