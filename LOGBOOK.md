# ARIS / Evolving AI Logbook

This logbook is the required record for major changes in the Evolving AI repo.

Rule:
- After every major change, append an entry here.
- Every entry must record:
  - `What changed`
  - `Why it changed`
  - `How it changed`
  - `Files changed`
  - `Verification`
  - `Remaining risks`

Entry template:

```md
## YYYY-MM-DD - Short Title
What changed:
- ...

Why it changed:
- ...

How it changed:
- ...

Files changed:
- [path]

Verification:
- ...

Remaining risks:
- ...
```

## 2026-04-13 - ARIS Governed Assembly (Backfilled)
What changed:
- Assembled ARIS inside the existing Evolving AI repo instead of a new project.
- Bound Jarvis blueprint inheritance, Operator flow, Forge, Forge Eval, guardrails, halls, and startup into one governed service.
- Added the ARIS startup path and operator console UI.

Why it changed:
- ARIS needed to exist as one unified governed build target inside the live repo.
- The startup path needed to be real, inspectable, and fail closed when governance was incomplete.
- The UI needed to show real runtime state instead of a disconnected mock shell.

How it changed:
- Added an ARIS runtime and service layer as the shared governance spine.
- Bound execution, approval, and mutation seams to ARIS review and finalize hooks.
- Extended the existing 630 shell and FastAPI app instead of replacing it.

Files changed:
- [README.md](/C:/Users/randj/Desktop/project%20infi/code/code/README.md)
- [evolving_ai/aris/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/runtime.py)
- [evolving_ai/aris/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/service.py)
- [evolving_ai/aris/launcher.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/launcher.py)
- [evolving_ai/app/server.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/server.py)
- [evolving_ai/app/static/index.html](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/index.html)
- [evolving_ai/app/static/app.js](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/app.js)

Verification:
- Core Python files compiled.
- ARIS startup and health output were exercised during assembly and hardening.
- Governed seams were covered with focused tests.

Remaining risks:
- Full startup still depends on the local Python environment having the required runtime dependencies installed.

## 2026-04-13 - Governance Hardening And Hall Separation (Backfilled)
What changed:
- Hardened risky-path verification, discard containment, kill switch enforcement, tamper lockdown, and hall separation.
- Split outcomes so correctness failures go to Hall of Shame, escalation failures go to Hall of Discard, and verified success goes to Hall of Fame.
- Added lineage-based re-evaluation tracking so items do not move directly between halls.

Why it changed:
- Assembly alone was not enough; risky paths needed to prove they could not proceed on one judgment alone.
- Hall separation needed to be explicit and enforceable.
- Startup, health, and UI needed to report real backend truth and not overclaim readiness.

How it changed:
- Routed approval, patch, write, hunk, line, and execution seams through the same enforcement spine.
- Added hall lineage metadata and immutable hall-entry behavior.
- Surfaced shell/backend degradation in runtime status, API health, launcher output, and UI.

Files changed:
- [evolving_ai/aris/hall_base.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/hall_base.py)
- [evolving_ai/aris/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/runtime.py)
- [evolving_ai/aris/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/service.py)
- [evolving_ai/aris/launcher.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/launcher.py)
- [evolving_ai/app/server.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/server.py)
- [evolving_ai/app/static/app.js](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/app.js)
- [tests/test_aris_governance.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_governance.py)

Verification:
- Governance tests were expanded and run.
- Health/status payloads were checked for backend truth.
- Launcher and UI were updated to reflect live state.

Remaining risks:
- Environment dependency gaps can still block full boot even when governance code is correct.

## 2026-04-13 - Mystic Core And Runtime Merged With Jarvis
What changed:
- Added a real Mystic runtime component to ARIS and marked it as Jarvis-merged rather than sidecar-only.
- Added a governed Mystic read path through ARIS service and API.
- Added a Mystic Deck panel to the existing UI.

Why it changed:
- Mystic needed to exist inside the governed ARIS/Jarvis architecture, not as an unbound separate repo.
- Mystic needed to be visible in startup and health state like Forge and Forge Eval.
- Mystic needed to run through the same law/evaluation spine as other ARIS actions.

How it changed:
- Ported the AAIS Jarvis-native Mystic engine into a dedicated ARIS runtime component.
- Registered Mystic in ARIS startup blockers and runtime status.
- Added `POST /api/aris/mystic-read` and routed it through `review_action -> Mystic -> finalize_action`.
- Extended the current console with a real Mystic Deck panel bound to the backend route.

Files changed:
- [evolving_ai/aris/mystic_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic_runtime.py)
- [evolving_ai/aris/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/runtime.py)
- [evolving_ai/aris/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/service.py)
- [evolving_ai/aris/launcher.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/launcher.py)
- [evolving_ai/app/server.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/server.py)
- [evolving_ai/app/static/index.html](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/index.html)
- [evolving_ai/app/static/app.js](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/app.js)
- [tests/test_aris_governance.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_governance.py)

Verification:
- `C:\Python314\python.exe -m py_compile ...`
- `node --check C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\static\app.js`
- Direct runtime probes confirmed Mystic is active and Jarvis-merged.
- Direct Mystic runtime execution returned a real reading.

Remaining risks:
- Full FastAPI startup is still blocked in this environment by missing runtime dependencies like `uvicorn` and `requests`.
- The current test environment also has an ABI mismatch if it tries to borrow AAIS `pydantic_core` binaries.

## 2026-04-13 - Logbook Requirement Added
What changed:
- Added this repo logbook and established the required major-change entry format.

Why it changed:
- Major ARIS work now needs a durable record of what changed, why it changed, and how it changed.
- The project needed one canonical place to inspect implementation history without relying on chat history alone.

How it changed:
- Added `LOGBOOK.md` at the repo root.
- Backfilled recent major ARIS changes.
- Added a pointer from the README so the logbook is visible from the main repo entrypoint.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [README.md](/C:/Users/randj/Desktop/project%20infi/code/code/README.md)

Verification:
- Logbook created in repo root.
- README points to the logbook.

Remaining risks:
- This depends on continued discipline: future major changes still need explicit entries appended here.

## 2026-04-13 - Repo-Changing Success Now Requires Verification And Logbook Match
What changed:
- Bound finalize-time success for repo-changing actions to a stricter 1001 gate.
- ARIS now refuses repo-changing success unless verification evidence and a matching Repo Logbook entry are both present.
- Surfaced Repo Logbook state in runtime health and status outputs.

Why it changed:
- Code written by itself is not enough to count as real success for a repo-changing action.
- Undocumented change must be treated as unverified change under 1001.
- Repo-changing completion needed one explicit rule: change, verification, and documentation must agree at finalize time.

How it changed:
- Added a Repo Logbook helper and startup/status visibility for the logbook.
- Added finalize-time enforcement in ARIS runtime for `repo_changed` actions.
- Required four conditions before repo-changing success can verify:
- `verification_artifacts`
- `logbook_entry`
- `logbook_entry_matches_change`
- `1001_pass`
- Added direct tests for the fail path and the verified path.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [evolving_ai/aris/logbook.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/logbook.py)
- [evolving_ai/aris/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/runtime.py)
- [evolving_ai/aris/launcher.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/launcher.py)
- [evolving_ai/app/static/app.js](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/app.js)
- [tests/test_aris_governance.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_governance.py)

Verification:
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\logbook.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\runtime.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\launcher.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_governance.py`
- `node --check C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\static\app.js`
- Direct runtime probe: repo-changing action without verification/docs was refused and routed to Hall of Discard.
- Direct runtime probe: same action with verification artifacts plus matching logbook entry verified to Hall of Fame.

Remaining risks:
- Full unittest execution is still blocked in this environment by missing FastAPI/uvicorn-compatible local dependencies.
- Repo-changing detection currently relies on explicit `repo_changed=True` or clear repo-target hints; broader repo-path classification may still need expansion later.

## 2026-04-13 - Shield And Mystic Refactor Completed Under Verification
What changed:
- Split Shield of Truth into the requested protected-core package structure under [evolving_ai/aris/shield](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/shield).
- Split Mystic into the requested sustainment-first package structure under [evolving_ai/aris/mystic](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic), with `Mystic` as operator sustainment and `Mystic Reflection` as the reflective subfeature.
- Rebound service, API, launcher, runtime, and UI so Shield remains behind the law spine and Mystic Reflection no longer impersonates the sustainment layer.
- Fixed the remaining hardening bugs discovered during verification.

Why it changed:
- The repo still had legacy single-name Mystic assumptions that blurred sustainment and reflection authority.
- Shield needed to exist as a real protected-core adjudication layer, not a single file with partial wiring.
- The new structure had to pass real startup and governance verification before it could count as success under 1001.

How it changed:
- Added canonical `shield/` modules for laws, registries, verification context, and the 1001 adjudicator, then left [shield_of_truth.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/shield_of_truth.py) as a compatibility export shim.
- Added canonical `mystic/` modules for sustainment, session monitoring, cooldowns, escalation, UI controls, reading, and reflection, then left [mystic_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic_runtime.py) and [mystic_reflection.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic_reflection.py) as compatibility shims.
- Fixed Shield entry/finalize mutation handling by carrying mutation artifacts through adjudication so ordinary governed workspace mutations are not falsely quarantined.
- Fixed Mystic sustainment JSON output so `minutes_since_voice` no longer emits non-JSON `Infinity`.
- Reordered bypass enforcement so bypass attempts still pass through Shield, but return the explicit `hard_kill` enforcement mode required by the bypass law.
- Installed the declared project dependencies into the active Python 3.12 environment and reran real verification instead of stopping at compile-only checks.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [evolving_ai/aris/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/runtime.py)
- [evolving_ai/aris/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/service.py)
- [evolving_ai/aris/launcher.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/launcher.py)
- [evolving_ai/aris/shield_of_truth.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/shield_of_truth.py)
- [evolving_ai/aris/shield/__init__.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/shield/__init__.py)
- [evolving_ai/aris/shield/laws.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/shield/laws.py)
- [evolving_ai/aris/shield/registries.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/shield/registries.py)
- [evolving_ai/aris/shield/verification.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/shield/verification.py)
- [evolving_ai/aris/shield/adjudicator_1001.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/shield/adjudicator_1001.py)
- [evolving_ai/aris/mystic/__init__.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/__init__.py)
- [evolving_ai/aris/mystic/sustainment.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/sustainment.py)
- [evolving_ai/aris/mystic/session_monitor.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/session_monitor.py)
- [evolving_ai/aris/mystic/cooldowns.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/cooldowns.py)
- [evolving_ai/aris/mystic/escalation.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/escalation.py)
- [evolving_ai/aris/mystic/ui_controls.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/ui_controls.py)
- [evolving_ai/aris/mystic/reading.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/reading.py)
- [evolving_ai/aris/mystic/reflection.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/reflection.py)
- [evolving_ai/aris/mystic/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/service.py)
- [evolving_ai/aris/mystic/state.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/state.py)
- [evolving_ai/aris/mystic/rules.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/rules.py)
- [evolving_ai/aris/mystic/messages.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic/messages.py)
- [evolving_ai/aris/mystic_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic_runtime.py)
- [evolving_ai/aris/mystic_reflection.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/mystic_reflection.py)
- [evolving_ai/app/server.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/server.py)
- [evolving_ai/app/static/index.html](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/index.html)
- [evolving_ai/app/static/app.js](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/app.js)
- [tests/test_aris_governance.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_governance.py)

Verification:
- `py -3.12 -m pip install -e .`
- `py -3.12 -m pip install pytest`
- `py -3.12 -m pytest -q tests\test_aris_governance.py`
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\runtime.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\service.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\launcher.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\server.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\shield\adjudicator_1001.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\mystic\sustainment.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_governance.py`
- `node --check C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\static\app.js`
- `py -3.12 -m evolving_ai.aris --reseal-integrity --healthcheck`
- Verified result: `28 passed` in `tests/test_aris_governance.py`

Remaining risks:
- Normal startup without reseal will still fail closed after protected-core edits, which is expected; protected changes require explicit reseal.
- Shell execution remains degraded on this machine because Docker is unavailable, but ARIS reports that truthfully and stays governed.

## 2026-04-13 - Added ARIS Demo Copy Stripped Of Forge And Evolving Engine
What changed:
- Added a separate `evolving_ai/aris_demo` package as a copy-profile of ARIS for demo use.
- Stripped Forge, Forge Eval, and the evolving engine admission path out of that demo runtime while keeping 1001, Shield of Truth, Mystic sustainment, Mystic Reflection, halls, integrity checks, and the kill switch.
- Added a dedicated demo launcher path, PowerShell helper, and Windows console-script shim support through `aris-demo`.
- Corrected the UI and welcome route text so the demo copy no longer claims the live Forge path when Forge is intentionally absent.

Why it changed:
- The user wanted a copy of ARIS, not a second live server, and wanted that copy stripped of the evolving engine.
- A demo runtime still needs to stay truthful under 1001; it cannot present `Jarvis -> Operator -> Forge -> Forge Eval -> Outcome` if Forge is removed.
- The repo needed a launchable demo profile that preserves ARIS identity and law while explicitly limiting authority.

How it changed:
- Added `ArisDemoRuntime` as a subclassed ARIS runtime profile that ignores Forge startup blockers, clears Forge and Forge Eval from runtime state, marks the evolving engine as stripped, and exposes a demo-safe route of `Jarvis Blueprint -> Operator -> Governance Review -> Outcome`.
- Added `ArisDemoChatService`, `aris_demo.server`, `aris_demo.launcher`, and `aris_demo.__main__` so the demo profile can boot through the existing FastAPI shell without duplicating the whole server stack.
- Updated the shared app factory in `evolving_ai/app/server.py` so alternate governed service builders can reuse the same UI/API surface.
- Updated the UI to render runtime identity from backend state, disable the governed plan button in demo mode, and replace the hardcoded Forge route copy with the live route supplied by runtime status.
- Added a PowerShell helper and a `pyproject.toml` console script so editable install creates `aris-demo.exe` on Windows.
- Added focused demo tests and reran the full ARIS governance suite after the app-factory seam change.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [README.md](/C:/Users/randj/Desktop/project%20infi/code/code/README.md)
- [pyproject.toml](/C:/Users/randj/Desktop/project%20infi/code/code/pyproject.toml)
- [run_aris_demo.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/run_aris_demo.ps1)
- [evolving_ai/app/server.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/server.py)
- [evolving_ai/app/static/index.html](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/index.html)
- [evolving_ai/app/static/app.js](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/app.js)
- [evolving_ai/aris_demo/__init__.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/__init__.py)
- [evolving_ai/aris_demo/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/runtime.py)
- [evolving_ai/aris_demo/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/service.py)
- [evolving_ai/aris_demo/server.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/server.py)
- [evolving_ai/aris_demo/launcher.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/launcher.py)
- [evolving_ai/aris_demo/__main__.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/__main__.py)
- [tests/test_aris_demo.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo.py)

Verification:
- `py -3.12 -m py_compile code\evolving_ai\app\server.py code\evolving_ai\aris_demo\__init__.py code\evolving_ai\aris_demo\runtime.py code\evolving_ai\aris_demo\service.py code\evolving_ai\aris_demo\server.py code\evolving_ai\aris_demo\launcher.py code\evolving_ai\aris_demo\__main__.py code\tests\test_aris_demo.py`
- `node --check code\evolving_ai\app\static\app.js`
- `py -3.12 -m pytest -q tests\test_aris_demo.py`
- `py -3.12 -m pytest -q tests\test_aris_governance.py tests\test_aris_demo.py`
- `py -3.12 -m evolving_ai.aris_demo --reseal-integrity --healthcheck`
- `py -3.12 -m pip install -e .`
- Verified `aris-demo.exe` created at `C:\Users\randj\AppData\Local\Packages\PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0\LocalCache\local-packages\Python312\Scripts\aris-demo.exe`

Remaining risks:
- The demo profile intentionally reports Forge and Forge Eval as stripped, so any risky repo mutation path remains blocked rather than partially emulated.
- The shared UI still contains general-purpose repo surfaces from the 630 shell; the demo runtime disables or truthfully reports unavailable governed plan paths, but broader cosmetic demo-specific trimming could still be done later if wanted.

## 2026-04-14 - Desktop Delivery Workspace And Windows Release Built
What changed:
- Added repo-level desktop delivery helpers and a cross-platform GitHub Actions workflow for native Windows, macOS, and Linux packaging.
- Created a dedicated desktop project folder at `C:\Users\randj\Desktop\project infi\ARIS Demo Desktop` with release docs, scripts, and build output directories.
- Built and zipped the optimized Windows desktop bundle into the new desktop project folder.

Why it changed:
- The user wanted the full delivery path, not only a desktop codebase sitting inside the repo.
- A top-level desktop workspace makes it easier to find launch/build artifacts from `project infi` without digging back into `code/code`.
- Native packaging for three operating systems needs both a local release workspace and an automation path that runs on each target OS.

How it changed:
- Added `run_aris_demo_desktop.ps1` and `build_aris_demo_desktop.ps1` in the repo so the desktop host can be launched and packaged directly from the codebase.
- Added `.github/workflows/aris-demo-desktop-build.yml` as a matrix workflow that installs desktop build dependencies, smokechecks the desktop host, and produces native artifacts on Windows, macOS, and Linux.
- Tightened `desktop_build.py` so the PyInstaller command only includes the Qt modules actually used by the desktop shell, reducing the Windows bundle from a broad over-collected build to a smaller targeted package.
- Created `ARIS Demo Desktop/README.md` plus platform scripts under `ARIS Demo Desktop/scripts/` and built the Windows release at `ARIS Demo Desktop/builds/windows/release-20260414/`.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [README.md](/C:/Users/randj/Desktop/project%20infi/code/code/README.md)
- [build_aris_demo_desktop.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/build_aris_demo_desktop.ps1)
- [run_aris_demo_desktop.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/run_aris_demo_desktop.ps1)
- [evolving_ai/aris_demo/desktop_build.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_build.py)
- [ARIS Demo Desktop/README.md](</C:/Users/randj/Desktop/project infi/ARIS Demo Desktop/README.md>)
- [ARIS Demo Desktop/scripts/build-windows.ps1](</C:/Users/randj/Desktop/project infi/ARIS Demo Desktop/scripts/build-windows.ps1>)
- [ARIS Demo Desktop/scripts/build-macos.sh](</C:/Users/randj/Desktop/project infi/ARIS Demo Desktop/scripts/build-macos.sh>)
- [ARIS Demo Desktop/scripts/build-linux.sh](</C:/Users/randj/Desktop/project infi/ARIS Demo Desktop/scripts/build-linux.sh>)
- [ARIS Demo Desktop/scripts/launch-windows.ps1](</C:/Users/randj/Desktop/project infi/ARIS Demo Desktop/scripts/launch-windows.ps1>)
- [ARIS Demo Desktop/scripts/print-targets.ps1](</C:/Users/randj/Desktop/project infi/ARIS Demo Desktop/scripts/print-targets.ps1>)
- [aris-demo-desktop-build.yml](/C:/Users/randj/Desktop/project%20infi/code/code/.github/workflows/aris-demo-desktop-build.yml)

Verification:
- `py -3.12 -m py_compile evolving_ai\aris_demo\desktop_build.py evolving_ai\aris_demo\desktop.py evolving_ai\aris_demo\desktop_app.py evolving_ai\aris_demo\desktop_support.py tests\test_aris_demo_desktop.py`
- `py -3.12 -m pytest -q tests\test_aris_demo_desktop.py tests\test_aris_demo.py`
- `py -3.12 -m evolving_ai.aris_demo.desktop_build --print-command`
- `C:\Users\randj\Desktop\project infi\ARIS Demo Desktop\scripts\print-targets.ps1`
- `C:\Users\randj\Desktop\project infi\ARIS Demo Desktop\scripts\build-windows.ps1 -BuildTag release-20260414`
- Packaged executable smokecheck: `ARIS Demo.exe --headless-smokecheck --no-workers`

Artifacts:
- Windows bundle folder: [ARIS Demo](</C:/Users/randj/Desktop/project infi/ARIS Demo Desktop/builds/windows/release-20260414/dist/ARIS Demo>)
- Windows bundle zip: [ARIS Demo-windows-release-20260414.zip](</C:/Users/randj/Desktop/project infi/ARIS Demo Desktop/builds/windows/release-20260414/ARIS Demo-windows-release-20260414.zip>)

Remaining risks:
- macOS and Linux bundles are wired and ready through scripts plus CI, but they still need to be built on native macOS and Linux runners or machines before those artifacts physically exist beside the Windows release.
- The Windows bundle is now significantly leaner, but signing, notarization, installer creation, and update delivery are still future delivery layers rather than part of this pass.

## 2026-04-14 - ARIS Demo Desktop Host Added On Top Of The Extracted UL Runtime
What changed:
- Added a cross-platform ARIS Demo desktop host and window shell on top of the existing `ArisDemoChatService` instead of creating a second runtime path.
- Exposed the extracted UL runtime, governance halls, workspace state, mystic surfaces, kill switch, and governed operator chat inside a dedicated desktop interface.
- Added native packaging entrypoints for Windows, macOS, and Linux without making the desktop dependency mandatory for headless ARIS or UL runtime users.

Why it changed:
- The user wanted ARIS Demo to become a real windowed program that shows usable features rather than a browser/API-only demo.
- The UL runtime extraction created a clean host boundary, so the right next step was to mount a desktop host onto the existing ARIS Demo service instead of refactoring core runtime code again.
- Cross-platform delivery needed one shared codebase and explicit packaging seams, not three separate UI rewrites.

How it changed:
- Added `evolving_ai/aris_demo/desktop_support.py` as the shared controller layer for desktop session management, feature inventory, SSE chat streaming, mystic controls, kill switch actions, and build-target metadata.
- Added `evolving_ai/aris_demo/desktop_app.py` as a PySide6 desktop shell with Overview, Operator, Governance, Workspace, and Mystic surfaces wired to live ARIS Demo payloads.
- Added `evolving_ai/aris_demo/desktop.py` for GUI launch and headless smokechecks, plus `evolving_ai/aris_demo/desktop_build.py` for native PyInstaller command generation and target inspection.
- Updated packaging metadata in `pyproject.toml` with optional desktop dependencies and desktop-specific entrypoints so Windows, macOS, and Linux can share the same host implementation.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [pyproject.toml](/C:/Users/randj/Desktop/project%20infi/code/code/pyproject.toml)
- [evolving_ai/aris_demo/__init__.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/__init__.py)
- [evolving_ai/aris_demo/desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop.py)
- [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py)
- [evolving_ai/aris_demo/desktop_build.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_build.py)
- [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py)
- [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py)

Verification:
- `py -3.12 -m py_compile evolving_ai\aris_demo\desktop_support.py evolving_ai\aris_demo\desktop_build.py evolving_ai\aris_demo\desktop.py evolving_ai\aris_demo\desktop_app.py tests\test_aris_demo_desktop.py`
- `py -3.12 -m pytest -q tests\test_aris_demo_desktop.py tests\test_aris_demo.py`
- `py -3.12 -m evolving_ai.aris_demo.desktop --headless-smokecheck --no-workers`
- `py -3.12 -m evolving_ai.aris_demo.desktop_build --print-command`

Remaining risks:
- Native binaries still need to be built on each target OS; the repo now exposes the shared desktop host and build commands, but it does not yet ship prebuilt artifacts or signing/notarization automation.
- The first desktop pass focuses on truthful runtime visibility and governed interaction; richer patch-approval editing or drag-and-drop attachments could still be added later without changing the runtime/core split.

## 2026-04-14 - UL Runtime Extracted From The Existing AAIS ARIS Blueprint
What changed:
- Extracted a canonical `ULRuntimeSubstrate` from the existing AAIS/ARIS law modules instead of inventing a separate runtime path.
- Made the Universal Adapter Protocol the active host-binding layer for runtime identity evaluation.
- Added explicit CISIV stage reporting and exposed the extracted UL runtime substrate through ARIS status.
- Hardened protected identity handling so copy-protected identities now require lawful adapter binding, declared host capabilities, legitimacy, and lineage.

Why it changed:
- The blueprint already contained the runtime substrate, but it was still implicit across `src` and `evolving_ai/aris`.
- Protected identity claims were still partially shaped by Python-side defaults instead of being evaluated through the Universal Adapter Protocol.
- CISIV, UL identity source, the Law of Speech, and the Non-Copy Clause needed to exist as first-class runtime enforcement data, not just comments or root-law text.

How it changed:
- Added `src/ul_runtime.py` as the extracted canonical substrate, composed from the existing law spine, bootstrap, ledger, foundation store, adapter, identity, mutation, and verification primitives.
- Added `src/cisiv.py` so staged governance is evaluated as runtime phase data without inventing a parallel architecture.
- Extended host declaration and adapter binding logic so hosts must declare capabilities and protected identities can be rejected when the host cannot satisfy identity-preserving requirements.
- Extended law context and runtime preflight/post-execution payloads to carry lineage origin, host capabilities, adapter-binding state, CISIV stage status, and the explicit `0001 -> 1000 -> 1001` speech chain.
- Rebound the FastAPI bridge and ARIS status surface onto the extracted substrate while keeping API/Jarvis/Forge concerns outside the runtime core.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [src/__init__.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/__init__.py)
- [src/adapter_protocol.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/adapter_protocol.py)
- [src/api.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/api.py)
- [src/cisiv.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/cisiv.py)
- [src/constants_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/constants_runtime.py)
- [src/host_attestation.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/host_attestation.py)
- [src/identity_registry.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/identity_registry.py)
- [src/identity_verifier.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/identity_verifier.py)
- [src/law_context_builder.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/law_context_builder.py)
- [src/runtime_law.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/runtime_law.py)
- [src/ul_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/ul_runtime.py)
- [src/verification_engine.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/verification_engine.py)
- [evolving_ai/aris/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/runtime.py)
- [tests/test_law_hardening.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_law_hardening.py)
- [tests/test_law_spine.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_law_spine.py)

Verification:
- `py -3.12 -m py_compile src\adapter_protocol.py src\cisiv.py src\host_attestation.py src\identity_registry.py src\identity_verifier.py src\law_context_builder.py src\runtime_law.py src\ul_runtime.py src\verification_engine.py src\api.py evolving_ai\aris\runtime.py tests\test_law_spine.py tests\test_law_hardening.py`
- `py -3.12 -m pytest -q tests\test_law_spine.py`
- `py -3.12 -m pytest -q tests\test_law_hardening.py`
- `py -3.12 -m pytest -q tests\test_mutation_gate.py`
- `py -3.12 -m pytest -q tests\test_aris_governance.py`

Remaining risks:
- The extracted substrate is now explicit, but more of the legacy ARIS review/finalize flow still references it as a consumer rather than delegating every law result into a single substrate API.
- External host identity claims now bind through declared capabilities, but no separate production host registry exists yet beyond legitimacy tokens plus the adapter capability contract.

## 2026-04-13 - UL CISLR Runtime Law Spine Enforced Across AAIS And ARIS
What changed:
- Added a real `src/` runtime-law package that loads immutable root law, builds internal law context, attests hosts, verifies identity, enforces mutation admission, binds Forge and Forge Eval, records a mandatory JSONL ledger, and performs post-execution `1001` verification.
- Bound the live ARIS runtime, FastAPI entry path, and memory layer onto that law spine instead of leaving enforcement as scattered local checks.
- Added Override Reckoning, post-verification observation freeze, foundational memory isolation, and caller-authority hardening so spoofed identity, fake verification, direct mutation, and law-context injection all fail closed.

Why it changed:
- The user asked for the full UL / CISLR dropdown implementation as structural runtime enforcement, not documentation.
- Law-relevant facts could not remain partially caller-shaped if ARIS and AAIS were going to enforce identity, lineage, boundaries, verification, and degradation truthfully.
- Repo-changing success in this repo now requires code, verification, and documentation to agree under `1001`, so the hardening pass also had to become explicit and traceable in the Repo Logbook.

How it changed:
- Created a new law kernel in `src/` with immutable root-law loading, manifest hashing, bootstrap integrity checks, host attestation, identity verification, mutation admission, verification engine, foundational store, and reusable law-wrapped execution primitives.
- Installed `LawApiBridge` at the FastAPI request entry seam, routed operator review through `JarvisOperator` and `RuntimeLaw`, wrapped Forge and Forge Eval with law-bound clients, and rebound ARIS `review_action` and `finalize_action` to consume the shared runtime law context.
- Hardened memory and repo-write seams so foundational memory cannot be shadowed, repo mutation cannot escape the mutation broker, post-`1001` mutation is temporarily frozen until observation occurs, and Windows local execution no longer leaks bad `%SystemDrive%` paths into the workspace when Docker fallback is used.
- Expanded the test surface with law-spine, memory-lock, mutation-gate, law-hardening, governance, and app-level observation tests, then reran the entire suite plus runtime health checks.

Files changed:
- Added:
  [src/__init__.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/__init__.py)
  [src/adapter_protocol.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/adapter_protocol.py)
  [src/api.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/api.py)
  [src/bootstrap_law.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/bootstrap_law.py)
  [src/cisiv.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/cisiv.py)
  [src/constants_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/constants_runtime.py)
  [src/conversation_memory.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/conversation_memory.py)
  [src/forge_client.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/forge_client.py)
  [src/forge_eval_client.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/forge_eval_client.py)
  [src/foundation_store.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/foundation_store.py)
  [src/host_attestation.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/host_attestation.py)
  [src/identity_registry.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/identity_registry.py)
  [src/identity_verifier.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/identity_verifier.py)
  [src/jarvis_operator.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/jarvis_operator.py)
  [src/law_context_builder.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/law_context_builder.py)
  [src/law_decorators.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/law_decorators.py)
  [src/law_ledger.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/law_ledger.py)
  [src/law_spine.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/law_spine.py)
  [src/mutation_broker.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/mutation_broker.py)
  [src/mutation_gate.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/mutation_gate.py)
  [src/runtime_law.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/runtime_law.py)
  [src/ul_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/ul_runtime.py)
  [src/verification_engine.py](/C:/Users/randj/Desktop/project%20infi/code/code/src/verification_engine.py)
  [tests/test_law_hardening.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_law_hardening.py)
  [tests/test_law_spine.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_law_spine.py)
  [tests/test_memory_lock.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_memory_lock.py)
  [tests/test_mutation_gate.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_mutation_gate.py)
- Modified:
  [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
  [pyproject.toml](/C:/Users/randj/Desktop/project%20infi/code/code/pyproject.toml)
  [evolving_ai/app/execution.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/execution.py)
  [evolving_ai/app/memory.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/memory.py)
  [evolving_ai/app/server.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/server.py)
  [evolving_ai/app/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/service.py)
  [evolving_ai/aris/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/runtime.py)
  [evolving_ai/aris/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/service.py)
  [tests/test_ai_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_ai_app.py)
  [tests/test_aris_governance.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_governance.py)

Verification:
- `py -3.12 -m pytest -q`
- `py -3.12 -m evolving_ai.aris --reseal-integrity --healthcheck`
- `py -3.12 -m py_compile C:\Users\randj\Desktop\project infi\code\code\src\__init__.py C:\Users\randj\Desktop\project infi\code\code\src\adapter_protocol.py C:\Users\randj\Desktop\project infi\code\code\src\api.py C:\Users\randj\Desktop\project infi\code\code\src\bootstrap_law.py C:\Users\randj\Desktop\project infi\code\code\src\cisiv.py C:\Users\randj\Desktop\project infi\code\code\src\constants_runtime.py C:\Users\randj\Desktop\project infi\code\code\src\conversation_memory.py C:\Users\randj\Desktop\project infi\code\code\src\forge_client.py C:\Users\randj\Desktop\project infi\code\code\src\forge_eval_client.py C:\Users\randj\Desktop\project infi\code\code\src\foundation_store.py C:\Users\randj\Desktop\project infi\code\code\src\host_attestation.py C:\Users\randj\Desktop\project infi\code\code\src\identity_registry.py C:\Users\randj\Desktop\project infi\code\code\src\identity_verifier.py C:\Users\randj\Desktop\project infi\code\code\src\jarvis_operator.py C:\Users\randj\Desktop\project infi\code\code\src\law_context_builder.py C:\Users\randj\Desktop\project infi\code\code\src\law_decorators.py C:\Users\randj\Desktop\project infi\code\code\src\law_ledger.py C:\Users\randj\Desktop\project infi\code\code\src\law_spine.py C:\Users\randj\Desktop\project infi\code\code\src\mutation_broker.py C:\Users\randj\Desktop\project infi\code\code\src\mutation_gate.py C:\Users\randj\Desktop\project infi\code\code\src\runtime_law.py C:\Users\randj\Desktop\project infi\code\code\src\ul_runtime.py C:\Users\randj\Desktop\project infi\code\code\src\verification_engine.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\execution.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\memory.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\server.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\service.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\runtime.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\service.py C:\Users\randj\Desktop\project infi\code\code\tests\test_ai_app.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_governance.py C:\Users\randj\Desktop\project infi\code\code\tests\test_law_hardening.py C:\Users\randj\Desktop\project infi\code\code\tests\test_law_spine.py C:\Users\randj\Desktop\project infi\code\code\tests\test_memory_lock.py C:\Users\randj\Desktop\project infi\code\code\tests\test_mutation_gate.py`
- Verified result: full suite passed with `110 passed`.
- Verified result: ARIS healthcheck reported `1001 active: True`, `Shield of Truth active: True`, `Forge connected: True`, `Forge Eval connected: True`, `Shell execution: ready`, and `Startup blockers: none`.

Remaining risks:
- The runtime law spine is structurally enforced, but any future entrypoint added outside the current FastAPI and ARIS runtime seams will still need to be explicitly law-wrapped rather than assumed safe by convention.
- Host legitimacy currently depends on runtime attestation plus adapter capability checks; a broader external production host registry could still be added later if the deployment model expands.

## 2026-04-14 - Hardened ARIS Demo EXE Startup And Desktop Entry
What changed:
- Fixed the broken desktop demo entry module so `evolving_ai.aris_demo.desktop` can launch again instead of dying on a malformed fallback import block.
- Hardened the demo startup path by removing eager optional dependency imports from the desktop-adjacent runtime stack.
- Added a safer desktop data-root fallback so the demo can start even when the default `%LOCALAPPDATA%` path is not writable.
- Added focused regression tests for the desktop entry and startup-softening seams.

Why it changed:
- The user reported that the demo EXE was not loading.
- The actual break was a bad import block in the desktop launcher, and the deeper seam problem was that optional parser and HTTP client dependencies were being imported at module load time, causing the app to fail before the UI could even open.
- The desktop shell needed to survive lighter Python environments and sandboxed paths more gracefully instead of crashing on import or default-path setup.

How it changed:
- Repaired the import fallback in [evolving_ai/aris_demo/desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop.py) so desktop-app import failure produces a clean startup error instead of a broken module.
- Added data-root fallback logic in [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py) so the host falls back to `.runtime/aris_demo_desktop` when the default desktop app-data path cannot be created.
- Moved optional import seams behind actual use in [evolving_ai/app/files.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/files.py), [evolving_ai/app/providers.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/providers.py), [evolving_ai/app/tools.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/tools.py), and [evolving_ai/app/web.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/web.py) so missing `bs4`, `pypdf`, `docx`, or `httpx` no longer kills startup on paths that do not actively need them.
- Added direct regression coverage in [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py) and [tests/test_demo_startup_softening.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_demo_startup_softening.py).

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [evolving_ai/aris_demo/desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop.py)
- [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py)
- [evolving_ai/app/files.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/files.py)
- [evolving_ai/app/providers.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/providers.py)
- [evolving_ai/app/tools.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/tools.py)
- [evolving_ai/app/web.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/web.py)
- [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py)
- [tests/test_ai_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_ai_app.py)
- [tests/test_demo_startup_softening.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_demo_startup_softening.py)

Verification:
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_support.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\files.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\providers.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\tools.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\web.py C:\Users\randj\Desktop\project infi\code\code\tests\test_demo_startup_softening.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_demo_desktop.py`
- `C:\Python314\python.exe -m unittest tests.test_demo_startup_softening tests.test_aris_demo_desktop`
- `C:\Python314\python.exe -m evolving_ai.aris_demo.desktop --headless-smokecheck --no-workers`
- Verified result: focused desktop/startup suite passed with `9 tests OK`.
- Verified result: headless desktop smokecheck succeeded and reported `ARIS Demo`, `ul_runtime_present: true`, and the demo-safe runtime route `Jarvis Blueprint -> Operator -> Governance Review -> Outcome`.

Remaining risks:
- If the user is launching a previously built packaged desktop binary, that binary will need to be rebuilt to pick up the fixed launcher and softened import seams.
- The desktop console-script entry now survives lighter environments much better, but full interactive runtime still depends on the declared GUI/runtime dependencies being installed when the user is not using a packaged binary.

## 2026-04-14 - Built Full ARIS Workspace Brain Controls Demo
What changed:
- Rebuilt the single-file ARIS workspace prototype into a full operator-facing demo with Brain Controls, repo/workspace navigation, ARIS chat, a task board, right-rail brain summary, activity feed, approvals, and worker status.
- Added demo behavior that changes ARIS wording, route summaries, status pills, and task updates based on Mode, Scope, Target, Permission, and Response Style.
- Added an explicit protected boundary so the evolving core is never exposed in target selectors, route lists, or demo behavior.
- Added a contract test that locks the target list and protected-route copy.

Why it changed:
- The user wanted a full demo version where ARIS feels like a real operator-facing intelligence layer instead of a plain chat surface.
- The demo needed to preserve ARIS identity while still showing believable routing to Forge and ForgeEval.
- The evolving core had to remain explicitly unavailable from the demo surface in both UI and logic.

How it changed:
- Replaced the earlier prototype shell in [prototypes/ArisWorkspaceDemo.jsx](/C:/Users/randj/Desktop/project%20infi/code/code/prototypes/ArisWorkspaceDemo.jsx) with a richer single-file React demo built from inline shadcn-style primitives plus Framer Motion transitions.
- Added control sets for Mode, Scope, Target, Permission / Risk, and Response Style; wired them into a deterministic `buildDecision` path that changes ARIS response content, route indicators, task-state mock updates, worker messaging, and activity items.
- Enforced the protected boundary in the same single-file demo by keeping the target list to `ARIS Only`, `Forge`, `ForgeEval`, `Runtime`, `Memory`, and `Operator Review`, then blocking prompt attempts that imply evolving-core access with explicit refusal messaging and allowed alternatives.
- Added [tests/test_aris_workspace_demo_contract.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_workspace_demo_contract.py) to verify the allowed target list, required brain-control sets, protected copy, and route examples.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [prototypes/ArisWorkspaceDemo.jsx](/C:/Users/randj/Desktop/project%20infi/code/code/prototypes/ArisWorkspaceDemo.jsx)
- [tests/test_aris_workspace_demo_contract.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_workspace_demo_contract.py)

Verification:
- `C:\Python314\python.exe -m unittest tests.test_aris_workspace_demo_contract`
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_workspace_demo_contract.py`
- Verified result: contract suite passed with `4 tests OK`.
- Verified result: target options include `ARIS Only`, `Forge`, `ForgeEval`, `Runtime`, `Memory`, and `Operator Review`, and do not include the evolving core.

Remaining risks:
- This demo is intentionally frontend-only and deterministic, so task changes and worker updates are mock behavior until it is wired into a real ARIS turn engine.
- I validated the protected boundary contract at the source level, but there is no JSX build pipeline in this repo yet to run a full component compile check automatically.

## 2026-04-14 - Upgraded ARIS Demo Into A Repo-Centered Operator Workspace
What changed:
- Reworked the ARIS Demo desktop operator tab into a real repo-centered workspace surface instead of a plain chat split.
- Added a host-generated workspace surface model with repo cards, task lanes, activity feed, and worker-status shaping that can use real workspace payloads when present and fall back to polished demo data when empty.
- Kept ARIS as the operator-facing voice while confining Forge to worker status, logs, patch output, and validation-style surfaces.
- Preserved the raw workspace inspector as a separate tab so the demo gains the polished operator shell without losing its lower-level diagnostic view.

Why it changed:
- The user wanted the actual ARIS Demo to reflect the Codex-like workspace model from the prototype rather than leaving that experience as a detached concept.
- The existing desktop host already had repo, task, approval, and workspace seams, but the visible surface still read more like a chat tool plus diagnostics than an operator workspace.

How it changed:
- Added workspace-surface shaping in [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py) so snapshots now expose repo, task, activity, and worker data for the UI.
- Reworked the main operator UI in [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py) into a three-pane workspace with repo management, ARIS chat, task board, selected repo/task context, worker surface, and activity feed.
- Extended [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py) to verify the new workspace surface is present and the selected project path flows into repo state.

Verification:
- `py -3.12 -m py_compile evolving_ai\aris_demo\desktop_support.py evolving_ai\aris_demo\desktop_app.py tests\test_aris_demo_desktop.py`
- `py -3.12 -m pytest -q tests\test_aris_demo_desktop.py tests\test_aris_demo.py`
- `py -3.12 -m evolving_ai.aris_demo.desktop --headless-smokecheck --no-workers`
- Offscreen window instantiation verified `ARIS Demo Desktop`, `Workspace`, repo list population, and task list population.

## 2026-04-14 - Mounted Brain Controls Into The Live ARIS Demo Desktop Workspace
What changed:
- Wired the full Brain Controls model into the existing ARIS Demo desktop Workspace tab instead of leaving it isolated in the React prototype.
- Replaced the old mode/fast-mode toolbar with a real operator-facing Brain Controls bar for `Mode`, `Scope`, `Target`, `Permission / Risk`, and `Response Style`.
- Rebound the Workspace chat surface to a deterministic ARIS demo decision spine so the desktop app now produces structured ARIS responses, route summaries, worker-lane updates, and protected-route refusals locally.
- Added a recent-tasks sidebar, a right-rail Brain State card, and a Worker / Protection Status card so the desktop shell reads like a real operator deck.
- Hardened the desktop host startup path against malformed local desktop state where `.forge_chat` or `knowledge` already exists as a file.

Why it changed:
- The next phase after the single-file prototype was to mount that experience into the actual downloadable ARIS Demo shell instead of leaving it as a disconnected concept file.
- The live desktop app already had a strong workspace frame, so the right move was seam-based extension rather than replacing the shell.
- The desktop startup path still had a real local-state bug that could block headless smokecheck and EXE startup when stale files polluted the expected desktop data tree.

How it changed:
- Added shared demo-decision logic in [evolving_ai/aris_demo/workspace_demo_logic.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/workspace_demo_logic.py) so the Brain Controls options, protected evolving-core boundary, route shaping, and ARIS response behavior all live in one reusable pure module.
- Extended [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py) to use that logic for the live Workspace tab, add the new Brain Controls bar, update selected repo/task context, populate a recent-tasks sidebar, and render Brain State plus Worker / Protection cards.
- Updated fallback workspace seed data in [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py) so the desktop shell and prototype now share the same repo/task story, including `Inspect protected execution boundaries`.
- Hardened [evolving_ai/app/knowledge.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/knowledge.py) and [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py) so malformed local state files no longer crash demo desktop startup; the host now falls back to a safe repo-local runtime directory when the default desktop tree is polluted.
- Added focused regression coverage in [tests/test_aris_demo_workspace_logic.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_workspace_logic.py) and extended [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py).

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [evolving_ai/app/knowledge.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/knowledge.py)
- [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py)
- [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py)
- [evolving_ai/aris_demo/workspace_demo_logic.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/workspace_demo_logic.py)
- [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py)
- [tests/test_aris_demo_workspace_logic.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_workspace_logic.py)

Verification:
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\knowledge.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\workspace_demo_logic.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_support.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_app.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_demo_workspace_logic.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_demo_desktop.py`
- `C:\Python314\python.exe -m unittest tests.test_aris_demo_workspace_logic tests.test_aris_demo_desktop`
- `C:\Python314\python.exe -m evolving_ai.aris_demo.desktop --headless-smokecheck --no-workers`
- Verified result: focused desktop workspace suite passed with `12 tests OK`.
- Verified result: headless desktop smokecheck succeeded and reported `ARIS Demo`, `ul_runtime_present: true`, and the demo runtime route `Jarvis Blueprint -> Operator -> Governance Review -> Outcome`.

Remaining risks:
- The Workspace tab brain behavior is now mounted into the live desktop shell, but it is still deterministic demo logic rather than a real ARIS turn engine.
- I could not run a live Qt window-instantiation smoke in this interpreter because `PySide6` is not installed in `C:\Python314`; the desktop host, smokecheck, and packaged-entry seams are verified, but live-window verification still needs the GUI runtime available in the executing Python environment.

## 2026-04-14 - Built A UL-Bound PySide6 Desktop Runtime For ARIS Demo
What changed:
- Added a real UL-bound desktop runtime bootstrap that creates, verifies, and documents a dedicated PySide6-capable runtime for ARIS Demo under `.runtime/ul_desktop_runtime`.
- Added a canonical manifest for the desktop runtime using the UL substrate, including identity source, governance model, speech chain, foundation entries, desktop modules, and build/launch modules.
- Updated the desktop run/build helper scripts to prefer the UL desktop runtime automatically once it exists.
- Added a Windows helper script for preparing the runtime and hardened the bootstrap against broken `venv` creation by falling back to `virtualenv` when needed.

Why it changed:
- The desktop shell was wired and verified headlessly, but `C:\Python314` itself was not PySide6-capable and could not cleanly materialize a desktop venv on this machine.
- The repo needed one canonical runtime path for the downloadable desktop app instead of relying on whichever interpreter happened to launch the script.
- The user asked for a PySide6-capable runtime using UL, so the correct move was to bind the desktop runtime bootstrap to the UL substrate rather than make it a separate ad hoc environment.

How it changed:
- Added [evolving_ai/aris_demo/desktop_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_runtime.py) to build and verify the UL desktop runtime, emit a manifest, print canonical run/build commands, and prepare the runtime with `desktop` or `desktop-build` extras.
- Extended [evolving_ai/aris_demo/desktop_build.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_build.py) so PyInstaller commands can be generated against the dedicated runtime interpreter instead of the host interpreter.
- Added [prepare_aris_demo_desktop_runtime.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/prepare_aris_demo_desktop_runtime.ps1) and updated [run_aris_demo_desktop.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/run_aris_demo_desktop.ps1) plus [build_aris_demo_desktop.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/build_aris_demo_desktop.ps1) to prefer `.runtime/ul_desktop_runtime/venv`, parse passthrough flags correctly, and default desktop build artifacts into a repo-local runtime build root instead of an out-of-workspace folder.
- Added [tests/test_aris_demo_desktop_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop_runtime.py) for the manifest and command seams.
- Added the new runtime entrypoint to [pyproject.toml](/C:/Users/randj/Desktop/project%20infi/code/code/pyproject.toml) and documented it in [README.md](/C:/Users/randj/Desktop/project%20infi/code/code/README.md).
- Materialized the runtime successfully by installing `virtualenv` and PySide6, then running the UL bootstrap outside the sandbox so it could reach the user-level runtime tools and complete the venv plus smokecheck.

Files changed:
- [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md)
- [README.md](/C:/Users/randj/Desktop/project%20infi/code/code/README.md)
- [pyproject.toml](/C:/Users/randj/Desktop/project%20infi/code/code/pyproject.toml)
- [build_aris_demo_desktop.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/build_aris_demo_desktop.ps1)
- [run_aris_demo_desktop.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/run_aris_demo_desktop.ps1)
- [prepare_aris_demo_desktop_runtime.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/prepare_aris_demo_desktop_runtime.ps1)
- [evolving_ai/aris_demo/desktop_build.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_build.py)
- [evolving_ai/aris_demo/desktop_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_runtime.py)
- [tests/test_aris_demo_desktop_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop_runtime.py)

Verification:
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_runtime.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_build.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_demo_desktop_runtime.py`
- `C:\Python314\python.exe -m unittest tests.test_aris_demo_desktop_runtime`
- `C:\Python314\python.exe -m evolving_ai.aris_demo.desktop_runtime --print-plan --with-build-tools`
- `C:\Python314\python.exe -m pip install virtualenv PySide6 PyInstaller`
- `C:\Python314\python.exe -m evolving_ai.aris_demo.desktop_runtime --prepare --with-build-tools`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -c "import PySide6; print(PySide6.__file__)"`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris_demo.desktop_runtime --print-build-command --with-build-tools`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m unittest tests.test_aris_demo_workspace_logic tests.test_aris_demo_desktop tests.test_aris_demo_desktop_runtime`
- `.\build_aris_demo_desktop.ps1 --print-command`
- Verified result: the UL desktop runtime was created successfully at `.runtime/ul_desktop_runtime/venv`.
- Verified result: the runtime imports `PySide6` successfully, desktop smokecheck passes, and the combined desktop test suite passes with `16 tests OK` from inside the UL runtime.

Remaining risks:
- This phase built the PySide6-capable UL desktop runtime and verified the canonical PyInstaller command, but it did not run the full native bundle build yet.
- The desktop runtime currently uses Python 3.14 because that was the accessible interpreter on this machine; if you later want strict parity with a separate 3.12 desktop toolchain, the bootstrap now supports swapping the base interpreter explicitly.

## 2026-04-15 - ARIS Shipping Lane

Implemented a dedicated Shipping Lane for ARIS Demo so release packaging is no longer a manual build-copy-zip sequence.

Added:
- [evolving_ai/aris_demo/shipping_lane.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/shipping_lane.py)
- [evolving_ai/aris_demo/profiles.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/profiles.py)
- [evolving_ai/aris_demo/desktop_v1.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_v1.py)
- [evolving_ai/aris_demo/desktop_v2.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_v2.py)
- [build_aris_demo_variants.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/build_aris_demo_variants.ps1)
- [tests/test_aris_demo_shipping_lane.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_shipping_lane.py)

Updated:
- [evolving_ai/aris_demo/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/runtime.py)
- [evolving_ai/aris_demo/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/service.py)
- [evolving_ai/aris_demo/desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop.py)
- [evolving_ai/aris_demo/desktop_build.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_build.py)
- [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py)
- [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py)
- [pyproject.toml](/C:/Users/randj/Desktop/project%20infi/code/code/pyproject.toml)
- [tests/test_aris_demo.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo.py)
- [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py)

Shipping Lane behavior:
- Runs precheck before shipping and fails if entry points, repo assets, or shipping dependencies are missing.
- Verifies source smokechecks for `demo`, `v1`, and `v2` before building.
- Builds each variant through the existing build lane, then copies the full runnable folder into the main project `dist` folder.
- Verifies release structure, writes `release-manifest.json`, creates `.zip` archives, and verifies the packaged EXEs launch from the shipped folders.
- Exposes a one-button `Ship Release` operator action in the desktop workspace and a CLI entrypoint via `aris-demo-ship-release`.

Verification:
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\shipping_lane.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_support.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_app.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_demo_shipping_lane.py`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m unittest tests.test_aris_demo tests.test_aris_demo_desktop tests.test_aris_demo_shipping_lane`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris_demo.shipping_lane --precheck-only`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris_demo.shipping_lane --build-tag ship-20260415`

Generated release artifacts:
- [dist](/C:/Users/randj/Desktop/project%20infi/dist)
- [release-manifest.json](/C:/Users/randj/Desktop/project%20infi/dist/release-manifest.json)
- [ARIS Demo](/C:/Users/randj/Desktop/project%20infi/dist/ARIS%20Demo)
- [ARIS Demo.zip](/C:/Users/randj/Desktop/project%20infi/dist/ARIS%20Demo.zip)
- [ARIS Demo V1](/C:/Users/randj/Desktop/project%20infi/dist/ARIS%20Demo%20V1)
- [ARIS Demo V1.zip](/C:/Users/randj/Desktop/project%20infi/dist/ARIS%20Demo%20V1.zip)
- [ARIS Demo V2](/C:/Users/randj/Desktop/project%20infi/dist/ARIS%20Demo%20V2)
- [ARIS Demo V2.zip](/C:/Users/randj/Desktop/project%20infi/dist/ARIS%20Demo%20V2.zip)

## 2026-04-15 - Lawful Completion Doctrine
What changed:
- Added a canonical doctrine file defining lawful completion of a system.
- Wrote the same completion rule into the main repo README and the parent workspace index.
- Added project-level document copies so the rule exists in both repo docs and Project Infi document space.

Why it changed:
- Build success was not strong enough as a completion claim.
- The project needed one plain rule that distinguishes source assembly from delivered completion.
- Shipping Lane needed an explicit doctrinal reason to exist separately from Build Lane.

How it changed:
- Authored one canonical markdown statement of lawful completion.
- Threaded the rule into repo-facing and workspace-facing documents.
- Generated a standalone project document and updated the core runtime spec document with the same completion doctrine.

Files changed:
- [LAWFUL_COMPLETION_OF_A_SYSTEM.md](/C:/Users/randj/Desktop/project%20infi/code/code/LAWFUL_COMPLETION_OF_A_SYSTEM.md)
- [README.md](/C:/Users/randj/Desktop/project%20infi/code/code/README.md)
- [WORKSPACE_INDEX.md](/C:/Users/randj/Desktop/project%20infi/WORKSPACE_INDEX.md)

Verification:
- Repo markdown files were updated and linked.
- Project-level document generation and runtime-spec document update were executed after the repo doc pass.

Remaining risks:
- Only the canonical project document and the core runtime spec were updated directly; other legacy Word documents in the parent workspace may still describe completion more loosely until they are individually revised.

## 2026-04-15 - ARIS Governed Memory Bank And Cognitive Upgrade Wrapper
What changed:
- Added a governed ARIS memory bank with separate foundational, operational, learned_patterns, rejected_patterns, and archive layers.
- Replaced the old flat ARIS memory adapter with a compatibility wrapper backed by the new layered bank.
- Added a bounded ARIS cognitive-upgrade wrapper that evaluates transformer-style upgrades relative to baseline, persists trial history, and keeps ARIS as the identity anchor.
- Wired both systems into live ARIS runtime status and the ARIS chat service.

Why it changed:
- ARIS needed its own bounded memory authority model instead of treating all memory as equal or flat session facts.
- The requested cognitive-upgrade corrections required relative improvement checks, persistent evidence, and explicit identity preservation.
- Upgrades needed to wrap the core ARIS call rather than creating a competing brain path.

How it changed:
- Added `GovernedMemoryBank` as the layered memory authority spine and projected foundational root memory from the locked foundation store.
- Reworked `MemoryStore` into a compatibility adapter that routes user memory into the governed operational layer while preserving a legacy export for existing callers.
- Added `CognitiveUpgradeManager` and `ArisCognitiveUpgradeProvider` so upgrades run as `pre_process -> core_aris_call -> post_process`, record history, and only admit results that improve relative to baseline while remaining lawful, stable, and identity-preserving.
- Bound the new bank and upgrade manager into `ArisRuntime` status and `ArisChatService` startup so the live service uses them instead of disconnected helpers.

Files changed:
- [evolving_ai/aris/memory_bank.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/memory_bank.py)
- [evolving_ai/aris/cognitive_upgrade.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/cognitive_upgrade.py)
- [evolving_ai/aris/runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/runtime.py)
- [evolving_ai/aris/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/service.py)
- [evolving_ai/app/memory.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/memory.py)
- [tests/test_aris_memory_bank.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_memory_bank.py)
- [tests/test_aris_cognitive_upgrade.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_cognitive_upgrade.py)

Verification:
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\memory_bank.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\cognitive_upgrade.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\runtime.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\service.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\memory.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_memory_bank.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_cognitive_upgrade.py`
- `C:\Python314\python.exe -m unittest tests.test_aris_memory_bank tests.test_aris_cognitive_upgrade`
- Direct runtime probe confirmed `memory_bank.active == True`, `cognitive_upgrade.active == True`, and foundational root memory resolves to `ARIS_HANDBOOK_LOCKED`.
- Direct service probe confirmed ARIS chat now uses `GovernedMemoryBank` and `ArisCognitiveUpgradeProvider`.

Remaining risks:
- The upgrade wrapper evaluates baseline plus transformed variants, so it adds latency on non-agent chat turns by design.
- Identity preservation is now an explicit guard, but it is still a placeholder-style structural check rather than a full semantic identity proof system.
- Archive and rejected-pattern retrieval rules are enforced in the bank, but broader runtime use of those layers for planning and avoidance can still be expanded later.

## 2026-04-15 - ARIS Studio Workspace, Feedback Path, And Voice Lane
What changed:
- Added a bounded multi-workspace registry and file explorer for ARIS Studio with registered roots, active workspace switching, safe path validation, file preview, search, and action packets.
- Rebuilt the main ARIS desktop workspace into a cockpit-style Studio shell with a top status strip, left explorer, center system tabs, right ARIS chat surface, and a bottom event/log stream.
- Added structured tester feedback export with runtime context, event snapshots, workspace metadata, and optional external form routing.
- Added a narrow ARIS voice lane for short system events with ElevenLabs-first delivery, PySide6 multimedia playback, and `pyttsx3` fallback when available.

Why it changed:
- The demo needed to move from a repo chat layout toward an operator-facing coding workspace where ARIS can work across bounded project roots safely.
- File actions, tester feedback, and event history all needed a shared runtime spine so the demo could stay believable and reproducible without opening machine-wide browsing.
- Voice needed to stay intentionally narrow and non-blocking so it supports the demo without turning ARIS into a chat reader.

How it changed:
- Added `WorkspaceRegistry` as a persisted workspace spine with allowed-action rules and path-bound validation before any file operation is admitted.
- Extended `ArisDemoDesktopHost` to manage workspace registry state, file previews, search, structured event logging, feedback packet export, and workspace-aware snapshot payloads.
- Replaced the old operator tab composition with an ARIS Studio shell that keeps governance, memory, upgrades, runtime, and file viewing in the center while leaving ARIS chat on the operator side and events in the lower stream.
- Added a voice module that uses ElevenLabs over HTTP with `eleven_flash_v2_5` by default, falls back to `eleven_multilingual_v2`, and drops to `pyttsx3` when the API path is unavailable.

Files changed:
- [evolving_ai/aris_demo/workspace_registry.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/workspace_registry.py)
- [evolving_ai/aris_demo/feedback.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/feedback.py)
- [evolving_ai/aris_demo/voice.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/voice.py)
- [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py)
- [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py)
- [evolving_ai/aris_demo/desktop_build.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_build.py)
- [pyproject.toml](/C:/Users/randj/Desktop/project%20infi/code/code/pyproject.toml)
- [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py)
- [tests/test_aris_demo_workspace_registry.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_workspace_registry.py)

Verification:
- `py -3.12 -m py_compile evolving_ai\aris_demo\desktop_app.py evolving_ai\aris_demo\desktop_support.py evolving_ai\aris_demo\workspace_registry.py evolving_ai\aris_demo\feedback.py evolving_ai\aris_demo\voice.py tests\test_aris_demo_desktop.py tests\test_aris_demo_workspace_registry.py`
- `py -3.12 -m pytest -q tests\test_aris_demo_desktop.py tests\test_aris_demo_workspace_registry.py`
- `py -3.12 -m evolving_ai.aris_demo.desktop --headless-smokecheck --no-workers`
- Offscreen Qt instantiation created the window and confirmed `Studio` tabs plus center surface tabs for `Governance`, `Memory`, `Upgrades`, `Runtime`, and `File Viewer`.

Remaining risks:
- ElevenLabs playback depends on API configuration and available multimedia support; when neither ElevenLabs nor `pyttsx3` are available, the voice lane degrades silently.
- The legacy top-level `Overview`, `Governance`, `Files`, and `Mystic` tabs still exist around the new Studio shell, so there is some duplicated surface area that can be collapsed in a later cleanup pass.
- Feedback export is local-first and file-based; if you want a live hosted tester intake loop, the external form URL still needs to be configured.

## 2026-04-15 - ARIS Demo V1 Forge Studio Posture
What changed:
- Tuned the shared ARIS Studio shell so V1 opens in a Forge-governed operating posture instead of inheriting demo-safe ARIS-only defaults.
- Made the default V1 worker lane explicitly show Forge as the active execution surface with Forge Eval noted as the validation lane.
- Hardened governed memory-bank layer reads so stale or corrupt local JSON no longer crashes the V1 desktop during startup.

Why it changed:
- V1 is the Forge-enabled version, so it should feel Forge-ready immediately without manual retuning of target, tier, and route controls.
- The local V1 runtime needed to survive old data-root state cleanly in the same way the fresh test roots already did.

How it changed:
- Added profile-aware brain defaults in the desktop shell so V1 now starts with `Mode=Build`, `Target=Forge`, and `Tier=Approval Required`.
- Updated the workspace surface builder to emit a `Forge Worker Lane` default worker summary whenever Forge is connected in the active profile.
- Changed governed memory-bank reads to recover corrupt non-foundational layer payloads by backing them up and reseeding an empty lawful layer.

Files changed:
- [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py)
- [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py)
- [evolving_ai/aris/memory_bank.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/memory_bank.py)
- [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py)
- [tests/test_aris_memory_bank.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_memory_bank.py)

Verification:
- `py -3.12 -m py_compile evolving_ai\aris_demo\desktop_app.py evolving_ai\aris_demo\desktop_support.py evolving_ai\aris\memory_bank.py tests\test_aris_demo_desktop.py tests\test_aris_memory_bank.py`
- `py -3.12 -m pytest -q tests\test_aris_demo_desktop.py tests\test_aris_memory_bank.py`
- `py -3.12 -m evolving_ai.aris_demo.desktop_v1 --headless-smokecheck --no-workers`
- Offscreen Qt instantiation of the V1 desktop confirmed `Target=Forge`, `Permission=Approval Required`, route summary `Jarvis Blueprint -> Operator -> Forge -> Outcome`, and worker header `Forge Worker Lane [Ready]`.

## 2026-04-15 - ARIS Three-System Model Switchboard
What changed:
- Added a three-system model switchboard for ARIS with automatic routing and manual pinning.
- Bound the requested routing roles so general chat uses `GENERAL_MODEL`, repo/coding work uses `CODING_MODEL`, and low-resource code/inspection uses `LIGHT_CODING_MODEL`.
- Exposed the router in the API and UI so ARIS can stay on auto or be locked to one of the three systems.

Why it changed:
- ARIS needed a real multi-model runtime lane instead of a single placeholder model route.
- The operator needed one inspectable place to see and control which model family ARIS is using.
- Model routing needed to stay structural and shared across chat, agent runs, and task flows rather than being reimplemented in separate features.

How it changed:
- Added `ModelSwitchboard` as a persisted routing spine with `auto` and `manual` modes.
- Wired `ChatService` model selection through the switchboard so model decisions are based on prompt class, mode, attachments, and operator pin state.
- Added API endpoints to read and update router state and extended the main web UI with a router selector and live model summary.
- Added the new env bindings and example values for `GENERAL_MODEL`, `CODING_MODEL`, and `LIGHT_CODING_MODEL`.

Files changed:
- [evolving_ai/app/model_switchboard.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/model_switchboard.py)
- [evolving_ai/app/config.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/config.py)
- [evolving_ai/app/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/service.py)
- [evolving_ai/app/server.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/server.py)
- [evolving_ai/app/static/index.html](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/index.html)
- [evolving_ai/app/static/app.js](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/static/app.js)
- [evolving_ai/aris/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/service.py)
- [forge.env.example](/C:/Users/randj/Desktop/project%20infi/code/code/forge.env.example)
- [tests/test_model_switchboard.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_model_switchboard.py)

Verification:
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\model_switchboard.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\config.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\service.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\server.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\service.py C:\Users\randj\Desktop\project infi\code\code\tests\test_model_switchboard.py`
- `node --check C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\static\app.js`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m unittest tests.test_model_switchboard`

Remaining risks:
- Auto-routing is heuristic by design, so some borderline prompts may still benefit from manual pinning.
- The router assumes one OpenAI-compatible provider endpoint can serve all three model names; if your backend splits them across separate endpoints, one more provider-routing layer will still be needed.

## 2026-04-16 - ARIS Studio Consolidation And Refresh Build
What changed:
- Removed the old outer ARIS demo shell from the operator-facing desktop flow so the upgraded Studio workspace is now the actual top-level app surface.
- Made the desktop branding and hero header profile-aware as `ARIS Studio`, `ARIS Studio V1`, and `ARIS Studio V2`.
- Rebuilt the repo-local release artifacts from the current upgraded source after clearing stale local demo packaging outputs.

Why it changed:
- The upgraded workspace, bounded explorer, feedback path, voice lane, and Forge-aware profiles were already implemented, but the app still looked like the older demo because Studio was only one tab inside a legacy shell.
- The operator-facing demo needed to present the new cockpit-like Studio as the product, not as a nested surface.
- The local release lane needed a fresh build from the current source instead of older packaging leftovers.

How it changed:
- Reduced the outer desktop container to a single top-level `Studio` tab and auto-hid the outer tab bar.
- Stopped the desktop refresh path from updating the old overview/governance/files/mystic outer tabs.
- Added a regression assertion that the V1 window instantiates with one top-level tab and the `ARIS Studio V1` hero title.
- Cleared repo-local `build`, `dist`, and stale Windows release staging folders, then ran Shipping Lane to regenerate `ARIS Demo`, `ARIS Demo V1`, and `ARIS Demo V2` folders plus zip archives.

Files changed:
- [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py)
- [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py)
- [dist/release-manifest.json](/C:/Users/randj/Desktop/project%20infi/code/code/dist/release-manifest.json)

Verification:
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m py_compile evolving_ai/aris_demo/desktop_app.py tests/test_aris_demo_desktop.py`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m unittest tests.test_aris_demo_desktop`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris_demo.desktop --headless-smokecheck --no-workers`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris_demo.desktop_v1 --headless-smokecheck --no-workers`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris_demo.desktop_v2 --headless-smokecheck --no-workers`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris_demo.shipping_lane --python .runtime\ul_desktop_runtime\venv\Scripts\python.exe --release-root dist --build-tag studio-refresh-20260416`
- Offscreen Qt instantiation confirmed the V1 window now launches with `1` top-level tab, label `Studio`, and hero title `ARIS Studio V1`.

Remaining risks:
- The legacy tab-builder methods still exist in the source as internal unused code; this pass removed them from the live operator flow but did not yet delete every dormant helper.
- The refreshed release artifacts were rebuilt in the repo-local [dist/](/C:/Users/randj/Desktop/project%20infi/code/code/dist) lane. If you want the parent `Project Infi` release folder replaced too, that needs one more shipping run targeting the outer distribution root.

## 2026-04-16 - Demo Package Model Router Wiring And ARIS Router Visibility
What changed:
- Wired the three-system model router all the way through the demo package surfaces for `ARIS Demo`, `ARIS Demo V1`, and `ARIS Demo V2` instead of leaving it only in the shared service layer.
- Fixed profile package drift so each demo variant now reports its own artifact names in desktop targets and smokechecks instead of falling back to the base `ARIS Demo` package labels.
- Extended core ARIS launcher and health surfaces so the same router mode and model lanes are visible outside the web UI too.

Why it changed:
- All demo variants needed the router baked into their package truth, not just their runtime chat behavior.
- V1 and V2 were still exposing generic demo package metadata, which could mislead anyone validating the packaged builds.
- ARIS itself needed the same upgrade so router state is inspectable from the launcher and health path, not only from the browser shell.

How it changed:
- Added reusable model-router payload helpers so packaging, smokecheck, runtime-manifest, shipping-manifest, and launcher surfaces all consume one shared three-lane definition.
- Made desktop packaging targets profile-aware and stamped them with router mode plus the configured `General`, `Coding`, and `Light Coding` model lanes.
- Added router data to demo smokechecks, UL desktop runtime manifests, shipping manifests, desktop feature inventory, desktop overview/context surfaces, ARIS health payload, and ARIS launcher status lines.
- Added regression coverage for demo package artifacts, runtime-manifest router metadata, shipping-manifest router metadata, and launcher router visibility.

Files changed:
- [evolving_ai/app/model_switchboard.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/app/model_switchboard.py)
- [evolving_ai/aris/service.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/service.py)
- [evolving_ai/aris/launcher.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris/launcher.py)
- [evolving_ai/aris_demo/profiles.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/profiles.py)
- [evolving_ai/aris_demo/desktop_support.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_support.py)
- [evolving_ai/aris_demo/desktop_build.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_build.py)
- [evolving_ai/aris_demo/desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop.py)
- [evolving_ai/aris_demo/desktop_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_runtime.py)
- [evolving_ai/aris_demo/desktop_app.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/desktop_app.py)
- [evolving_ai/aris_demo/shipping_lane.py](/C:/Users/randj/Desktop/project%20infi/code/code/evolving_ai/aris_demo/shipping_lane.py)
- [tests/test_aris_demo_desktop.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop.py)
- [tests/test_aris_demo_desktop_runtime.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_desktop_runtime.py)
- [tests/test_aris_demo_shipping_lane.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_demo_shipping_lane.py)
- [tests/test_aris_launcher.py](/C:/Users/randj/Desktop/project%20infi/code/code/tests/test_aris_launcher.py)

Verification:
- `C:\Python314\python.exe -m py_compile C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\model_switchboard.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\profiles.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_support.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_build.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_runtime.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\desktop_app.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris_demo\shipping_lane.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\service.py C:\Users\randj\Desktop\project infi\code\code\evolving_ai\aris\launcher.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_demo_desktop.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_demo_desktop_runtime.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_demo_shipping_lane.py C:\Users\randj\Desktop\project infi\code\code\tests\test_aris_launcher.py`
- `node --check C:\Users\randj\Desktop\project infi\code\code\evolving_ai\app\static\app.js`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m unittest tests.test_model_switchboard`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m unittest tests.test_aris_demo_desktop tests.test_aris_demo_desktop_runtime tests.test_aris_demo_shipping_lane tests.test_aris_launcher`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris_demo.desktop --headless-smokecheck --no-workers --profile v2`
- `C:\Users\randj\Desktop\project infi\code\code\.runtime\ul_desktop_runtime\venv\Scripts\python.exe -m evolving_ai.aris --healthcheck`
- Demo smokecheck returned profile-specific artifacts `ARIS Demo V2.exe`, `ARIS Demo V2.app`, and `dist/ARIS Demo V2/` with router mode `auto` and the three configured models.
- ARIS launcher printed the router lanes correctly and truthfully failed health because the runtime is currently in lockdown from an existing protected-component integrity issue.

Remaining risks:
- ARIS launcher visibility is upgraded, but core ARIS is still fail-closed in the current environment due an existing integrity-lockdown condition; this pass did not clear or reseal that separate blocker.
- The demo desktop surfaces now expose router/package truth, but the actual packaged executables still need a fresh build if you want the already-built binaries on disk to pick up these metadata changes.
