# UL stdlib v0.1

UL stdlib v0.1 gives CoGOS a small practical library for normal-user work:
workspaces, memory, safe file notes, device status, notices, and summaries.
It is available in two lanes:

- `ul_lang.py` programs call `ul_*` builtins.
- `.ulsub` substrate commands use governed verbs such as `remembers`,
  `recalls`, `prepares`, `organizes`, `reports`, and `notices`.

## Builtins

| UL builtin | Stdlib call | Purpose |
| --- | --- | --- |
| `ul_now()` | `core.now` | UTC timestamp |
| `ul_slug(text)` | `core.slug` | Stable filename/workspace slug |
| `ul_json(value)` | `core.json` | Deterministic JSON string |
| `ul_read_text(path)` | `fs.read_text` | Read from governed CoGOS roots |
| `ul_write_text(path, text)` | `fs.write_text` | Write under `memory/ul` or other governed roots |
| `ul_remember(key, value)` | `state.remember` | Persist a small state value |
| `ul_recall(key)` | `state.recall` | Read a state value |
| `ul_workspace(name)` | `auto.workspace` | Create a CoGOS workspace |
| `ul_organize_plan(source)` | `auto.organize_plan` | Plan file organization without moving files |
| `ul_status()` | `auto.status` | Automatic mode status |
| `ul_device_status()` | `device.status` | HAL/device snapshot |
| `ul_notice(text)` | `ui.notice` | Append a user-facing notice |
| `ul_summary(text)` | `agent.summary` | Short deterministic summary |

## Governed substrate verbs

| Verb | Capability | Handler |
| --- | --- | --- |
| `prepares` | mutate | Create a workspace |
| `organizes` | mutate | Create an organization plan |
| `remembers` | mutate | Store state |
| `recalls` | query | Recall state |
| `reports` | query | Report Automatic/HAL status |
| `notices` | harmless | Append a notice |
| `summarizes` | harmless | Summarize text |

Example:

```text
agent remembers x1
agent recalls x1
system reports x1
```

## CLI

```sh
cogos-ul-stdlib manifest
cogos-ul-stdlib call core.slug "Dragon Game Workspace"
cogos-ul-stdlib demo
```

The library is deliberately small. v0.1 is the stable base for workspace and
stateful user help; later versions can add richer file transforms and package
APIs without changing these names.

