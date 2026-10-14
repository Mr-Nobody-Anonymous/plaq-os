/**
 * Plaq-OS Right Inspector Component: Agent Plan, Telemetry, and Human Approval Gates
 */
class PlaqInspector {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.pendingApprovals = [];
  }

  renderApprovalModal(approval) {
    return `
      <div class="approval-card" id="approval-card-${approval.id}">
        <div class="approval-title">
          <span>⚠️</span>
          <span>HUMAN APPROVAL REQUIRED</span>
        </div>
        <div class="approval-reason">
          <strong>Tool:</strong> <code>${approval.tool_name}</code><br/>
          <strong>Reason:</strong> ${approval.reason}<br/>
          <strong>Params:</strong> <code>${JSON.stringify(approval.parameters)}</code>
        </div>
        <div class="approval-actions">
          <button class="btn btn-approve" onclick="window.plaqApp.decideApproval('${approval.id}', true)">
            Approve &amp; Resume
          </button>
          <button class="btn btn-deny" onclick="window.plaqApp.decideApproval('${approval.id}', false)">
            Reject
          </button>
        </div>
      </div>
    `;
  }

  updateApprovals(approvals) {
    this.pendingApprovals = approvals;
    const approvalContainer = document.getElementById("inspector-approvals-area");
    if (!approvalContainer) return;

    if (!approvals || approvals.length === 0) {
      approvalContainer.innerHTML = `<div style="font-size:11px; color:var(--text-dim);">No pending human approvals. System operating autonomously.</div>`;
      return;
    }

    approvalContainer.innerHTML = approvals.map(app => this.renderApprovalModal(app)).join("");
  }

  updatePlan(steps) {
    const planContainer = document.getElementById("inspector-plan-list");
    if (!planContainer) return;

    if (!steps || steps.length === 0) {
      planContainer.innerHTML = `<li style="font-size:11px; color:var(--text-dim);">No active plan steps currently executing.</li>`;
      return;
    }

    planContainer.innerHTML = steps.map((s, idx) => `
      <li class="plan-step-item ${s.status}">
        <div style="display:flex; justify-content:space-between; font-weight:600;">
          <span>Step ${idx + 1}: ${s.step_name}</span>
          <span style="font-size:10px; text-transform:uppercase;">${s.status}</span>
        </div>
        <div style="color:var(--text-muted); font-size:10px;">${s.criteria || ""}</div>
      </li>
    `).join("");
  }

  updateTelemetry(metrics) {
    const el = document.getElementById("hardware-metrics-content");
    if (el && metrics) {
      el.innerHTML = `
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:8px; font-family:var(--font-mono); font-size:11px;">
          <div>Logical Qubits: <strong style="color:var(--accent);">${metrics.qubits || 4}</strong></div>
          <div>Code Dist (d): <strong style="color:var(--accent);">${metrics.code_distance || 3}</strong></div>
          <div>Physical Qubits: <strong style="color:var(--accent-purple);">${metrics.physical_qubits || "N/A"}</strong></div>
          <div>Feasibility: <strong style="color:var(--accent-emerald);">${metrics.feasible !== false ? "PASS" : "EXCEEDED"}</strong></div>
        </div>
      `;
    }
  }
}

window.plaqInspector = new PlaqInspector("right-inspector");
