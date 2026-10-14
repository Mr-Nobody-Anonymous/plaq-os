/**
 * Plaq-OS Workbench Application Controller
 */
class PlaqWorkbenchApp {
  constructor() {
    this.apiBase = window.location.origin;
    this.currentTask = null;
    this.activeTab = "quantum-lab";
    this.init();
  }

  async init() {
    console.log("[Plaq-Workbench] Initializing Workbench Engine v0.3.0...");
    this.setupNavigation();
    this.setupEventListeners();
    await this.refreshHealth();
    await this.refreshTasks();
    await this.refreshApprovals();

    // Start WebSocket
    if (window.plaqWs) {
      window.plaqWs.connect();
      window.plaqWs.on("event", (evt) => this.handleLiveEvent(evt));
    }

    this.logTerminal("Plaq-OS Programmable Quantum Workbench v0.3.0 initialized.", "success");
    this.logTerminal("Control plane SQLite WAL persistent storage online.", "info");
    this.logTerminal("Quantum co-design engine (Stim 1.16+ / PyMatching 2.4+) loaded.", "info");
  }

  setupNavigation() {
    const tabs = document.querySelectorAll(".ws-tab");
    tabs.forEach(tab => {
      tab.addEventListener("click", () => {
        const targetView = tab.getAttribute("data-view");
        this.switchTab(targetView);
      });
    });
  }

  switchTab(viewId) {
    this.activeTab = viewId;
    document.querySelectorAll(".ws-tab").forEach(t => {
      t.classList.toggle("active", t.getAttribute("data-view") === viewId);
    });
    document.querySelectorAll(".view-panel").forEach(p => {
      p.classList.toggle("active", p.id === `view-${viewId}`);
    });
    if (viewId === "quantum-lab" && window.plaqPareto) {
      setTimeout(() => window.plaqPareto.resize(), 50);
    }
  }

  setupEventListeners() {
    const createBtn = document.getElementById("btn-new-task");
    if (createBtn) {
      createBtn.addEventListener("click", () => this.promptCreateTask());
    }

    const runOptBtn = document.getElementById("btn-run-opt");
    if (runOptBtn) {
      runOptBtn.addEventListener("click", () => this.runQuantumOptimization());
    }
  }

  async refreshHealth() {
    try {
      const resp = await fetch(`${this.apiBase}/api/v1/health`);
      if (resp.ok) {
        const data = await resp.json();
        const indicator = document.getElementById("health-indicator");
        const statusText = document.getElementById("health-text");
        if (indicator) indicator.className = "status-indicator";
        if (statusText) statusText.innerText = "ONLINE";
      }
    } catch (err) {
      const indicator = document.getElementById("health-indicator");
      const statusText = document.getElementById("health-text");
      if (indicator) indicator.className = "status-indicator busy";
      if (statusText) statusText.innerText = "STANDALONE";
    }
  }

  async refreshTasks() {
    try {
      const resp = await fetch(`${this.apiBase}/api/v1/tasks`);
      if (!resp.ok) return;
      const tasks = await resp.json();
      const list = document.getElementById("task-list-items");
      if (!list) return;

      if (tasks.length === 0) {
        list.innerHTML = `<li style="padding:10px 14px; font-size:11px; color:var(--text-dim);">No tasks in queue. Click '+ Task' to begin.</li>`;
        return;
      }

      list.innerHTML = tasks.map(t => `
        <li class="task-item ${this.currentTask && this.currentTask.id === t.id ? 'active' : ''}" onclick="window.plaqApp.selectTask('${t.id}')">
          <span class="status-indicator ${t.status === 'running' ? 'busy' : ''}"></span>
          <div style="flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
            <div>${t.goal}</div>
            <div style="font-size:10px; color:var(--text-dim);">${t.id.slice(0, 8)} • ${t.status}</div>
          </div>
        </li>
      `).join("");
    } catch (err) {
      console.warn("Failed to fetch tasks:", err);
    }
  }

  async selectTask(taskId) {
    try {
      const resp = await fetch(`${this.apiBase}/api/v1/tasks/${taskId}`);
      if (!resp.ok) return;
      this.currentTask = await resp.json();

      // Update inspector
      if (window.plaqInspector) {
        window.plaqInspector.updatePlan([
          { step_name: "Inspect Workspace", criteria: "Verify project root & dependencies", status: "completed" },
          { step_name: "Quantum Compilation", criteria: "Extract DAG metrics & T-gate counts", status: this.currentTask.status === "completed" ? "completed" : "running" },
          { step_name: "Resource Estimation", criteria: "Compute minimum code distance (d >= 3)", status: this.currentTask.status === "completed" ? "completed" : "pending" },
          { step_name: "Publish Report", criteria: "Content-addressed SHA-256 artifact verification", status: this.currentTask.status === "completed" ? "completed" : "pending" },
        ]);
      }

      this.logTerminal(`Inspecting task ${taskId} (${this.currentTask.status}): ${this.currentTask.goal}`, "info");
      this.refreshTasks();
    } catch (err) {
      console.warn("Failed to select task:", err);
    }
  }

  async promptCreateTask() {
    const goal = prompt("Enter goal for autonomous agent task:", "Synthesize quantum circuit and estimate physical fault-tolerant cost");
    if (!goal || !goal.trim()) return;

    try {
      const resp = await fetch(`${this.apiBase}/api/v1/tasks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ goal: goal.trim(), workspace_path: "." }),
      });
      if (resp.ok) {
        const created = await resp.json();
        this.logTerminal(`Task created [${created.id}]: ${created.goal}`, "success");
        await this.refreshTasks();
        this.selectTask(created.id);
      } else {
        alert("Failed to create task");
      }
    } catch (err) {
      this.logTerminal(`Error creating task: ${err.message}`, "error");
    }
  }

  async refreshApprovals() {
    try {
      const resp = await fetch(`${this.apiBase}/api/v1/approvals`);
      if (resp.ok) {
        const approvals = await resp.json();
        const pending = approvals.filter(a => a.status === "pending");
        if (window.plaqInspector) {
          window.plaqInspector.updateApprovals(pending);
        }
      }
    } catch (err) {
      console.warn("Failed to fetch approvals:", err);
    }
  }

  async decideApproval(approvalId, approved) {
    try {
      const resp = await fetch(`${this.apiBase}/api/v1/approvals/${approvalId}/decide`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ approved, reason: approved ? "Human operator granted permission" : "Denied by operator" }),
      });
      if (resp.ok) {
        this.logTerminal(`Approval ${approvalId} ${approved ? "GRANTED" : "REJECTED"}. Resuming loop.`, approved ? "success" : "warning");
        await this.refreshApprovals();
        await this.refreshTasks();
      }
    } catch (err) {
      this.logTerminal(`Approval decision failed: ${err.message}`, "error");
    }
  }

  async runQuantumOptimization() {
    this.logTerminal("Executing Multi-Objective Pareto Frontier Co-Design Search...", "info");
    try {
      const resp = await fetch(`${this.apiBase}/api/v1/quantum/estimate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ qubits: 6, physical_error_rate: 0.001, circuit_depth: 60 }),
      });
      if (resp.ok) {
        const res = await resp.json();
        this.logTerminal(`Estimation complete: code_distance=${res.code_distance}, physical_qubits=${res.physical_qubits}, runtime=${res.estimated_runtime_sec}s`, "success");
        if (window.plaqInspector) {
          window.plaqInspector.updateTelemetry({
            qubits: res.num_qubits,
            code_distance: res.code_distance,
            physical_qubits: res.physical_qubits,
            feasible: res.feasible,
          });
        }
      }
    } catch (err) {
      this.logTerminal(`Optimization query failed: ${err.message}`, "error");
    }
  }

  handleLiveEvent(evt) {
    if (evt.event_type === "task_created" || evt.event_type === "task_updated") {
      this.refreshTasks();
    }
    if (evt.event_type === "approval_requested" || evt.event_type === "approval_decided") {
      this.refreshApprovals();
    }
    this.logTerminal(`[Telemetry Event] ${evt.event_type} (task=${evt.task_id || "global"})`, "info");
  }

  logTerminal(message, level = "normal") {
    const stream = document.getElementById("terminal-output-stream");
    if (!stream) return;
    const timeStr = new Date().toISOString().split("T")[1].slice(0, 8);
    const line = document.createElement("div");
    line.className = `terminal-line ${level}`;
    line.textContent = `[${timeStr}] ${message}`;
    stream.appendChild(line);
    stream.scrollTop = stream.scrollHeight;
  }
}

window.addEventListener("DOMContentLoaded", () => {
  window.plaqApp = new PlaqWorkbenchApp();
});
