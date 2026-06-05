from __future__ import annotations

"""全局配置 — 统一管理三个模块的参数"""

from dataclasses import dataclass, field


@dataclass
class PipelineConfig:
    """端到端评估管线的全局配置"""

    # ---- 指令解析器 ----
    use_llm_fallback: bool = False          # 启用 LLM 补全解析

    # ---- 用户模拟器 ----
    max_turns: int = 15                     # 最大对话轮次
    num_profiles: int = 6                   # 用户画像数量
    sut_provider: str = "mock"              # SUT 提供方式: "mock" / "callback"
    llm_provider: str = "mock"              # "mock" / "anthropic" / "deepseek" / "openai"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str = ""
    llm_base_url: str = ""                  # 自定义 API 端点（DeepSeek/OpenAI 兼容）
    llm_temperature: float = 0.8
    llm_timeout: int = 30

    # ---- 评测引擎 ----
    length_tolerance: int = 5               # 字数容差
    faq_similarity_threshold: float = 0.7   # FAQ 相似度阈值
    hard_constraint_deduction: float = 10.0
    soft_constraint_deduction: float = 3.0
    step_miss_deduction: float = 8.0
    hallucination_deduction: float = 15.0
    llm_judge_enabled: bool = False         # LLM-as-Judge

    # ---- 输出 ----
    output_dir: str = "output"              # 对话记录输出目录
    report_dir: str = "reports"             # 评测报告输出目录

    def to_dict(self) -> dict:
        return {
            "max_turns": self.max_turns,
            "num_profiles": self.num_profiles,
            "sut_provider": self.sut_provider,
            "llm_provider": self.llm_provider,
            "use_llm_fallback": self.use_llm_fallback,
            "llm_judge_enabled": self.llm_judge_enabled,
        }
