"use strict";

// ============================================================
// DOM References
// ============================================================
const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const uploadZone = $("#upload-zone");
const fileInput = $("#file-input");
const filenameDisplay = $("#filename-display");
const btnRun = $("#btn-run");
const btnSample = $("#btn-sample");
const inputSection = $("#input-section");
const progressSection = $("#progress-section");
const resultSection = $("#result-section");
const headerStatus = $("#header-status");
const progressCircle = $("#progress-circle");
const progressText = $("#progress-text");
const progressPhase = $("#progress-phase");
const overviewRow = $("#overview-row");
const instTabs = $("#inst-tabs");
const violationList = $("#violation-list");
const violationCount = $("#violation-count");
const reportPreview = $("#report-preview");
const improvementList = $("#improvement-list");

const profilesSlider = $("#profiles");
const turnsSlider = $("#max-turns");
const llmToggle = $("#use-llm");
const llmKeyGroup = $("#llm-key-group");
const llmKeyGroup2 = $("#llm-key-group2");
const llmBaseUrlGroup = $("#llm-base-url-group");
const llmProviderSelect = $("#llm-provider");
const llmKeyInput = $("#llm-key");
const llmBaseUrlInput = $("#llm-base-url");

const CIRCUMFERENCE = 2 * Math.PI * 52; // ~326.73

let selectedFile = null;
let currentTaskId = null;
let pollTimer = null;
let allResults = null;
let currentInstIdx = 0;
let charts = {};

// ============================================================
// File Upload
// ============================================================
uploadZone.addEventListener("click", () => fileInput.click());

uploadZone.addEventListener("dragover", (e) => {
  e.preventDefault();
  uploadZone.classList.add("drag-over");
});
uploadZone.addEventListener("dragleave", () => {
  uploadZone.classList.remove("drag-over");
});
uploadZone.addEventListener("drop", (e) => {
  e.preventDefault();
  uploadZone.classList.remove("drag-over");
  const files = e.dataTransfer.files;
  if (files.length > 0) handleFile(files[0]);
});

fileInput.addEventListener("change", () => {
  if (fileInput.files.length > 0) handleFile(fileInput.files[0]);
});

function handleFile(file) {
  const ext = file.name.split(".").pop().toLowerCase();
  const valid = ["xlsx", "xls", "json", "md"];
  if (!valid.includes(ext)) {
    alert(`不支持的文件格式: .${ext}，请选择 .xlsx / .json / .md 文件`);
    return;
  }
  selectedFile = file;
  filenameDisplay.textContent = `已选择: ${file.name}`;
  btnRun.disabled = false;
  uploadZone.style.borderColor = "var(--success)";
}

// Sample file
if (btnSample) {
  btnSample.addEventListener("click", () => {
    selectedFile = null;
    filenameDisplay.textContent = "已选择: 样例文件 (parsed_output.json)";
    btnRun.disabled = false;
    uploadZone.style.borderColor = "var(--success)";
  });
}

// Config sliders
profilesSlider.addEventListener("input", () => {
  $("#val-profiles").textContent = profilesSlider.value;
});
turnsSlider.addEventListener("input", () => {
  $("#val-turns").textContent = turnsSlider.value;
});
llmToggle.addEventListener("change", () => {
  const show = llmToggle.checked ? "flex" : "none";
  llmKeyGroup.style.display = show;
  llmKeyGroup2.style.display = show;
  llmBaseUrlGroup.style.display = show;
});

// Run button
btnRun.addEventListener("click", startEvaluation);

// ============================================================
// API Calls
// ============================================================
function startEvaluation() {
  const formData = new FormData();

  if (selectedFile) {
    formData.append("file", selectedFile);
  } else if (btnSample && filenameDisplay.textContent.includes("样例")) {
    formData.append("use_sample", "true");
  } else {
    alert("请先选择指令文件");
    return;
  }

  formData.append("profiles", profilesSlider.value);
  formData.append("max_turns", turnsSlider.value);
  formData.append("use_llm", llmToggle.checked);
  formData.append("llm_provider", llmProviderSelect.value);
  formData.append("llm_key", llmKeyInput.value);
  formData.append("llm_base_url", llmBaseUrlInput.value);

  // Switch UI to progress
  inputSection.style.display = "none";
  resultSection.style.display = "none";
  progressSection.style.display = "block";
  setStatus("busy", "评估中...");
  setProgress(0, "正在提交...");

  fetch("/api/run", { method: "POST", body: formData })
    .then((r) => r.json())
    .then((data) => {
      if (data.error) {
        showError(data.error);
        return;
      }
      currentTaskId = data.task_id;
      pollStatus();
    })
    .catch((err) => showError("请求失败: " + err.message));
}

function pollStatus() {
  if (!currentTaskId) return;

  fetch(`/api/status/${currentTaskId}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "completed") {
        setProgress(100, "评估完成");
        setStatus("done", "就绪");
        setTimeout(() => loadResults(), 400);
      } else if (data.status === "failed") {
        showError(data.error || "评估过程中发生未知错误");
      } else {
        setProgress(data.progress || 0, data.phase || "运行中...");
        pollTimer = setTimeout(pollStatus, 800);
      }
    })
    .catch((err) => {
      pollTimer = setTimeout(pollStatus, 1500);
    });
}

function loadResults() {
  fetch(`/api/result/${currentTaskId}`)
    .then((r) => r.json())
    .then((data) => {
      allResults = data;
      progressSection.style.display = "none";
      resultSection.style.display = "flex";
      resultSection.style.flexDirection = "column";
      resultSection.style.gap = "20px";
      // 等待 DOM 布局完成后再渲染图表，确保 ECharts 容器尺寸有效
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          renderResults();
        });
      });
    })
    .catch((err) => showError("加载结果失败: " + err.message));
}

function showError(msg) {
  setStatus("error", "错误");
  progressSection.style.display = "none";
  inputSection.style.display = "block";
  alert("评估失败: " + msg);
}

// ============================================================
// Status Helpers
// ============================================================
function setStatus(state, text) {
  const dot = headerStatus.querySelector(".status-dot");
  dot.className = "status-dot";
  if (state === "busy") dot.classList.add("busy");
  if (state === "error") dot.classList.add("error");
  headerStatus.querySelector("span:last-child").textContent = text;
}

function setProgress(pct, phase) {
  const offset = CIRCUMFERENCE - (pct / 100) * CIRCUMFERENCE;
  progressCircle.style.strokeDashoffset = offset;
  progressText.textContent = Math.round(pct) + "%";
  progressPhase.textContent = phase;
}

// ============================================================
// Render Results
// ============================================================
function renderResults() {
  const instructions = allResults.instructions || [];
  if (instructions.length === 0) return;

  renderOverview(instructions);
  renderTabs(instructions);
  switchInstruction(0);
}

// --------------------------------------------------
// Overview cards
// --------------------------------------------------
function renderOverview(instructions) {
  const s = allResults.summary || {};
  const avgScore =
    instructions.reduce((sum, r) => sum + (r.overall_score || 0), 0) /
    (instructions.length || 1);

  overviewRow.innerHTML = `
    <div class="stat-card">
      <div class="stat-value" style="color:var(--primary)">${instructions.length}</div>
      <div class="stat-label">测试指令数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color:var(--primary)">${s.total_records || 0}</div>
      <div class="stat-label">对话记录数</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color:${scoreColor(avgScore)}">${avgScore.toFixed(1)}</div>
      <div class="stat-label">平均综合得分</div>
    </div>
    <div class="stat-card">
      <div class="stat-value" style="color:var(--text-secondary)">${s.elapsed ? s.elapsed.toFixed(1) + 's' : 'N/A'}</div>
      <div class="stat-label">评估耗时</div>
    </div>
  `;
}

// --------------------------------------------------
// Instruction tabs
// --------------------------------------------------
function renderTabs(instructions) {
  instTabs.innerHTML = instructions
    .map(
      (inst, i) =>
        `<button class="tab-btn${i === 0 ? " active" : ""}" data-idx="${i}">
          ${inst.instruction_id || "INST_" + (i + 1)}
        </button>`
    )
    .join("");

  instTabs.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      instTabs.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      switchInstruction(parseInt(btn.dataset.idx));
    });
  });
}

// --------------------------------------------------
// Switch to instruction
// --------------------------------------------------
function switchInstruction(idx) {
  currentInstIdx = idx;
  const inst = (allResults.instructions || [])[idx];
  if (!inst) return;

  renderGauge(inst);
  renderRadar(inst);
  renderBar(inst);
  renderViolations(inst);
  renderImprovements(inst);
  loadReportPreview();
}

// ============================================================
// Charts
// ============================================================
const DIM_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#3b82f6", "#ec4899"];
const DIM_KEYS = ["flow", "constraint", "faq", "naturalness", "task"];
const DIM_LABELS = ["流程完整度", "约束遵循度", "FAQ准确性", "对话自然度", "任务完成度"];
const DIM_WEIGHTS = [0.30, 0.30, 0.20, 0.10, 0.10];
const GRADE_COLORS = {
  A: "#15803d", B: "#16a34a", C: "#eab308", D: "#f97316", F: "#dc2626",
};

function scoreColor(s) {
  if (s >= 90) return "#15803d";
  if (s >= 75) return "#16a34a";
  if (s >= 60) return "#eab308";
  if (s >= 40) return "#f97316";
  return "#dc2626";
}

function ensureChart(id) {
  if (charts[id]) charts[id].dispose();
  const dom = document.getElementById(id);
  if (!dom) return null;
  const c = echarts.init(dom);
  charts[id] = c;
  return c;
}

function renderGauge(inst) {
  const chart = ensureChart("chart-gauge");
  if (!chart) return;
  const score = inst.overall_score || 0;
  const grade = inst.grade || "N/A";

  chart.setOption({
    series: [
      {
        type: "gauge",
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        center: ["50%", "55%"],
        radius: "85%",
        splitNumber: 10,
        axisLine: {
          lineStyle: {
            width: 14,
            color: [
              [0.4, "#dc2626"],
              [0.6, "#f97316"],
              [0.75, "#eab308"],
              [0.9, "#16a34a"],
              [1, "#15803d"],
            ],
          },
        },
        pointer: { length: "65%", width: 6, itemStyle: { color: "auto" } },
        axisTick: { distance: -14, length: 6, lineStyle: { width: 1.5, color: "#999" } },
        splitLine: { distance: -18, length: 14, lineStyle: { width: 2.5, color: "#999" } },
        axisLabel: { distance: 20, fontSize: 11, color: "#999" },
        anchor: { show: true, size: 14 },
        title: { offsetCenter: [0, "82%"], fontSize: 13, color: "#64748b" },
        detail: {
          valueAnimation: true,
          fontSize: 36,
          fontWeight: 800,
          offsetCenter: [0, "58%"],
          formatter: "{value}",
          color: scoreColor(score),
        },
        data: [{ value: score, name: `等级: ${grade}` }],
      },
    ],
  });
}

function renderRadar(inst) {
  const chart = ensureChart("chart-radar");
  if (!chart) return;

  const dims = inst.dimensions || {};
  const values = DIM_KEYS.map((k) => (dims[k] ? dims[k].score || 0 : 0));

  chart.setOption({
    tooltip: { trigger: "item" },
    legend: { bottom: 0, textStyle: { fontSize: 11 } },
    radar: {
      center: ["50%", "48%"],
      radius: "65%",
      indicator: DIM_LABELS.map((name, i) => ({
        name,
        max: 100,
        color: "#64748b",
      })),
      axisName: { fontSize: 11 },
      shape: "polygon",
      splitArea: {
        areaStyle: { color: ["rgba(79,70,229,0.02)", "rgba(79,70,229,0.04)"] },
      },
    },
    series: [
      {
        type: "radar",
        data: [
          {
            value: values,
            name: inst.instruction_id || "评分",
            areaStyle: { color: "rgba(99,102,241,0.25)" },
            lineStyle: { color: "#6366f1", width: 2 },
            itemStyle: { color: "#6366f1", borderColor: "#fff", borderWidth: 2 },
            symbol: "circle",
            symbolSize: 6,
          },
        ],
      },
    ],
  });
}

function renderBar(inst) {
  const chart = ensureChart("chart-bar");
  if (!chart) return;

  const dims = inst.dimensions || {};
  const scores = DIM_KEYS.map((k) => (dims[k] ? dims[k].score || 0 : 0));

  chart.setOption({
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params) => {
        const p = params[0];
        return `${p.name}<br/>得分: ${p.value.toFixed(1)} / 100<br/>权重: ${(DIM_WEIGHTS[p.dataIndex] * 100).toFixed(0)}%`;
      },
    },
    grid: { left: 12, right: 24, top: 12, bottom: 24 },
    xAxis: {
      type: "value",
      max: 100,
      axisLabel: { fontSize: 10, color: "#94a3b8" },
      splitLine: { lineStyle: { color: "#f1f5f9" } },
    },
    yAxis: {
      type: "category",
      data: DIM_LABELS.map((l, i) => `${l} (${(DIM_WEIGHTS[i] * 100).toFixed(0)}%)`),
      axisLabel: { fontSize: 11, color: "#64748b" },
      axisLine: { show: false },
      axisTick: { show: false },
      inverse: true,
    },
    series: [
      {
        type: "bar",
        data: scores.map((v, i) => ({
          value: v,
          itemStyle: {
            color: v >= 80 ? "#10b981" : v >= 60 ? "#f59e0b" : "#ef4444",
            borderRadius: [0, 4, 4, 0],
          },
        })),
        barWidth: 18,
        label: {
          show: true,
          position: "right",
          fontSize: 11,
          fontWeight: 600,
          color: "#64748b",
          formatter: (p) => p.value.toFixed(0),
        },
      },
    ],
  });
}

// ============================================================
// Violations
// ============================================================
function renderViolations(inst) {
  const allViolations = [];
  const dims = inst.dimensions || {};
  DIM_KEYS.forEach((k, i) => {
    const dim = dims[k] || {};
    (dim.violations || []).forEach((v) => {
      allViolations.push({ ...v, _dimLabel: dim.label || DIM_LABELS[i] });
    });
  });

  violationCount.textContent = `共 ${allViolations.length} 条`;

  if (allViolations.length === 0) {
    violationList.innerHTML = '<div class="empty-state">该指令无违规记录</div>';
    return;
  }

  violationList.innerHTML = allViolations
    .slice(0, 30)
    .map(
      (v) => `
    <div class="violation-item">
      <div class="violation-header">
        <span class="violation-type">[${v._dimLabel}] ${v.violation_type || "未分类"}</span>
        <span class="violation-severity ${v.severity || "medium"}">${v.severity || "medium"} · -${v.deduction || 0}分</span>
      </div>
      <div class="violation-detail">
        ${v.explanation || "无详细说明"}${v.test_case_id ? ` · 用例: ${v.test_case_id}` : ""}${v.turn_number ? ` · 第${v.turn_number}轮` : ""}
      </div>
      ${v.sut_message ? `<div class="violation-evidence">SUT: 「${escapeHtml(v.sut_message).substring(0, 120)}」</div>` : ""}
    </div>`
    )
    .join("");
}

// ============================================================
// Improvements
// ============================================================
function renderImprovements(inst) {
  const items = inst.improvement_items || [];
  if (items.length === 0) {
    improvementList.innerHTML = '<div class="empty-state">暂无改进建议</div>';
    return;
  }
  improvementList.innerHTML = items
    .slice(0, 10)
    .map((item) => `<div class="improvement-item">${escapeHtml(item)}</div>`)
    .join("");
}

// ============================================================
// Report Preview — 维度得分表格 + 案例摘要
// ============================================================
function loadReportPreview() {
  const inst = (allResults.instructions || [])[currentInstIdx];
  if (!inst) {
    reportPreview.innerHTML = '<div class="empty-state">暂无数据</div>';
    return;
  }

  const dims = inst.dimensions || {};
  const gradeDesc = { A: "优秀", B: "良好", C: "合格", D: "待改进", F: "不合格" };
  const gradeColor = {
    A: "var(--success)", B: "#22c55e", C: "var(--warning)", D: "#f97316", F: "var(--danger)",
  };

  // Score color helper
  const sc = (s) => s >= 80 ? "var(--success)" : s >= 60 ? "var(--warning)" : "var(--danger)";

  let rows = DIM_KEYS.map((k, i) => {
    const dim = dims[k] || {};
    const s = dim.score || 0;
    const w = (DIM_WEIGHTS[i] * 100).toFixed(0);
    const icon = s >= 80 ? "✅" : s >= 60 ? "⚠️" : "❌";
    const barW = Math.max(0, Math.min(100, s));
    return `
      <tr>
        <td style="font-weight:600">${dim.label || DIM_LABELS[i]}</td>
        <td style="color:var(--text-secondary)">${w}%</td>
        <td>
          <div style="display:flex;align-items:center;gap:8px">
            <div style="flex:1;height:8px;border-radius:4px;background:var(--border);overflow:hidden">
              <div style="width:${barW}%;height:100%;border-radius:4px;background:${sc(s)};transition:width 0.6s ease"></div>
            </div>
            <span style="font-weight:700;font-size:14px;color:${sc(s)};min-width:40px">${s.toFixed(0)}</span>
          </div>
        </td>
        <td>${icon}</td>
      </tr>`;
  }).join("");

  reportPreview.innerHTML = `
    <div class="preview-section">
      <h3>综合得分: <span style="color:${scoreColor(inst.overall_score || 0)};font-size:22px">${(inst.overall_score || 0).toFixed(1)}</span> / 100
      <span style="display:inline-block;margin-left:8px;padding:2px 12px;border-radius:20px;background:${gradeColor[inst.grade] || '#999'};color:#fff;font-size:14px">${inst.grade || 'N/A'} · ${gradeDesc[inst.grade] || ''}</span>
      </h3>
    </div>
    <div class="preview-section">
      <h3>分维度得分</h3>
      <table class="dim-table">
        <thead><tr><th>维度</th><th>权重</th><th>得分</th><th>状态</th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <div class="preview-section">
      <h3>测评摘要</h3>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:13px">
        <div><strong>测试用例数:</strong> ${inst.total_cases || 0}</div>
        <div><strong>违规总数:</strong> ${Object.values(dims).reduce((sum,d) => sum + (d.violations_count || d.violations?.length || 0), 0)}</div>
        <div style="word-break:break-all;overflow-wrap:break-word"><strong>角色:</strong> ${inst.instruction_role || ''}</div>
        <div style="word-break:break-all;overflow-wrap:break-word"><strong>任务:</strong> ${inst.instruction_task || ''}</div>
        <div><strong>运行模式:</strong> ${renderModeBadge(inst)}</div>
        <div><strong>LLM-as-Judge:</strong> ${renderJudgeStatus(inst)}</div>
      </div>
    </div>
    ${renderApiErrors(inst)}
  `;
}

function renderModeBadge(inst) {
  const mode = inst.simulation_mode || 'mock';
  if (mode === 'llm') {
    return '<span style="display:inline-block;padding:1px 10px;border-radius:12px;background:#dcfce7;color:#166534;font-size:12px;font-weight:600">LLM 增强</span>';
  }
  return '<span style="display:inline-block;padding:1px 10px;border-radius:12px;background:#f1f5f9;color:#64748b;font-size:12px;font-weight:600">Mock 模式</span>';
}

function renderJudgeStatus(inst) {
  const status = inst.llm_status || {};
  if (!status.judge_enabled) {
    return '<span style="color:var(--text-muted);font-size:12px">未启用</span>';
  }
  if (status.judge_used) {
    return '<span style="display:inline-block;padding:1px 10px;border-radius:12px;background:#dcfce7;color:#166534;font-size:12px;font-weight:600">已生效</span>';
  }
  return '<span style="display:inline-block;padding:1px 10px;border-radius:12px;background:#fef3c7;color:#92400e;font-size:12px;font-weight:600">未生效</span>';
}

function renderApiErrors(inst) {
  const status = inst.llm_status || {};
  const errors = [];
  if (status.judge_enabled && !status.judge_used && status.judge_error) {
    errors.push(status.judge_error);
  }
  if (!errors.length) return '';

  return `
    <div class="preview-section">
      <h3 style="color:#dc2626">API 错误</h3>
      <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;font-size:13px;color:#991b1b">
        ${errors.map(e => `<div style="margin-bottom:4px">⚠️ ${e}</div>`).join('')}
        <div style="margin-top:6px;color:#64748b;font-size:11px">提示：使用 --llm 并配置正确的 --llm-key 以启用 LLM 增强功能。</div>
      </div>
    </div>`;
}

function simpleMarkdown(md) {
  let html = md
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  // Code blocks with conversation highlighting
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    // Highlight conversation roles
    let highlighted = code
      .replace(/^(\[SUT\])/gm, '<span class="conv-sut">$1</span>')
      .replace(/^(\[USER\])/gm, '<span class="conv-user">$1</span>')
      .replace(/^(\[.*?\])/gm, '<span class="conv-label">$1</span>');
    return `<pre><code>${highlighted}</code></pre>`;
  });

  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Bold
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  // Headers
  html = html.replace(/^#### (.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  // Horizontal rules
  html = html.replace(/^---$/gm, "<hr>");
  // Tables (simple)
  html = html.replace(
    /^\|(.+)\|\n\|[-| ]+\|\n((?:\|.+\|\n?)*)/gm,
    (_, header, rows) => {
      const hcells = header.split("|").filter((c) => c.trim());
      const ths = hcells.map((c) => `<th>${c.trim()}</th>`).join("");
      const trs = rows
        .trim()
        .split("\n")
        .map((row) => {
          const cells = row.split("|").filter((c) => c.trim());
          return `<tr>${cells.map((c) => `<td>${c.trim()}</td>`).join("")}</tr>`;
        })
        .join("");
      return `<table><thead><tr>${ths}</tr></thead><tbody>${trs}</tbody></table>`;
    }
  );
  // Simple lists
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");
  // Conversation code blocks → wrap in highlight card
  html = html.replace(
    /(<p>)?(<pre><code>(<span class="conv-(sut|user)">.*?<\/span>[\s\S]*?)<\/code><\/pre>)(<\/p>)?/g,
    '<div class="case-highlight">$2</div>'
  );
  // Line breaks
  html = html.replace(/\n\n/g, "</p><p>");
  html = html.replace(/\n/g, "<br>");

  return "<p>" + html + "</p>";
}

// ============================================================
// Download buttons
// ============================================================
$("#btn-download-md")?.addEventListener("click", () => downloadReport("md"));
$("#btn-download-json")?.addEventListener("click", () => downloadReport("json"));

function downloadReport(fmt) {
  if (!currentTaskId) return;
  window.open(`/api/report/${currentTaskId}/${fmt}`, "_blank");
}

// ============================================================
// Helpers
// ============================================================
function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

// Window resize → redraw charts
let resizeTimeout;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(() => {
    Object.values(charts).forEach((c) => {
      try { c.resize(); } catch (_) {}
    });
  }, 200);
});
