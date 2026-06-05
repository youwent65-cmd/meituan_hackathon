from __future__ import annotations

"""对话驱动器 - 管理多轮对话的回合循环与层路由"""

import random
import re
import time
from typing import Callable, Optional

from .models import (
    UserProfile,
    TestCase,
    DialogueRecord,
    Turn,
    SimulationConfig,
)
from .context_tracker import DialogueContext
from .layers.l1_rule_engine import L1RuleEngine, FlowGraph
from .layers.l2_adversarial import L2AdversarialGen
from .layers.l3_llm_agent import L3LLMAgent


# SUT 类型定义：接受用户消息，返回 SUT 回复
SutCallback = Callable[[str], str]


class DialogueDriver:
    """对话驱动器：核心调度器

    管理一条完整对话的完整生命周期：
    初始化 → 轮次循环 (SUT ⇄ 模拟器) → 终止检测 → 输出记录
    """

    TERMINATION_KEYWORDS = {
        "sut_hangup": ["再见", "祝您", "生活愉快", "稍后再打", "那我稍后"],
        "user_hangup": ["挂断", "不说了", "挂了"],
    }

    def __init__(
        self,
        config: SimulationConfig,
        instruction: "ParsedInstruction",
        sut_callback: Optional[SutCallback] = None,
    ):
        self.config = config
        self.instruction = instruction
        self.sut_callback = sut_callback or self._mock_sut

        # 提取并采样变量值
        self._variables: dict[str, str] = {}
        for v in (instruction.variables if hasattr(instruction, "variables") else []):
            if isinstance(v, dict):
                self._variables[v["name"]] = self._sample_var_value(v["name"])
            else:
                self._variables[v.name] = self._sample_var_value(v.name)

        # 构建流程 DAG（步骤描述已经过变量替换）
        flow_steps = instruction.flow_steps
        self.flow_graph = FlowGraph(
            [self._step_to_dict(s) for s in flow_steps]
        )

        # 初始化三层引擎
        self.l1_engine = L1RuleEngine(self.flow_graph)
        self.l2_engine = L2AdversarialGen(
            instruction.constraints if hasattr(instruction, "constraints") else [],
            instruction.faq if hasattr(instruction, "faq") else [],
        )
        self.l3_agent = L3LLMAgent(config, instruction)

    def _step_to_dict(self, step) -> dict:
        """将 FlowNode（dataclass 或 dict）统一转为 dict，并替换其中的变量"""
        if isinstance(step, dict):
            raw = step
        else:
            raw = {
                "id": getattr(step, "id", ""),
                "description": getattr(step, "description", ""),
                "node_type": getattr(step, "node_type", "action"),
                "conditions": [],
                "default_next": getattr(step, "default_next", None),
                "is_required": getattr(step, "is_required", True),
                "detection_hint": getattr(step, "detection_hint", None),
            }
            for c in (step.conditions if hasattr(step, "conditions") else []):
                if isinstance(c, dict):
                    raw["conditions"].append(c)
                else:
                    raw["conditions"].append({
                        "trigger": getattr(c, "trigger", ""),
                        "action": getattr(c, "action", None),
                        "next_step": getattr(c, "next_step", None),
                        "is_terminal": getattr(c, "is_terminal", False),
                    })

        # 替换步骤描述中的变量占位符
        raw["description"] = self._substitute_variables(raw["description"])
        # 也替换条件分支中的触发词
        for cond in raw.get("conditions", []):
            if "trigger" in cond:
                cond["trigger"] = self._substitute_variables(cond["trigger"])

        return raw

    def run_dialogue(
        self,
        instruction_id: str,
        profile: UserProfile,
        test_case: TestCase,
    ) -> DialogueRecord:
        """执行单条完整对话模拟

        Args:
            instruction_id: 指令 ID
            profile: 用户画像
            test_case: 测试用例

        Returns:
            完整的对话记录
        """
        record = DialogueRecord(
            instruction_id=instruction_id,
            test_case_id=test_case.id,
            test_dimension=test_case.type,
            layer_used=test_case.layer,
            profile=profile,
        )

        # 初始化上下文
        context = DialogueContext(
            instruction_id=instruction_id,
            task=self.instruction.task if hasattr(self.instruction, "task") else "",
            role=self.instruction.role if hasattr(self.instruction, "role") else "",
            opening=self.instruction.opening if hasattr(self.instruction, "opening") else "",
        )

        # 变量填充（使用已构建的变量值）
        variables = self._variables

        # 第 0 轮：SUT 开场白（替换变量后的文本）
        opening = self.instruction.opening if hasattr(self.instruction, "opening") else ""
        opening = self._substitute_variables(opening)

        if not opening:
            opening = "您好，请问有什么可以帮您？"

        record.add_turn(role="SUT", content=opening)

        # 重置 L1 引擎状态
        self.l1_engine.reset()
        # 重置 Mock SUT 步骤指针，每次对话从第一个步骤开始
        self._mock_step_idx = 0

        # 对话循环
        last_step_idx = -1
        for turn in range(1, self.config.max_turns + 1):
            # Step 1: 检查上一轮 SUT 消息是否触发终止
            last_sut = context.get_last_sut_msg() or opening
            if self._should_end(last_sut, context):
                record.end_reason = self._determine_end_reason(last_sut, context)
                record.metadata["termination_turn"] = turn
                break

            # Step 2: 路由到对应层生成用户回复
            user_reply = self._route_and_generate(
                test_case, turn, last_sut, context, profile
            )

            # Step 3: 记录用户回复
            record.add_turn(role="USER", content=user_reply)

            # Step 4: 发送给 SUT，获取回复
            sut_reply = self._call_sut(user_reply)
            record.add_turn(role="SUT", content=sut_reply)

            # Step 5: 优先检查当前 SUT 回复是否含结束语（在 no_progress 之前）
            if self._should_end(sut_reply, context):
                record.end_reason = self._determine_end_reason(sut_reply, context)
                record.metadata["termination_turn"] = turn
                break

            # Step 6: 更新上下文（传递步骤变化信号，避免误判 no_progress）
            current_step_idx = getattr(self, "_mock_step_idx", 0)
            step_changed = current_step_idx != last_step_idx
            last_step_idx = current_step_idx
            context.update(
                user_reply, sut_reply,
                current_step=str(current_step_idx) if step_changed else context.current_step_id,
            )

            # Step 7: 检查是否长期无进展
            if context.is_no_progress():
                record.end_reason = "no_progress"
                record.metadata["termination_turn"] = turn
                break

        else:
            record.end_reason = "max_turns"

        record.total_turns = len([t for t in record.turns if t.role == "USER"])
        record.metadata["completed_steps"] = list(self.l1_engine.completed_steps)
        record.metadata["flow_complete"] = self.l1_engine.is_complete()
        record.metadata["variables_used"] = variables

        # 传递 FAQ 预期答案给评估器
        if test_case.type == "faq_trigger" and test_case.trigger_question:
            record.metadata["expected_faq_answers"] = {
                test_case.trigger_question: test_case.expected_answer
            }

        return record

    def _route_and_generate(
        self,
        test_case: TestCase,
        turn: int,
        sut_msg: str,
        context: DialogueContext,
        profile: UserProfile,
    ) -> str:
        """根据测试用例类型路由到合适的模拟层"""
        tc_type = test_case.type
        layer = test_case.layer

        if layer == "L1":
            return self.l1_engine.generate_reply(sut_msg, context, profile)

        elif layer == "L2":
            # L2 在触发轮次使用对抗生成，其余轮次用 L1
            if test_case.trigger_turn > 0 and turn == test_case.trigger_turn:
                context.adversarial_triggered = True
                context.current_strategy = tc_type
                return self.l2_engine.generate_reply(
                    sut_msg, context, profile, test_case
                )
            else:
                return self.l1_engine.generate_reply(sut_msg, context, profile)

        elif layer == "L3":
            return self.l3_agent.generate_reply(sut_msg, context, profile, test_case)

        else:
            # 默认：L1 规则引擎
            return self.l1_engine.generate_reply(sut_msg, context, profile)

    def _call_sut(self, user_message: str) -> str:
        """调用 SUT 获取回复"""
        try:
            return self.sut_callback(user_message)
        except Exception as e:
            return f"[SUT 调用失败: {e}]"

    def _should_end(self, sut_message: str, context: DialogueContext) -> bool:
        """检查是否应终止对话"""
        # SUT 结束语检测
        for keyword in self.TERMINATION_KEYWORDS["sut_hangup"]:
            if keyword in sut_message:
                return True

        # 用户侧触发的结束（通过上下文判断）
        last_user = context.get_last_user_msg()
        if last_user:
            for keyword in self.TERMINATION_KEYWORDS["user_hangup"]:
                if keyword in last_user:
                    return True

        # 流程完成
        if self.l1_engine.is_complete() and context.total_sut_turns >= len(self.flow_graph.steps):
            return True

        return False

    def _determine_end_reason(self, sut_msg: str, context: DialogueContext) -> str:
        """确定对话结束原因"""
        if "再见" in sut_msg or "祝您" in sut_msg:
            return "sut_normal_end"
        if "稍后再打" in sut_msg or "回电" in sut_msg:
            return "sut_transfer"
        if context.is_no_progress():
            return "no_progress"
        if self.l1_engine.is_complete():
            return "flow_complete"
        return "unknown"

    def _mock_sut(self, user_message: str) -> str:
        """Mock SUT V2：检测用户信号 → FAQ → 流程步骤，按优先级处理"""
        from .mock_sut_v2 import (
            generate_step_aware_reply, detect_faq_question, generate_faq_reply,
            detect_user_signal,
        )

        # 连续信号计数器（防止死循环）
        if not hasattr(self, "_signal_count"):
            self._signal_count = 0
            self._last_signal_type = None

        # 优先级1: 检测用户信号
        signal_type, signal_reply = detect_user_signal(user_message)
        if signal_type:
            if signal_type == "reject":
                return signal_reply

            # 跟踪连续同类型信号
            if signal_type == self._last_signal_type:
                self._signal_count += 1
            else:
                self._signal_count = 1
                self._last_signal_type = signal_type

            # 连续3次同类型信号 → 直接推进步骤，打破死循环
            if self._signal_count >= 3:
                self._signal_count = 0
                idx = getattr(self, "_mock_step_idx", 0)
                reply, new_idx = generate_step_aware_reply(idx, self.flow_graph.steps)
                self._mock_step_idx = new_idx
                return reply

            if signal_type == "interrupt":
                # 打断：简短回应，不推进步骤，等用户说话
                return signal_reply
            else:
                # 不耐烦/困惑：用信号回复简短回应，同时推进步骤
                idx = getattr(self, "_mock_step_idx", 0)
                reply, new_idx = generate_step_aware_reply(idx, self.flow_graph.steps)
                self._mock_step_idx = new_idx
                # 如果步骤回复太长则只回信号语，否则拼接
                if len(reply) < 30:
                    return signal_reply + reply
                else:
                    return signal_reply
        else:
            # 无信号时重置计数
            self._signal_count = 0
            self._last_signal_type = None

        # 优先级2: 检测 FAQ 问题
        faq_items = self.instruction.faq if hasattr(self.instruction, "faq") else []
        if faq_items:
            faq_match = detect_faq_question(user_message, faq_items)
            if faq_match:
                return generate_faq_reply(faq_match)

        # 优先级3: 按流程步骤推进
        idx = getattr(self, "_mock_step_idx", 0)
        reply, new_idx = generate_step_aware_reply(idx, self.flow_graph.steps)
        self._mock_step_idx = new_idx
        return reply

    @staticmethod
    def _substitute_text(text: str, variables: dict[str, str]) -> str:
        """对文本进行变量替换，支持简单和复合加粗标记。

        - ${var_name} → value
        - **Y 天** → 3天（简单加粗标记，保留单位）
        - **连续 Y 天** → 连续3天（复合加粗标记，保留上下文和单位）
        """
        if not text or not variables:
            return text

        for var_name, val in variables.items():
            val_str = str(val)
            # ${var_name} 占位符
            text = text.replace(f"${{{var_name}}}", val_str)

            # 对加粗标记做 regex 替换：保留单位词和上下文文字
            letter_match = re.match(r"([A-Za-z\d]+)\s*(\S+)", var_name)
            if letter_match:
                letter = letter_match.group(1)
                unit = letter_match.group(2)
                # 匹配 ** (前缀) 字母 单位 (后缀) **，替换时去掉 ** 并保留上下文和单位
                # Group 2: 前缀, Group 3: 单位, Group 4: 后缀
                # 使用 \g<N> 避免数字值导致的反向引用歧义
                text = re.sub(
                    rf"\*\*(([^*]*?){re.escape(letter)}\s*({re.escape(unit)})([^*]*?))\*\*",
                    rf"\g<2>{val_str}\g<3>\g<4>",
                    text,
                )

        return text

    def _substitute_variables(self, text: str) -> str:
        """对文本应用当前指令的变量替换。"""
        return self._substitute_text(text, self._variables)

    @staticmethod
    def _sample_var_value(var_name: str) -> str:
        """为变量采样一个合理的值"""
        name_lower = var_name.lower()
        if "rider" in name_lower or "姓名" in var_name or "名字" in var_name:
            return random.choice(["张三", "李四", "王五", "赵六"])
        # 单: 优先精确匹配字母+单位组合
        if "x" in name_lower and "单" in name_lower:
            return str(random.choice([5, 8, 10]))
        if "y" in name_lower and "单" in name_lower:
            return str(random.choice([8, 10, 12]))
        if "单" in name_lower:
            return str(random.choice([5, 8, 10]))
        # 天: 优先精确匹配
        if "y" in name_lower and "天" in name_lower:
            return str(random.choice([3, 5, 7]))
        if "w" in name_lower and "天" in name_lower:
            return str(random.choice([7, 14, 30]))
        if "天" in name_lower:
            return str(random.choice([7, 14, 30]))
        if "z" in name_lower:
            return random.choice(["18:00", "20:00", "22:00"])
        return "..."
