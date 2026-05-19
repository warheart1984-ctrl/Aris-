#!/usr/bin/env python3
"""CoGOS Control Center UI."""

from __future__ import annotations

import html
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(os.environ.get("COGOS_ROOT", "/opt/cogos"))
RUNTIME = ROOT / "runtime"
for p in (RUNTIME, RUNTIME / "ul", RUNTIME / "voss"):
    s = str(p)
    if s not in sys.path:
        sys.path.insert(0, s)

from automatic_mode import AutomaticModeEngine  # noqa: E402
from cogos_backup import export_backup  # noqa: E402
from cogos_pkg import install as pkg_install  # noqa: E402
from cogos_pkg import remove as pkg_remove  # noqa: E402
from determinism_corridor import run_boot_verification  # noqa: E402
from device_storage_manager import DeviceStorageManager  # noqa: E402
from eval_harness import run_eval_suite  # noqa: E402
from first_run_wizard import FirstRunWizard  # noqa: E402
from hal_service import write_hal_snapshot  # noqa: E402
from phase1_panels import enqueue_operator_command, phase1_status  # noqa: E402
from phase2_panels import phase2_status  # noqa: E402
from phase3_panels import phase3_status  # noqa: E402
from recovery_mode import RecoveryMode  # noqa: E402

PORT = int(os.environ.get("COGOS_DESKTOP_PORT", "8081"))
LAST_ACTION = ROOT / "memory" / "logs" / "control_center_last_action.json"


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""))


def read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return default


def write_last_action(action: str, result) -> None:
    LAST_ACTION.parent.mkdir(parents=True, exist_ok=True)
    LAST_ACTION.write_text(
        json.dumps({"ts": utc_now(), "action": action, "result": result}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def last_action() -> dict:
    return read_json(LAST_ACTION, {})


def persistence_status() -> dict:
    cmd = Path("/usr/local/bin/cogos-persist")
    if cmd.exists():
        try:
            completed = subprocess.run(
                [str(cmd), "status"],
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=12,
            )
            if completed.stdout.strip().startswith("{"):
                out = json.loads(completed.stdout)
                out["ok"] = completed.returncode == 0
                return out
            return {"ok": False, "error": completed.stderr.strip() or completed.stdout.strip()}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
    return {
        "ok": True,
        "label": "COGOSDATA",
        "mounted": False,
        "config_bound": False,
        "memory_bound": False,
        "mountpoint": "/var/lib/cogos",
        "note": "cogos-persist is available inside the ISO",
    }


def install_plan(target: str) -> dict:
    target = target.strip()
    if not target:
        return {"ok": False, "error": "target required"}
    cmd = Path("/usr/local/bin/cogos-install")
    if not cmd.exists():
        return {"ok": False, "error": "cogos-install is available inside the ISO", "target": target}
    try:
        completed = subprocess.run(
            [str(cmd), "plan", "--target", target, "--json"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        if completed.stdout.strip().startswith("{"):
            out = json.loads(completed.stdout)
            out["ok"] = completed.returncode == 0
            out["stderr"] = completed.stderr.strip()
            return out
        return {
            "ok": completed.returncode == 0,
            "target": target,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except Exception as exc:
        return {"ok": False, "target": target, "error": str(exc)}


def install_validate(target: str) -> dict:
    target = target.strip()
    if not target:
        return {"ok": False, "error": "target required"}
    cmd = Path("/usr/local/bin/cogos-install")
    if not cmd.exists():
        return {"ok": False, "error": "cogos-install is available inside the ISO", "target": target}
    try:
        completed = subprocess.run(
            [str(cmd), "validate", "--target", target, "--json"],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
        )
        if completed.stdout.strip().startswith("{"):
            out = json.loads(completed.stdout)
            out["ok"] = completed.returncode == 0
            out["stderr"] = completed.stderr.strip()
            return out
        return {"ok": completed.returncode == 0, "target": target, "stdout": completed.stdout.strip(), "stderr": completed.stderr.strip()}
    except Exception as exc:
        return {"ok": False, "target": target, "error": str(exc)}


def control_center_status() -> dict:
    p1 = phase1_status()
    p2 = phase2_status()
    p3 = phase3_status()
    return {
        **p1,
        "phase2": p2,
        "phase3": p3,
        "persistence": persistence_status(),
        "first_run": FirstRunWizard().status(),
        "device_storage": DeviceStorageManager().inventory(),
        "storage_plans": DeviceStorageManager().list_plans(),
        "recovery": RecoveryMode().status(),
        "last_action": last_action(),
    }


def pill(label: str, value: object, ok: bool | None = None) -> str:
    cls = "pill"
    if ok is True:
        cls += " ok"
    elif ok is False:
        cls += " bad"
    return f"<span class='{cls}'><b>{esc(label)}</b>{esc(value)}</span>"


def button(action: str, label: str, cls: str = "") -> str:
    return f"<button class='{esc(cls)}' name='action' value='{esc(action)}'>{esc(label)}</button>"


def render_packages(packages: dict) -> str:
    rows = []
    for pkg in packages.get("packages", []):
        action = "pkg_remove" if pkg.get("installed") else "pkg_install"
        label = "Remove" if pkg.get("installed") else "Install"
        status = "Installed" if pkg.get("installed") else "Available"
        rows.append(
            "<tr>"
            f"<td><b>{esc(pkg.get('id'))}</b><div class='sub'>{esc(pkg.get('description', ''))}</div></td>"
            f"<td>{esc(pkg.get('version', ''))}</td><td>{esc(status)}</td>"
            f"<td><form method='post' action='/api/operator'><input type='hidden' name='package_id' value='{esc(pkg.get('id'))}'>"
            f"{button(action, label, 'secondary')}</form></td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='4' class='sub'>No packages</td></tr>"


def render_timeline(events: list[dict]) -> str:
    rows = []
    for event in events[:14]:
        rows.append(
            "<tr>"
            f"<td>{esc(event.get('ts', ''))}</td>"
            f"<td>{esc(event.get('kind', ''))}</td>"
            f"<td>{esc(event.get('summary', event.get('detail', '')))}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='3' class='sub'>No events</td></tr>"


def render_suggestions(items: list[dict]) -> str:
    if not items:
        return "<li class='sub'>No workflow suggestions</li>"
    return "".join(
        f"<li><b>{esc(item.get('title'))}</b><span>{esc(item.get('reason'))}</span></li>"
        for item in items[:8]
    )


def render_devices(devices: list[dict]) -> str:
    rows = []
    for dev in devices[:12]:
        usage = dev.get("usage") or {}
        mount = dev.get("mount") or {}
        size_gb = round(float(dev.get("size_bytes") or 0) / (1024 ** 3), 2)
        rows.append(
            "<tr>"
            f"<td><b>{esc(dev.get('name'))}</b><div class='sub'>{esc(dev.get('model', ''))}</div></td>"
            f"<td>{esc(dev.get('class'))}</td>"
            f"<td>{esc(size_gb)} GB</td>"
            f"<td>{esc(mount.get('target', 'not mounted'))}</td>"
            f"<td>{esc(usage.get('used_percent', 'n/a'))}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='5' class='sub'>No devices observed</td></tr>"


def render_storage_plans(plans: list[dict]) -> str:
    rows = []
    for plan in plans[:8]:
        detail = plan.get("detail", {})
        rows.append(
            "<tr>"
            f"<td><b>{esc(plan.get('kind'))}</b><div class='sub'>{esc(plan.get('id'))}</div></td>"
            f"<td>{esc(plan.get('status'))}</td>"
            f"<td>{esc(detail.get('device') or detail.get('source') or detail.get('target', ''))}</td>"
            f"<td>{esc(plan.get('timestamp'))}</td>"
            "</tr>"
        )
    return "".join(rows) or "<tr><td colspan='4' class='sub'>No storage plans</td></tr>"


def render_desktop(data: dict) -> bytes:
    op = data["operator_dashboard"]
    pulse = data["law_pulse"]
    p2 = data.get("phase2", {})
    p3 = data.get("phase3", {})
    persistence = data.get("persistence", {})
    first_run = data.get("first_run", {})
    first_defaults = first_run.get("defaults", {})
    last = data.get("last_action", {})
    timeline = data["governance_timeline"]["events"]
    creative = p2.get("creative", {})
    mesh = p2.get("mesh", {})
    tiers = p3.get("tiers", {})
    pkgs = p3.get("packages", {})
    backup = p3.get("backup", {})
    eval_r = p3.get("eval", {})
    release = p3.get("release", {})
    automatic = p3.get("automatic", {})
    device_storage = data.get("device_storage", {})
    storage_plans = data.get("storage_plans", [])
    recovery = data.get("recovery", {})
    storage_summary = device_storage.get("storage", {})
    payload_usage = storage_summary.get("payload", {})

    profiles = "".join(
        f"<option value='{esc(p['id'])}' {'selected' if p.get('active') else ''}>{esc(p['display_name'])}</option>"
        for p in op.get("profiles", [])
    )

    last_result = json.dumps(last.get("result", {}), indent=2, sort_keys=True)[:2500]

    page = f"""<!doctype html>
<html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>
<meta http-equiv='refresh' content='12'>
<title>CoGOS Control Center</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#f4f6f1;color:#1e262b;font-family:Segoe UI,Arial,sans-serif;font-size:14px}}
header{{height:56px;display:flex;align-items:center;justify-content:space-between;padding:0 20px;background:#fafbf8;border-bottom:1px solid #cfd8d2}}
h1{{margin:0;font-size:19px;font-weight:700}}
a{{color:#155e75;text-decoration:none}}
.shell{{display:grid;grid-template-columns:214px 1fr;min-height:calc(100vh - 56px)}}
nav{{background:#e9eee7;border-right:1px solid #cfd8d2;padding:14px 12px}}
nav a{{display:block;padding:9px 10px;border-radius:6px;color:#263238;margin-bottom:4px;font-weight:600}}
nav a:hover{{background:#dce7df}}
main{{padding:14px;display:grid;grid-template-columns:1.15fr .85fr;gap:12px;align-content:start}}
section{{background:#fff;border:1px solid #cfd8d2;border-radius:8px;padding:14px;min-width:0}}
section.wide{{grid-column:1 / -1}}
h2{{font-size:13px;margin:0 0 10px;color:#46615a;text-transform:uppercase;letter-spacing:0}}
.strip{{display:flex;gap:8px;flex-wrap:wrap}}
.pill{{display:inline-flex;gap:8px;align-items:center;border:1px solid #cfd8d2;background:#f7f9f6;border-radius:999px;padding:6px 10px;min-height:30px}}
.pill.ok{{border-color:#90b99d;background:#edf7ef;color:#1f6b3a}} .pill.bad{{border-color:#d39a8d;background:#fff1ed;color:#9b2f1f}}
.grid2{{display:grid;grid-template-columns:1fr 1fr;gap:10px}} .grid3{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
.metric{{font-size:24px;font-weight:800;margin:4px 0}} .sub{{color:#63746e;font-size:12px}}
form{{margin:0}} label{{display:block;color:#63746e;font-size:12px;margin:8px 0 3px}}
input,select{{width:100%;padding:8px;border:1px solid #b9c6bf;border-radius:6px;background:#fbfcfa;color:#1e262b}}
button{{border:0;border-radius:6px;background:#176b87;color:#fff;padding:8px 11px;font-weight:700;cursor:pointer;margin-top:8px}}
button.secondary{{background:#51635d}} button.warn{{background:#9b4d1f}}
table{{width:100%;border-collapse:collapse}} th,td{{border-bottom:1px solid #e1e7e2;text-align:left;padding:8px;vertical-align:top}} th{{color:#63746e;font-size:12px}}
pre{{white-space:pre-wrap;word-break:break-word;background:#f7f9f6;border:1px solid #dbe3dd;border-radius:6px;padding:10px;max-height:260px;overflow:auto;font-size:12px}}
ul{{margin:0;padding-left:18px}} li span{{display:block;color:#63746e;font-size:12px;margin-top:2px}}
@media(max-width:900px){{.shell{{grid-template-columns:1fr}}nav{{display:flex;overflow:auto;gap:6px}}nav a{{white-space:nowrap}}main{{grid-template-columns:1fr}}.grid2,.grid3{{grid-template-columns:1fr}}}}
</style></head>
<body>
<header>
  <h1>CoGOS Control Center</h1>
  <div class='strip'>
    {pill("Release", release.get("version", "unknown"))}
    {pill("Profile", op.get("active_profile", "?"))}
    {pill("Mode", op.get("mode_hint", "?"))}
    {pill("Eval", f"{eval_r.get('passed', '?')}/{eval_r.get('total', '?')}", bool(eval_r.get("ok")))}
    {pill("First run", "done" if first_run.get("completed") else "needed", bool(first_run.get("completed")))}
  </div>
</header>
<div class='shell'>
<nav>
  <a href='#overview'>Overview</a>
  <a href='#first-run'>First Run</a>
  <a href='#automatic'>Automatic</a>
  <a href='#governance'>Governance</a>
  <a href='#system'>System</a>
  <a href='#devices'>Devices</a>
  <a href='#recovery'>Recovery</a>
  <a href='#packages'>Packages</a>
  <a href='#install'>Install</a>
  <a href='#proofs'>Proofs</a>
</nav>
<main>
  <section id='overview' class='wide'>
    <h2>Overview</h2>
    <div class='strip'>
      {pill("PID1", "OK" if op.get("pid1_ok") else "FAIL", bool(op.get("pid1_ok")))}
      {pill("Daemon", "RUN" if op.get("daemon_running") else "STOP", bool(op.get("daemon_running")))}
      {pill("Ledger", "OK" if pulse.get("ledger_health", {}).get("ok") else "FAIL", bool(pulse.get("ledger_health", {}).get("ok")))}
      {pill("Drift", f"{pulse.get('drift_composite', 0):.2f}")}
      {pill("HAL disks", pulse.get("hal_disks", 0))}
      {pill("Storage", f"{len(device_storage.get('devices', []))} devices", bool(device_storage.get("ok")))}
      {pill("Recovery", "armed" if recovery.get("recovery_flag") else "off", not bool(recovery.get("recovery_flag")))}
      {pill("Mesh", mesh.get("mesh_name", "?"))}
      {pill("Automatic", f"{automatic.get('workspace_count', 0)} workspaces")}
      {pill("Backups", backup.get("backup_count", 0))}
    </div>
  </section>

  <section id='first-run' class='wide'>
    <h2>First Run</h2>
    <div class='strip'>
      {pill("Status", "Complete" if first_run.get("completed") else "Needs setup", bool(first_run.get("completed")))}
      {pill("Profile", first_defaults.get("profile_id", "operator"))}
      {pill("Mode", first_defaults.get("mode_default", "manual"))}
    </div>
    <form method='post' action='/api/operator'>
      <div class='grid3'>
        <div><label>Hostname</label><input name='hostname' value='{esc(first_defaults.get("hostname", "cogos"))}'></div>
        <div><label>Profile ID</label><input name='profile_id' value='{esc(first_defaults.get("profile_id", "operator"))}'></div>
        <div><label>Display name</label><input name='display_name' value='{esc(first_defaults.get("display_name", "Operator"))}'></div>
      </div>
      <div class='grid3'>
        <div><label>Default mode</label><select name='mode_default'>
          <option value='manual' {'selected' if first_defaults.get("mode_default") == "manual" else ''}>manual</option>
          <option value='automatic' {'selected' if first_defaults.get("mode_default") == "automatic" else ''}>automatic</option>
        </select></div>
        <div><label>First workspace</label><input name='workspace_name' value='{esc(first_defaults.get("workspace_name", "Home Base"))}'></div>
        <div><label><input style='width:auto' type='checkbox' name='enable_kid' value='1' checked> create kid profile</label></div>
      </div>
      {button("first_run_apply", "Complete setup")}
      {button("first_run_reset", "Reset first-run", "secondary")}
    </form>
  </section>

  <section id='automatic'>
    <h2>Automatic</h2>
    <div class='grid2'>
      <div><div class='metric'>{automatic.get('workspace_count', 0)}</div><div class='sub'>Workspaces</div></div>
      <div><div class='metric'>{automatic.get('suggestions_count', 0)}</div><div class='sub'>Suggestions</div></div>
    </div>
    <form method='post' action='/api/operator'>
      <label>Workspace name</label><input name='workspace_name' value='Family Photos'>
      {button("auto_workspace", "Create workspace")}
    </form>
    <form method='post' action='/api/operator'>
      <label>Organize folder</label><input name='source' value='/home/user/Downloads'>
      <label><input style='width:auto' type='checkbox' name='apply' value='1'> apply moves</label>
      {button("auto_organize", "Organize files", "secondary")}
    </form>
    <form method='post' action='/api/operator'>
      <label>Remember key</label><input name='memory_key' value='goal'>
      <label>Remember value</label><input name='memory_value' value='finish the OS vision'>
      {button("auto_remember", "Remember", "secondary")}
      {button("auto_suggest", "Suggest workflows", "secondary")}
    </form>
    <ul>{render_suggestions(automatic.get('suggestions', []))}</ul>
  </section>

  <section id='governance'>
    <h2>Governance</h2>
    <div class='strip'>
      {pill("Law", pulse.get("law_version", "?"))}
      {pill("Tier", tiers.get("active_tier", "?"))}
      {pill("Creative", creative.get("artifacts_total", 0))}
      {pill("Network flows", len(pulse.get("network_visibility", [])))}
    </div>
    <form method='post' action='/api/operator'>
      {button("corridor_verify", "Verify corridor", "secondary")}
      {button("eval_run", "Run eval", "secondary")}
    </form>
    <table><thead><tr><th>Time</th><th>Kind</th><th>Summary</th></tr></thead><tbody>{render_timeline(timeline)}</tbody></table>
  </section>

  <section id='system'>
    <h2>System</h2>
    <form method='post' action='/api/operator'>
      <label>Profile</label><select name='profile_id'>{profiles}</select>
      {button("switch_profile", "Switch profile")}
      {button("pause", "Pause", "secondary")}
      {button("resume", "Resume", "secondary")}
      {button("hal_refresh", "Refresh HAL", "secondary")}
    </form>
    <pre>{esc(json.dumps({"load": pulse.get("loadavg"), "hal": {"disks": pulse.get("hal_disks"), "interfaces": pulse.get("hal_interfaces")}, "mesh": mesh.get("identity", {})}, indent=2))}</pre>
  </section>

  <section id='devices' class='wide'>
    <h2>Device + Storage Manager</h2>
    <div class='strip'>
      {pill("Devices", len(device_storage.get("devices", [])), bool(device_storage.get("ok")))}
      {pill("Payload used", f"{payload_usage.get('used_percent', 'n/a')}%")}
      {pill("Plans", len(storage_plans))}
      {pill("Warnings", len(device_storage.get("warnings", [])), len(device_storage.get("warnings", [])) == 0)}
    </div>
    <form method='post' action='/api/operator'>
      {button("device_refresh", "Refresh inventory", "secondary")}
    </form>
    <div class='grid3'>
      <form method='post' action='/api/operator'>
        <label>Device path</label><input name='device' value='/dev/sdb1'>
        <label>Mountpoint</label><input name='mountpoint' value='/mnt/cogos-usb'>
        {button("device_plan_mount", "Plan mount", "secondary")}
        {button("device_execute_mount", "Mount read-only", "warn")}
      </form>
      <form method='post' action='/api/operator'>
        <label>Archive source</label><input name='source' value='/opt/cogos/memory'>
        <label>Archive label</label><input name='label' value='before-update'>
        {button("storage_plan_archive", "Plan archive", "secondary")}
      </form>
      <form method='post' action='/api/operator'>
        <label>Cleanup target</label><input name='target' value='/opt/cogos/memory'>
        {button("storage_plan_cleanup", "Plan cleanup", "secondary")}
      </form>
    </div>
    <form method='post' action='/api/operator'>
      <label>Unmount CoGOS mountpoint</label><input name='mountpoint' value='/mnt/cogos-usb'>
      {button("device_execute_unmount", "Unmount", "warn")}
    </form>
    <table><thead><tr><th>Device</th><th>Class</th><th>Size</th><th>Mount</th><th>Used %</th></tr></thead><tbody>{render_devices(device_storage.get('devices', []))}</tbody></table>
    <table><thead><tr><th>Plan</th><th>Status</th><th>Target</th><th>Time</th></tr></thead><tbody>{render_storage_plans(storage_plans)}</tbody></table>
  </section>

  <section id='packages'>
    <h2>Packages And Backup</h2>
    <table><thead><tr><th>Package</th><th>Version</th><th>Status</th><th></th></tr></thead><tbody>{render_packages(pkgs)}</tbody></table>
    <form method='post' action='/api/operator'>
      <label>Backup label</label><input name='backup_label' value='control-center'>
      {button("backup_export", "Export backup", "secondary")}
    </form>
  </section>

  <section id='recovery'>
    <h2>Recovery Mode</h2>
    <div class='strip'>
      {pill("Flag", "armed" if recovery.get("recovery_flag") else "off", not bool(recovery.get("recovery_flag")))}
      {pill("Boot", recovery.get("boot_stage", "unknown"), bool(recovery.get("boot_ok")))}
      {pill("PID1", recovery.get("pid1_gate_ok", False), bool(recovery.get("pid1_gate_ok")))}
      {pill("Eval", recovery.get("eval_ok", "unknown"), recovery.get("eval_ok") if isinstance(recovery.get("eval_ok"), bool) else None)}
    </div>
    <form method='post' action='/api/operator'>
      {button("recovery_verify", "Verify recovery", "secondary")}
      {button("recovery_enable", "Arm next boot", "warn")}
      {button("recovery_disable", "Disarm", "secondary")}
      {button("recovery_reset_first_run", "Reset first-run", "secondary")}
    </form>
    <pre>{esc(json.dumps({"release": recovery.get("release"), "backups": recovery.get("backups", []), "snapshots": recovery.get("snapshots", [])}, indent=2))}</pre>
  </section>

  <section id='install'>
    <h2>Install And Persistence</h2>
    <div class='strip'>
      {pill("Label", persistence.get("label", "COGOSDATA"))}
      {pill("Mounted", persistence.get("mounted", False), bool(persistence.get("mounted")))}
      {pill("Config", persistence.get("config_bound", False), bool(persistence.get("config_bound")))}
      {pill("Memory", persistence.get("memory_bound", False), bool(persistence.get("memory_bound")))}
    </div>
    <form method='post' action='/api/operator'>
      {button("persist_status", "Refresh persistence", "secondary")}
    </form>
    <form method='post' action='/api/operator'>
      <label>Install target</label><input name='target' value='/dev/sdX'>
      {button("install_plan", "Plan install", "warn")}
      {button("install_validate", "Validate target", "secondary")}
    </form>
  </section>

  <section id='proofs'>
    <h2>Proofs</h2>
    <div class='strip'>
      {pill("Last action", last.get("action", "none"))}
      {pill("Action time", last.get("ts", ""))}
    </div>
    <pre>{esc(last_result or "{}")}</pre>
  </section>
</main>
</div>
</body></html>"""
    return page.encode("utf-8")


def handle_action(action: str, params: dict[str, list[str]]) -> dict:
    profile_id = (params.get("profile_id") or ["operator"])[0]
    auto = AutomaticModeEngine()

    if action == "hal_refresh":
        return {"ok": True, "hal": str(write_hal_snapshot())}
    if action == "device_refresh":
        return DeviceStorageManager().inventory()
    if action == "device_plan_mount":
        return DeviceStorageManager().plan_mount(
            (params.get("device") or [""])[0],
            (params.get("mountpoint") or [""])[0],
        )
    if action == "device_execute_mount":
        device = (params.get("device") or [""])[0]
        return DeviceStorageManager().execute_mount(
            device,
            (params.get("mountpoint") or [""])[0],
            readonly=True,
            yes=True,
            confirm=Path(device).name,
        )
    if action == "device_execute_unmount":
        mountpoint = (params.get("mountpoint") or [""])[0]
        return DeviceStorageManager().execute_unmount(
            mountpoint,
            yes=True,
            confirm=Path(mountpoint).name,
        )
    if action == "storage_plan_archive":
        return DeviceStorageManager().plan_archive(
            (params.get("source") or [str(ROOT / "memory")])[0],
            (params.get("label") or ["archive"])[0],
        )
    if action == "storage_plan_cleanup":
        return DeviceStorageManager().plan_cleanup((params.get("target") or [str(ROOT / "memory")])[0])
    if action == "first_run_apply":
        return FirstRunWizard().apply(
            hostname=(params.get("hostname") or ["cogos"])[0],
            profile_id=(params.get("profile_id") or ["operator"])[0],
            display_name=(params.get("display_name") or ["Operator"])[0],
            mode_default=(params.get("mode_default") or ["manual"])[0],
            workspace_name=(params.get("workspace_name") or ["Home Base"])[0],
            enable_kid=bool(params.get("enable_kid")),
        )
    if action == "first_run_reset":
        return FirstRunWizard().reset()
    if action == "recovery_verify":
        return RecoveryMode().verify()
    if action == "recovery_enable":
        return RecoveryMode().enable()
    if action == "recovery_disable":
        return RecoveryMode().disable()
    if action == "recovery_reset_first_run":
        return RecoveryMode().reset_first_run()
    if action == "corridor_verify":
        return run_boot_verification()
    if action == "eval_run":
        return run_eval_suite()
    if action == "backup_export":
        label = (params.get("backup_label") or ["control-center"])[0]
        return export_backup(label, profile_id=profile_id)
    if action == "auto_workspace":
        return auto.create_workspace((params.get("workspace_name") or ["New Workspace"])[0], profile_id=profile_id)
    if action == "auto_organize":
        return auto.organize_files(
            (params.get("source") or ["."])[0],
            workspace_id=(params.get("workspace_id") or [None])[0],
            apply=bool(params.get("apply")),
        )
    if action == "auto_remember":
        return auto.remember(
            (params.get("memory_key") or ["note"])[0],
            (params.get("memory_value") or [""])[0],
            workspace_id=(params.get("workspace_id") or [None])[0],
        )
    if action == "auto_suggest":
        return auto.suggest_workflows()
    if action == "pkg_install":
        return pkg_install((params.get("package_id") or [""])[0], profile_id=profile_id)
    if action == "pkg_remove":
        return pkg_remove((params.get("package_id") or [""])[0], profile_id=profile_id)
    if action == "persist_status":
        return persistence_status()
    if action == "install_plan":
        return install_plan((params.get("target") or [""])[0])
    if action == "install_validate":
        return install_validate((params.get("target") or [""])[0])
    return enqueue_operator_command(action, profile_id=profile_id)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/phase1":
            self._send(200, "application/json", json.dumps(phase1_status(), indent=2).encode("utf-8"))
            return
        if parsed.path == "/api/phase2":
            self._send(200, "application/json", json.dumps(phase2_status(), indent=2).encode("utf-8"))
            return
        if parsed.path == "/api/phase3":
            self._send(200, "application/json", json.dumps(phase3_status(), indent=2).encode("utf-8"))
            return
        if parsed.path == "/api/control-center":
            self._send(200, "application/json", json.dumps(control_center_status(), indent=2).encode("utf-8"))
            return
        if parsed.path in ("/", "/desktop", "/control"):
            self._send(200, "text/html; charset=utf-8", render_desktop(control_center_status()))
            return
        self.send_error(404)

    def do_POST(self):
        if urlparse(self.path).path != "/api/operator":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        params = parse_qs(body)
        action = (params.get("action") or [""])[0]
        result = handle_action(action, params)
        write_last_action(action, result)
        self.send_response(303)
        self.send_header("Location", "/desktop")
        self.end_headers()

    def _send(self, code: int, ctype: str, payload: bytes) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main() -> int:
    pid_path = Path("/run/cogos-desktop.pid")
    try:
        pid_path.write_text(str(os.getpid()) + "\n", encoding="utf-8")
    except OSError:
        pass
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"CoGOS Control Center on http://127.0.0.1:{PORT}/desktop", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
