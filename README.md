# Evolving AI

`evolving-ai` is a pure-Python framework for building small neural agents with evolutionary search instead of gradient descent. It now also includes a local-first AI app shell that can sit in front of your own model APIs.

It includes:

- An advanced code-writing-agent benchmark with recurrent controller memory and reusable temporary variables
- A Grok-style chat app with streaming, retrieval, caching, and your-own-API integration
- A flat genome that encodes neural network weights and biases
- Self-adaptive mutation and arithmetic crossover
- Tournament selection with elitism
- Novelty search with a behavior archive
- Stagnation recovery via diversity injection
- A CLI with runnable tasks for code generation, XOR, and sequence prediction

## Change Logbook

Major ARIS and Evolving AI changes are recorded in [LOGBOOK.md](/C:/Users/randj/Desktop/project%20infi/code/code/LOGBOOK.md).

The current delivery rule for release truth is defined in [LAWFUL_COMPLETION_OF_A_SYSTEM.md](/C:/Users/randj/Desktop/project%20infi/code/code/LAWFUL_COMPLETION_OF_A_SYSTEM.md).

Each major entry records:

- what changed
- why it changed
- how it changed
- files changed
- verification
- remaining risks

## Lawful Completion

A system is not complete when it builds successfully.

A system is complete only when it has been verified, packaged into its declared distribution form, and proven to run correctly as a delivered artifact.

Completion requires:

- verified structure
- validated behavior
- generated distribution artifacts
- successful post-packaging execution

If any of these are missing, the system is not complete.

In this repo, that rule is enforced operationally by keeping `Build Lane` and `Shipping Lane` separate. Build can prepare artifacts. Shipping is the completion authority because it verifies source state, creates the declared release form, and proves the packaged artifact runs after packaging.

## Quick Start

Install the package in editable mode:

```bash
python -m pip install -e .
```

Run the chat app:

```bash
forge-chat
```

Then open `http://127.0.0.1:8080`.

Run the stripped ARIS demo copy:

```bash
aris-demo --reseal-integrity
```

On Windows, `pip install -e .` creates the `aris-demo.exe` shim automatically. A helper script is also included at [run_aris_demo.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/run_aris_demo.ps1).

Run the ARIS Demo desktop host:

```bash
python -m pip install -e .[desktop]
py -3.12 -m evolving_ai.aris_demo.desktop
```

On Windows, helper scripts are included at [run_aris_demo_desktop.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/run_aris_demo_desktop.ps1) and [build_aris_demo_desktop.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/build_aris_demo_desktop.ps1).

Prepare the UL-bound PySide6 desktop runtime:

```bash
python -m evolving_ai.aris_demo.desktop_runtime --prepare --with-build-tools
```

On Windows, a helper script is included at [prepare_aris_demo_desktop_runtime.ps1](/C:/Users/randj/Desktop/project%20infi/code/code/prepare_aris_demo_desktop_runtime.ps1). Once prepared, the desktop run/build helper scripts automatically prefer the UL desktop runtime in `.runtime/ul_desktop_runtime/venv`.

Print the native build targets and packaging command:

```bash
py -3.12 -m evolving_ai.aris_demo.desktop --print-build-targets --no-workers
py -3.12 -m evolving_ai.aris_demo.desktop_build --print-command
```

Build the native bundle for the current platform:

```bash
python -m pip install -e .[desktop-build]
py -3.12 -m evolving_ai.aris_demo.desktop_build --build-current
```

Point it at your own model endpoint with environment variables:

```bash
$env:FORGE_PROVIDER_MODE="custom"
$env:FORGE_API_URL="http://127.0.0.1:8001/v1/chat/completions"
$env:FORGE_FAST_MODEL="my-fast-model"
$env:FORGE_QUALITY_MODEL="my-quality-model"
$env:FORGE_VISION_MODEL="my-vision-model"
forge-chat
```

Turn on container-backed execution:

```bash
$env:FORGE_EXECUTION_BACKEND="docker"
$env:FORGE_DOCKER_IMAGE="python:3.11-alpine"
forge-chat
```

A starter env template is included in `forge.env.example`.

Run the default advanced code-writing benchmark:

```bash
python -m evolving_ai --task code-agent --generations 50 --population 96
```

Run the sequence-prediction experiment:

```bash
python -m evolving_ai --task sequence --generations 40 --population 80
```

Run the XOR task and save a JSON report:

```bash
python -m evolving_ai --task xor --generations 60 --population 96 --json-out results/xor.json
```

## Architecture

- `evolving_ai/app/`: local-first AI app, your-own-API adapter, retrieval, cache, and UI
- `evolving_ai/config.py`: experiment and network configuration
- `evolving_ai/genome.py`: genome representation, mutation, crossover
- `evolving_ai/network.py`: genome-to-network decoding and inference
- `evolving_ai/code_agents.py`: public code-agent API and compatibility exports
- `evolving_ai/advanced_code_agents.py`: recurrent controller, statement-based synthesis grammar, and benchmark suite
- `evolving_ai/tasks.py`: pluggable evaluation tasks
- `evolving_ai/archive.py`: novelty archive
- `evolving_ai/engine.py`: evolutionary training loop
- `evolving_ai/cli.py`: command-line entry point

## Local Entry Docs

- [`evolving_ai/README.md`](./evolving_ai/README.md)
  - package ownership, app lane, ARIS lane, and demo lane
- [`forge/README.md`](./forge/README.md)
  - Forge runtime/service ownership
- [`forge_eval/README.md`](./forge_eval/README.md)
  - Forge evaluation and sandbox support
- [`release/README.md`](./release/README.md)
  - packaged artifact lane
- [`tests/README.md`](./tests/README.md)
  - verification authority
- [`prototypes/README.md`](./prototypes/README.md)
  - prototype-only surfaces
- [`Code/README.md`](./Code/README.md)
  - external mirror/import lane

## Why This Structure?

This project is meant to be extended. You can add:

- a richer provider adapter in `evolving_ai/app/providers.py` if your API uses a custom wire format
- custom tools, auth, and product logic in `evolving_ai/app/service.py`
- new tasks by implementing `evaluate()`
- richer code-generation grammars or repair operators in `evolving_ai/advanced_code_agents.py`
- new selection or mutation operators in `engine.py` or `genome.py`
- richer behavior signatures for more advanced novelty search
- serialization, visualization, or distributed evaluation on top of the current core

## Example Output

```text
gen=000 best_obj=0.7874 best_mix=0.8421 avg_obj=0.5219 archive=1
gen=001 best_obj=0.8116 best_mix=0.8587 avg_obj=0.5482 archive=4
...
best task=sequence objective=0.9783 combined=0.9621 archive=24
```

## Own API Contract

The chat app expects your endpoint to accept a JSON payload shaped like:

```json
{
  "model": "my-model",
  "messages": [
    { "role": "system", "content": "..." },
    { "role": "user", "content": "..." }
  ],
  "stream": true,
  "temperature": 0.25,
  "max_tokens": 900
}
```

It can consume:

- SSE chunks such as `data: {"delta":"hello"}`
- OpenAI-style chunks such as `data: {"choices":[{"delta":{"content":"hello"}}]}`
- a plain JSON response containing `content`, `text`, `response`, or `choices`

## Capability Coverage

The app now includes:

- chat mode
- agent mode
- deep research mode
- fast/quality/vision model routing
- streaming responses
- local knowledge retrieval
- URL fetch support and web search in deeper research flows
- lightweight user memory
- text and image attachments
- server-side file parsing for PDF, DOCX, CSV, HTML, and text uploads
- a local Python workspace/interpreter panel for quick code execution
- repo bundle upload into the session workspace
- controlled HTTPS git clone with host allowlists
- repo-aware workspace search for filenames, text hits, and symbol lookup
- symbol-level repo tools for listing, reading, referencing, and editing functions/classes
- repo-map inspection for owner files, related modules, and likely test targets
- automatic project detection for languages, frameworks, package managers, entrypoints, and suggested commands
- full workspace snapshots and restore, including hidden repo metadata
- a streamed repo task runner for inspect -> edit -> test -> review -> approve
- deterministic task planning before the agent loop starts, with repo-map-aware focus files, scoped validation suggestions, stored step plans, and suggested Git branch names
- Git workflow helpers for repo inspection, branch creation, and PR-ready handoff drafts with commit and validation notes

This still is not full parity with Grok, Claude, and ChatGPT. Those products also include proprietary search stacks, mature multimodal pipelines, connectors, code execution sandboxes, voice systems, image generation systems, and large safety/evaluation layers. The current app is designed as the foundation you can keep extending behind your own APIs.

## Local Interpreter

The interpreter runs Python code inside a per-session workspace under `.forge_chat/workspaces`.

Current behavior:

- captures stdout and stderr with output truncation
- preserves files created in the workspace
- enforces a timeout
- validates code before execution and blocks disallowed imports such as `socket` and `subprocess`
- runs Python in isolated mode with a stripped environment
- blocks network access, shell/process spawning, and file access outside the session workspace
- enforces per-workspace file-count and file-size limits

Sandbox tuning:

- `FORGE_EXECUTION_TIMEOUT_SECONDS`
- `FORGE_EXECUTION_MAX_CODE_CHARS`
- `FORGE_EXECUTION_MAX_OUTPUT_CHARS`
- `FORGE_EXECUTION_MAX_FILES`
- `FORGE_EXECUTION_MAX_FILE_BYTES`

Container-backed execution:

- `FORGE_EXECUTION_BACKEND=auto|local|docker`
- `FORGE_DOCKER_IMAGE`
- `FORGE_DOCKER_MEMORY`
- `FORGE_DOCKER_CPUS`
- `FORGE_DOCKER_PIDS_LIMIT`
- `FORGE_DOCKER_WORKDIR`
- `FORGE_DOCKER_TMPFS_SIZE`
- `FORGE_DOCKER_NETWORK_DISABLED`
- `FORGE_DOCKER_READ_ONLY_ROOT`
- `FORGE_DOCKER_NO_NEW_PRIVILEGES`
- `FORGE_DOCKER_USER`

Backend behavior:

- `local` uses the hardened in-process Python sandbox
- `docker` requires a running Docker daemon and executes code inside a resource-limited persistent per-session container
- `auto` prefers Docker when available and falls back to the local sandbox when Docker is unavailable

Persistent Docker workspace behavior:

- each chat/code session gets its own named container
- repeated `/api/execute` calls for the same session reuse that container and mounted workspace
- `/api/exec` runs approved commands inside that same persistent session container
- `/api/exec/stream` streams command logs back as SSE events
- `/api/workspace/{session_id}/import/upload` imports a bundle or single file into the workspace
- `/api/workspace/{session_id}/import/clone` performs a controlled HTTPS git clone using the host Git binary
- `/api/workspace/{session_id}/search` finds files, text hits, and symbols inside the workspace
- `/api/workspace/{session_id}/symbols`, `/symbol`, and `/symbol/references` expose symbol-aware repo navigation
- `/api/workspace/{session_id}/symbol` with `PUT` applies a focused symbol-level edit
- `/api/workspace/{session_id}/project` reports detected languages, frameworks, package managers, entrypoints, and suggested commands
- `/api/workspace/{session_id}/repo-map` reports likely owner files, related files, likely tests, and suggested validation commands for a goal/path/symbol
- `/api/workspace/{session_id}/git` reports repo state, branch/head, changed files, and recent commits
- `/api/workspace/{session_id}/git/branch` creates a task-scoped branch inside the workspace repo
- `/api/workspace/{session_id}/git/handoff` drafts a branch suggestion, commit message, validation summary, and PR body
- `/api/workspace/{session_id}/snapshots` lists or creates full workspace restore points
- `/api/workspace/{session_id}/snapshots/{snapshot_id}/restore` rolls the workspace back to a saved restore point
- `/api/workspace/{session_id}/tasks/plan` returns the preflight task plan without starting the streamed run
- `/api/workspace/{session_id}/tasks/run` streams a managed repo task flow with inspect, edit, test, and review phases
- `/api/workspace/{session_id}/tasks/{task_id}/approve` and `/reject` resolve the final human approval step
- `/api/agent/{session_id}/runs` lists durable agent jobs for that chat session
- `/api/agent/runs/{run_id}` returns the current status and summary for one durable run
- `/api/agent/runs/{run_id}/stream` replays or tails the persisted SSE event history for that run
- `/api/agent/runs/{run_id}/cancel` requests cancellation for an active background run
- `/api/agent/{session_id}/approvals` lists pending command approvals and resumable patch reviews
- `/api/agent/{session_id}/audit` returns the durable approval/review audit history for that session
- `/api/agent/{session_id}/approvals/{approval_id}/approve` approves a blocked step and resumes the agent over SSE
- `/api/agent/{session_id}/approvals/{approval_id}/reject` rejects a blocked step and lets the agent continue with that decision
- `/api/sandbox/{session_id}` reports container state
- `/api/sandbox/{session_id}/reset` removes the session container so the next run starts fresh

Command execution tuning:

- `FORGE_AGENT_RUN_DB_PATH`
- `FORGE_AGENT_WORKER_ENABLED`
- `FORGE_AGENT_WORKER_CONCURRENCY`
- `FORGE_AGENT_WORKER_POLL_SECONDS`
- `FORGE_AGENT_WORKER_LEASE_SECONDS`
- `FORGE_AGENT_WORKER_HEARTBEAT_SECONDS`
- `FORGE_AGENT_WORKER_MAX_ATTEMPTS`
- `FORGE_AGENT_WORKER_RETRY_DELAY_SECONDS`
- `FORGE_COMMAND_TIMEOUT_SECONDS`
- `FORGE_ALLOWED_COMMANDS`
- `FORGE_AGENT_MAX_COMMAND_TIER`
- `FORGE_REPO_UPLOAD_MAX_BYTES`
- `FORGE_REPO_ARCHIVE_MAX_ENTRIES`
- `FORGE_REPO_MAX_TOTAL_BYTES`
- `FORGE_REPO_CLONE_TIMEOUT_SECONDS`
- `FORGE_REPO_ALLOWED_CLONE_HOSTS`
- `FORGE_WORKSPACE_SEARCH_MAX_RESULTS`
- `FORGE_WORKSPACE_SEARCH_MAX_EXCERPT_CHARS`
- `FORGE_WORKSPACE_SNAPSHOT_MAX_ENTRIES`
- `FORGE_WORKSPACE_SNAPSHOT_MAX_TOTAL_BYTES`
- `FORGE_WORKSPACE_SNAPSHOT_MAX_SNAPSHOTS`

Agent command policy:

- agent `run_command` defaults to the `read_only` tier
- raise `FORGE_AGENT_MAX_COMMAND_TIER` to `test` or `package` only if you want the agent to run higher-impact tools like `python`, `pytest`, `pip`, or `uv`
- the agent prompt only sees commands that fit its current tier, so read-only inspection stays the default path
- `FORGE_AGENT_ALLOW_PYTHON`, `FORGE_AGENT_ALLOW_SHELL`, `FORGE_AGENT_ALLOW_FILESYSTEM_READ`, and `FORGE_AGENT_ALLOW_FILESYSTEM_WRITE` let you gate Python execution, shell access, file reads, and patch proposal tools separately
- agent file edits are now review-gated: they land as pending patches first, show a unified diff in the UI, and require manual `Apply` or `Reject`
- agent `run_command` now streams live shell output into the agent trace instead of waiting for one buffered observation at the end
- agent chat requests now run as durable background jobs backed by a SQLite run store plus a SQLite queue/lease worker, so the request stream no longer owns the whole run lifecycle
- worker-owned runs are claimed with a lease, heartbeated while they execute, and retried from the durable queue if the worker crashes before finishing
- leased jobs are requeued on the next startup instead of disappearing silently, and recovered runs emit a `worker_recovered` trace event when they are scheduled again
- when a command exceeds the current agent tier, ForgeChat pauses the run, stores a resume checkpoint, and lets you approve or reject that exact step later without restarting the whole task
- resumable patch proposals work the same way: approving or rejecting the patch can feed that decision back into the same agent run so it continues from the saved context
- run history and event replay are stored in SQLite at `FORGE_AGENT_RUN_DB_PATH`
- the same run database now stores the durable execution queue, lease ownership, retry counters, and worker heartbeats
- pending command approvals and patch resume checkpoints are persisted in SQLite at `FORGE_APPROVAL_DB_PATH` so they survive a server restart
- persisted checkpoints include a workspace fingerprint; if the workspace changes before approval, ForgeChat keeps the approval visible but marks the resume path as stale instead of blindly replaying it
- each approval request, decision, stale resume, and successful resume is written to the same SQLite audit log and exposed through `/api/agent/{session_id}/audit`
- if you still have the older JSON snapshot file, ForgeChat will import it once from `FORGE_APPROVAL_STATE_PATH` into the SQLite store on startup

Command execution guardrails:

- commands are passed as argument arrays, not shell strings
- blocked shells like `sh`, `bash`, `cmd`, and `powershell` are rejected
- executables must be in the allowed-command list
- working directories are normalized and must stay inside the workspace
- `git` is limited to safe read-oriented subcommands such as `status`, `diff`, `log`, `show`, `rev-parse`, and `ls-files`
- imported archives cannot write into protected paths like `.git` or internal Forge metadata files
- git clone only accepts HTTPS remotes from the configured host allowlist
- task runs raise command access to the `test` tier for that workflow only, so repo validation can run without opening package-install access

Current limitation:

- the `docker` backend is a real OS-level isolation step up, but the default `local` backend is still a policy sandbox, not a VM or microVM boundary
- for hostile multi-tenant traffic, you still want stronger isolation, image control, audit logging, and lifecycle cleanup around the container path
