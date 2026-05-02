# ARIS — Law-Governed Coding Agent

> ARIS is a coding agent that does not guess intent.  
> It **derives, verifies, and executes under law**.

---

## 🚀 Start Here (30 seconds)

1. Download the Windows build (ARIS V2):
   → [Download ARIS.exe](./release/ARIS_V2.exe) *(update link if needed)*

2. Run the executable

3. Tell ARIS what to do (or drop a file)

4. Watch the system:

   input  
   → semantic interpretation  
   → proposed action  
   → **approval under law**  
   → execution with visible state  

---

## 🧠 What ARIS Actually Does

ARIS is not a chatbot.

It is a **law-driven execution system** where:

- Input is converted into a **SemanticEvent**
- Actions are **proposed, not assumed**
- Execution is **blocked unless approved**
- Every decision carries **identity, audit, and lineage**

---

## 🔁 Core Flow


Input (text / file)
↓
Semantic Intake (no guessing)
↓
Decision Engine
↓
Law Gate (approval required)
↓
Execution (observable)
↓
Evidence + audit trail


---

## ⚙️ Key Properties

- **Canonical Truth**  
  One semantic object flows through the entire system

- **Observation ≠ Execution**  
  ARIS can analyze without acting

- **Governance on the Causal Path**  
  Nothing executes without passing law

- **Fail-Closed Behavior**  
  If something breaks, execution stops visibly

- **No Demo Shortcuts**  
  Archived experiments are isolated from runtime

---

## 📄 Example Interaction

You:

Add environment controls to this project


ARIS:

Intent: Modify System
Risk: High
Actions: analyze → propose → apply → validate

[Approve] [Reject] [Inspect]


---

## 📁 Project Structure


/aris_runtime/ → core system (semantic + law + execution)
/release/ → packaged builds
/LOGBOOK.md → chronological system evolution
/SCARS.md → why the system stays stable


---

## 🧠 Why This Exists

Most AI systems:
- guess intent  
- execute immediately  
- drift over time  

ARIS is built to:
- **derive intent structurally**
- **enforce decision boundaries**
- **remain stable under iteration**

---

## 📘 Documentation

- [Semantic Intake Under Law](./SEMANTIC_INTAKE_UNDER_LAW.md)
- [Release Notes (V2)](./release/ARIS_V2_SEMANTIC_INTAKE_RELEASE_NOTE.md)
- [System Logbook](./LOGBOOK.md)
- [SCARS — Stability Model](./SCARS.md)

---

## 🧪 Development

Run locally:

```bash
py -3.12 -m evolving_ai.aris_runtime.desktop

Run tests:

pytest -q
