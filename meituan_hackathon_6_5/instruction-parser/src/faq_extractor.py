from __future__ import annotations

"""FAQ 提取器 - 从独立章节和 Flow 步骤中提取知识点"""

import re

from .models import FAQItem
from .section_splitter import Section


def extract_faq(faq_sections: list[Section], flow_sections: list[Section] | None = None) -> list[FAQItem]:
    """提取 FAQ 知识点。

    来源1: 独立的 Knowledge Points / FAQ 章节
    来源2: Flow 步骤中嵌入的结构化知识（如区别、价格等信息块）
    """
    items: list[FAQItem] = []

    # 来源1: 独立 FAQ 章节
    for sec in faq_sections:
        items.extend(_parse_faq_section(sec))

    # 来源2: Flow 中嵌入的知识
    if flow_sections:
        for sec in flow_sections:
            items.extend(_extract_embedded_knowledge(sec))

    return items


def _parse_faq_section(section: Section) -> list[FAQItem]:
    """解析独立 FAQ 章节中的知识点。

    格式通常为 bullet list，每条是一个完整知识点。
    """
    items: list[FAQItem] = []
    content = section.content
    if not content:
        return items

    # 按 bullet 分割
    bullets = re.split(r"\n\s*[-*]\s+", "\n" + content)
    for bullet in bullets:
        bullet = bullet.strip()
        if not bullet:
            continue

        # FAQ 章节的每条 bullet 既是问题也是答案
        # 尝试识别 Q/A 格式
        qa_match = re.match(r"[QqＱ问][：:]\s*(.+?)\s*[AaＡ答][：:]\s*(.+)", bullet, re.DOTALL)
        if qa_match:
            items.append(FAQItem(
                question=qa_match.group(1).strip(),
                answer=qa_match.group(2).strip(),
                source="faq_section",
            ))
        else:
            # 没有明确 Q/A 分隔，整条作为知识点
            # 用第一句话作为"问题"（触发条件），全文作为"答案"
            first_sentence = re.split(r"[。；;]", bullet)[0]
            items.append(FAQItem(
                question=first_sentence.strip(),
                answer=bullet.strip(),
                source="faq_section",
            ))

    return items


def _extract_embedded_knowledge(section: Section) -> list[FAQItem]:
    """从 Flow 章节中提取嵌入的知识点。

    识别模式：
    - 子步骤标题含"区别"/"价格"/"说明"等关键词
    - 内容为结构化的对比信息
    """
    items: list[FAQItem] = []
    knowledge_keywords = ["区别", "价格", "说明", "对比", "差异", "费用"]

    def _scan_section(sec: Section):
        # 检查标题是否包含知识类关键词
        if any(kw in sec.title for kw in knowledge_keywords):
            if sec.content:
                # 提取加粗标记的知识条目
                bold_items = re.findall(
                    r"\*\*(.+?)[：:]\*\*\s*(.+?)(?=\n\*\*|\n\n|$)",
                    sec.content,
                    re.DOTALL,
                )
                for name, desc in bold_items:
                    items.append(FAQItem(
                        question=f"{sec.title} - {name.strip()}",
                        answer=desc.strip(),
                        source="flow_embedded",
                    ))

                # 如果没有加粗条目，整段作为知识
                if not bold_items and sec.content.strip():
                    items.append(FAQItem(
                        question=sec.title,
                        answer=sec.content.strip(),
                        source="flow_embedded",
                    ))

        # 递归子章节
        for child in sec.children:
            _scan_section(child)

    _scan_section(section)
    return items
