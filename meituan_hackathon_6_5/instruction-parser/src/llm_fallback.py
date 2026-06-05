from __future__ import annotations

"""LLM Fallback 通道

当规则解析器无法处理某些字段时，使用 Claude API 进行辅助解析。
仅在规则解析失败或结果不完整时触发，避免不必要的 API 调用。
"""

import json
import os
from typing import Any

from .models import ParsedInstruction, FlowNode, Condition, FAQItem, Constraint


def get_client(api_key: str = None, provider: str = "anthropic", base_url: str = ""):
    """获取 LLM 客户端，支持 Anthropic / DeepSeek / OpenAI。"""
    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
            return ("anthropic", client)
        elif provider in ("deepseek", "openai"):
            import openai
            url = base_url or ("https://api.deepseek.com" if provider == "deepseek" else None)
            kwargs = {"api_key": api_key}
            if url:
                kwargs["base_url"] = url
            return ("openai", openai.OpenAI(**kwargs))
        else:
            print(f"[LLM Fallback] 不支持的 provider: {provider}")
            return None
    except Exception as e:
        print(f"[LLM Fallback] 无法初始化 LLM 客户端: {e}")
        return None


def _llm_chat(client_type, client, model, prompt, max_tokens=4096):
    """统一的 LLM 调用接口"""
    if client_type == "anthropic":
        response = client.messages.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    else:
        response = client.chat.completions.create(
            model=model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content


def llm_parse_full(raw_text: str, api_key: str = None,
                   provider: str = "anthropic", base_url: str = "") -> dict[str, Any] | None:
    """使用 LLM 对整个指令进行全量解析（最后兜底）。"""
    result = get_client(api_key, provider, base_url)
    if not result:
        return None
    client_type, client = result

    model = "claude-sonnet-4-20250514"
    if provider == "deepseek":
        model = "deepseek-chat"
    elif provider == "openai":
        model = "gpt-4o"

    prompt = f"""你是一个指令解析专家。请将以下外呼任务对话模型指令解析为结构化 JSON。

要求提取以下字段：
1. role: 角色描述（字符串）
2. task: 任务目标（字符串）
3. opening: 开场白（字符串）
4. flow_steps: 对话流程步骤数组，每个步骤包含:
   - id: 步骤编号
   - description: 步骤描述
   - node_type: action/branch/info/guide/terminal
   - conditions: 条件分支数组 [{{trigger, action, next_step, is_terminal}}]
   - default_next: 默认下一步编号
5. faq: 知识点数组 [{{question, answer}}]
6. constraints: 约束数组 [{{raw, constraint_type, params, is_hard}}]
   constraint_type 可选: length_limit, forbidden_words, forbidden_topic, termination_condition, conditional_response, fallback_response, no_repeat, style, generic

请严格输出 JSON，不要有其他文字。

指令原文：
---
{raw_text}
---"""

    try:
        content = _llm_chat(client_type, client, model, prompt, max_tokens=4096)
        # 提取 JSON（可能被 ```json 包裹）
        json_match = content
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if match:
                json_match = match.group(1)
        return json.loads(json_match)
    except Exception as e:
        print(f"[LLM Fallback] 全量解析失败: {e}")
        return None


def llm_parse_flow_conditions(step_content: str, api_key: str = None,
                              provider: str = "anthropic", base_url: str = "") -> list[dict] | None:
    """使用 LLM 解析步骤中的条件分支逻辑。"""
    result = get_client(api_key, provider, base_url)
    if not result:
        return None
    client_type, client = result

    model = "claude-sonnet-4-20250514"
    if provider == "deepseek":
        model = "deepseek-chat"
    elif provider == "openai":
        model = "gpt-4o"

    prompt = f"""分析以下对话流程步骤内容，提取其中的条件分支逻辑。

如果包含条件分支，返回 JSON 数组：
[{{"trigger": "触发条件", "action": "执行动作", "next_step": "跳转步骤编号或null", "is_terminal": false}}]

如果没有条件分支，返回空数组 []。

步骤内容：
---
{step_content}
---

只输出 JSON 数组，不要其他文字。"""

    try:
        content = _llm_chat(client_type, client, model, prompt, max_tokens=1024).strip()
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if match:
                content = match.group(1)
        return json.loads(content)
    except Exception as e:
        print(f"[LLM Fallback] 条件解析失败: {e}")
        return None


def llm_classify_constraint(raw_text: str, api_key: str = None,
                            provider: str = "anthropic", base_url: str = "") -> dict | None:
    """使用 LLM 对无法自动分类的约束进行分类。"""
    result = get_client(api_key, provider, base_url)
    if not result:
        return None
    client_type, client = result

    model = "claude-sonnet-4-20250514"
    if provider == "deepseek":
        model = "deepseek-chat"
    elif provider == "openai":
        model = "gpt-4o"

    prompt = f"""将以下对话约束分类并提取参数。

约束类型可选：
- length_limit: 字数限制 (params: max_chars, tolerance)
- forbidden_words: 禁用词 (params: words[])
- forbidden_topic: 禁止话题 (params: topic_keywords[], topic_desc)
- termination_condition: 终止条件 (params: trigger_pattern, expected_action)
- conditional_response: 条件响应 (params: trigger_scenario, expected_script)
- fallback_response: 越界处理 (params: trigger_scenario, expected_script)
- no_repeat: 避免重复 (params: similarity_threshold)
- style: 风格要求 (params: style_desc)
- generic: 其他 (params: desc)

约束原文："{raw_text}"

返回 JSON: {{"constraint_type": "...", "params": {{...}}, "is_hard": true/false}}
只输出 JSON。"""

    try:
        content = _llm_chat(client_type, client, model, prompt, max_tokens=512).strip()
        if "```" in content:
            import re
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", content, re.DOTALL)
            if match:
                content = match.group(1)
        return json.loads(content)
    except Exception as e:
        print(f"[LLM Fallback] 约束分类失败: {e}")
        return None


def enhance_with_llm(instruction: ParsedInstruction, api_key: str = None,
                     provider: str = "anthropic", base_url: str = "") -> ParsedInstruction:
    """检查规则解析结果的完整性，对缺失/不完整的部分用 LLM 补全。"""
    needs_full_parse = False

    # 检查关键字段是否为空
    if not instruction.role:
        needs_full_parse = True
    if not instruction.task:
        needs_full_parse = True
    if not instruction.flow_steps:
        needs_full_parse = True

    if not needs_full_parse:
        return instruction

    if not api_key:
        print("[LLM Fallback] WARNING: use_llm_fallback=True 但未配置 API Key，无法调用 LLM 补全。"
              "规则解析结果可能不完整。")
        return instruction

    # 触发全量 LLM 解析
    print("[LLM Fallback] 规则解析结果不完整，触发 LLM 全量解析...")
    result = llm_parse_full(instruction.raw_text, api_key, provider, base_url)
    if not result:
        return instruction

    # 用 LLM 结果补全缺失字段
    if not instruction.role and result.get("role"):
        instruction.role = result["role"]
    if not instruction.task and result.get("task"):
        instruction.task = result["task"]
    if not instruction.opening and result.get("opening"):
        instruction.opening = result["opening"]

    if not instruction.flow_steps and result.get("flow_steps"):
        for step_data in result["flow_steps"]:
            conditions = [
                Condition(**c) for c in step_data.get("conditions", [])
            ]
            node = FlowNode(
                id=str(step_data.get("id", "")),
                description=step_data.get("description", ""),
                node_type=step_data.get("node_type", "action"),
                conditions=conditions,
                default_next=step_data.get("default_next"),
            )
            instruction.flow_steps.append(node)

    if not instruction.faq and result.get("faq"):
        for faq_data in result["faq"]:
            instruction.faq.append(FAQItem(
                question=faq_data.get("question", ""),
                answer=faq_data.get("answer", ""),
                source="llm_parsed",
            ))

    if not instruction.constraints and result.get("constraints"):
        for c_data in result["constraints"]:
            instruction.constraints.append(Constraint(
                raw=c_data.get("raw", ""),
                constraint_type=c_data.get("constraint_type", "generic"),
                params=c_data.get("params", {}),
                is_hard=c_data.get("is_hard", False),
            ))

    return instruction
