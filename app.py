from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import json
import os
import math
import random
import cmath

app = Flask(__name__)
CORS(app)

DB_PATH = "circuits.db"

# ─────────────────────────────────────────
# QISKIT IMPORT (optional — graceful fallback)
# ─────────────────────────────────────────
try:
    from qiskit import QuantumCircuit, transpile
    from qiskit.quantum_info import Statevector, DensityMatrix, partial_trace
    from qiskit_aer import AerSimulator
    import numpy as np
    QISKIT_AVAILABLE = True
    print("✅ Qiskit + Aer loaded — using real quantum simulation")
except ImportError:
    QISKIT_AVAILABLE = False
    print("⚠️  Qiskit not found — using built-in statevector simulator")
    try:
        import numpy as np
        NUMPY_AVAILABLE = True
    except ImportError:
        NUMPY_AVAILABLE = False


# ─────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS circuits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            qubits INTEGER NOT NULL,
            gates TEXT NOT NULL,
            last_result TEXT,
            description TEXT DEFAULT '',
            tags TEXT DEFAULT '[]',
            run_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    for col, defval in [("description","''"), ("tags","'[]'"),
                        ("run_count","0"), ("updated_at","CURRENT_TIMESTAMP")]:
        try:
            c.execute(f"ALTER TABLE circuits ADD COLUMN {col} TEXT DEFAULT {defval}")
        except Exception:
            pass
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────
# QISKIT-POWERED SIMULATOR
# ─────────────────────────────────────────
def simulate_with_qiskit(num_qubits, gates, shots=2048):
    qc = QuantumCircuit(num_qubits, num_qubits)
    sorted_gates = sorted(gates, key=lambda g: g.get("step", 0))
    gate_count = {"single": 0, "two": 0, "three": 0}

    for gate in sorted_gates:
        g   = gate.get("gate", "").upper()
        q   = gate.get("qubit", 0)
        c   = gate.get("control", 0)
        t   = gate.get("target", 1)
        ang = float(gate.get("angle", math.pi / 2))
        try:
            if   g == "H"   and q < num_qubits: qc.h(q);          gate_count["single"] += 1
            elif g == "X"   and q < num_qubits: qc.x(q);          gate_count["single"] += 1
            elif g == "Y"   and q < num_qubits: qc.y(q);          gate_count["single"] += 1
            elif g == "Z"   and q < num_qubits: qc.z(q);          gate_count["single"] += 1
            elif g == "S"   and q < num_qubits: qc.s(q);          gate_count["single"] += 1
            elif g == "SDG" and q < num_qubits: qc.sdg(q);        gate_count["single"] += 1
            elif g == "T"   and q < num_qubits: qc.t(q);          gate_count["single"] += 1
            elif g == "TDG" and q < num_qubits: qc.tdg(q);        gate_count["single"] += 1
            elif g == "SX"  and q < num_qubits: qc.sx(q);         gate_count["single"] += 1
            elif g == "RX"  and q < num_qubits: qc.rx(ang, q);    gate_count["single"] += 1
            elif g == "RY"  and q < num_qubits: qc.ry(ang, q);    gate_count["single"] += 1
            elif g == "RZ"  and q < num_qubits: qc.rz(ang, q);    gate_count["single"] += 1
            elif g == "P"   and q < num_qubits: qc.p(ang, q);     gate_count["single"] += 1
            elif g in ("CNOT","CX") and c < num_qubits and t < num_qubits and c!=t:
                qc.cx(c, t);   gate_count["two"] += 1
            elif g == "CZ"  and c < num_qubits and t < num_qubits and c!=t:
                qc.cz(c, t);   gate_count["two"] += 1
            elif g == "CY"  and c < num_qubits and t < num_qubits and c!=t:
                qc.cy(c, t);   gate_count["two"] += 1
            elif g == "CH"  and c < num_qubits and t < num_qubits and c!=t:
                qc.ch(c, t);   gate_count["two"] += 1
            elif g == "SWAP" and c < num_qubits and t < num_qubits and c!=t:
                qc.swap(c, t); gate_count["two"] += 1
            elif g == "CRX" and c < num_qubits and t < num_qubits and c!=t:
                qc.crx(ang, c, t); gate_count["two"] += 1
            elif g == "CRY" and c < num_qubits and t < num_qubits and c!=t:
                qc.cry(ang, c, t); gate_count["two"] += 1
            elif g == "CRZ" and c < num_qubits and t < num_qubits and c!=t:
                qc.crz(ang, c, t); gate_count["two"] += 1
            elif g == "RZZ" and c < num_qubits and t < num_qubits and c!=t:
                qc.rzz(ang, c, t); gate_count["two"] += 1
            elif g == "CCX":
                c1=gate.get("control1",c); c2=gate.get("control2",1); tt=gate.get("target",2)
                if c1<num_qubits and c2<num_qubits and tt<num_qubits:
                    qc.ccx(c1, c2, tt); gate_count["three"] += 1
            elif g == "CSWAP":
                c1=gate.get("control",0); q1=gate.get("target",1); q2=gate.get("target2",2)
                if c1<num_qubits and q1<num_qubits and q2<num_qubits:
                    qc.cswap(c1, q1, q2); gate_count["three"] += 1
        except Exception as e:
            print(f"Gate error [{g}]: {e}")

    sv       = Statevector.from_instruction(qc)
    sv_data  = sv.data
    probs_dict = sv.probabilities_dict()
    probabilities = {k: round(float(v), 6) for k, v in
                     sorted(probs_dict.items(), key=lambda x: -x[1]) if v > 1e-6}

    qc_meas = qc.copy()
    qc_meas.measure(range(num_qubits), range(num_qubits))
    simulator = AerSimulator()
    job       = simulator.run(transpile(qc_meas, simulator), shots=shots)
    counts    = {k.replace(" ", ""): v for k, v in job.result().get_counts().items()}

    # Bloch vectors
    bloch = []
    dm = DensityMatrix(sv)
    for i in range(num_qubits):
        try:
            rho = np.array(partial_trace(dm, [j for j in range(num_qubits) if j!=i]).data)
            sx  = np.array([[0,1],[1,0]]); sy=np.array([[0,-1j],[1j,0]]); sz=np.array([[1,0],[0,-1]])
            bloch.append({"qubit":i,
                          "x": round(float(np.real(np.trace(rho@sx))),4),
                          "y": round(float(np.real(np.trace(rho@sy))),4),
                          "z": round(float(np.real(np.trace(rho@sz))),4)})
        except Exception:
            bloch.append({"qubit":i,"x":0,"y":0,"z":1})

    sv_display = []
    for idx, amp in enumerate(sv_data):
        if abs(amp) > 1e-6:
            sv_display.append({
                "state": format(idx, f"0{num_qubits}b"),
                "real":  round(float(np.real(amp)), 4),
                "imag":  round(float(np.imag(amp)), 4),
                "prob":  round(float(abs(amp)**2), 6),
                "phase": round(float(cmath.phase(complex(amp))), 4)
            })
    sv_display.sort(key=lambda x: -x["prob"])

    # Entanglement entropy
    entanglement = 0.0
    if num_qubits >= 2:
        try:
            half    = num_qubits // 2
            reduced = np.array(partial_trace(dm, list(range(half))).data)
            eigs    = np.linalg.eigvalsh(reduced)
            eigs    = eigs[eigs > 1e-12]
            entanglement = round(float(-np.sum(eigs * np.log2(eigs))), 4)
        except Exception:
            pass

    transpiled = transpile(qc, AerSimulator())
    return {
        "success": True, "engine": "Qiskit Aer",
        "probabilities": probabilities, "counts": counts,
        "statevector": sv_display, "bloch": bloch,
        "total_shots": shots, "num_qubits": num_qubits,
        "circuit_depth": transpiled.depth(),
        "gate_count": gate_count,
        "total_gates": sum(gate_count.values()),
        "entanglement_entropy": entanglement,
    }


# ─────────────────────────────────────────
# PURE-PYTHON FALLBACK SIMULATOR
# ─────────────────────────────────────────
def simulate_pure_python(num_qubits, gates, shots=2048):
    size  = 2 ** num_qubits
    state = [complex(0)] * size
    state[0] = complex(1)

    def apply_single(state, qubit, mat):
        ns = [complex(0)] * size
        for i in range(size):
            bit = (i >> qubit) & 1
            partner = i ^ (1 << qubit)
            if bit == 0:
                ns[i] += mat[0][0]*state[i] + mat[0][1]*state[partner]
            else:
                ns[i] += mat[1][0]*state[partner] + mat[1][1]*state[i]
        return ns

    def apply_cnot(state, ctrl, tgt):
        ns = [complex(0)] * size
        for i in range(size):
            if (i >> ctrl) & 1: ns[i^(1<<tgt)] += state[i]
            else:                ns[i]           += state[i]
        return ns

    def apply_cz(state, ctrl, tgt):
        ns = list(state)
        for i in range(size):
            if ((i>>ctrl)&1) and ((i>>tgt)&1): ns[i] = -state[i]
        return ns

    def apply_swap(state, q1, q2):
        ns = [complex(0)] * size
        for i in range(size):
            b1=(i>>q1)&1; b2=(i>>q2)&1
            if b1!=b2: ns[i^(1<<q1)^(1<<q2)] += state[i]
            else:       ns[i] += state[i]
        return ns

    def apply_ccx(state, c1, c2, tgt):
        ns = [complex(0)] * size
        for i in range(size):
            if ((i>>c1)&1) and ((i>>c2)&1): ns[i^(1<<tgt)] += state[i]
            else:                              ns[i]           += state[i]
        return ns

    sq2 = math.sqrt(2)
    MATS = {
        "H":  [[1/sq2,1/sq2],[1/sq2,-1/sq2]],
        "X":  [[0,1],[1,0]], "Y":[[0,complex(0,-1)],[complex(0,1),0]],
        "Z":  [[1,0],[0,-1]], "S":[[1,0],[0,complex(0,1)]],
        "SDG":[[1,0],[0,complex(0,-1)]],
        "T":  [[1,0],[0,cmath.exp(complex(0,math.pi/4))]],
        "TDG":[[1,0],[0,cmath.exp(complex(0,-math.pi/4))]],
        "SX": [[complex(.5,.5),complex(.5,-.5)],[complex(.5,-.5),complex(.5,.5)]],
    }

    def rx(a): return [[math.cos(a/2),complex(0,-math.sin(a/2))],[complex(0,-math.sin(a/2)),math.cos(a/2)]]
    def ry(a): return [[math.cos(a/2),-math.sin(a/2)],[math.sin(a/2),math.cos(a/2)]]
    def rz(a): return [[cmath.exp(complex(0,-a/2)),0],[0,cmath.exp(complex(0,a/2))]]
    def ph(a): return [[1,0],[0,cmath.exp(complex(0,a))]]

    for gate in sorted(gates, key=lambda g: g.get("step",0)):
        g   = gate.get("gate","").upper()
        q   = gate.get("qubit",0)
        c   = gate.get("control",0)
        t   = gate.get("target",1)
        ang = float(gate.get("angle",math.pi/2))
        if g in MATS and q < num_qubits:    state = apply_single(state, q, MATS[g])
        elif g=="RX" and q<num_qubits:       state = apply_single(state, q, rx(ang))
        elif g=="RY" and q<num_qubits:       state = apply_single(state, q, ry(ang))
        elif g=="RZ" and q<num_qubits:       state = apply_single(state, q, rz(ang))
        elif g=="P"  and q<num_qubits:       state = apply_single(state, q, ph(ang))
        elif g in ("CNOT","CX") and c<num_qubits and t<num_qubits and c!=t:
            state = apply_cnot(state, c, t)
        elif g=="CZ" and c<num_qubits and t<num_qubits and c!=t:
            state = apply_cz(state, c, t)
        elif g=="SWAP" and c<num_qubits and t<num_qubits and c!=t:
            state = apply_swap(state, c, t)
        elif g=="CCX":
            c1=gate.get("control1",c); c2=gate.get("control2",1); tt=gate.get("target",2)
            if c1<num_qubits and c2<num_qubits and tt<num_qubits:
                state = apply_ccx(state, c1, c2, tt)

    probs = {}
    for i in range(size):
        p = abs(state[i])**2
        if p > 1e-6: probs[format(i,f"0{num_qubits}b")] = round(p,6)
    probs = dict(sorted(probs.items(), key=lambda x: -x[1]))

    ks=list(probs.keys()); ps=list(probs.values())
    total=sum(ps); ps=[p/total for p in ps]
    counts={k:0 for k in ks}
    for _ in range(shots):
        r=random.random(); cum=0
        for k,p in zip(ks,ps):
            cum+=p
            if r<=cum: counts[k]+=1; break

    sv_display=[]
    for i,amp in enumerate(state):
        if abs(amp)>1e-6:
            sv_display.append({"state":format(i,f"0{num_qubits}b"),
                "real":round(amp.real,4),"imag":round(amp.imag,4),
                "prob":round(abs(amp)**2,6),"phase":round(cmath.phase(amp),4)})
    sv_display.sort(key=lambda x:-x["prob"])

    bloch=[]
    for qi in range(num_qubits):
        rho00=sum(abs(state[i])**2 for i in range(size) if not((i>>qi)&1))
        rho11=sum(abs(state[i])**2 for i in range(size) if (i>>qi)&1)
        rho01=sum(state[i]*state[i^(1<<qi)].conjugate() for i in range(size) if not((i>>qi)&1))
        bloch.append({"qubit":qi,"x":round(2*rho01.real,4),"y":round(-2*rho01.imag,4),"z":round(rho00-rho11,4)})

    return {
        "success":True,"engine":"Pure Python Statevector",
        "probabilities":probs,"counts":counts,"statevector":sv_display,"bloch":bloch,
        "total_shots":shots,"num_qubits":num_qubits,
        "circuit_depth":max((g.get("step",0) for g in gates),default=0)+1,
        "gate_count":{"single":0,"two":0,"three":0},"total_gates":len(gates),
        "entanglement_entropy":0.0,
    }


def simulate_circuit(num_qubits, gates, shots=2048):
    if QISKIT_AVAILABLE:
        try:
            return simulate_with_qiskit(num_qubits, gates, shots)
        except Exception as e:
            print(f"Qiskit error: {e}")
    return simulate_pure_python(num_qubits, gates, shots)


def export_qasm(num_qubits, gates):
    lines = ["OPENQASM 2.0;", 'include "qelib1.inc";',
             f"qreg q[{num_qubits}];", f"creg c[{num_qubits}];",""]
    SM = {"H":"h","X":"x","Y":"y","Z":"z","S":"s","SDG":"sdg","T":"t","TDG":"tdg","SX":"sx"}
    for g in sorted(gates, key=lambda x: x.get("step",0)):
        gn=g.get("gate","").upper(); q=g.get("qubit",0)
        c=g.get("control",0); t=g.get("target",1); ang=g.get("angle",math.pi/2)
        if gn in SM:             lines.append(f"{SM[gn]} q[{q}];")
        elif gn in("RX","RY","RZ"): lines.append(f"{gn.lower()}({ang:.6f}) q[{q}];")
        elif gn=="P":            lines.append(f"p({ang:.6f}) q[{q}];")
        elif gn in("CNOT","CX"): lines.append(f"cx q[{c}],q[{t}];")
        elif gn=="CZ":           lines.append(f"cz q[{c}],q[{t}];")
        elif gn=="CY":           lines.append(f"cy q[{c}],q[{t}];")
        elif gn=="SWAP":         lines.append(f"swap q[{c}],q[{t}];")
        elif gn=="CH":           lines.append(f"ch q[{c}],q[{t}];")
        elif gn=="CCX":
            c1=g.get("control1",c); c2=g.get("control2",1)
            lines.append(f"ccx q[{c1}],q[{c2}],q[{t}];")
    for i in range(num_qubits): lines.append(f"measure q[{i}] -> c[{i}];")
    return "\n".join(lines)


# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def status():
    return jsonify({"qiskit_available": QISKIT_AVAILABLE,
                    "engine": "Qiskit Aer" if QISKIT_AVAILABLE else "Pure Python Statevector"})

@app.route("/api/simulate", methods=["POST"])
def simulate():
    data   = request.get_json()
    qubits = int(data.get("qubits", 2))
    gates  = data.get("gates", [])
    shots  = int(data.get("shots", 2048))
    if not gates: return jsonify({"error": "Add at least one gate!"}), 400
    if qubits < 1 or qubits > 10: return jsonify({"error": "Qubits must be 1–10"}), 400
    if shots < 128 or shots > 65536: shots = 2048
    return jsonify(simulate_circuit(qubits, gates, shots))

@app.route("/api/export/qasm", methods=["POST"])
def export_qasm_route():
    data = request.get_json()
    return jsonify({"qasm": export_qasm(int(data.get("qubits",2)), data.get("gates",[]))})

@app.route("/api/circuits", methods=["GET"])
def get_circuits():
    conn = get_db()
    rows = conn.execute("SELECT * FROM circuits ORDER BY created_at DESC").fetchall()
    conn.close()
    out = []
    for row in rows:
        try: lr = json.loads(row["last_result"]) if row["last_result"] else None
        except: lr = None
        out.append({
            "id": row["id"], "name": row["name"], "qubits": row["qubits"],
            "gates": json.loads(row["gates"]), "last_result": lr,
            "description": row["description"] or "",
            "tags": json.loads(row["tags"]) if row["tags"] else [],
            "run_count": row["run_count"] or 0,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"] if row["updated_at"] else row["created_at"],
        })
    return jsonify(out)

@app.route("/api/circuits", methods=["POST"])
def save_circuit():
    data = request.get_json()
    name=data.get("name","Untitled"); qubits=int(data.get("qubits",2))
    gates=data.get("gates",[]); result=data.get("last_result",None)
    desc=data.get("description",""); tags=data.get("tags",[])
    conn = get_db()
    conn.execute(
        "INSERT INTO circuits (name,qubits,gates,last_result,description,tags) VALUES(?,?,?,?,?,?)",
        (name,qubits,json.dumps(gates),json.dumps(result) if result else None,desc,json.dumps(tags))
    )
    conn.commit(); conn.close()
    return jsonify({"message": f"Circuit '{name}' saved!", "success": True}), 201

@app.route("/api/circuits/<int:cid>", methods=["PUT"])
def update_circuit(cid):
    data=request.get_json(); conn=get_db()
    fields=[]; values=[]
    if "name"        in data: fields.append("name=?");        values.append(data["name"])
    if "description" in data: fields.append("description=?"); values.append(data["description"])
    if "tags"        in data: fields.append("tags=?");        values.append(json.dumps(data["tags"]))
    if "run_count"   in data: fields.append("run_count=?");   values.append(data["run_count"])
    fields.append("updated_at=CURRENT_TIMESTAMP")
    values.append(cid)
    conn.execute(f"UPDATE circuits SET {', '.join(fields)} WHERE id=?", values)
    conn.commit(); conn.close()
    return jsonify({"success": True})

@app.route("/api/circuits/<int:cid>", methods=["DELETE"])
def delete_circuit(cid):
    conn = get_db()
    conn.execute("DELETE FROM circuits WHERE id=?", (cid,))
    conn.commit(); conn.close()
    return jsonify({"message": "Deleted", "success": True})

@app.route("/api/examples")
def get_examples():
    return jsonify([
        {"name":"Bell State","desc":"Maximum entanglement: 50% |00⟩ + 50% |11⟩","category":"Entanglement",
         "qubits":2,"gates":[{"gate":"H","qubit":0,"step":0},{"gate":"CNOT","control":0,"target":1,"qubit":0,"step":1}]},
        {"name":"GHZ State","desc":"3-qubit entanglement: (|000⟩+|111⟩)/√2","category":"Entanglement",
         "qubits":3,"gates":[{"gate":"H","qubit":0,"step":0},{"gate":"CNOT","control":0,"target":1,"qubit":0,"step":1},{"gate":"CNOT","control":0,"target":2,"qubit":0,"step":2}]},
        {"name":"Superposition","desc":"Single qubit: |+⟩ = (|0⟩+|1⟩)/√2","category":"Basics",
         "qubits":1,"gates":[{"gate":"H","qubit":0,"step":0}]},
        {"name":"Quantum NOT","desc":"X gate: |0⟩ → |1⟩","category":"Basics",
         "qubits":1,"gates":[{"gate":"X","qubit":0,"step":0}]},
        {"name":"Phase Kickback","desc":"H-Z-H = X (phase kickback demo)","category":"Algorithms",
         "qubits":1,"gates":[{"gate":"H","qubit":0,"step":0},{"gate":"Z","qubit":0,"step":1},{"gate":"H","qubit":0,"step":2}]},
        {"name":"Quantum Teleportation","desc":"Teleports qubit state using 3 qubits","category":"Algorithms",
         "qubits":3,"gates":[{"gate":"H","qubit":0,"step":0},{"gate":"H","qubit":1,"step":1},
                              {"gate":"CNOT","control":1,"target":2,"qubit":1,"step":2},
                              {"gate":"CNOT","control":0,"target":1,"qubit":0,"step":3},
                              {"gate":"H","qubit":0,"step":4}]},
        {"name":"Toffoli Gate","desc":"CCX: flips target when both controls = |1⟩","category":"Multi-qubit",
         "qubits":3,"gates":[{"gate":"X","qubit":0,"step":0},{"gate":"X","qubit":1,"step":0},
                              {"gate":"CCX","control1":0,"control2":1,"target":2,"qubit":0,"step":1}]},
        {"name":"2-Qubit QFT","desc":"Quantum Fourier Transform — core of Shor's algorithm","category":"Algorithms",
         "qubits":2,"gates":[{"gate":"H","qubit":0,"step":0},{"gate":"CRZ","control":1,"target":0,"angle":1.5707963,"qubit":1,"step":1},
                              {"gate":"H","qubit":1,"step":2},{"gate":"SWAP","control":0,"target":1,"qubit":0,"step":3}]},
    ])


if __name__ == "__main__":
    init_db()
    print(f"🔬 Engine: {'Qiskit Aer' if QISKIT_AVAILABLE else 'Pure Python'}")
    print("🚀 http://localhost:5000")
    app.run(debug=True, port=5000)
