"""
Quantum Circuit Builder — Flask backend
Zero external dependencies beyond Flask (no flask-cors, no qiskit, no numpy).
Pure-Python statevector simulator included.
Run:  python3 app.py
Open: http://localhost:5000
"""

from flask import Flask, request, jsonify, render_template, make_response
import sqlite3
import json
import math
import cmath
import random
import os

app = Flask(__name__)
DB_PATH = "circuits.db"

# ── CORS helper (replaces flask-cors) ─────────────────
def cors(response):
    response.headers["Access-Control-Allow-Origin"]  = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
    return response

@app.after_request
def add_cors(response):
    return cors(response)

@app.route("/", defaults={"path": ""}, methods=["OPTIONS"])
@app.route("/<path:path>",             methods=["OPTIONS"])
def handle_options(path=""):
    return cors(make_response("", 204))


# ── DATABASE ───────────────────────────────────────────


# ── PURE-PYTHON STATEVECTOR SIMULATOR ─────────────────
def simulate_circuit(num_qubits, gates, shots=2048):
    """
    Full statevector simulator — no external libs needed.
    Supports: H X Y Z S S† T T† SX  (single)
              Rx Ry Rz P             (rotation)
              CNOT/CX CZ CY CH SWAP (two-qubit)
              CRX CRY CRZ RZZ       (controlled rotation)
              CCX CSWAP             (three-qubit)
    Returns probabilities, shot counts, statevector, Bloch vectors.
    """
    size  = 2 ** num_qubits
    state = [complex(0.0)] * size
    state[0] = complex(1.0)

    # ── gate appliers ──────────────────────────────────
    def apply1(state, q, mat):
        ns = [complex(0)] * size
        for i in range(size):
            b = (i >> q) & 1
            p = i ^ (1 << q)
            if b == 0:
                ns[i] += mat[0][0]*state[i] + mat[0][1]*state[p]
            else:
                ns[i] += mat[1][0]*state[p] + mat[1][1]*state[i]
        return ns

    def apply_cx(state, ctrl, tgt):
        ns = [complex(0)] * size
        for i in range(size):
            if (i >> ctrl) & 1: ns[i ^ (1 << tgt)] += state[i]
            else:                ns[i]               += state[i]
        return ns

    def apply_cz(state, ctrl, tgt):
        ns = list(state)
        for i in range(size):
            if ((i >> ctrl) & 1) and ((i >> tgt) & 1):
                ns[i] = -state[i]
        return ns

    def apply_swap(state, q1, q2):
        ns = [complex(0)] * size
        for i in range(size):
            b1, b2 = (i>>q1)&1, (i>>q2)&1
            ns[i^(1<<q1)^(1<<q2)] += state[i] if b1 != b2 else complex(0)
            if b1 == b2: ns[i] += state[i]
        return ns

    def apply_ccx(state, c1, c2, tgt):
        ns = [complex(0)] * size
        for i in range(size):
            if ((i>>c1)&1) and ((i>>c2)&1): ns[i^(1<<tgt)] += state[i]
            else:                             ns[i]           += state[i]
        return ns

    def apply_cswap(state, ctrl, q1, q2):
        ns = [complex(0)] * size
        for i in range(size):
            if (i >> ctrl) & 1:
                b1, b2 = (i>>q1)&1, (i>>q2)&1
                ns[i^(1<<q1)^(1<<q2)] += state[i] if b1 != b2 else complex(0)
                if b1 == b2: ns[i] += state[i]
            else:
                ns[i] += state[i]
        return ns

    def ctrl_gate(state, ctrl, tgt, mat):
        """Apply mat to tgt conditioned on ctrl=1."""
        ns = list(state)
        for i in range(size):
            if (i >> ctrl) & 1:
                b = (i >> tgt) & 1
                p = i ^ (1 << tgt)
                if b == 0:
                    ns[i] = mat[0][0]*state[i] + mat[0][1]*state[p]
                    ns[p] = mat[1][0]*state[i] + mat[1][1]*state[p]
        return ns

    # ── gate matrices ──────────────────────────────────
    sq2 = math.sqrt(2)
    I2  = [[1,0],[0,1]]
    def H():  return [[1/sq2, 1/sq2],[1/sq2,-1/sq2]]
    def X():  return [[0,1],[1,0]]
    def Y():  return [[0,complex(0,-1)],[complex(0,1),0]]
    def Z():  return [[1,0],[0,-1]]
    def S():  return [[1,0],[0,complex(0,1)]]
    def Sdg():return [[1,0],[0,complex(0,-1)]]
    def T():  return [[1,0],[0,cmath.exp(complex(0,math.pi/4))]]
    def Tdg():return [[1,0],[0,cmath.exp(complex(0,-math.pi/4))]]
    def SX(): return [[complex(.5,.5),complex(.5,-.5)],[complex(.5,-.5),complex(.5,.5)]]
    def Rx(a):return [[math.cos(a/2),complex(0,-math.sin(a/2))],[complex(0,-math.sin(a/2)),math.cos(a/2)]]
    def Ry(a):return [[math.cos(a/2),-math.sin(a/2)],[math.sin(a/2),math.cos(a/2)]]
    def Rz(a):return [[cmath.exp(complex(0,-a/2)),0],[0,cmath.exp(complex(0,a/2))]]
    def Ph(a):return [[1,0],[0,cmath.exp(complex(0,a))]]

    SINGLE = {"H":H,"X":X,"Y":Y,"Z":Z,"S":S,"SDG":Sdg,"T":T,"TDG":Tdg,"SX":SX}

    # ── execute gates ──────────────────────────────────
    for gate in sorted(gates, key=lambda g: g.get("step", 0)):
        g   = gate.get("gate","").upper()
        q   = int(gate.get("qubit", 0))
        c   = int(gate.get("control", 0))
        t   = int(gate.get("target", 1))
        ang = float(gate.get("angle", math.pi/2))

        def ok1(q):  return 0 <= q < num_qubits
        def ok2(a,b):return ok1(a) and ok1(b) and a != b

        if g in SINGLE and ok1(q):
            state = apply1(state, q, SINGLE[g]())
        elif g == "RX" and ok1(q): state = apply1(state, q, Rx(ang))
        elif g == "RY" and ok1(q): state = apply1(state, q, Ry(ang))
        elif g == "RZ" and ok1(q): state = apply1(state, q, Rz(ang))
        elif g == "P"  and ok1(q): state = apply1(state, q, Ph(ang))
        elif g in ("CNOT","CX") and ok2(c,t): state = apply_cx(state, c, t)
        elif g == "CZ"  and ok2(c,t): state = apply_cz(state, c, t)
        elif g == "CY"  and ok2(c,t): state = ctrl_gate(state, c, t, Y())
        elif g == "CH"  and ok2(c,t): state = ctrl_gate(state, c, t, H())
        elif g == "SWAP" and ok2(c,t): state = apply_swap(state, c, t)
        elif g == "CRX" and ok2(c,t): state = ctrl_gate(state, c, t, Rx(ang))
        elif g == "CRY" and ok2(c,t): state = ctrl_gate(state, c, t, Ry(ang))
        elif g == "CRZ" and ok2(c,t): state = ctrl_gate(state, c, t, Rz(ang))
        elif g == "RZZ" and ok2(c,t):
            for i in range(size):
                bc, bt = (i>>c)&1, (i>>t)&1
                state[i] *= cmath.exp(complex(0, ang/2 * (1 if bc==bt else -1)))
        elif g == "CCX":
            c1=int(gate.get("control1",c)); c2=int(gate.get("control2",1)); tt=int(gate.get("target",2))
            if ok1(c1) and ok1(c2) and ok1(tt) and len({c1,c2,tt})==3:
                state = apply_ccx(state, c1, c2, tt)
        elif g == "CSWAP":
            c1=int(gate.get("control",0)); q1=int(gate.get("target",1)); q2=int(gate.get("target2",2))
            if ok1(c1) and ok1(q1) and ok1(q2) and len({c1,q1,q2})==3:
                state = apply_cswap(state, c1, q1, q2)

    # ── extract results ────────────────────────────────
    # Probabilities
    probs = {}
    for i in range(size):
        p = abs(state[i])**2
        if p > 1e-7:
            probs[format(i, f"0{num_qubits}b")] = round(p, 6)
    probs = dict(sorted(probs.items(), key=lambda x: -x[1]))

    # Shot simulation
    ks = list(probs.keys())
    ps = list(probs.values())
    tot = sum(ps)
    ps  = [p/tot for p in ps]
    counts = {k: 0 for k in ks}
    for _ in range(shots):
        r = random.random(); cum = 0.0
        for k, p in zip(ks, ps):
            cum += p
            if r <= cum:
                counts[k] += 1
                break

    # Statevector display
    sv_display = []
    for i, amp in enumerate(state):
        if abs(amp) > 1e-7:
            sv_display.append({
                "state": format(i, f"0{num_qubits}b"),
                "real":  round(amp.real, 4),
                "imag":  round(amp.imag, 4),
                "prob":  round(abs(amp)**2, 6),
                "phase": round(cmath.phase(amp), 4),
            })
    sv_display.sort(key=lambda x: -x["prob"])

    # Bloch vectors (reduced single-qubit state)
    bloch = []
    for qi in range(num_qubits):
        rho00 = sum(abs(state[i])**2 for i in range(size) if not((i>>qi)&1))
        rho11 = sum(abs(state[i])**2 for i in range(size) if      (i>>qi)&1 )
        rho01 = sum(
            state[i] * state[i^(1<<qi)].conjugate()
            for i in range(size) if not((i>>qi)&1)
        )
        bloch.append({
            "qubit": qi,
            "x": round(2*rho01.real, 4),
            "y": round(-2*rho01.imag, 4),
            "z": round(rho00 - rho11, 4),
        })

    # Entanglement entropy (bipartite, split at half)
    entropy = 0.0
    if num_qubits >= 2:
        half = num_qubits // 2
        dim_a = 2 ** half
        dim_b = 2 ** (num_qubits - half)
        # Build reduced density matrix of subsystem A by tracing out B
        rho_a = [[complex(0)]*dim_a for _ in range(dim_a)]
        for ia in range(dim_a):
            for ja in range(dim_a):
                for ib in range(dim_b):
                    idx1 = ia * dim_b + ib
                    idx2 = ja * dim_b + ib
                    rho_a[ia][ja] += state[idx1] * state[idx2].conjugate()
        # Eigenvalues via power method for 2×2 / 4×4 (simple: just use diagonal for estimate)
        # For exact: use the characteristic polynomial for small matrices
        eigs = _hermitian_eigenvalues(rho_a, dim_a)
        entropy = round(-sum(e * math.log2(e) for e in eigs if e > 1e-12), 4)

    circuit_depth = (max((g.get("step",0) for g in gates), default=-1) + 1) if gates else 0

    return {
        "success":   True,
        "engine":    "Pure Python Statevector",
        "probabilities": probs,
        "counts":    counts,
        "statevector": sv_display,
        "bloch":     bloch,
        "total_shots": shots,
        "num_qubits":  num_qubits,
        "circuit_depth": circuit_depth,
        "total_gates":   len(gates),
        "entanglement_entropy": entropy,
    }


def _hermitian_eigenvalues(mat, n):
    """Eigenvalues of a small Hermitian matrix (n ≤ 4) — no numpy needed."""
    if n == 1:
        return [mat[0][0].real]
    if n == 2:
        a, b = mat[0][0].real, mat[1][1].real
        c    = abs(mat[0][1])
        d    = math.sqrt(((a-b)/2)**2 + c**2)
        mid  = (a+b)/2
        return [mid - d, mid + d]
    # For n=4 or larger: Jacobi iteration (good enough for 4×4)
    import copy
    A = [[mat[i][j].real for j in range(n)] for i in range(n)]
    for _ in range(200):
        # find off-diagonal max
        p, q_idx = 0, 1
        mv = 0
        for i in range(n):
            for j in range(i+1, n):
                if abs(A[i][j]) > mv:
                    mv = abs(A[i][j]); p, q_idx = i, j
        if mv < 1e-10:
            break
        theta = 0.5 * math.atan2(2*A[p][q_idx], A[p][p]-A[q_idx][q_idx])
        c_, s_ = math.cos(theta), math.sin(theta)
        B = [row[:] for row in A]
        for r in range(n):
            B[r][p] =  c_*A[r][p] + s_*A[r][q_idx]
            B[r][q_idx] = -s_*A[r][p] + c_*A[r][q_idx]
        for r in range(n):
            A[p][r] =  c_*B[p][r] + s_*B[q_idx][r]
            A[q_idx][r] = -s_*B[p][r] + c_*B[q_idx][r]
        A[p][q_idx] = A[q_idx][p] = 0
    return [max(0.0, A[i][i]) for i in range(n)]


# ── QASM export ────────────────────────────────────────
def export_qasm(num_qubits, gates):
    SM = {"H":"h","X":"x","Y":"y","Z":"z","S":"s","SDG":"sdg",
          "T":"t","TDG":"tdg","SX":"sx"}
    lines = [
        "OPENQASM 2.0;",
        'include "qelib1.inc";',
        f"qreg q[{num_qubits}];",
        f"creg c[{num_qubits}];",
        "",
    ]
    for g in sorted(gates, key=lambda x: x.get("step",0)):
        gn  = g.get("gate","").upper()
        q   = g.get("qubit", 0)
        c   = g.get("control", 0)
        t   = g.get("target", 1)
        ang = g.get("angle", math.pi/2)
        if gn in SM:                 lines.append(f"{SM[gn]} q[{q}];")
        elif gn in("RX","RY","RZ"):  lines.append(f"{gn.lower()}({ang:.6f}) q[{q}];")
        elif gn == "P":              lines.append(f"p({ang:.6f}) q[{q}];")
        elif gn in("CNOT","CX"):     lines.append(f"cx q[{c}],q[{t}];")
        elif gn == "CZ":             lines.append(f"cz q[{c}],q[{t}];")
        elif gn == "CY":             lines.append(f"cy q[{c}],q[{t}];")
        elif gn == "CH":             lines.append(f"ch q[{c}],q[{t}];")
        elif gn == "SWAP":           lines.append(f"swap q[{c}],q[{t}];")
        elif gn == "CRX":            lines.append(f"crx({ang:.6f}) q[{c}],q[{t}];")
        elif gn == "CRY":            lines.append(f"cry({ang:.6f}) q[{c}],q[{t}];")
        elif gn == "CRZ":            lines.append(f"crz({ang:.6f}) q[{c}],q[{t}];")
        elif gn == "CCX":
            c1=g.get("control1",c); c2=g.get("control2",1)
            lines.append(f"ccx q[{c1}],q[{c2}],q[{t}];")
    for i in range(num_qubits):
        lines.append(f"measure q[{i}] -> c[{i}];")
    return "\n".join(lines)


# ── ROUTES ─────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    return jsonify({"engine": "Pure Python Statevector", "qiskit_available": False, "ready": True})

@app.route("/api/simulate", methods=["POST"])
def simulate():
    data   = request.get_json(force=True)
    qubits = int(data.get("qubits", 2))
    gates  = data.get("gates", [])
    shots  = int(data.get("shots", 2048))
    if not gates:            return jsonify({"error": "Add at least one gate first!"}), 400
    if not (1 <= qubits <= 10): return jsonify({"error": "Qubits must be 1–10"}), 400
    if not (128 <= shots <= 65536): shots = 2048
    try:
        return jsonify(simulate_circuit(qubits, gates, shots))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/export/qasm", methods=["POST"])
def export_qasm_route():
    data = request.get_json(force=True)
    return jsonify({"qasm": export_qasm(int(data.get("qubits",2)), data.get("gates",[]))})

@app.route("/api/circuits", methods=["GET"])
def get_circuits():
    conn = get_db()
    rows = conn.execute("SELECT * FROM circuits ORDER BY created_at DESC").fetchall()
    conn.close()
    out = []
    for row in rows:
        try:    lr = json.loads(row["last_result"]) if row["last_result"] else None
        except: lr = None
        try:    tg = json.loads(row["tags"]) if row["tags"] else []
        except: tg = []
        out.append({
            "id": row["id"], "name": row["name"], "qubits": row["qubits"],
            "gates": json.loads(row["gates"]), "last_result": lr,
            "description": row["description"] or "",
            "tags": tg, "run_count": row["run_count"] or 0,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] if row["updated_at"] else row["created_at"],
        })
    return jsonify(out)

@app.route("/api/circuits", methods=["POST"])
def save_circuit():
    data   = request.get_json(force=True)
    name   = data.get("name", "Untitled")
    qubits = int(data.get("qubits", 2))
    gates  = data.get("gates", [])
    result = data.get("last_result", None)
    desc   = data.get("description", "")
    tags   = data.get("tags", [])
    conn   = get_db()
    conn.execute(
        "INSERT INTO circuits (name,qubits,gates,last_result,description,tags) VALUES(?,?,?,?,?,?)",
        (name, qubits, json.dumps(gates),
         json.dumps(result) if result else None, desc, json.dumps(tags))
    )
    conn.commit(); conn.close()
    return jsonify({"message": f"Circuit '{name}' saved!", "success": True}), 201

@app.route("/api/circuits/<int:cid>", methods=["DELETE"])
def delete_circuit(cid):
    conn = get_db()
    conn.execute("DELETE FROM circuits WHERE id=?", (cid,))
    conn.commit(); conn.close()
    return jsonify({"message": "Deleted", "success": True})

@app.route("/api/examples")
def get_examples():
    return jsonify([
        {"name":"Bell State","desc":"Max entanglement: 50% |00⟩ + 50% |11⟩","category":"Entanglement","qubits":2,
         "gates":[{"gate":"H","qubit":0,"step":0},{"gate":"CNOT","control":0,"target":1,"qubit":0,"step":1}]},
        {"name":"GHZ State","desc":"3-qubit: (|000⟩+|111⟩)/√2","category":"Entanglement","qubits":3,
         "gates":[{"gate":"H","qubit":0,"step":0},{"gate":"CNOT","control":0,"target":1,"qubit":0,"step":1},
                  {"gate":"CNOT","control":0,"target":2,"qubit":0,"step":2}]},
        {"name":"Superposition","desc":"H gate → |+⟩ = (|0⟩+|1⟩)/√2","category":"Basics","qubits":1,
         "gates":[{"gate":"H","qubit":0,"step":0}]},
        {"name":"Quantum NOT","desc":"X gate: |0⟩ → |1⟩","category":"Basics","qubits":1,
         "gates":[{"gate":"X","qubit":0,"step":0}]},
        {"name":"Phase Kickback","desc":"H → Z → H  =  X","category":"Algorithms","qubits":1,
         "gates":[{"gate":"H","qubit":0,"step":0},{"gate":"Z","qubit":0,"step":1},{"gate":"H","qubit":0,"step":2}]},
        {"name":"Toffoli Gate","desc":"CCX flips target when both controls = |1⟩","category":"Multi-qubit","qubits":3,
         "gates":[{"gate":"X","qubit":0,"step":0},{"gate":"X","qubit":1,"step":0},
                  {"gate":"CCX","control1":0,"control2":1,"target":2,"qubit":0,"step":1}]},
        {"name":"2-Qubit QFT","desc":"Quantum Fourier Transform (core of Shor's)","category":"Algorithms","qubits":2,
         "gates":[{"gate":"H","qubit":0,"step":0},{"gate":"CRZ","control":1,"target":0,"angle":1.5707963,"qubit":1,"step":1},
                  {"gate":"H","qubit":1,"step":2},{"gate":"SWAP","control":0,"target":1,"qubit":0,"step":3}]},
        {"name":"Teleportation","desc":"Quantum state teleportation (3 qubits)","category":"Algorithms","qubits":3,
         "gates":[{"gate":"H","qubit":0,"step":0},{"gate":"H","qubit":1,"step":1},
                  {"gate":"CNOT","control":1,"target":2,"qubit":1,"step":2},
                  {"gate":"CNOT","control":0,"target":1,"qubit":0,"step":3},
                  {"gate":"H","qubit":0,"step":4}]},
    ])


if __name__ == "__main__":
    init_db()
    print("=" * 50)
    print("  ⚛  Quantum Circuit Builder")
    print("  Engine : Pure Python Statevector")
    print("  DB     : circuits.db (SQLite)")
    print("  Open   : http://localhost:5000")
    print("=" * 50)
    app.run(debug=True, port=5000, host="0.0.0.0")
