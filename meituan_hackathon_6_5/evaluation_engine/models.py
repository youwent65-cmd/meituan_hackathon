from __future__ import annotations

"""评测引擎数据模型 - 评估结果、证据、报告结构"""

from dataclasses import dataclass, field
from typing import Optional


def safe_attr(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


# ============================================================
# 单维度评估结果
# ============================================================

@dataclass
class DimensionScore:
    """单个评测维度的得分"""
    dimension: str = ""             # flow | constraint | faq | naturalness | task
    label_cn: str = ""              # 中文标签
    weight: float = 0.0             # 权重 (0.0 ~ 1.0)
    score: float = 100.0            # 本维度得分 (0 ~ 100)
    raw_metrics: dict = field(default_factory=dict)       # 原始指标值
    violations: list[Violation] = field(default_factory=list)  # 违规/扣分详情
    details: str = ""               # 维度分析概要


@dataclass
class Violation:
    """单条违规/扣分证据"""
    dimension: str = ""                 # 属于哪个维度
    violation_type: str = ""            # 违规类型
    severity: str = "medium"            # high / medium / low
    deduction: float = 0.0              # 扣分值
    test_case_id: str = ""              # 发生在哪条测试用例
    turn_number: int = 0                # 发生在第几轮
    sut_message: str = ""               # SUT 的实际回复
    expected: str = ""                  # 期望的行为/回答
    actual: str = ""                    # 实际的行为/回答
    constraint_raw: str = ""            # 违反的原始约束文本
    explanation: str = ""               # 可解释的说明


# ============================================================
# 综合评估结果
# ============================================================

@dataclass
class EvaluationResult:
    """一条指令的完整评测结果"""
    instruction_id: str = ""
    instruction_role: str = ""          # Role 描述
    instruction_task: str = ""          # Task 描述
    test_time: str = ""
    total_cases: int = 0

    # 分维度得分
    flow_score: DimensionScore = field(default_factory=DimensionScore)
    constraint_score: DimensionScore = field(default_factory=DimensionScore)
    faq_score: DimensionScore = field(default_factory=DimensionScore)
    naturalness_score: DimensionScore = field(default_factory=DimensionScore)
    task_score: DimensionScore = field(default_factory=DimensionScore)

    # 综合
    overall_score: float = 0.0
    grade: str = ""                     # A / B / C / D / F

    # LLM 状态
    simulation_mode: str = "mock"  # "mock" | "llm"
    llm_status: dict = field(default_factory=lambda: {
        "judge_enabled": False,
        "judge_used": False,
        "judge_error": None,
    })

    # 案例
    best_case: dict = field(default_factory=dict)
    worst_case: dict = field(default_factory=dict)
    improvement_items: list[str] = field(default_factory=list)

    def compute_overall(self):
        """计算加权总分，自动处理 N/A 维度（weight=0）的权重重新分配"""
        dims = [self.flow_score, self.constraint_score, self.faq_score,
                self.naturalness_score, self.task_score]
        default_weights = [0.30, 0.30, 0.20, 0.10, 0.10]

        # 分离活跃维度和N/A维度
        active_dims = []
        na_dims = []
        for i, d in enumerate(dims):
            if d.weight > 0:
                active_dims.append(d)
            else:
                na_dims.append((i, d))

        if not active_dims:
            # 所有维度都为N/A：使用默认权重
            for d, w in zip(dims, default_weights):
                d.weight = w
            active_dims = list(dims)
            na_dims = []

        # 将 N/A 维度的权重按比例重新分配给活跃维度
        na_weight_sum = sum(default_weights[i] for i, _ in na_dims)
        if na_weight_sum > 0 and active_dims:
            active_weight_sum = sum(d.weight for d in active_dims)
            for d in active_dims:
                # 按活跃维度的原始权重比例分配N/A权重
                d_original_weight = d.weight
                d.weight = d_original_weight + na_weight_sum * (d_original_weight / active_weight_sum)

        self.overall_score = sum(d.score * d.weight for d in active_dims)
        if self.overall_score >= 90:
            self.grade = "A"
        elif self.overall_score >= 75:
            self.grade = "B"
        elif self.overall_score >= 60:
            self.grade = "C"
        elif self.overall_score >= 40:
            self.grade = "D"
        else:
            self.grade = "F"

    def to_dict(self) -> dict:
        return {
            "instruction_id": self.instruction_id,
            "instruction_role": self.instruction_role,
            "instruction_task": self.instruction_task,
            "test_time": self.test_time,
            "total_cases": self.total_cases,
            "overall_score": round(self.overall_score, 1),
            "grade": self.grade,
            "dimensions": {
                "flow": self._dim_to_dict(self.flow_score),
                "constraint": self._dim_to_dict(self.constraint_score),
                "faq": self._dim_to_dict(self.faq_score),
                "naturalness": self._dim_to_dict(self.naturalness_score),
                "task": self._dim_to_dict(self.task_score),
            },
            "simulation_mode": self.simulation_mode,
            "llm_status": self.llm_status,
            "best_case": self.best_case,
            "worst_case": self.worst_case,
            "improvement_items": self.improvement_items,
        }

    @staticmethod
    def _dim_to_dict(d: DimensionScore) -> dict:
        return {
            "label": d.label_cn,
            "weight": d.weight,
            "score": round(d.score, 1),
            "raw_metrics": d.raw_metrics,
            "violations_count": len(d.violations),
            "violations": [v.__dict__ for v in d.violations[:10]],
            "details": d.details,
        }


@dataclass
class EvalConfig:
    """评测引擎全局配置"""
    # 评分阈值
    length_tolerance: int = 5            # 字数容差
    similarity_threshold: float = 0.7    # FAQ 相似度阈值
    repeat_similarity_threshold: float = 0.85  # 重复检测阈值

    # 扣分配置
    hard_constraint_deduction: float = 10.0   # 硬约束违规单次扣分
    soft_constraint_deduction: float = 3.0    # 软约束违规单次扣分
    step_miss_deduction: float = 8.0          # 步骤遗漏扣分
    step_order_deduction: float = 5.0         # 步骤错序扣分
    faq_miss_deduction: float = 6.0           # FAQ 未命中扣分
    hallucination_deduction: float = 15.0     # 幻觉严重扣分

    # LLM 配置
    llm_enabled: bool = False
    llm_provider: str = "anthropic"     # "anthropic" / "deepseek" / "openai"
    llm_model: str = "claude-sonnet-4-6"
    llm_api_key: str = ""
    llm_base_url: str = ""              # 自定义 API 端点（DeepSeek/OpenAI 兼容）

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}
