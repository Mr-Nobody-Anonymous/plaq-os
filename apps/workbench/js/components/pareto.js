/**
 * Interactive Quantum Pareto Frontier Visualizer using HTML5 Canvas
 */
class PlaqParetoChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas ? this.canvas.getContext("2d") : null;
    this.points = [
      { name: "Sequential Baseline", qubits: 5036, runtime: 9.58, color: "#94a3b8" },
      { name: "Standard Mapping", qubits: 5420, runtime: 6.12, color: "#ffb703" },
      { name: "Independent FT Layout", qubits: 5600, runtime: 4.50, color: "#ff0054" },
      { name: "Plaq Joint Plan", qubits: 5836, runtime: 3.85, color: "#00f0ff" },
    ];
    this.init();
  }

  init() {
    if (!this.canvas || !this.ctx) return;
    this.resize();
    window.addEventListener("resize", () => this.resize());
    this.render();
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.parentElement.getBoundingClientRect();
    this.canvas.width = rect.width;
    this.canvas.height = rect.height || 320;
    this.render();
  }

  render() {
    if (!this.ctx) return;
    const ctx = this.ctx;
    const w = this.canvas.width;
    const h = this.canvas.height;
    const pad = 50;

    ctx.clearRect(0, 0, w, h);

    // Draw Grid
    ctx.strokeStyle = "rgba(0, 240, 255, 0.08)";
    ctx.lineWidth = 1;

    for (let x = pad; x < w - pad; x += 60) {
      ctx.beginPath();
      ctx.moveTo(x, pad);
      ctx.lineTo(x, h - pad);
      ctx.stroke();
    }

    for (let y = pad; y < h - pad; y += 40) {
      ctx.beginPath();
      ctx.moveTo(pad, y);
      ctx.lineTo(w - pad, y);
      ctx.stroke();
    }

    // Axes
    ctx.strokeStyle = "rgba(0, 240, 255, 0.4)";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(pad, pad);
    ctx.lineTo(pad, h - pad);
    ctx.lineTo(w - pad, h - pad);
    ctx.stroke();

    // Axis Labels
    ctx.fillStyle = "#94a3b8";
    ctx.font = "10px monospace";
    ctx.fillText("Physical Qubits ->", w - pad - 120, h - pad + 30);
    ctx.fillText("Runtime (ms)", 10, pad - 15);

    // Coordinate Mapping
    const minQ = 4800, maxQ = 6200;
    const minR = 2.0, maxR = 12.0;

    const mapX = (q) => pad + ((q - minQ) / (maxQ - minQ)) * (w - 2 * pad);
    const mapY = (r) => (h - pad) - ((r - minR) / (maxR - minR)) * (h - 2 * pad);

    // Draw connecting curve
    ctx.strokeStyle = "rgba(0, 240, 255, 0.5)";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    const sorted = [...this.points].sort((a, b) => a.qubits - b.qubits);
    sorted.forEach((pt, i) => {
      const cx = mapX(pt.qubits);
      const cy = mapY(pt.runtime);
      if (i === 0) ctx.moveTo(cx, cy);
      else ctx.lineTo(cx, cy);
    });
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw Points
    this.points.forEach((pt) => {
      const cx = mapX(pt.qubits);
      const cy = mapY(pt.runtime);

      // Glow circle
      ctx.fillStyle = pt.color;
      ctx.shadowColor = pt.color;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.arc(cx, cy, 6, 0, Math.PI * 2);
      ctx.fill();
      ctx.shadowBlur = 0;

      // Label
      ctx.fillStyle = "#ffffff";
      ctx.font = "11px monospace";
      ctx.fillText(`${pt.name} (${pt.qubits}q, ${pt.runtime}ms)`, cx + 8, cy - 8);
    });
  }

  setPoints(newPoints) {
    if (Array.isArray(newPoints) && newPoints.length > 0) {
      this.points = newPoints;
      this.render();
    }
  }
}

window.plaqPareto = new PlaqParetoChart("pareto-canvas");
