from __future__ import annotations

"""对话记录器 - 结构化存储全量对话"""

import json
import time
from pathlib import Path
from datetime import datetime

from .models import DialogueRecord


class ConversationRecorder:
    """将模拟对话保存为结构化记录，供评测引擎使用"""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.records: list[DialogueRecord] = []

    def record(self, dr: DialogueRecord):
        """添加一条对话记录"""
        dr.created_at = datetime.now().isoformat()
        self.records.append(dr)

    def save_all(self, filename: str = "dialogue_records.json") -> str:
        """保存所有记录到 JSON 文件"""
        output_path = self.output_dir / filename
        data = [r.to_dict() for r in self.records]
        output_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(output_path)

    def save_summary(self, filename: str = "simulation_summary.json") -> str:
        """保存模拟摘要"""
        output_path = self.output_dir / filename
        summary = {
            "total_records": len(self.records),
            "by_dimension": {},
            "by_layer": {},
            "end_reasons": {},
            "records": [],
        }
        for r in self.records:
            summary["by_dimension"][r.test_dimension] = (
                summary["by_dimension"].get(r.test_dimension, 0) + 1
            )
            summary["by_layer"][r.layer_used] = (
                summary["by_layer"].get(r.layer_used, 0) + 1
            )
            summary["end_reasons"][r.end_reason] = (
                summary["end_reasons"].get(r.end_reason, 0) + 1
            )
            summary["records"].append({
                "instruction_id": r.instruction_id,
                "test_case_id": r.test_case_id,
                "test_dimension": r.test_dimension,
                "layer_used": r.layer_used,
                "total_turns": r.total_turns,
                "end_reason": r.end_reason,
            })
        output_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(output_path)

    def get_all(self) -> list[DialogueRecord]:
        return self.records

    def clear(self):
        self.records.clear()
