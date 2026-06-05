#!/usr/bin/env python3
"""评测系统 Web UI 后端 —— Flask 应用"""

from __future__ import annotations

import json
import os
import sys
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, request, jsonify, send_file

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import PipelineConfig

app = Flask(
    __name__,
    template_folder=str(PROJECT_ROOT / "templates"),
    static_folder=str(PROJECT_ROOT / "static"),
)

UPLOAD_DIR = PROJECT_ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

ARCHIVE_DIR = PROJECT_ROOT / "archive"
ARCHIVE_DIR.mkdir(exist_ok=True)

tasks: dict[str, "EvalTask"] = {}


class EvalTask:
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.status = "pending"
        self.progress = 0
        self.phase = ""
        self.result = None
        self.error = None
        self.archive_paths: list[Path] = []


@app.route("/")
def index():
    sample_exists = (
        PROJECT_ROOT / "instruction-parser" / "data" / "parsed_output.json"
    ).exists()
    return render_template("index.html", sample_exists=sample_exists)


@app.route("/api/run", methods=["POST"])
def run_evaluation():
    file = request.files.get("file")
    use_sample = request.form.get("use_sample", "false") == "true"

    if not file and not use_sample:
        return jsonify({"error": "请上传指令文件或使用样例"}), 400

    if file and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in (".xlsx", ".xls", ".json", ".md"):
            return jsonify({"error": f"不支持的文件格式: {ext}"}), 400
        file_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
        file.save(str(file_path))
    else:
        file_path = PROJECT_ROOT / "instruction-parser" / "data" / "parsed_output.json"

    profiles = min(max(int(request.form.get("profiles", 6)), 2), 12)
    max_turns = min(max(int(request.form.get("max_turns", 15)), 5), 30)
    use_llm = request.form.get("use_llm", "false") == "true"
    llm_provider = request.form.get("llm_provider", "deepseek").strip()
    llm_key = request.form.get("llm_key", "").strip()
    llm_base_url = request.form.get("llm_base_url", "").strip()

    output_dir = str(PROJECT_ROOT / "output")
    report_dir = str(PROJECT_ROOT / "reports")

    task_id = uuid.uuid4().hex[:12]
    task = EvalTask(task_id)
    tasks[task_id] = task

    thread = threading.Thread(
        target=_run_pipeline,
        args=(
            task,
            str(file_path),
            profiles,
            max_turns,
            use_llm,
            llm_provider,
            llm_key,
            llm_base_url,
            output_dir,
            report_dir,
        ),
        daemon=True,
    )
    thread.start()

    return jsonify({"task_id": task_id})


@app.route("/api/status/<task_id>")
def task_status(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    return jsonify(
        {
            "status": task.status,
            "progress": task.progress,
            "phase": task.phase,
            "error": task.error,
        }
    )


@app.route("/api/result/<task_id>")
def task_result(task_id: str):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    if task.status != "completed":
        return jsonify({"error": "任务未完成"}), 400
    return jsonify(task.result)


@app.route("/api/report/<task_id>/<fmt>")
def download_report(task_id: str, fmt: str):
    task = tasks.get(task_id)
    if not task:
        return jsonify({"error": "任务不存在"}), 404
    for rp in task.archive_paths:
        if rp.suffix.lstrip(".") == fmt:
            return send_file(str(rp), as_attachment=True, download_name=rp.name)
    return jsonify({"error": "报告文件不存在"}), 404


@app.route("/api/debug-mock")
def debug_mock():
    """诊断端点：检查当前加载的 mock SUT 版本"""
    import user_simulator.dialogue_driver as dd
    import inspect
    src = inspect.getsource(dd.DialogueDriver._mock_sut)
    return jsonify({
        "mock_sut_source": src[:300],
        "has_v2": "mock_sut_v2" in src,
        "has_step_aware": "generate_step_aware_reply" in src,
        "has_old_replies": "我了解了" in src,
    })

@app.route("/api/sample-report")
def sample_report():
    """返回最近一次样例报告的 Markdown 内容，供 UI 预览"""
    report_dir = PROJECT_ROOT / "reports"
    if not report_dir.exists():
        return jsonify({"content": ""})
    md_files = sorted(report_dir.glob("evaluation_report_*.md"), key=os.path.getmtime, reverse=True)
    if not md_files:
        return jsonify({"content": ""})
    try:
        content = md_files[0].read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = md_files[0].read_text(encoding="gbk")
    return jsonify({"content": content})


def _run_pipeline(
    task: EvalTask,
    file_path: str,
    profiles: int,
    max_turns: int,
    use_llm: bool,
    llm_provider: str,
    llm_key: str,
    llm_base_url: str,
    output_dir: str,
    report_dir: str,
):
    try:
        task.status = "running"

        task.phase = "指令解析中..."
        task.progress = 15

        # 自动选择默认模型
        model_defaults = {"deepseek": "deepseek-chat", "openai": "gpt-4o", "anthropic": "claude-sonnet-4-6"}
        llm_model = model_defaults.get(llm_provider, "claude-sonnet-4-6")

        config = PipelineConfig(
            num_profiles=profiles,
            max_turns=max_turns,
            output_dir=output_dir,
            report_dir=report_dir,
            use_llm_fallback=use_llm,
            llm_provider=llm_provider if use_llm else "mock",
            llm_model=llm_model,
            llm_judge_enabled=use_llm,
            llm_api_key=llm_key,
            llm_base_url=llm_base_url,
        )

        import importlib
        import user_simulator.dialogue_driver as dd_mod
        import user_simulator.layers.l1_rule_engine as l1_mod
        import evaluation_engine.flow_evaluator as fe_mod
        import evaluation_engine.task_evaluator as te_mod
        importlib.reload(l1_mod)
        importlib.reload(dd_mod)
        importlib.reload(fe_mod)
        importlib.reload(te_mod)

        from main import InstructionFollowEvaluator

        evaluator = InstructionFollowEvaluator(config)

        task.phase = "用户模拟中..."
        task.progress = 40

        raw_result = evaluator.run(file_path)

        task.phase = "生成评测图表..."
        task.progress = 75

        results_list = []
        for r in raw_result.get("results", []):
            rd = r.to_dict() if hasattr(r, "to_dict") else r
            results_list.append(rd)

        task.phase = "归档报告中..."
        task.progress = 90
        archive_paths = _archive_reports(results_list, report_dir, output_dir)

        task.result = {
            "summary": {
                "instructions": raw_result.get("instructions", 0),
                "total_records": raw_result.get("total_records", 0),
                "elapsed": raw_result.get("elapsed", 0),
            },
            "instructions": results_list,
            "archive_paths": [str(p) for p in archive_paths],
        }
        task.archive_paths = archive_paths
        task.status = "completed"
        task.progress = 100
        task.phase = "评估完成"

    except Exception as e:
        import traceback

        task.status = "failed"
        task.error = str(e)
        task.phase = f"发生错误"
        traceback.print_exc()


def _archive_reports(
    results_list: list[dict], report_dir: str, output_dir: str
) -> list[Path]:
    date_str = datetime.now().strftime("%Y-%m-%d")
    time_str = datetime.now().strftime("%H%M%S")
    archive_paths: list[Path] = []

    report_path = Path(report_dir)
    output_path = Path(output_dir)

    for result in results_list:
        inst_id = result.get("instruction_id", "UNKNOWN")
        archive_subdir = ARCHIVE_DIR / date_str / f"{inst_id}_{time_str}"
        archive_subdir.mkdir(parents=True, exist_ok=True)

        for name_glob, ext in [
            ("evaluation_report", "md"),
            ("evaluation_report", "json"),
        ]:
            candidates = sorted(
                report_path.glob(f"{name_glob}_{inst_id}_*.{ext}"),
                key=os.path.getmtime,
                reverse=True,
            )
            for src in candidates[:1]:
                dst = archive_subdir / src.name
                shutil.copy2(str(src), str(dst))
                archive_paths.append(dst)

        for name_glob in ["evaluation_summary", "all_dialogue_records"]:
            for ext in ["md", "json"]:
                candidates = sorted(
                    output_path.glob(f"{name_glob}_*.{ext}"),
                    key=os.path.getmtime,
                    reverse=True,
                )
                for src in candidates[:1]:
                    dst = archive_subdir / src.name
                    shutil.copy2(str(src), str(dst))
                    archive_paths.append(dst)

    return archive_paths


if __name__ == "__main__":
    print(f"\n{'=' * 60}")
    print(f"  外呼任务对话模型 — 指令遵循能力评估系统 Web UI")
    print(f"  访问地址: http://127.0.0.1:5000")
    print(f"{'=' * 60}\n")
    app.run(debug=False, host="127.0.0.1", port=5000, threaded=True)
