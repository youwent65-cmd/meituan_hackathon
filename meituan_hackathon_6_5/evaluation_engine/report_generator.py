from __future__ import annotations

"""评测报告生成器 - 生成可解释、可量化的评测报告

输出格式：JSON（结构化数据）+ Markdown（人类可读）
"""

import json
import os
from datetime import datetime
from pathlib import Path

from .models import EvaluationResult, safe_attr


class ReportGenerator:
    """生成 Markdown + JSON 格式的评测报告"""

    def __init__(self, output_dir: str = "reports"):
        if isinstance(output_dir, str):
            output_dir = Path(output_dir)
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, result: EvaluationResult) -> str:
        """生成完整的评测报告，返回报告路径"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        inst_id = result.instruction_id or "UNKNOWN"

        output_dir = self.output_dir
        if isinstance(output_dir, str):
            output_dir = Path(output_dir)
            self.output_dir = output_dir

        # 1. 生成 Markdown 报告
        md_path = output_dir / f"evaluation_report_{inst_id}_{timestamp}.md"
        md_content = self._build_markdown(result)
        md_path.write_text(md_content, encoding="utf-8")

        # 2. 生成 JSON 报告
        json_path = output_dir / f"evaluation_report_{inst_id}_{timestamp}.json"
        json_content = json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
        json_path.write_text(json_content, encoding="utf-8")

        return str(md_path)

    def _build_markdown(self, r: EvaluationResult) -> str:
        """构建 Markdown 格式报告"""
        lines = []

        # 标题
        lines.append("# 外呼任务对话模型 — 指令遵循能力评测报告")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # 一、评测概览
        lines.append("## 一、评测概览")
        lines.append("")
        lines.append(f"| 项目 | 内容 |")
        lines.append(f"|------|------|")
        lines.append(f"| 指令 ID | {r.instruction_id} |")
        lines.append(f"| 角色设定 | {r.instruction_role[:60]}… |" if len(r.instruction_role) > 60 else f"| 角色设定 | {r.instruction_role} |")
        lines.append(f"| 任务目标 | {r.instruction_task[:60]}… |" if len(r.instruction_task) > 60 else f"| 任务目标 | {r.instruction_task} |")
        lines.append(f"| 测试用例数 | {r.total_cases} |")
        lines.append(f"| **综合得分** | **{r.overall_score:.1f} / 100** |")
        lines.append(f"| **等级** | **{r.grade}** |")
        mode_label = "LLM增强" if r.simulation_mode == "llm" else "Mock"
        lines.append(f"| **运行模式** | {mode_label} |")
        # LLM Judge 状态
        ls = r.llm_status
        if ls.get("judge_enabled"):
            if ls.get("judge_used"):
                lines.append(f"| **LLM-as-Judge** | ✅ 已启用（评分: {r.naturalness_score.raw_metrics.get('llm_judge_score', 'N/A')}） |")
            else:
                error_msg = ls.get("judge_error", "未知错误")
                lines.append(f"| **LLM-as-Judge** | ⚠️ 已启用但未生效 — {error_msg} |")
        else:
            lines.append(f"| **LLM-as-Judge** | 未启用 |")
        lines.append("")

        # 等级说明
        grade_desc = {"A": "优秀", "B": "良好", "C": "合格", "D": "待改进", "F": "不合格"}
        lines.append(f"**评级**: {grade_desc.get(r.grade, 'N/A')}")
        lines.append("")

        # 二、分维度得分
        lines.append("## 二、分维度得分")
        lines.append("")
        lines.append("| 维度 | 权重 | 得分 | 状态 |")
        lines.append("|------|------|------|------|")
        for dim in [r.flow_score, r.constraint_score, r.faq_score, r.naturalness_score, r.task_score]:
            if dim.weight == 0:
                status = "⚪"
                score_text = "N/A"
            else:
                status = "✅" if dim.score >= 80 else ("⚠️" if dim.score >= 60 else "❌")
                score_text = f"{dim.score:.1f} / 100"
            lines.append(f"| {dim.label_cn} | {dim.weight:.0%} | {score_text} | {status} |")
        lines.append("")

        # 得分柱状图 (ASCII)
        lines.append("```")
        for dim in [r.flow_score, r.constraint_score, r.faq_score, r.naturalness_score, r.task_score]:
            if dim.weight == 0:
                bar = "·" * 20
                label = f"{dim.label_cn:　<8s}  |{bar}| N/A"
            else:
                bar_len = int(dim.score / 5)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                label = f"{dim.label_cn:　<8s}  |{bar}| {dim.score:.1f}"
            lines.append(f"  {label}")
        lines.append("```")
        lines.append("")

        # 三、详细分析
        lines.append("## 三、详细分析")
        lines.append("")

        # 3.1 流程执行分析
        lines.append("### 3.1 流程执行分析")
        lines.append("")
        fm = r.flow_score.raw_metrics
        lines.append(f"- **必需步骤数**: {fm.get('total_required_steps', 'N/A')}")
        lines.append(f"- **平均步骤覆盖率**: {fm.get('avg_step_coverage', 0):.1%}")
        lines.append(f"- **步骤顺序正确率**: {fm.get('order_correctness_rate', 0):.1%}")
        lines.append(f"- **步骤遗漏**: {fm.get('total_misses', 0)} 次")
        lines.append(f"- **步骤错序**: {fm.get('total_order_errors', 0)} 次")
        lines.append("")

        flow_violations = [v for v in r.flow_score.violations if v.violation_type == "step_miss"]
        if flow_violations:
            lines.append("**步骤遗漏详情**:")
            lines.append("")
            for v in flow_violations[:5]:
                lines.append(f"- **用例 {v.test_case_id}**: ❌ {v.explanation}")
            lines.append("")

        # 3.2 约束违规明细
        lines.append("### 3.2 约束违规明细")
        lines.append("")
        cm = r.constraint_score.raw_metrics
        lines.append(f"- **总约束数**: {cm.get('total_constraints', 0)} (硬约束 {cm.get('hard_constraints', 0)} + 软约束 {cm.get('soft_constraints', 0)})")
        lines.append(f"- **总违规数**: {cm.get('total_violations', 0)}")
        lines.append("")

        if cm.get("violation_by_type"):
            lines.append("**违规类型分布**:")
            lines.append("")
            for vtype, count in sorted(cm["violation_by_type"].items(), key=lambda x: -x[1]):
                lines.append(f"  - {vtype}: {count} 次")
            lines.append("")

        constraint_vs = r.constraint_score.violations[:10]
        if constraint_vs:
            lines.append("**典型违规案例**:")
            lines.append("")
            for i, v in enumerate(constraint_vs[:5]):
                lines.append(f"**案例 {i+1}** — {v.violation_type} (严重度: {v.severity})")
                lines.append(f"- 用例: {v.test_case_id}, 第 {v.turn_number} 轮")
                lines.append(f"- SUT 回复: 「{v.sut_message[:60]}…」" if len(v.sut_message) > 60 else f"- SUT 回复: 「{v.sut_message}」")
                lines.append(f"- 说明: {v.explanation}")
                lines.append("")

        # 3.3 FAQ 回答质量
        lines.append("### 3.3 FAQ 回答质量")
        lines.append("")
        if r.faq_score.weight == 0:
            lines.append(f"**该维度不适用(N/A)** — {r.faq_score.details}")
            lines.append("")
        else:
            fm2 = r.faq_score.raw_metrics
            lines.append(f"- **FAQ 条目总数**: {fm2.get('faq_items_total', 0)}")
            lines.append(f"- **被触发次数**: {fm2.get('faq_triggered_count', 0)}")
            lines.append(f"- **召回率**: {fm2.get('recall_rate', 0):.1%}")
            lines.append(f"- **平均精确度**: {fm2.get('avg_precision', 0):.1%}")
            lines.append(f"- **疑似幻觉**: {fm2.get('hallucination_count', 0)} 次")
            lines.append("")

        faq_vs = r.faq_score.violations[:5]
        if faq_vs:
            lines.append("**FAQ 回答问题**:")
            lines.append("")
            for i, v in enumerate(faq_vs):
                lines.append(f"**案例 {i+1}** — {v.violation_type}")
                lines.append(f"- 期望答案: 「{v.expected[:80]}…」" if len(v.expected) > 80 else f"- 期望答案: 「{v.expected}」")
                lines.append(f"- 实际回答: 「{v.actual[:80]}…」" if len(v.actual) > 80 else f"- 实际回答: 「{v.actual}」")
                lines.append(f"- {v.explanation}")
                lines.append("")

        # 3.4 对话自然度
        lines.append("### 3.4 对话自然度")
        lines.append("")
        nm = r.naturalness_score.raw_metrics
        lines.append(f"- **回应多样性 (1-相似度)**: {nm.get('avg_diversity', 0):.1%}")
        lines.append(f"- **平均过渡语数/对话**: {nm.get('avg_transition_phrases', 0):.1f}")
        lines.append(f"- **书面语问题/对话**: {nm.get('avg_formal_issues', 0):.1f}")
        if "rule_score" in nm:
            lines.append(f"- **规则评分**: {nm['rule_score']:.1f}")
        if "llm_judge_score" in nm:
            lines.append(f"- **LLM-as-Judge 评分**: {nm['llm_judge_score']:.1f} （抽样 {nm.get('llm_samples_evaluated', 0)} 条）")
            lines.append(f"- **最终得分**: 规则40% + LLM60% = {r.naturalness_score.score:.1f}")
        lines.append("")

        # 四、典型案例
        lines.append("## 四、典型对话案例")
        lines.append("")
        bc = r.best_case
        wc = r.worst_case
        lines.append("### 最佳案例")
        lines.append(f"- 用例 ID: {bc.get('test_case_id', 'N/A')}")
        lines.append(f"- 测试维度: {bc.get('test_dimension', 'N/A')}")
        lines.append(f"- 总轮次: {bc.get('total_turns', 'N/A')}, 结束原因: {bc.get('end_reason', 'N/A')}")
        lines.append(f"```\n{bc.get('conversation_snippet', 'N/A')}\n```")
        lines.append("")
        lines.append("### 最差案例")
        lines.append(f"- 用例 ID: {wc.get('test_case_id', 'N/A')}")
        lines.append(f"- 测试维度: {wc.get('test_dimension', 'N/A')}")
        lines.append(f"- 总轮次: {wc.get('total_turns', 'N/A')}, 结束原因: {wc.get('end_reason', 'N/A')}")
        lines.append(f"```\n{wc.get('conversation_snippet', 'N/A')}\n```")
        lines.append("")

        # 五、改进建议
        lines.append("## 五、改进建议")
        lines.append("")
        for item in r.improvement_items:
            lines.append(f"- {item}")
        lines.append("")

        lines.append("---")
        lines.append(f"*报告由评测引擎自动生成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")

        return "\n".join(lines)
