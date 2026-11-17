"""Topology-aware SWAP routing (linear, grid, IBM-like heavy-hex).

A BFS router inserts SWAPs so every CX is adjacent on the coupling graph.
This is the same idea as Qiskit's Sabre/BasicSwap, kept tiny and dependency-free
so agents can ask "how many SWAPs does heavy-hex add?" without Aer.

Coupling references:
- IBM Eagle/Heron heavy-hex (cross-links every 3rd qubit in the toy model)
- 2-D grid (neutral-atom / superconducting lattice)
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .workloads import resolve_circuit

try:
    from qiskit import QuantumCircuit

    HAS_QISKIT = True
except ImportError:  # pragma: no cover
    HAS_QISKIT = False
    QuantumCircuit = Any  # type: ignore[misc,assignment]


Edge = Tuple[int, int]


def coupling_edges(topology: str, n: int) -> List[Edge]:
    """Undirected coupling list for ``n`` physical qubits."""
    n = max(1, int(n))
    kind = (topology or "linear").lower().replace("-", "_")
    if kind in {"all", "complete", "fully_connected"}:
        return [(i, j) for i in range(n) for j in range(i + 1, n)]
    if kind in {"grid", "square", "planar"}:
        w = int(max(1, round(n ** 0.5)))
        edges: List[Edge] = []
        for i in range(n):
            r, c = divmod(i, w)
            if c + 1 < w and i + 1 < n:
                edges.append((i, i + 1))
            down = i + w
            if down < n:
                edges.append((i, down))
        return edges
    if kind in {"heavy_hex", "heavyhex", "ibm", "heron", "eagle"}:
        edges = [(i, i + 1) for i in range(n - 1)]
        for i in range(0, n - 2, 3):
            if i + 2 < n:
                edges.append((i, i + 2))
        return edges
    # default linear / path
    return [(i, i + 1) for i in range(n - 1)]


def _adj(edges: Sequence[Edge], n: int) -> Dict[int, List[int]]:
    g: Dict[int, List[int]] = defaultdict(list)
    for a, b in edges:
        if 0 <= a < n and 0 <= b < n and a != b:
            g[a].append(b)
            g[b].append(a)
    for i in range(n):
        g.setdefault(i, [])
    return g


def _bfs_path(adj: Dict[int, List[int]], src: int, dst: int) -> Optional[List[int]]:
    if src == dst:
        return [src]
    prev = {src: -1}
    q = deque([src])
    while q:
        u = q.popleft()
        for v in adj[u]:
            if v not in prev:
                prev[v] = u
                if v == dst:
                    path = [dst]
                    while path[-1] != src:
                        path.append(prev[path[-1]])
                    path.reverse()
                    return path
                q.append(v)
    return None


def _swap_logical(phys_of: List[int], p: int, q: int) -> None:
    for i, loc in enumerate(phys_of):
        if loc == p:
            phys_of[i] = q
        elif loc == q:
            phys_of[i] = p


@dataclass
class RoutingResult:
    topology: str
    num_qubits: int
    coupling: List[List[int]]
    original_cx: int
    swap_count: int
    routed_cx: int
    original_depth: int
    routed_depth: int
    overhead: float
    connected: bool
    unroutable: int = 0
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        return payload


def route_circuit(
    circuit: Optional[QuantumCircuit] = None,
    *,
    workload: Optional[str] = None,
    qubits: Optional[int] = None,
    qasm: Optional[str] = None,
    topology: str = "linear",
) -> RoutingResult:
    """Insert SWAPs so every 2-qubit gate is adjacent on ``topology``."""
    if not HAS_QISKIT:
        raise RuntimeError("Qiskit is required for transpilation.")
    qc = circuit or resolve_circuit(workload=workload, qubits=qubits, qasm=qasm)
    n = qc.num_qubits
    edges = coupling_edges(topology, n)
    adj = _adj(edges, n)
    phys_of = list(range(n))  # logical → physical
    skip = {"measure", "barrier", "reset", "delay"}
    original_cx = 0
    swap_count = 0
    routed_cx = 0
    unroutable = 0
    extra_depth = 0
    for inst in qc.data:
        name = getattr(inst.operation, "name", "")
        if name in skip:
            continue
        qidx = [qc.find_bit(q).index for q in inst.qubits]
        if len(qidx) < 2:
            continue
        original_cx += 1
        a, b = phys_of[qidx[0]], phys_of[qidx[1]]
        if b in adj[a]:
            routed_cx += 1
            continue
        path = _bfs_path(adj, a, b)
        if not path or len(path) < 2:
            unroutable += 1
            continue
        # SWAP along path until adjacent to target
        for u, v in zip(path[:-2], path[1:-1]):
            _swap_logical(phys_of, u, v)
            swap_count += 1
            routed_cx += 3  # SWAP = 3 CX
            extra_depth += 3
        routed_cx += 1
    orig_depth = int(qc.depth())
    routed_depth = orig_depth + extra_depth
    overhead = (routed_cx / original_cx) if original_cx else 1.0
    notes = [
        "BFS greedy router (not Sabre). SWAP = 3 CX on the coupling graph.",
        "Toy heavy-hex adds skip-2 links every 3 qubits — not a full IBM lattice.",
    ]
    if unroutable:
        notes.append(f"{unroutable} two-qubit gates could not be routed (disconnected map).")
    return RoutingResult(
        topology=topology,
        num_qubits=n,
        coupling=[[a, b] for a, b in edges],
        original_cx=original_cx,
        swap_count=swap_count,
        routed_cx=routed_cx,
        original_depth=orig_depth,
        routed_depth=routed_depth,
        overhead=float(overhead),
        connected=unroutable == 0,
        unroutable=unroutable,
        notes=notes,
    )
