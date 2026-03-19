# ⚛ Quantum Circuit Builder
**Simple Full Stack: Flask + HTML/CSS/JS + SQLite**

No Node.js. No React. No MongoDB. Just Python.

---

## 📁 Project Structure
```
quantum-circuit-builder/
├── app.py              ← Flask backend (ALL backend code here)
├── requirements.txt    ← Python packages needed
├── circuits.db         ← SQLite database (auto-created on run)
└── templates/
    └── index.html      ← Frontend (HTML + CSS + JS all in one file)
```

---

## 🚀 How to Run

### Step 1 — Install Python packages
```bash
pip install -r requirements.txt
```

### Step 2 — Run the app
```bash
python app.py
```

### Step 3 — Open browser
```
http://localhost:5000
```

That's it! ✅

---

## 🔌 API Endpoints

| Method | URL | What it does |
|--------|-----|-------------|
| GET | `/` | Opens the web app |
| POST | `/api/simulate` | Runs quantum simulation |
| GET | `/api/circuits` | Gets all saved circuits |
| POST | `/api/circuits` | Saves a circuit |
| DELETE | `/api/circuits/<id>` | Deletes a circuit |

---

## ⚛ Quantum Gates

| Gate | What it does |
|------|-------------|
| H | Hadamard — superposition |
| X | Pauli-X — bit flip (quantum NOT) |
| Y | Pauli-Y — Y rotation |
| Z | Pauli-Z — phase flip |
| S | π/4 phase rotation |
| T | π/8 phase rotation |
| CNOT | Entangles two qubits |
| SWAP | Swaps two qubits |

---

## 🧪 Try These

**Bell State (Entanglement):**
- Qubits = 2 → H on Q0 (Step 0) → CNOT Q0→Q1 (Step 1)
- Result: 50% |00⟩ and 50% |11⟩

**Superposition:**
- Qubits = 1 → H on Q0
- Result: 50% |0⟩ and 50% |1⟩

**Bit Flip:**
- Qubits = 1 → X on Q0
- Result: 100% |1⟩

Or use the Quick Examples buttons in the app!

---

## 🎓 How the Simulator Works

The quantum simulator in `app.py` uses **pure Python math** (no Qiskit needed):

1. Starts in state |000...0⟩ (all zeros)
2. Represents the quantum state as a list of complex numbers (state vector)
3. Each gate applies a matrix transformation to the state vector
4. After all gates, calculates measurement probabilities using |amplitude|²
5. Simulates 1024 "shots" (measurements) to produce realistic counts

---

## 📦 Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML + CSS + Vanilla JavaScript |
| Backend | Python + Flask |
| Database | SQLite (built into Python!) |
| Simulation | Pure Python math (complex numbers) |
