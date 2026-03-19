from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import json
import os
import math
import random

app = Flask(__name__)
CORS(app)

DB_PATH = "circuits.db"

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
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────
# QUANTUM SIMULATOR (Pure Python, no Qiskit needed)
# ─────────────────────────────────────────
def simulate_circuit(num_qubits, gates):
    """
    Simple statevector quantum simulator using complex numbers.
    Supports: H, X, Y, Z, S, T, CNOT, SWAP gates.
    """
    size = 2 ** num_qubits
    # Start in |000...0> state
    state = [complex(0)] * size
    state[0] = complex(1)

    def apply_single_gate(state, qubit, matrix):
        """Apply a 2x2 gate matrix to a single qubit."""
        new_state = [complex(0)] * size
        for i in range(size):
            # Check if qubit bit is 0 or 1
            bit = (i >> qubit) & 1
            # Partner index (flip that bit)
            partner = i ^ (1 << qubit)
            if bit == 0:
                new_state[i] += matrix[0][0] * state[i] + matrix[0][1] * state[partner]
            else:
                new_state[i] += matrix[1][0] * state[partner] + matrix[1][1] * state[i]
        return new_state

    def apply_cnot(state, control, target):
        """Apply CNOT gate."""
        new_state = [complex(0)] * size
        for i in range(size):
            ctrl_bit = (i >> control) & 1
            if ctrl_bit == 1:
                # Flip target bit
                j = i ^ (1 << target)
                new_state[j] += state[i]
            else:
                new_state[i] += state[i]
        return new_state

    def apply_swap(state, q1, q2):
        """Apply SWAP gate."""
        new_state = [complex(0)] * size
        for i in range(size):
            b1 = (i >> q1) & 1
            b2 = (i >> q2) & 1
            if b1 != b2:
                j = i ^ (1 << q1) ^ (1 << q2)
                new_state[j] += state[i]
            else:
                new_state[i] += state[i]
        return new_state

    # Gate matrices
    I  = [[1, 0], [0, 1]]
    H  = [[1/math.sqrt(2),  1/math.sqrt(2)],
          [1/math.sqrt(2), -1/math.sqrt(2)]]
    X  = [[0, 1], [1, 0]]
    Y  = [[0, complex(0,-1)], [complex(0,1), 0]]
    Z  = [[1, 0], [0, -1]]
    S  = [[1, 0], [0, complex(0,1)]]
    T  = [[1, 0], [0, complex(math.cos(math.pi/4), math.sin(math.pi/4))]]

    GATE_MATRICES = {"H": H, "X": X, "Y": Y, "Z": Z, "S": S, "T": T}

    # Sort gates by step
    sorted_gates = sorted(gates, key=lambda g: g.get("step", 0))

    for gate in sorted_gates:
        g = gate.get("gate", "").upper()
        qubit = gate.get("qubit", 0)
        control = gate.get("control", 0)
        target = gate.get("target", 1)

        if g in GATE_MATRICES:
            if qubit < num_qubits:
                state = apply_single_gate(state, qubit, GATE_MATRICES[g])
        elif g == "CNOT":
            if control < num_qubits and target < num_qubits and control != target:
                state = apply_cnot(state, control, target)
        elif g == "SWAP":
            q1 = gate.get("qubit", 0)
            q2 = gate.get("target", 1)
            if q1 < num_qubits and q2 < num_qubits and q1 != q2:
                state = apply_swap(state, q1, q2)

    # Calculate probabilities from state vector
    probabilities = {}
    for i in range(size):
        prob = abs(state[i]) ** 2
        if prob > 0.0001:
            # Format as binary string, most significant bit first
            binary = format(i, f'0{num_qubits}b')
            probabilities[binary] = round(prob, 4)

    # Simulate 1024 shots based on probabilities
    states = list(probabilities.keys())
    probs  = list(probabilities.values())
    # Normalize
    total_prob = sum(probs)
    probs = [p / total_prob for p in probs]

    counts = {s: 0 for s in states}
    for _ in range(1024):
        r = random.random()
        cumulative = 0
        for s, p in zip(states, probs):
            cumulative += p
            if r <= cumulative:
                counts[s] += 1
                break

    return {
        "success": True,
        "probabilities": {k: round(v, 4) for k, v in probabilities.items()},
        "counts": counts,
        "total_shots": 1024,
        "num_qubits": num_qubits
    }


# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/simulate", methods=["POST"])
def simulate():
    data = request.get_json()
    qubits = data.get("qubits", 2)
    gates  = data.get("gates", [])

    if not gates:
        return jsonify({"error": "Add at least one gate!"}), 400
    if qubits < 1 or qubits > 8:
        return jsonify({"error": "Qubits must be between 1 and 8"}), 400

    result = simulate_circuit(qubits, gates)
    return jsonify(result)


@app.route("/api/circuits", methods=["GET"])
def get_circuits():
    conn = get_db()
    rows = conn.execute("SELECT * FROM circuits ORDER BY created_at DESC").fetchall()
    conn.close()
    circuits = []
    for row in rows:
        circuits.append({
            "id": row["id"],
            "name": row["name"],
            "qubits": row["qubits"],
            "gates": json.loads(row["gates"]),
            "last_result": json.loads(row["last_result"]) if row["last_result"] else None,
            "created_at": row["created_at"]
        })
    return jsonify(circuits)


@app.route("/api/circuits", methods=["POST"])
def save_circuit():
    data = request.get_json()
    name   = data.get("name", "Untitled")
    qubits = data.get("qubits", 2)
    gates  = data.get("gates", [])
    result = data.get("last_result", None)

    conn = get_db()
    conn.execute(
        "INSERT INTO circuits (name, qubits, gates, last_result) VALUES (?, ?, ?, ?)",
        (name, qubits, json.dumps(gates), json.dumps(result) if result else None)
    )
    conn.commit()
    conn.close()
    return jsonify({"message": f"Circuit '{name}' saved!"}), 201


@app.route("/api/circuits/<int:circuit_id>", methods=["DELETE"])
def delete_circuit(circuit_id):
    conn = get_db()
    conn.execute("DELETE FROM circuits WHERE id = ?", (circuit_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "Deleted"})


if __name__ == "__main__":
    init_db()
    print("✅ Database initialized")
    print("🚀 Starting Quantum Circuit Builder...")
    print("🌐 Open: http://localhost:5000")
    app.run(debug=True, port=5000)
