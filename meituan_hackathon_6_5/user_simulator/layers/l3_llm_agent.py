from __future__ import annotations

"""L3 LLM Agent - 基于大语言模型的自由对话模拟"""

import json
import random
import time
from typing import Optional

from ..models import UserProfile, SimulationConfig
from ..context_tracker import DialogueContext


class L3LLMAgent:
    """L3 层：使用 LLM 扮演用户角色进行自由对话

    通过 System Prompt 注入用户画像和对话上下文，
    生成自然度最高、多样性最强的用户回复。
    """

    SYSTEM_PROMPT_TEMPLATE = """你正在扮演一位真实用户，接听来自平台的电话。

## 你的角色信息
- 你的名字：{name}
- 你的身份：{identity}
- 对方身份：{role_description}

## 对方的目标
{task_description}

## 你的个人画像
- 配合度：{cooperation_label}
  * {cooperation_behavior}
- 说话风格：{verbosity_label}
- 当前情绪：{emotion_label}
- 跑题概率：{distraction_level}

## 回复要求
1. 用口语化的中文回复，像打电话一样自然
2. 每次回复保持{verbosity_label}的长度
3. 回复要简短自然，不要过于正式
4. 如果情绪为生气/急躁，语气可以更不耐烦
5. 不要回复得过于机械或书面，要像真人说话
6. {special_instructions}

## 对话历史
{conversation_history}

## 对方刚说的话
"{sut_last_message}"

请用自然的口语回复对方上面的话。只输出你的回复内容，不要加任何前缀或说明。"""

    _mock_warned = False  # 类级别，整个进程只警告一次

    def __init__(self, config: SimulationConfig, instruction: "ParsedInstruction"):
        self.config = config
        self.instruction = instruction
        self._used_replies = set()  # 已用回复追踪，避免重复

        if config.llm_provider == "mock" and not L3LLMAgent._mock_warned:
            L3LLMAgent._mock_warned = True
            print("[L3 Agent] 当前使用 mock 模式（预置模板），L3 对话多样性受限。"
                  "使用 --llm 参数并配置 --llm-key 以启用 LLM 增强。")

        # 结构化回复库：按场景分类，每个场景有独立完整的回复（不再随机拼接）
        self._replies = {
            "neutral_ack": [
                "嗯，好的，我了解了。",
                "这样啊，那我注意一下。",
                "好的，没问题。",
                "我知道了，谢谢啊。",
                "行吧，那就先这样。",
                "嗯嗯，你说得对。",
                "好，我记住了。",
                "可以的，我没问题。",
                "那就按你说的来吧。",
                "明白了，还有别的吗？",
                "好的，你继续说吧。",
                "行，我清楚了。",
            ],
            "angry": [
                "烦死了，能不能快点说完？",
                "有完没完，我还有事呢。",
                "你们每次打电话来都是这些，能不能换点新鲜的？",
                "行行行，我知道了，别啰嗦了。",
                "我说你到底要讲多久？",
            ],
            "confused": [
                "嗯？什么意思，我没太听懂。",
                "等一下，你能再说一遍吗？",
                "这个我不太明白，能解释一下吗？",
                "你说得有点复杂，我还没搞清楚。",
                "慢点说，我没跟上。",
            ],
            "impatient": [
                "嗯，然后呢？说重点吧。",
                "直接说重点，别绕弯子。",
                "简短点，我没太多时间。",
                "能快点说完吗？",
            ],
            "low_cooperation": [
                "再说吧，我现在不想聊这个。",
                "我没兴趣，就这样吧。",
                "说实话，我对这个不太关心。",
                "你能不能说点有用的？",
            ],
            "diversion": [
                "对了，我有个问题想问你。",
                "等一下，我想起一件事要确认。",
                "先不说这个，我问你个事儿。",
                "说到这个，我正好有个疑问。",
                "换个话题，有件事想跟你确认。",
            ],
            "question": [
                "这个具体是什么意思，能举个例子吗？",
                "你说的这个有具体的时间吗？",
                "如果我不按你说的做，会有什么后果？",
                "这个规定是谁定的，有依据吗？",
            ],
            "ending": [
                "好的，没有其他问题了，谢谢。",
                "明白了，那就这样吧。",
                "行，我知道了，再见。",
                "嗯嗯，你忙吧，挂了。",
            ],
        }

    def generate_reply(
        self,
        sut_message: str,
        context: DialogueContext,
        profile: UserProfile,
        test_case: "TestCase",
    ) -> str:
        """生成 LLM 驱动的回复"""
        provider = self.config.llm_provider

        if provider == "mock":
            return self._mock_reply(profile, sut_message, context)

        if not self.config.llm_api_key:
            print(f"[L3 Agent] WARNING: llm_provider='{provider}' 但未配置 API Key，降级为 mock")
            return self._mock_reply(profile, sut_message, context)

        try:
            if provider == "anthropic":
                return self._call_anthropic(profile, sut_message, context)
            elif provider in ("deepseek", "openai"):
                return self._call_openai_compat(profile, sut_message, context)
            else:
                print(f"[L3 Agent] WARNING: 不支持的 provider '{provider}'，降级为 mock")
                return self._mock_reply(profile, sut_message, context)
        except Exception as e:
            print(f"[L3 Agent] WARNING: LLM 调用失败 ({e})，降级为 mock。"
                  "请检查 API Key、网络和 provider 配置。")
            return self._mock_reply(profile, sut_message, context)

    def _pick_reply(self, category: str) -> str:
        """从指定分类中选一条未使用过的回复"""
        pool = self._replies.get(category, self._replies["neutral_ack"])
        # 优先选没用过的
        unused = [r for r in pool if r not in self._used_replies]
        if not unused:
            unused = pool  # 都用过了就重置
        reply = random.choice(unused)
        self._used_replies.add(reply)
        return reply

    def _mock_reply(
        self,
        profile: UserProfile,
        sut_message: str,
        context: DialogueContext,
    ) -> str:
        """基于用户画像和对话上下文生成连贯的 mock 回复。

        关键原则：每次只生成一个完整的独立回复，不再随机拼接多个片段。
        """
        turn_count = context.total_user_turns
        sut_len = len(sut_message) if sut_message else 0

        # 策略0: SUT 在等用户说话 → 生成实质性内容
        if sut_len < 30 and any(kw in sut_message for kw in ["请说", "请讲", "您说", "什么问题", "想了解"]):
            if random.random() < 0.5:
                return self._pick_reply("question")
            else:
                return self._pick_reply("diversion")

        # 策略1: 低配合度 → 优先拒绝/不配合
        if profile.cooperation_level < 0.3:
            if turn_count <= 2:
                return self._pick_reply("low_cooperation")
            elif random.random() < 0.6:
                return self._pick_reply("low_cooperation")

        # 策略2: 情绪驱动 → 根据情绪选回复
        if profile.emotion == "angry" and random.random() < 0.6:
            return self._pick_reply("angry")
        elif profile.emotion == "confused" and random.random() < 0.5:
            return self._pick_reply("confused")
        elif profile.emotion == "impatient" and random.random() < 0.5:
            return self._pick_reply("impatient")

        # 策略3: 跑题/转移话题 → 中期轮次以独立句子出现
        if turn_count >= 2 and random.random() < profile.distraction_level:
            return self._pick_reply("diversion")

        # 策略4: SUT 说了很多 → 用户可能提问或确认
        if sut_len > 80 and random.random() < 0.4:
            return self._pick_reply("question")

        # 策略5: 后期轮次 → 倾向于结束
        if turn_count >= 6 and random.random() < 0.4:
            return self._pick_reply("ending")

        # 默认: 中性确认回复
        return self._pick_reply("neutral_ack")

    def _call_anthropic(
        self,
        profile: UserProfile,
        sut_message: str,
        context: DialogueContext,
    ) -> str:
        """调用 Anthropic Claude API 生成回复"""
        import anthropic

        client = anthropic.Anthropic(api_key=self.config.llm_api_key)
        prompt = self._build_prompt(profile, sut_message, context)
        response = client.messages.create(
            model=self.config.llm_model,
            max_tokens=150,
            temperature=self.config.temperature,
            system=prompt,
            messages=[{"role": "user", "content": "请生成用户回复"}],
        )
        return response.content[0].text.strip()

    def _call_openai_compat(
        self,
        profile: UserProfile,
        sut_message: str,
        context: DialogueContext,
    ) -> str:
        """调用 OpenAI 兼容 API（DeepSeek / OpenAI）生成回复"""
        import openai

        provider = self.config.llm_provider
        base_url = self.config.llm_base_url
        if not base_url and provider == "deepseek":
            base_url = "https://api.deepseek.com"
        model = self.config.llm_model
        if model == "claude-sonnet-4-6":
            model = "deepseek-chat" if provider == "deepseek" else "gpt-4o"

        kwargs = {"api_key": self.config.llm_api_key}
        if base_url:
            kwargs["base_url"] = base_url
        client = openai.OpenAI(**kwargs)

        system_prompt = self._build_prompt(profile, sut_message, context)
        response = client.chat.completions.create(
            model=model,
            max_tokens=150,
            temperature=self.config.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "请生成用户回复"},
            ],
        )
        return response.choices[0].message.content.strip()

    def _build_prompt(
        self,
        profile: UserProfile,
        sut_message: str,
        context: DialogueContext,
    ) -> str:
        """构建 System Prompt"""
        cooperation_label = (
            "高" if profile.cooperation_level > 0.7
            else "中" if profile.cooperation_level > 0.3
            else "低"
        )
        cooperation_behaviors = {
            "高": "积极配合，有问必答",
            "中": "偶尔不配合，会反问",
            "低": "不配合，经常岔开话题或拒绝回答",
        }
        emotion_cn = {
            "neutral": "平静", "happy": "开心", "impatient": "急躁",
            "angry": "生气", "confused": "困惑",
        }

        special = "保持自然的口语对话"
        if profile.is_driving:
            special = "你正在开车，应该很快结束对话或要求对方稍后再打"
        if profile.has_special_request:
            special = "你有一个特殊请求想要提出（如优惠、折扣等）"

        return self.SYSTEM_PROMPT_TEMPLATE.format(
            name=profile.name,
            identity=profile.identity,
            role_description=self.instruction.role,
            task_description=self.instruction.task,
            cooperation_label=cooperation_label,
            cooperation_behavior=cooperation_behaviors.get(cooperation_label, ""),
            verbosity_label=profile.verbosity,
            emotion_label=emotion_cn.get(profile.emotion, "平静"),
            distraction_level=profile.distraction_level,
            special_instructions=special,
            conversation_history=context.get_history_text(max_turns=8),
            sut_last_message=sut_message,
        )

    def _mock_fuzzy_match(self, keyword: str, text: str) -> bool:
        """简单的模糊匹配"""
        return keyword.lower() in text.lower()
