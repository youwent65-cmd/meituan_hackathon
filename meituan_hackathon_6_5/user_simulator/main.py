from __future__ import annotations

"""用户模拟器主入口

提供三种使用方式：
1. Python API：代码中直接调用
2. CLI：命令行运行
3. 集成模式：从指令解析器接收结构化数据
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

from .models import (
    UserProfile,
    TestCase,
    DialogueRecord,
    SimulationConfig,
)
from .profile_manager import ProfileManager
from .test_case_generator import TestCaseGenerator
from .dialogue_driver import DialogueDriver
from .recorder import ConversationRecorder


class UserSimulator:
    """用户模拟器主类

    封装完整的模拟管线：
    加载指令 → 生成画像 → 生成测试用例 → 执行模拟 → 保存记录

    Usage:
        # 方式1: Python API
        simulator = UserSimulator(config)
        records = simulator.run(parsed_instruction)

        # 方式2: 从解析器输出JSON加载
        simulator = UserSimulator(config)
        records = simulator.run_from_json("parsed_output.json")

        # 方式3: 连接真实SUT
        def my_sut(user_msg: str) -> str:
            return call_your_model(user_msg)
        simulator = UserSimulator(config, sut_callback=my_sut)
    """

    def __init__(
        self,
        config: Optional[SimulationConfig] = None,
        sut_callback: Optional[Callable[[str], str]] = None,
    ):
        self.config = config or SimulationConfig()
        self.sut_callback = sut_callback
        self.profile_manager = ProfileManager()
        self.test_gen = TestCaseGenerator()
        self.recorder = ConversationRecorder()

    def run(
        self,
        instruction: "ParsedInstruction",
        instruction_id: str = "",
    ) -> list[DialogueRecord]:
        """对一条指令运行完整的模拟流程

        Args:
            instruction: 解析后的结构化指令对象（ParsedInstruction 或 dict）
            instruction_id: 指令标识符（用于输出标识）

        Returns:
            对话记录列表
        """
        # 将 dict 转为 object-like 以兼容两种输入
        if isinstance(instruction, dict):
            instruction = self._dict_to_obj(instruction)

        inst_id = instruction_id or self._extract_id(instruction)

        # Step 1: 生成用户画像
        profiles = self.profile_manager.generate_profiles(instruction, num_profiles=6)

        # Step 2: 生成测试用例矩阵
        test_cases = self.test_gen.generate(instruction, profiles)

        # Step 3: 创建对话驱动器
        driver = DialogueDriver(self.config, instruction, self.sut_callback)

        # Step 4: 执行每条测试用例
        total = len(test_cases)
        for i, tc in enumerate(test_cases):
            # 为每个测试用例选择合适的画像（如果未设置）
            profile = tc.profile or profiles[0]

            record = driver.run_dialogue(
                instruction_id=inst_id,
                profile=profile,
                test_case=tc,
            )
            self.recorder.record(record)

        # Step 5: 保存记录
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.recorder.save_all(f"dialogue_records_{inst_id}_{timestamp}.json")
        summary_path = self.recorder.save_summary(f"simulation_summary_{inst_id}_{timestamp}.json")

        return self.recorder.get_all()

    def run_from_json(
        self,
        json_path: str,
    ) -> list[DialogueRecord]:
        """从指令解析器输出的 JSON 文件加载指令并运行模拟

        Args:
            json_path: parsed_output.json 的路径

        Returns:
            所有指令的对话记录列表
        """
        path = Path(json_path)
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            raw = path.read_text(encoding="gbk")
        data = json.loads(raw)
        instructions = data if isinstance(data, list) else [data]

        all_records = []
        for i, inst_dict in enumerate(instructions):
            inst_id = f"INST_{i+1:03d}"
            records = self.run(inst_dict, instruction_id=inst_id)
            all_records.extend(records)

        return all_records

    @staticmethod
    def _dict_to_obj(d: dict):
        """将 dict 递归转为嵌套对象，兼容 ParsedInstruction 接口"""
        class Obj:
            pass

        def _convert(val):
            if isinstance(val, dict):
                o = Obj()
                for k, v in val.items():
                    setattr(o, k, _convert(v))
                return o
            elif isinstance(val, list):
                return [_convert(item) for item in val]
            return val

        return _convert(d)

    @staticmethod
    def _extract_id(instruction) -> str:
        role = getattr(instruction, "role", "") or ""
        if "骑" in role:
            return "RIDER_001"
        elif "直播" in role or "Course" in role or "Customer" in role:
            return "COURSE_001"
        return "INST_001"

    @staticmethod
    def print_records(records: list[DialogueRecord]):
        """打印对话记录摘要"""
        print(f"\n{'='*60}")
        print(f"  用户模拟器 - 运行结果")
        print(f"{'='*60}")
        print(f"  总对话数: {len(records)}")

        by_dim = {}
        for r in records:
            by_dim[r.test_dimension] = by_dim.get(r.test_dimension, 0) + 1
        print(f"\n  各维度覆盖:")
        for dim, count in by_dim.items():
            print(f"    - {dim}: {count} 条")

        print(f"\n  详细记录:")
        for i, r in enumerate(records[:5]):  # 只显示前5条
            print(f"\n  --- 对话 {i+1}: {r.test_case_id} ---")
            print(f"    维度: {r.test_dimension} | 层: {r.layer_used}")
            print(f"    画像: {r.profile.describe() if r.profile else 'N/A'}")
            print(f"    轮次: {r.total_turns} | 结束原因: {r.end_reason}")
            for t in r.turns[:6]:  # 只显示前3轮
                role = "SUT " if t.role == "SUT" else "用户"
                print(f"    [{role}] {t.content[:60]}…" if len(t.content) > 60 else f"    [{role}] {t.content}")

        if len(records) > 5:
            print(f"\n  ... 还有 {len(records) - 5} 条记录")


# ---- CLI 入口 ----

def main():
    """命令行入口"""
    if len(sys.argv) < 2:
        print("用法: python -m user_simulator.main <parsed_output.json>")
        print("  从指令解析器输出的 JSON 文件运行用户模拟器")
        print()
        print("用法: python -m user_simulator.main <path> --mock")
        print("  使用 mock SUT 运行（不需要真实对话模型）")
        sys.exit(1)

    input_path = sys.argv[1]

    config = SimulationConfig(
        max_turns=15,
        llm_provider="mock",  # 默认 mock 模式
    )

    simulator = UserSimulator(config)
    records = simulator.run_from_json(input_path)

    # 显示结果
    UserSimulator.print_records(records)

    print(f"\n[OK] 对话记录已保存到 output/ 目录")


if __name__ == "__main__":
    main()
