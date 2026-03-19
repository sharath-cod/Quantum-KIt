# ⚛ Quantum Circuit Builder
**Simple Full Stack: Flask + HTML/CSS/JS + SQLite**

No Node.js. No React. No MongoDB. Just Python.

## 📁 Project Structure
```
quantum-circuit-builder/
├── app.py              ← Flask backend (ALL backend code here)
├── requirements.txt    ← Python packages needed
├── circuits.db         ← SQLite database (auto-created on run)
└── templates/
    └── index.html      ← Frontend (HTML + CSS + JS all in one file)
```
## How the Simulator Works

The quantum simulator in `app.py` uses **pure Python math** (no Qiskit needed):

1. Starts in state |000...0⟩ (all zeros)
2. Represents the quantum state as a list of complex numbers (state vector)
3. Each gate applies a matrix transformation to the state vector
4. After all gates, calculates measurement probabilities using |amplitude|²
5. Simulates 1024 "shots" (measurements) to produce realistic counts



## Tech Stack

| Layer | Technology |
| Frontend | HTML + CSS + Vanilla JavaScript |
| Backend | Python + Flask |
| Database | SQLite (built into Python!) |
| Simulation | Pure Python math (complex numbers) |
