# ARIS — Law-Governed Execution System

ARIS is not a chatbot.

It is a law-governed execution system that **does not guess intent**.
It derives, verifies, and executes under constraint.

---

## 🚀 Start Here (30 seconds)

ARIS is currently distributed as **source** while runtime builds are being stabilized.

Run locally:

```bash
py -3.12 -m evolving_ai.aris_runtime.desktop
```

Then:

* Provide input (text or file)
* Observe semantic interpretation
* Review proposed actions
* Approve execution under law

> Prebuilt binaries (Windows/macOS/Linux) will be added in a future release.

---

## 🧠 What ARIS Actually Does

ARIS enforces structure where most systems rely on assumption.

* Input becomes a **SemanticEvent**
* Actions are **proposed, not assumed**
* Execution is **blocked unless approved**
* Every decision carries **identity, audit, and lineage**

---

## 🔁 Core Flow

```
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
```

---

## ⚙️ Key Properties

**Canonical Truth**
One semantic object flows through the entire system

**Observation ≠ Execution**
ARIS can analyze without acting

**Governance on the Causal Path**
Nothing executes without passing law

**Fail-Closed Behavior**
If something breaks, execution stops visibly

**No Demo Shortcuts**
Archived experiments are isolated from runtime

---

## 📄 Example Interaction

**You:**

```
Add environment controls to this project
```

**ARIS:**

```
Intent: Modify
System Risk: High
Actions: analyze → propose → apply → validate

[Approve] [Reject] [Inspect]
```

---

## 📁 Project Structure

```
/aris_runtime/   → core system (semantic + law + execution)
/release/        → packaged builds (in progress)
/docs/           → governance + system documentation
/LOGBOOK.md      → chronological system evolution
/SCARS.md        → stability model
```

---

## 🧠 Why This Exists

Most AI systems:

* guess intent
* execute immediately
* drift over time

ARIS is built to:

* derive intent structurally
* enforce decision boundaries
* remain stable under iteration

---

## 📘 Documentation

* Semantic Intake Under Law
* System Logbook
* SCARS — Stability Model
* Voss Binding (governance framework)

---

## 🧪 Development

Run locally:

```bash
py -3.12 -m evolving_ai.aris_runtime.desktop
```

Run tests:

```bash
pytest -q
```

---

## 🧩 Voss Binding Bundle

This repository includes a dedicated governance layer:

* Markdown governance artifacts
* Machine-readable `governance.json`
* Python implementations for binding + execution

Example usage:

```python
from evolving_ai.voss_binding import load_governance_bundle

bundle = load_governance_bundle()
print(bundle["suite"]["name"])
```

---

## ⚠️ Current Status

ARIS is in an **active development and stabilization phase**.

* Core system: functional
* Governance: enforced
* Runtime builds: in progress

---

## 🧭 Philosophy

> Infi = unbounded evolution within bounded law.

ARIS is designed so that:

* testing produces evidence
* verification determines truth
* proof grants admission

The system does not drift.
It evolves under constraint.

---

## 📌 Notes

* This is a **system-first project**, not a packaged product (yet)
* No binaries are distributed in this version
* Focus is on **architecture, law, and execution integrity**

---

## 👤 Author

Jon Halstead
(@warheart1984-ctrl)

---
## 📄 License

This project is licensed under the Apache License 2.0.

You are free to use, modify, and distribute this software, including for commercial use, under the terms of the license.

See the LICENSE file for details.

