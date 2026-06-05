"""Mock SUT V2 — 步骤感知回复生成器，支持指令→口语转换和自然语言输出"""

import random
import re

# ---- 确认语 ----
_ACKS = [
    "好的", "嗯，了解", "收到", "明白", "行", "好嘞",
    "没问题", "可以", "清楚了", "知道了", "嗯嗯", "好",
]

# ---- 自然过渡语（不直接嵌入描述文本） ----
_TRANSITIONS = [
    "另外跟您说一下，{desc}",
    "还有一件事，{desc}",
    "接下来跟您讲讲，{desc}",
    "下面我跟您说明一下，{desc}",
    "再跟您补充一点，{desc}",
    "然后呢，{desc}",
]

# ---- 跟进/收尾 ----
_FOLLOW_UPS = [
    "请问您还有其他问题吗？",
    "还有什么需要帮您的吗？",
    "您看还有什么不清楚的吗？",
    "还有其他想了解的吗？",
    "有什么问题随时问我。",
    "您还有疑问吗？",
    "需要我再解释一下吗？",
    "这个您清楚了吗？",
]

_PLAIN_FOLLOW_UPS = [
    "您说我听着呢。",
    "您说。",
    "您讲。",
    "嗯您接着说。",
    "好，您有什么想法？",
]

_CLOSING_TAGS = [
    "那我顺便问一句，{desc}",
    "对了，{desc}",
    "哦还有，{desc}",
    "差点忘了，{desc}",
]

_ENDING_PHRASES = [
    "好的，以上就是要跟您确认的全部内容了。如果没有其他问题，祝您生活愉快，再见！",
    "感谢您的耐心配合，今天的信息就确认到这儿，祝您一切顺利，再见！",
    "好的，该说的都跟您讲清楚了。感谢接听，祝您生活愉快，再见！",
    "行，基本就是这些。您看还有需要补充的吗？没有的话祝您顺利，再见！",
    "嗯，要确认的就是这些了。感谢您的配合，再见！",
    "好的，这边就全部跟您确认完了。谢谢您的时间，祝您愉快！",
    "没问题的话今天就到这儿。再次感谢，再见！",
    "好的，信息都核对过了。不打扰您了，再见！",
]


# ---- 指令动词 → 口语转换规则 ----
# 每个规则: (pattern, replacement_template) — replacement 中用 {content} 代表剩余内容
_INSTRUCTION_PATTERNS = [
    # 告知/通知骑手/站长XXX → 直接说内容
    (r"^告知(?:骑手|站长|用户|对方|他们|您)?[，。,，\s]*", ""),
    (r"^通知(?:骑手|站长|用户|对方|他们|您)?[，。,，\s]*", ""),

    # 说明/解释XXX → "跟您说一下，XXX"
    (r"^说明[：:，。,，\s]*", ""),
    (r"^解释[：:，。,，\s]*", ""),

    # 询问XXX → "请问XXX？"（注意：不要消耗后面的"是否"，留给后续步骤处理）
    (r"^询问(?:骑手|站长|用户|对方|他们|您)?[，。,，\s]*", ""),

    # 确认XXX → "跟您确认一下，XXX"
    (r"^确认[：:，。,，\s]*", "跟您确认一下，"),

    # 提醒XXX → "提醒您，XXX"
    (r"^提醒(?:骑手|站长|用户|对方|他们|您)?[，。,，\s]*", ""),

    # 尽量挽留不想配送的骑手 → natural retention speech
    (r"^尽量挽留(?:不想配送的)?骑手[，。,，\s]*", "希望您能尽量参与配送，"),
    (r"^挽留(?:骑手|用户|对方)?[，。,，\s]*", "希望您能继续参与，"),

    # 鼓励能配送的骑手 → natural encouragement
    (r"^鼓励(?:能配送的)?(?:骑手|用户|对方)?[，。,，\s]*", "如果您方便的话希望能多接单，"),

    # 强调XXX → "需要特别注意的是，XXX"
    (r"^强调[：:，。,，\s]*", "需要注意的是，"),

    # 核实/了解XXX
    (r"^核实[：:，。,，\s]*", "跟您核实一下，"),
    (r"^了解[：:，。,，\s]*", "想了解一下，"),

    # 介绍XXX
    (r"^介绍[：:，。,，\s]*", "给您介绍一下，"),

    # 提供XXX
    (r"^提供[：:，。,，\s]*", ""),

    # 重复/再次XXX
    (r"^(?:再次|重复)(?:告知|说明|提醒|强调|确认)[：:，。,，\s]*", "再跟您说一下，"),
]

# 代词转换：将第三人称转为第二人称（SUT 直接对用户说话）
_PRONOUN_MAP = [
    ("骑手应", "您平时"),
    ("骑手需要", "您需要"),
    ("骑手可以", "您可以"),
    ("骑手", "您"),
    ("他们", "您"),
    ("对方", "您"),
    ("用户", "您"),
]


def _clean_punctuation(text: str) -> str:
    """规范化标点：移除连续重复标点，修复错位标点。"""
    # 移除句尾标点后紧跟逗号/分号的情况: 。，→ ，
    text = re.sub(r"[。！？](?=[，,；;、])", "", text)
    # 连续相同标点去重: ，，→ ，
    text = re.sub(r"([。！？，,；;、])\1+", r"\1", text)
    # 移除首尾多余的非句子级标点（保留 。！？ 等句子结尾标点）
    text = text.strip("，,；;、 \t")
    return text


def _remove_trailing_period(text: str) -> str:
    """移除末尾句号（用于嵌入模板前），但保留问号和感叹号。"""
    return re.sub(r"[。；;，,、\s]+$", "", text)


def _instruction_to_speech(desc: str) -> str:
    """将指令式步骤描述转换为自然口语对话。

    例如:
      "告知骑手今天飞毛腿合同已生效，并询问他们是否可以开始配送。"
      → "今天飞毛腿合同已生效，请问您现在可以开始配送吗？"

      "说明单日飞毛腿合同需要连续7天完成配送；否则合同将受到影响。"
      → "单日飞毛腿合同需要连续7天完成配送，否则合同会受到影响。"

      "尽量挽留不想配送的骑手，鼓励能配送的骑手，并提醒他们注意安全。"
      → "希望您能尽量参与配送，如果您方便的话希望能多接单，提醒您注意安全。"
    """
    text = desc.strip()

    # Step 1: 按中文标点分段，逐段处理指令前缀
    # 这样可以处理 "A，B，并C" 等多段复合指令
    segments = re.split(r"([，。；;,])", text)
    processed_parts = []
    for i, seg in enumerate(segments):
        if i % 2 == 1:
            # 分隔符：保留
            processed_parts.append(seg)
            continue
        seg = seg.strip()
        if not seg:
            continue
        # 对每段独立应用指令前缀移除（多轮处理）
        for _ in range(2):
            # 清理句首连接词（保留 "并非" 等固定搭配）
            seg = re.sub(r"^并且[，。,，\s]*", "", seg)
            seg = re.sub(r"^而且[，。,，\s]*", "", seg)
            seg = re.sub(r"^以及[，。,，\s]*", "", seg)
            seg = re.sub(r"^同时[，。,，\s]*", "", seg)
            seg = re.sub(r"^另外[，。,，\s]*", "", seg)
            seg = re.sub(r"^此外[，。,，\s]*", "", seg)
            # 单独的 "并" / "且" 仅在后续为标点时才作为连接词移除
            seg = re.sub(r"^并(?=[，。,，；;、])[，。,，\s]*", "", seg)
            seg = re.sub(r"^且(?=[，。,，；;、])[，。,，\s]*", "", seg)
            seg = re.sub(r"^[，。,，；;、\s]+", "", seg)
            for pattern, replacement in _INSTRUCTION_PATTERNS:
                seg = re.sub(pattern, replacement, seg, count=1)
        if seg.strip():
            processed_parts.append(seg)

    text = "".join(processed_parts)

    # Step 2: 代词转换（第三人称→第二人称）
    for old, new in _PRONOUN_MAP:
        text = text.replace(old, new)

    # Step 3: 转换"并询问..."为问句
    text = re.sub(
        r"[，,]?\s*并询问(?:他们|您|骑手)?(?:是否|是不是)?(.+?)([。；;]|$)",
        r"，请问您现在\1吗？",
        text,
    )
    text = re.sub(r"是否可以(.+?)([。；;]|$)", r"可以\1吗？", text)
    text = re.sub(r"是否(.+?)([。；;]|$)", r"\1吗？", text)

    # Step 4: 自然化表达 — 将分号转为逗号（口语中不用分号）
    text = text.replace("；", "，")

    # Step 5: 清理标点（不去掉句尾的。！？等有意义的标点）
    text = _clean_punctuation(text)

    # Step 6: 确保以合适标点结尾
    if text and not re.search(r"[。！？，,～~]$", text):
        text += "。"

    # Step 7: 问句结尾修正（放在最后，避免被 strip 掉）
    if re.search(r"[吗呢吧]|是不是|能不能|可不可以", text):
        text = re.sub(r"。$", "？", text)

    return text


def _format_speech(desc: str, style: float) -> str:
    """根据风格权重，将口语化描述包装为不同的话术模板。"""
    speech = _instruction_to_speech(desc)
    clean = _remove_trailing_period(speech)

    if style < 0.15:
        # 简洁确认 + 自然陈述
        ack = random.choice(_ACKS)
        return f"{ack}，{speech}"
    elif style < 0.30:
        # 过渡语开头
        tmpl = random.choice(_TRANSITIONS)
        return tmpl.format(desc=speech)
    elif style < 0.50:
        # 陈述 + 跟进
        follow = random.choice(_FOLLOW_UPS)
        return f"{speech} {follow}"
    elif style < 0.65:
        # 确认 + 陈述 + 简短跟进
        ack = random.choice(_ACKS)
        pf = random.choice(_PLAIN_FOLLOW_UPS)
        return f"{ack}，{speech} {pf}"
    elif style < 0.78:
        # 顺带风格
        tmpl = random.choice(_CLOSING_TAGS)
        return tmpl.format(desc=clean)
    elif style < 0.90:
        # 确认 + 强调陈述
        ack = random.choice(_ACKS)
        return f"{ack}，这一点很重要——{speech}"
    else:
        # 对用户上轮回应后的推进
        ack = random.choice(_ACKS)
        return f"{ack}，那接下来{clean}，您看可以吗？"


# ---- FAQ 相关 ----

_FAQ_ACKS = [
    "好的，关于您问的这个问题——",
    "嗯，这个问题是这样的——",
    "了解，您问的是——",
    "好的，我给您解释一下——",
    "关于这个问题——",
]


def detect_faq_question(user_msg: str, faq_items: list) -> dict:
    """检测用户消息是否匹配某个 FAQ 条目。

    使用关键词重叠度匹配，返回最佳匹配的 FAQ 条目，或 None。
    """
    if not faq_items or not user_msg.strip():
        return None

    best_item = None
    best_score = 0.0

    for item in faq_items:
        if isinstance(item, dict):
            q = item.get("question", "")
        else:
            q = getattr(item, "question", "")
        if not q:
            continue

        # 计算关键词重叠度
        score = _question_overlap(user_msg, q)
        if score > best_score:
            best_score = score
            best_item = item

    if best_score >= 0.25:
        return best_item
    return None


def _question_overlap(user_msg: str, faq_question: str) -> float:
    """计算用户消息与 FAQ 问题的关键词重叠度"""
    # 提取中文关键词（2字及以上片段）
    def _extract_keywords(text):
        # 移除常见问句前缀
        text = re.sub(r"^(我想问一下|请问|我想了解|问一下|那个|就是|对了|还有|那)", "", text)
        text = re.sub(r"[？?！!。，,、\s]+", "", text)
        if len(text) >= 2:
            return {text[i:i + 2] for i in range(len(text) - 1)}
        return set()

    kw_user = _extract_keywords(user_msg)
    kw_faq = _extract_keywords(faq_question)

    if not kw_user or not kw_faq:
        return 0.0

    intersection = kw_user & kw_faq
    union = kw_user | kw_faq
    return len(intersection) / len(union) if union else 0.0


def generate_faq_reply(faq_item: dict) -> str:
    """根据 FAQ 条目生成自然语言回复"""
    if isinstance(faq_item, dict):
        answer = faq_item.get("answer", "")
    else:
        answer = getattr(faq_item, "answer", "")

    if not answer:
        return "抱歉，这个问题我暂时无法回答，建议您联系站长咨询。"

    ack = random.choice(_FAQ_ACKS)
    # 清理答案文本，确保自然
    answer = answer.strip()
    if not answer.endswith(("。", "！", "？")):
        answer += "。"
    return f"{ack}{answer}"


# ---- 用户信号检测与响应 ----

# 用户信号模式：匹配到任一关键词即认为检测到对应信号
_USER_SIGNALS = {
    "interrupt": {
        "patterns": ["先不说", "等一下", "打断", "先别说", "换个话题", "岔开", "别说了"],
        "replies": [
            "好的，您请说，我听着呢。",
            "您说，有什么问题？",
            "好的，您想了解什么？",
            "请讲，我记一下。",
        ],
    },
    "impatient": {
        "patterns": ["快点", "简短", "没时间", "有完没完", "烦死", "别啰嗦", "说重点", "能快点"],
        "replies": [
            "好的，我尽量简短说。",
            "理解，我说快一点。",
            "抱歉，我长话短说。",
            "好的，那就简单跟您说一下。",
        ],
    },
    "reject": {
        "patterns": ["不需要", "别再打", "没兴趣", "不说了", "挂了", "拉黑", "别再打来"],
        "replies": [
            "理解，那我就不多打扰了。如果后续有需要可以联系我们，祝您生活愉快，再见。",
            "好的，感谢您的接听。如有需要随时联系我们，再见。",
            "明白了，那就不打扰您了，祝您顺利，再见。",
        ],
    },
    "confused": {
        "patterns": ["没听懂", "不明白", "再说一遍", "什么意思", "没跟上", "没听清", "能解释"],
        "replies": [
            "好的，我重新给您说一遍。",
            "明白了，我用更简单的方式说一下。",
            "抱歉没说清楚，我再解释一下。",
        ],
    },
}


def detect_user_signal(user_msg: str) -> tuple:
    """检测用户消息中的信号类型。

    Returns:
        (signal_type, reply) 如果检测到信号
        (None, None) 如果未检测到
    """
    if not user_msg or not user_msg.strip():
        return None, None

    for signal_type, config in _USER_SIGNALS.items():
        for pattern in config["patterns"]:
            if pattern in user_msg:
                reply = random.choice(config["replies"])
                return signal_type, reply

    return None, None


def generate_step_aware_reply(mock_step_idx: int, steps: dict) -> tuple:
    """生成步骤感知的 Mock SUT 回复，返回 (reply_text, new_step_idx)。

    与旧版的关键区别：
    - 步骤描述经过指令→口语转换，不再直接输出元指令文本
    - 标点经过规范化处理，杜绝 `。，` `。。` 等错误拼接
    - 话术模板更加自然多样
    """
    if not steps:
        return (
            random.choice([
                "好的，我了解了。请问还有什么可以帮您的？",
                "明白了，谢谢您的配合。还有什么需要确认的吗？",
                "嗯，您说的情况我记下了。还有其他问题吗？",
                "行，这些信息我这边都登记好了，您还有什么要补充的吗？",
                "清楚了，感谢您的反馈，还有其他需要吗？",
            ]),
            mock_step_idx,
        )

    step_ids = sorted(steps.keys())
    if mock_step_idx >= len(step_ids):
        return random.choice(_ENDING_PHRASES), mock_step_idx

    sid = step_ids[mock_step_idx]
    step = steps[sid]
    desc = step.get("description", str(sid))
    new_idx = mock_step_idx + 1

    reply = _format_speech(desc, random.random())

    # 终检：确保没有残留的标点错误
    reply = _clean_punctuation(reply)

    return reply, new_idx
