const state = {
  sessionId: null,
  sessions: [],
  knowledge: [],
  memory: [],
  attachments: [],
  workspace: {
    projectProfile: null,
    verificationProfile: null,
    imports: [],
    tasks: [],
    snapshots: [],
    searchResults: [],
    symbols: [],
    selectedSymbol: null,
    pendingPatches: [],
    appliedChanges: [],
    review: null,
    selectedChangedFile: null,
    selectedChange: null,
    selectedChangeToken: null,
    selectedPatchLine: null,
    reviewDiffIndex: {},
  },
  approvals: [],
  runs: [],
  activeRunId: null,
  activeRun: null,
  activeRunEvents: [],
  activeRunEventIds: new Set(),
  activeRunDraft: "",
  runAudit: [],
  runStream: {
    controller: null,
    runId: null,
    lastEventId: 0,
    source: "",
  },
  exec: {
    allowedCommands: [],
    timeoutSeconds: 60,
    shellEnabled: false,
  },
  aris: {
    status: null,
    activity: [],
    discards: [],
    shames: [],
    fame: [],
    latestDecision: null,
    latestPlan: null,
    latestMystic: null,
    mysticSession: null,
    lastSpokenMysticReminderId: null,
  },
};

const elements = {
  brandName: document.querySelector("#brandName"),
  providerMode: document.querySelector("#providerMode"),
  modelLabel: document.querySelector("#modelLabel"),
  modelRouterSelect: document.querySelector("#modelRouterSelect"),
  applyModelRouterButton: document.querySelector("#applyModelRouterButton"),
  workspaceTitle: document.querySelector("#workspaceTitle"),
  arisRouteCopy: document.querySelector("#arisRouteCopy"),
  arisGoalInput: document.querySelector("#arisGoalInput"),
  arisFocusPathsInput: document.querySelector("#arisFocusPathsInput"),
  arisPlanButton: document.querySelector("#arisPlanButton"),
  mysticSessionBadge: document.querySelector("#mysticSessionBadge"),
  mysticSessionOutput: document.querySelector("#mysticSessionOutput"),
  mysticTickButton: document.querySelector("#mysticTickButton"),
  mysticBreakButton: document.querySelector("#mysticBreakButton"),
  mysticAcknowledgeButton: document.querySelector("#mysticAcknowledgeButton"),
  mysticMuteButton: document.querySelector("#mysticMuteButton"),
  mysticInput: document.querySelector("#mysticInput"),
  mysticReadButton: document.querySelector("#mysticReadButton"),
  mysticStatusBadge: document.querySelector("#mysticStatusBadge"),
  mysticOutput: document.querySelector("#mysticOutput"),
  arisOutcomeBadge: document.querySelector("#arisOutcomeBadge"),
  arisRouteList: document.querySelector("#arisRouteList"),
  arisPlanOutput: document.querySelector("#arisPlanOutput"),
  arisHealthList: document.querySelector("#arisHealthList"),
  arisLawBadge: document.querySelector("#arisLawBadge"),
  arisGuardrailList: document.querySelector("#arisGuardrailList"),
  arisEvaluationList: document.querySelector("#arisEvaluationList"),
  arisDiscardCount: document.querySelector("#arisDiscardCount"),
  arisDiscardList: document.querySelector("#arisDiscardList"),
  arisShameCount: document.querySelector("#arisShameCount"),
  arisShameList: document.querySelector("#arisShameList"),
  arisFameCount: document.querySelector("#arisFameCount"),
  arisFameList: document.querySelector("#arisFameList"),
  arisActivityCount: document.querySelector("#arisActivityCount"),
  arisActivityList: document.querySelector("#arisActivityList"),
  arisSoftKillButton: document.querySelector("#arisSoftKillButton"),
  arisHardKillButton: document.querySelector("#arisHardKillButton"),
  arisResetButton: document.querySelector("#arisResetButton"),
  messageList: document.querySelector("#messageList"),
  emptyState: document.querySelector("#emptyState"),
  sessionList: document.querySelector("#sessionList"),
  sessionCount: document.querySelector("#sessionCount"),
  knowledgeList: document.querySelector("#knowledgeList"),
  knowledgeCount: document.querySelector("#knowledgeCount"),
  agentTrace: document.querySelector("#agentTrace"),
  metaTools: document.querySelector("#metaTools"),
  metaRetrieval: document.querySelector("#metaRetrieval"),
  runCount: document.querySelector("#runCount"),
  runList: document.querySelector("#runList"),
  runStatusBadge: document.querySelector("#runStatusBadge"),
  runMetaList: document.querySelector("#runMetaList"),
  tailRunButton: document.querySelector("#tailRunButton"),
  cancelRunButton: document.querySelector("#cancelRunButton"),
  retryRunButton: document.querySelector("#retryRunButton"),
  runFinalMessage: document.querySelector("#runFinalMessage"),
  runEventCount: document.querySelector("#runEventCount"),
  runEventList: document.querySelector("#runEventList"),
  runFileCount: document.querySelector("#runFileCount"),
  runFileList: document.querySelector("#runFileList"),
  runAuditCount: document.querySelector("#runAuditCount"),
  runAuditList: document.querySelector("#runAuditList"),
  cacheBadge: document.querySelector("#cacheBadge"),
  fastModeToggle: document.querySelector("#fastModeToggle"),
  modeSelect: document.querySelector("#modeSelect"),
  retrievalRange: document.querySelector("#retrievalRange"),
  retrievalValue: document.querySelector("#retrievalValue"),
  messageInput: document.querySelector("#messageInput"),
  composer: document.querySelector("#composer"),
  sendButton: document.querySelector("#sendButton"),
  newSessionButton: document.querySelector("#newSessionButton"),
  fileInput: document.querySelector("#fileInput"),
  attachmentList: document.querySelector("#attachmentList"),
  memoryList: document.querySelector("#memoryList"),
  codeInput: document.querySelector("#codeInput"),
  runCodeButton: document.querySelector("#runCodeButton"),
  commandInput: document.querySelector("#commandInput"),
  commandCwdInput: document.querySelector("#commandCwdInput"),
  runCommandButton: document.querySelector("#runCommandButton"),
  resetSandboxButton: document.querySelector("#resetSandboxButton"),
  commandOutput: document.querySelector("#commandOutput"),
  sandboxBackendBadge: document.querySelector("#sandboxBackendBadge"),
  sandboxStatus: document.querySelector("#sandboxStatus"),
  allowedCommandsHint: document.querySelector("#allowedCommandsHint"),
  refreshWorkspaceButton: document.querySelector("#refreshWorkspaceButton"),
  codeOutput: document.querySelector("#codeOutput"),
  workspaceFiles: document.querySelector("#workspaceFiles"),
  workspaceCount: document.querySelector("#workspaceCount"),
  repoBundleInput: document.querySelector("#repoBundleInput"),
  cloneRepoUrlInput: document.querySelector("#cloneRepoUrlInput"),
  cloneRepoBranchInput: document.querySelector("#cloneRepoBranchInput"),
  cloneRepoTargetInput: document.querySelector("#cloneRepoTargetInput"),
  cloneRepoButton: document.querySelector("#cloneRepoButton"),
  importCount: document.querySelector("#importCount"),
  importStatus: document.querySelector("#importStatus"),
  importList: document.querySelector("#importList"),
  searchQueryInput: document.querySelector("#searchQueryInput"),
  searchModeSelect: document.querySelector("#searchModeSelect"),
  searchPathPrefixInput: document.querySelector("#searchPathPrefixInput"),
  runSearchButton: document.querySelector("#runSearchButton"),
  searchResultCount: document.querySelector("#searchResultCount"),
  searchStatus: document.querySelector("#searchStatus"),
  searchResults: document.querySelector("#searchResults"),
  projectLanguageCount: document.querySelector("#projectLanguageCount"),
  projectStatus: document.querySelector("#projectStatus"),
  projectMeta: document.querySelector("#projectMeta"),
  projectCommands: document.querySelector("#projectCommands"),
  symbolNameInput: document.querySelector("#symbolNameInput"),
  symbolPathInput: document.querySelector("#symbolPathInput"),
  symbolPathPrefixInput: document.querySelector("#symbolPathPrefixInput"),
  listSymbolsButton: document.querySelector("#listSymbolsButton"),
  loadSymbolButton: document.querySelector("#loadSymbolButton"),
  findReferencesButton: document.querySelector("#findReferencesButton"),
  symbolCount: document.querySelector("#symbolCount"),
  symbolStatus: document.querySelector("#symbolStatus"),
  symbolList: document.querySelector("#symbolList"),
  symbolEditor: document.querySelector("#symbolEditor"),
  applySymbolEditButton: document.querySelector("#applySymbolEditButton"),
  snapshotLabelInput: document.querySelector("#snapshotLabelInput"),
  createSnapshotButton: document.querySelector("#createSnapshotButton"),
  snapshotCount: document.querySelector("#snapshotCount"),
  snapshotStatus: document.querySelector("#snapshotStatus"),
  snapshotList: document.querySelector("#snapshotList"),
  taskTitleInput: document.querySelector("#taskTitleInput"),
  taskGoalInput: document.querySelector("#taskGoalInput"),
  taskCwdInput: document.querySelector("#taskCwdInput"),
  taskCommandsInput: document.querySelector("#taskCommandsInput"),
  runTaskButton: document.querySelector("#runTaskButton"),
  taskCount: document.querySelector("#taskCount"),
  taskList: document.querySelector("#taskList"),
  taskOutput: document.querySelector("#taskOutput"),
  approvalCount: document.querySelector("#approvalCount"),
  approvalList: document.querySelector("#approvalList"),
  patchCount: document.querySelector("#patchCount"),
  patchList: document.querySelector("#patchList"),
  historyCount: document.querySelector("#historyCount"),
  changeHistoryList: document.querySelector("#changeHistoryList"),
  changeInspectorMeta: document.querySelector("#changeInspectorMeta"),
  changeInspectorActions: document.querySelector("#changeInspectorActions"),
  changeInspectorDiff: document.querySelector("#changeInspectorDiff"),
  changeInspectorContent: document.querySelector("#changeInspectorContent"),
  reviewCount: document.querySelector("#reviewCount"),
  reviewSummary: document.querySelector("#reviewSummary"),
  changedFileList: document.querySelector("#changedFileList"),
  changedFileEditor: document.querySelector("#changedFileEditor"),
  selectedFileLabel: document.querySelector("#selectedFileLabel"),
  selectedDiffLabel: document.querySelector("#selectedDiffLabel"),
  reloadChangedFileButton: document.querySelector("#reloadChangedFileButton"),
  stageChangedFileButton: document.querySelector("#stageChangedFileButton"),
  reviewDiff: document.querySelector("#reviewDiff"),
  docNameInput: document.querySelector("#docNameInput"),
  docContentInput: document.querySelector("#docContentInput"),
  saveKnowledgeButton: document.querySelector("#saveKnowledgeButton"),
};

async function boot() {
  await Promise.all([loadConfig(), loadSessions(), loadKnowledge(), loadMemory(), loadArisRuntime()]);
  elements.fastModeToggle.checked = true;
  elements.retrievalRange.addEventListener("input", syncRetrievalValue);
  elements.composer.addEventListener("submit", onSubmit);
  elements.newSessionButton.addEventListener("click", resetSession);
  elements.arisPlanButton?.addEventListener("click", runArisPlan);
  elements.mysticTickButton?.addEventListener("click", runMysticTick);
  elements.mysticBreakButton?.addEventListener("click", runMysticBreak);
  elements.mysticAcknowledgeButton?.addEventListener("click", runMysticAcknowledge);
  elements.mysticMuteButton?.addEventListener("click", runMysticMute);
  elements.mysticReadButton?.addEventListener("click", runMysticReading);
  elements.arisSoftKillButton?.addEventListener("click", () => triggerArisKill("soft"));
  elements.arisHardKillButton?.addEventListener("click", () => triggerArisKill("hard"));
  elements.arisResetButton?.addEventListener("click", resetArisKillSwitch);
  elements.applyModelRouterButton?.addEventListener("click", applyModelRouterSelection);
  elements.saveKnowledgeButton.addEventListener("click", saveKnowledge);
  elements.fileInput.addEventListener("change", onFilesSelected);
  elements.repoBundleInput.addEventListener("change", uploadWorkspaceBundle);
  elements.cloneRepoButton.addEventListener("click", cloneWorkspaceRepo);
  elements.runSearchButton.addEventListener("click", runWorkspaceSearch);
  elements.listSymbolsButton.addEventListener("click", listWorkspaceSymbols);
  elements.loadSymbolButton.addEventListener("click", loadWorkspaceSymbol);
  elements.findReferencesButton.addEventListener("click", findSymbolReferences);
  elements.applySymbolEditButton.addEventListener("click", applySymbolEdit);
  elements.createSnapshotButton.addEventListener("click", createWorkspaceSnapshot);
  elements.runCodeButton.addEventListener("click", runCode);
  elements.runCommandButton.addEventListener("click", runCommand);
  elements.runTaskButton.addEventListener("click", runWorkspaceTask);
  elements.resetSandboxButton.addEventListener("click", resetSandbox);
  elements.refreshWorkspaceButton.addEventListener("click", refreshWorkspace);
  elements.reloadChangedFileButton.addEventListener("click", reloadSelectedChangedFile);
  elements.stageChangedFileButton.addEventListener("click", stageSelectedChangedFile);
  elements.tailRunButton.addEventListener("click", reconnectActiveRun);
  elements.cancelRunButton.addEventListener("click", cancelActiveRun);
  elements.retryRunButton.addEventListener("click", retryActiveRun);
  syncRetrievalValue();
  renderWorkspaceFiles([]);
  renderProjectProfile(null);
  renderImports([]);
  renderWorkspaceSearchResults([]);
  renderSymbols([]);
  renderSnapshots([]);
  renderTasks([]);
  renderRuns([]);
  renderRunInspector();
  renderApprovals([]);
  renderPendingPatches([]);
  renderAppliedChanges([]);
  renderSelectedChange(null);
  renderWorkspaceReview(null);
  renderArisStatus(null);
  renderMysticSession(null);
  renderArisDiscards([]);
  renderArisShames([]);
  renderArisFame([]);
  renderArisActivity([]);
}

async function loadConfig() {
  const response = await fetch("/api/config");
  const config = await response.json();
  elements.brandName.textContent = config.app_name;
  elements.providerMode.textContent = config.provider_mode;
  syncModelRouterControl(config.model_router);
  elements.modelLabel.textContent = formatModelRouterLabel(config.model_router, config);
  elements.workspaceTitle.textContent = config.aris?.service_name || "Advanced Repo Intelligence Service";
  elements.fastModeToggle.checked = config.fast_mode_default;
  state.exec.allowedCommands = config.exec?.allowed_commands || [];
  state.exec.timeoutSeconds = config.exec?.timeout_seconds || 60;
  state.exec.shellEnabled = Boolean(config.capabilities?.shell_exec);
  const importConfig = config.workspace?.imports || {};
  const searchConfig = config.workspace?.search || {};
  const snapshotConfig = config.workspace?.snapshots || {};
  updateSandboxStatus(config.sandbox);
  const cloneHosts = importConfig.allowed_clone_hosts || [];
  const uploadLimit = importConfig.max_upload_bytes || 0;
  elements.importStatus.textContent = cloneHosts.length
    ? `Clone hosts: ${cloneHosts.join(", ")}${uploadLimit ? ` | upload limit ${formatBytes(uploadLimit)}` : ""}`
    : "Import activity will appear here.";
  if (state.exec.allowedCommands.length) {
    elements.commandInput.title = `Allowed commands: ${state.exec.allowedCommands.join(", ")}`;
    elements.allowedCommandsHint.textContent = `Allowed: ${state.exec.allowedCommands.join(", ")}`;
  }
  if (!state.exec.shellEnabled) {
    elements.runCommandButton.disabled = true;
    elements.resetSandboxButton.disabled = true;
    elements.commandOutput.textContent = "Shell execution requires the Docker backend.";
  }
  if (searchConfig.max_results) {
    elements.searchStatus.textContent = `Search up to ${searchConfig.max_results} workspace hits per query.`;
    elements.symbolStatus.textContent = `Symbol tools read up to ${searchConfig.max_results} matching definitions at a time.`;
  }
  if (snapshotConfig.max_total_bytes) {
    elements.snapshotStatus.textContent =
      `Snapshots keep up to ${snapshotConfig.max_snapshots || 0} saves and ${formatBytes(snapshotConfig.max_total_bytes)} per snapshot.`;
  }
  elements.projectStatus.textContent = "Project detection will appear here.";
  if (config.aris) {
    state.aris.status = config.aris;
    renderArisStatus(config.aris);
  }
}

function formatModelRouterLabel(modelRouter, config) {
  const systems = Object.fromEntries((modelRouter?.systems || []).map((item) => [item.id, item]));
  const mode = modelRouter?.mode || "auto";
  if (mode === "manual" && modelRouter?.pinned_system && systems[modelRouter.pinned_system]) {
    const profile = systems[modelRouter.pinned_system];
    return `Pinned ${profile.label}: ${profile.model}`;
  }
  const general = systems.general?.model || config.general_model || config.model || "";
  const coding = systems.coding?.model || config.coding_model || config.quality_model || "";
  const light = systems.light_coding?.model || config.light_coding_model || config.fast_model || "";
  return `Auto: general ${general} | coding ${coding} | light ${light}`;
}

function syncModelRouterControl(modelRouter) {
  if (!elements.modelRouterSelect) {
    return;
  }
  const mode = modelRouter?.mode || "auto";
  const pinned = modelRouter?.pinned_system || "";
  elements.modelRouterSelect.value = mode === "manual" && pinned ? `manual:${pinned}` : "auto";
}

async function applyModelRouterSelection() {
  if (!elements.modelRouterSelect) {
    return;
  }
  const selected = elements.modelRouterSelect.value || "auto";
  const [mode, pinnedSystem = ""] = selected.split(":");
  const response = await fetch("/api/model-router", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      mode,
      pinned_system: mode === "manual" ? pinnedSystem : null,
    }),
  });
  const payload = await response.json();
  if (!response.ok || payload.ok === false) {
    elements.modelLabel.textContent = payload.error || "Model router update failed.";
    return;
  }
  syncModelRouterControl(payload.model_router);
  await Promise.all([loadConfig(), loadArisRuntime()]);
}

async function loadSessions() {
  const response = await fetch("/api/sessions");
  state.sessions = await response.json();
  renderSessions();
}

async function loadKnowledge() {
  const response = await fetch("/api/knowledge");
  state.knowledge = await response.json();
  renderKnowledge();
}

async function loadMemory() {
  const response = await fetch("/api/memory");
  const payload = await response.json();
  state.memory = payload.facts || [];
  renderMemory();
}

async function loadArisRuntime() {
  const sessionId = state.sessionId || "scratchpad";
  const [statusResponse, activityResponse, discardResponse, shameResponse, fameResponse, mysticResponse] = await Promise.all([
    fetch("/api/aris/status"),
    fetch("/api/aris/activity?limit=20"),
    fetch("/api/aris/discards?limit=20"),
    fetch("/api/aris/shame?limit=20"),
    fetch("/api/aris/fame?limit=20"),
    fetch(`/api/aris/mystic/status?session_id=${encodeURIComponent(sessionId)}`),
  ]);
  state.aris.status = await statusResponse.json();
  state.aris.activity = (await activityResponse.json()).activity || [];
  state.aris.discards = (await discardResponse.json()).entries || [];
  state.aris.shames = (await shameResponse.json()).entries || [];
  state.aris.fame = (await fameResponse.json()).entries || [];
  state.aris.mysticSession = await mysticResponse.json();
  state.aris.latestDecision = state.aris.activity.find(
    (entry) => entry.kind === "governance_result" || entry.kind === "governance_review"
  ) || null;
  renderArisStatus(state.aris.status);
  renderMysticSession(state.aris.mysticSession);
  renderArisDiscards(state.aris.discards);
  renderArisShames(state.aris.shames);
  renderArisFame(state.aris.fame);
  renderArisActivity(state.aris.activity);
}

async function loadRuns({ selectLatest = false } = {}) {
  if (!state.sessionId) {
    state.runs = [];
    renderRuns([]);
    renderRunInspector();
    return;
  }
  const priorActiveRunId = state.activeRunId;
  const response = await fetch(`/api/agent/${encodeURIComponent(state.sessionId)}/runs`);
  const payload = await response.json();
  state.runs = payload.runs || [];
  if (selectLatest && state.runs.length) {
    state.activeRunId = state.runs[0].id;
  } else if (state.activeRunId && !state.runs.some((run) => run.id === state.activeRunId)) {
    state.activeRunId = state.runs[0]?.id || null;
  } else if (!state.activeRunId && state.runs.length) {
    state.activeRunId = state.runs[0].id;
  }
  renderRuns(state.runs);
  if (state.activeRunId) {
    await loadActiveRun({
      replayStream: false,
      preserveEvents: priorActiveRunId === state.activeRunId,
    });
  } else {
    renderRunInspector();
  }
}

async function loadRunAudit() {
  if (!state.sessionId) {
    state.runAudit = [];
    renderRunInspector();
    return;
  }
  const response = await fetch(`/api/agent/${encodeURIComponent(state.sessionId)}/audit?limit=100`);
  const payload = await response.json();
  state.runAudit = payload.entries || [];
  renderRunInspector();
}

function renderSessions() {
  elements.sessionCount.textContent = `${state.sessions.length}`;
  elements.sessionList.innerHTML = "";
  for (const session of state.sessions) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `session-item${session.id === state.sessionId ? " active" : ""}`;
    item.innerHTML = `
      <p class="session-title">${escapeHtml(session.title)}</p>
      <p class="session-preview muted">${escapeHtml(session.preview || "No messages yet")}</p>
    `;
    item.addEventListener("click", () => {
      state.sessionId = session.id;
      elements.workspaceTitle.textContent = session.title;
      renderWorkspaceSearchResults([]);
      elements.searchStatus.textContent = "Search results will appear here.";
      renderSymbols([]);
      elements.symbolStatus.textContent = "Symbol details will appear here.";
      renderSessions();
      void Promise.all([refreshWorkspace(), loadRuns({ selectLatest: true }), loadRunAudit()]);
    });
    elements.sessionList.appendChild(item);
  }
}

function renderKnowledge() {
  elements.knowledgeCount.textContent = `${state.knowledge.length}`;
  elements.knowledgeList.innerHTML = "";
  for (const source of state.knowledge) {
    const item = document.createElement("div");
    item.className = "knowledge-item";
    item.innerHTML = `
      <p class="knowledge-title">${escapeHtml(source)}</p>
      <p class="knowledge-snippet muted">Available for retrieval grounding.</p>
    `;
    elements.knowledgeList.appendChild(item);
  }
}

function renderMemory() {
  elements.memoryList.innerHTML = "";
  if (!state.memory.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No memory facts saved yet.";
    elements.memoryList.appendChild(item);
    return;
  }
  for (const fact of state.memory) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(fact.category)}</p>
      <div class="muted">${escapeHtml(fact.value)}</div>
    `;
    elements.memoryList.appendChild(item);
  }
}

function renderArisStatus(status) {
  elements.arisHealthList.innerHTML = "";
  elements.arisGuardrailList.innerHTML = "";
  elements.arisEvaluationList.innerHTML = "";
  if (!status) {
    if (elements.arisLawBadge) {
      elements.arisLawBadge.textContent = "offline";
    }
    if (elements.arisOutcomeBadge) {
      elements.arisOutcomeBadge.textContent = "idle";
    }
    return;
  }
  const killSwitch = status.kill_switch || {};
  const shellExecution = status.shell_execution || {};
  const executionBackend = status.execution_backend || {};
  const demoMode = status.demo_mode || {};
  const modelRouter = status.model_router || {};
  const lawBadge = status.meta_law_1001_active ? "1001 active" : "1001 offline";
  elements.brandName.textContent = status.system_name || "ARIS";
  elements.workspaceTitle.textContent = status.service_name || "Advanced Repo Intelligence Service";
  document.title = status.system_name || "ARIS";
  elements.modelLabel.textContent = formatModelRouterLabel(modelRouter, status);
  syncModelRouterControl(modelRouter);
  elements.arisLawBadge.textContent = lawBadge;
  elements.arisOutcomeBadge.textContent = killSwitch.mode || "nominal";
  if (elements.arisRouteCopy) {
    elements.arisRouteCopy.textContent = demoMode.active
      ? `Route: ${(demoMode.route || ["Jarvis Blueprint", "Operator", "Governance Review", "Outcome"]).join(" -> ")}`
      : "Route: Jarvis blueprint inheritance -> Operator -> Forge -> Forge Eval when required -> output or Hall of Discard, Hall of Shame, or Hall of Fame.";
  }
  if (elements.arisPlanButton) {
    elements.arisPlanButton.disabled = Boolean(demoMode.active);
    elements.arisPlanButton.textContent = demoMode.active ? "Forge Stripped In Demo" : "Run Governed Plan";
  }
  const healthRows = [
    ["System", status.system_name || "ARIS"],
    ["Service", status.service_name || "Advanced Repo Intelligence Service"],
    ["Runtime Profile", status.runtime_profile || "full"],
    ["Repo Target", status.repo_target || "unknown"],
    ["Law Mode", status.law_mode || "unknown"],
    ["Model Router", modelRouter.mode === "manual" ? `Pinned ${modelRouter.pinned_system || "unknown"}` : "Auto"],
    [
      "General Model",
      (modelRouter.systems || []).find((item) => item.id === "general")?.model || "unconfigured",
    ],
    [
      "Coding Model",
      (modelRouter.systems || []).find((item) => item.id === "coding")?.model || "unconfigured",
    ],
    [
      "Light Coding Model",
      (modelRouter.systems || []).find((item) => item.id === "light_coding")?.model || "unconfigured",
    ],
    ["Startup", status.startup_ready ? "Ready" : "Blocked"],
    ["1001", status.meta_law_1001_active ? "Active" : "Inactive"],
    ["Shield of Truth", status.shield_of_truth?.active ? "Active" : "Unavailable"],
    ["Repo Logbook", status.repo_logbook?.active ? "Active" : "Missing"],
    ["Operator", status.operator?.active ? "Active" : "Offline"],
    [
      "Mystic",
      status.mystic?.active ? "Sustainment active" : "Unavailable",
    ],
    [
      "Mystic Reflection",
      status.mystic_reflection?.active
        ? status.mystic_reflection?.merged_with_jarvis
          ? "Merged with Jarvis"
          : "Active"
        : "Unavailable",
    ],
    [
      "Forge",
      status.forge?.connected
        ? status.forge?.provider_configured
          ? "Connected"
          : "Connected (provider not configured)"
        : "Disconnected",
    ],
    ["Forge Eval", status.forge_eval?.connected ? "Connected" : "Disconnected"],
    [
      "Evolving Engine",
      status.evolving_engine?.active ? "Active" : demoMode.active ? "Stripped in demo" : "Inactive",
    ],
    ["Hall of Discard", status.hall_of_discard?.active ? "Active" : "Unavailable"],
    ["Hall of Shame", status.hall_of_shame?.active ? "Active" : "Unavailable"],
    ["Hall of Fame", status.hall_of_fame?.active ? "Active" : "Unavailable"],
    [
      "Execution",
      shellExecution.enabled
        ? shellExecution.degraded
          ? `Degraded (${shellExecution.active_backend || executionBackend.active_backend || "unknown"})`
          : `Ready (${shellExecution.active_backend || executionBackend.active_backend || "unknown"})`
        : "Disabled",
    ],
    [
      "Execution Detail",
      shellExecution.detail || executionBackend.docker_detail || "No backend issues reported.",
    ],
    ["Kill Switch", killSwitch.summary || killSwitch.mode || "nominal"],
  ];
  for (const [label, value] of healthRows) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(label)}</p>
      <div class="muted">${escapeHtml(value)}</div>
    `;
    elements.arisHealthList.appendChild(item);
  }
  const blockers = status.startup_blockers || [];
  if (blockers.length) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">Startup Blockers</p>
      <div class="muted">${escapeHtml(blockers.join(" | "))}</div>
    `;
    elements.arisHealthList.appendChild(item);
  }
  for (const guardrail of status.guardrails || []) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(guardrail.title || guardrail.id || "guardrail")}</p>
      <div class="muted">${escapeHtml(guardrail.summary || "")}</div>
    `;
    elements.arisGuardrailList.appendChild(item);
  }
  const latest = state.aris.latestDecision;
  if (!latest) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No governed action has been recorded yet.";
    elements.arisEvaluationList.appendChild(item);
    renderArisRoute(null);
    return;
  }
  renderArisRoute(latest);
  const evalSections = [
    ...(latest.law_results || []),
    ...(latest.guardrails || []),
    ...(latest.shield
      ? [
          {
            title: "Shield of Truth",
            reason: `Verdict: ${latest.shield.verdict || "unknown"}${
              latest.shield.severity ? ` | Severity: ${latest.shield.severity}` : ""
            }`,
          },
        ]
      : []),
    ...(latest.forge_eval || []),
  ];
  for (const section of evalSections) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(section.title || section.id || section.mode || "check")}</p>
      <div class="muted">${escapeHtml(section.reason || "")}</div>
    `;
    elements.arisEvaluationList.appendChild(item);
  }
  if (latest.hall_name) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">Disposition Hall</p>
      <div class="muted">${escapeHtml(latest.hall_name)}</div>
    `;
    elements.arisEvaluationList.appendChild(item);
  }
}

function speakMysticReminder(message, reminderId) {
  if (!message || !("speechSynthesis" in window)) {
    return;
  }
  if (state.aris.lastSpokenMysticReminderId === reminderId) {
    return;
  }
  state.aris.lastSpokenMysticReminderId = reminderId || null;
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(new SpeechSynthesisUtterance(message));
}

function renderMysticSession(payload) {
  if (!elements.mysticSessionOutput || !elements.mysticSessionBadge) {
    return;
  }
  if (!payload) {
    elements.mysticSessionBadge.textContent = "idle";
    elements.mysticSessionOutput.textContent = "Mystic sustainment state will appear here.";
    return;
  }
  const latestReminder = payload.latest_trigger || payload.latest_reminder || null;
  elements.mysticSessionBadge.textContent = payload.active
    ? `level ${payload.alert_level || 0}`
    : "offline";
  const lines = [
    `Session: ${payload.session_id || "scratchpad"}`,
    `Alert level: ${payload.alert_level ?? 0}`,
    `Session minutes: ${payload.session_minutes ?? "unknown"}`,
    `Minutes since break: ${payload.minutes_since_break ?? "unknown"}`,
    `Minutes since voice: ${payload.minutes_since_voice ?? "unknown"}`,
    `Errors: ${payload.consecutive_errors ?? 0}`,
    `Loop count: ${payload.repeated_loop_count ?? 0}`,
    `Muted: ${payload.muted ? "yes" : "no"}`,
  ];
  if (latestReminder?.message) {
    lines.push(`Latest reminder: ${latestReminder.message}`);
    speakMysticReminder(latestReminder.message, latestReminder.id);
  } else if (payload.last_message) {
    lines.push(`Last message: ${payload.last_message}`);
  }
  const enabledControls = (payload.ui_controls || []).filter((control) => control.enabled !== false);
  if (enabledControls.length) {
    lines.push(`Controls: ${enabledControls.map((control) => control.label).join(", ")}`);
  }
  elements.mysticSessionOutput.textContent = lines.join("\n");
}

async function invokeMysticControl(endpoint, payload = {}) {
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: state.sessionId || "scratchpad",
      ...payload,
    }),
  });
  const data = await response.json();
  state.aris.mysticSession = data;
  renderMysticSession(state.aris.mysticSession);
  await loadArisRuntime();
}

async function runMysticTick() {
  await invokeMysticControl("/api/aris/mystic/tick");
}

async function runMysticBreak() {
  await invokeMysticControl("/api/aris/mystic/break");
}

async function runMysticAcknowledge() {
  await invokeMysticControl("/api/aris/mystic/acknowledge");
}

async function runMysticMute() {
  await invokeMysticControl("/api/aris/mystic/mute", { minutes: 10 });
}

async function runMysticReading() {
  const input = String(elements.mysticInput?.value || "").trim();
  if (!input) {
    elements.mysticStatusBadge.textContent = "input required";
    elements.mysticOutput.textContent = "Enter a Mystic Reflection prompt before running the reading.";
    return;
  }
  elements.mysticReadButton.disabled = true;
  elements.mysticStatusBadge.textContent = "running";
  elements.mysticOutput.textContent = "Running Mystic Reflection through Jarvis + ARIS governance...";
  try {
    const response = await fetch("/api/aris/mystic-read", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: state.sessionId || "scratchpad",
        input,
      }),
    });
    const payload = await response.json();
    state.aris.latestMystic = payload;
    elements.mysticStatusBadge.textContent = payload.ok ? "verified" : "blocked";
    const lines = [];
    if (payload.tool_result?.summary) {
      lines.push(payload.tool_result.summary);
    }
    if (payload.tool_result?.result) {
      const reading = payload.tool_result.result;
      lines.push(`State: ${reading.state_label || reading.state || "Unknown"}`);
      lines.push(
        `Archetypes: ${(reading.dominant_archetype_label || reading.dominant_archetype || "Witness")} vs ${(reading.opposing_archetype_label || reading.opposing_archetype || "Trickster")}`
      );
      lines.push(`Trial: ${reading.trial || "Action vs avoidance"}`);
      lines.push(`Next action: ${reading.next_action || "Choose one small action and complete it fully."}`);
    }
    if (payload.error) {
      lines.push(`Error: ${payload.error}`);
    }
    if (payload.governance?.hall_name) {
      lines.push(`Hall: ${payload.governance.hall_name}`);
    }
    if (payload.tool_result?.tool) {
      lines.push(`Tool: ${payload.tool_result.tool}`);
    }
    elements.mysticOutput.textContent = lines.join("\n");
    await loadArisRuntime();
  } catch (error) {
    elements.mysticStatusBadge.textContent = "error";
    elements.mysticOutput.textContent = `Mystic Reflection request failed: ${error.message}`;
  } finally {
    elements.mysticReadButton.disabled = false;
  }
}

function renderArisRoute(entry) {
  if (!elements.arisRouteList) {
    return;
  }
  elements.arisRouteList.innerHTML = "";
  const stages = Array.isArray(entry?.route)
    ? entry.route.map((item) => [item.stage, item.status])
    : entry
    ? [
        ["Jarvis Blueprint", "observed"],
        ["Operator", entry.operator_decision || "approved"],
        ["Forge", entry.kind === "forge_repo_plan" ? (entry.ok ? "completed" : "failed") : "governed"],
        ["Forge Eval", entry.requires_forge_eval ? (entry.verified ? "verified" : entry.disposition || "review") : "proposal-only"],
        ["Outcome", entry.disposition || "idle"],
      ]
    : [
        ["Jarvis Blueprint", "standby"],
        ["Operator", "standby"],
        ["Forge", "standby"],
        ["Forge Eval", "standby"],
        ["Outcome", "standby"],
      ];
  for (const [label, value] of stages) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(label)}</p>
      <div class="muted">${escapeHtml(String(value || ""))}</div>
    `;
    elements.arisRouteList.appendChild(item);
  }
}

function renderArisDiscards(entries) {
  renderArisHallEntries({
    countElement: elements.arisDiscardCount,
    listElement: elements.arisDiscardList,
    entries,
    emptyText: "Hall of Discard is empty.",
    fallbackLabel: "discard",
  });
}

function renderArisShames(entries) {
  renderArisHallEntries({
    countElement: elements.arisShameCount,
    listElement: elements.arisShameList,
    entries,
    emptyText: "Hall of Shame is empty.",
    fallbackLabel: "shame",
  });
}

function renderArisFame(entries) {
  renderArisHallEntries({
    countElement: elements.arisFameCount,
    listElement: elements.arisFameList,
    entries,
    emptyText: "Hall of Fame is waiting for verified returns.",
    fallbackLabel: "fame",
  });
}

function renderArisHallEntries({ countElement, listElement, entries, emptyText, fallbackLabel }) {
  countElement.textContent = `${entries.length} recent`;
  listElement.innerHTML = "";
  if (!entries.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = emptyText;
    listElement.appendChild(item);
    return;
  }
  for (const entry of entries) {
    const reEvaluationOf = entry.re_evaluation_of || entry.metadata?.re_evaluation_of || null;
    const transitionLine = reEvaluationOf
      ? `Re-evaluated from ${reEvaluationOf.hall || "prior hall"} · ${reEvaluationOf.entry_id || "entry"}`
      : entry.hall_transition_rule
        ? `Transition rule: ${entry.hall_transition_rule}`
        : "";
    const transitionHtml = transitionLine
      ? `<div class="muted">${escapeHtml(transitionLine)}</div>`
      : "";
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(entry.action?.action_type || entry.id || fallbackLabel)}</p>
      <div class="muted">${escapeHtml(entry.reason || "")}</div>
      <div class="muted">${escapeHtml(entry.action?.target || entry.source || "")}</div>
      ${transitionHtml}
      <div class="muted">${escapeHtml(entry.created_at || "")}</div>
    `;
    listElement.appendChild(item);
  }
}

function renderArisActivity(activity) {
  elements.arisActivityCount.textContent = `${activity.length} events`;
  elements.arisActivityList.innerHTML = "";
  if (!activity.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No ARIS activity recorded yet.";
    elements.arisActivityList.appendChild(item);
    return;
  }
  for (const entry of activity) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(entry.kind || entry.action_type || "activity")}</p>
      <div class="muted">${escapeHtml(entry.reason || entry.goal || entry.disposition || "")}</div>
      <div class="muted">${escapeHtml(entry.recorded_at || "")}</div>
    `;
    elements.arisActivityList.appendChild(item);
  }
}

function resetSession() {
  stopRunTail();
  state.sessionId = null;
  state.runs = [];
  state.activeRunId = null;
  state.activeRun = null;
  state.activeRunEvents = [];
  state.activeRunEventIds = new Set();
  state.activeRunDraft = "";
  state.runAudit = [];
  state.runStream = { controller: null, runId: null, lastEventId: 0, source: "" };
  elements.workspaceTitle.textContent = "Talk to your model";
  elements.messageList.innerHTML = "";
  elements.emptyState.style.display = "";
  state.attachments = [];
  renderAttachments();
  elements.codeOutput.textContent = "Interpreter output will appear here.";
  elements.commandOutput.textContent = state.exec.shellEnabled
    ? "Shell output will appear here."
    : "Shell execution requires the Docker backend.";
  elements.importStatus.textContent = "Import activity will appear here.";
  elements.searchStatus.textContent = "Search results will appear here.";
  elements.projectStatus.textContent = "Project detection will appear here.";
  elements.symbolStatus.textContent = "Symbol details will appear here.";
  elements.snapshotStatus.textContent = "Snapshot activity will appear here.";
  elements.taskOutput.textContent = "Task workflow output will appear here.";
  elements.symbolNameInput.value = "";
  elements.symbolPathInput.value = "";
  elements.symbolPathPrefixInput.value = "";
  elements.symbolEditor.value = "";
  renderWorkspaceFiles([]);
  renderProjectProfile(null);
  renderImports([]);
  renderWorkspaceSearchResults([]);
  renderSymbols([]);
  renderSnapshots([]);
  renderTasks([]);
  renderRuns([]);
  renderRunInspector();
  renderApprovals([]);
  renderPendingPatches([]);
  renderAppliedChanges([]);
  renderSelectedChange(null);
  renderWorkspaceReview(null);
  updateSandboxStatus(null);
  renderSessions();
  clearMeta();
}

function stopRunTail() {
  if (state.runStream.controller) {
    state.runStream.controller.abort();
  }
  state.runStream = {
    controller: null,
    runId: null,
    lastEventId: 0,
    source: "",
  };
}

function shortId(value) {
  const text = String(value || "").trim();
  return text ? text.slice(0, 8) : "run";
}

function runStatusLabel(status) {
  const value = String(status || "idle").trim() || "idle";
  return value.replaceAll("_", " ");
}

function runStatusClass(status) {
  const value = String(status || "idle").trim().toLowerCase();
  return value.replaceAll(/[^a-z0-9]+/g, "-") || "idle";
}

function normalizeRunAttachments(attachments) {
  if (!Array.isArray(attachments)) {
    return [];
  }
  return attachments
    .filter((attachment) => attachment && typeof attachment === "object")
    .map((attachment) => ({
      name: String(attachment.name || "").trim(),
      mime_type: String(attachment.mime_type || "").trim(),
      content: String(attachment.content || ""),
      kind: String(attachment.kind || "").trim(),
    }))
    .filter((attachment) => attachment.name && attachment.mime_type);
}

function upsertRunSummary(runPatch) {
  if (!runPatch || typeof runPatch !== "object") {
    return;
  }
  const runId = String(runPatch.id || "").trim();
  if (!runId) {
    return;
  }
  const index = state.runs.findIndex((candidate) => candidate.id === runId);
  const next = index >= 0 ? { ...state.runs[index], ...runPatch } : { ...runPatch };
  if (index >= 0) {
    state.runs.splice(index, 1, next);
  } else {
    state.runs.unshift(next);
  }
  state.runs.sort((left, right) => {
    const leftTime = Date.parse(left.updated_at || left.created_at || 0) || 0;
    const rightTime = Date.parse(right.updated_at || right.created_at || 0) || 0;
    return rightTime - leftTime;
  });
  if (state.activeRunId === runId) {
    state.activeRun = { ...(state.activeRun || {}), ...next };
  }
  renderRuns(state.runs);
}

function renderRuns(runs) {
  elements.runCount.textContent = `${runs.length} run${runs.length === 1 ? "" : "s"}`;
  elements.runList.innerHTML = "";
  if (!runs.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No durable agent runs yet.";
    elements.runList.appendChild(item);
    return;
  }
  for (const run of runs) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `context-item patch-item run-item${
      run.id === state.activeRunId ? " active" : ""
    }`;
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(run.title || run.kind || "run")}</p>
        <span class="badge badge-muted run-status-${escapeHtml(runStatusClass(run.status))}">
          ${escapeHtml(runStatusLabel(run.status))}
        </span>
      </div>
      <div class="muted patch-summary">${escapeHtml(run.user_message || "No prompt recorded.")}</div>
      <div class="run-card-meta">
        <span>${escapeHtml(run.kind || run.mode || "agent")}</span>
        <span>${escapeHtml(formatTimestamp(run.updated_at || run.created_at))}</span>
      </div>
    `;
    item.addEventListener("click", () => {
      void selectRun(run.id, { replayStream: true });
    });
    elements.runList.appendChild(item);
  }
}

async function selectRun(runId, { replayStream = true } = {}) {
  state.activeRunId = runId || null;
  renderRuns(state.runs);
  if (!runId) {
    stopRunTail();
    state.activeRun = null;
    state.activeRunEvents = [];
    state.activeRunEventIds = new Set();
    state.activeRunDraft = "";
    renderRunInspector();
    return;
  }
  await loadActiveRun({ replayStream, preserveEvents: false });
}

async function loadActiveRun({ replayStream = false, preserveEvents = false } = {}) {
  const runId = state.activeRunId;
  if (!runId) {
    renderRunInspector();
    return;
  }
  if (!preserveEvents) {
    state.activeRunEvents = [];
    state.activeRunEventIds = new Set();
    state.activeRunDraft = "";
  }
  const response = await fetch(`/api/agent/runs/${encodeURIComponent(runId)}`);
  const payload = await response.json();
  if (!payload.ok || !payload.run) {
    state.activeRun = null;
    renderRunInspector();
    return;
  }
  state.activeRun = payload.run;
  upsertRunSummary(payload.run);
  renderRunInspector();
  if (replayStream || (!payload.run.terminal && state.runStream.runId !== runId)) {
    void tailRun(runId, { reset: !preserveEvents });
  }
}

async function reconnectActiveRun() {
  if (!state.activeRunId) {
    return;
  }
  await loadActiveRun({ replayStream: true, preserveEvents: false });
}

async function cancelActiveRun() {
  if (!state.activeRunId) {
    return;
  }
  elements.cancelRunButton.disabled = true;
  try {
    const response = await fetch(`/api/agent/runs/${encodeURIComponent(state.activeRunId)}/cancel`, {
      method: "POST",
    });
    const payload = await response.json();
    if (payload.run) {
      upsertRunSummary(payload.run);
      state.activeRun = { ...(state.activeRun || {}), ...payload.run };
    }
    renderRunInspector();
    await loadRuns();
  } finally {
    elements.cancelRunButton.disabled = false;
  }
}

async function retryActiveRun() {
  if (!state.activeRun?.user_message) {
    return;
  }
  elements.modeSelect.value = "agent";
  await startChatRequest({
    message: state.activeRun.user_message,
    mode: "agent",
    attachments: normalizeRunAttachments(state.activeRun.request?.attachments || []),
    sessionId: state.activeRun.session_id || state.sessionId,
  });
}

function trackRunMeta(payload) {
  const runId = String(payload.run_id || "").trim();
  if (!runId) {
    return;
  }
  const preservingExistingRun = state.activeRunId === runId && state.activeRunEvents.length > 0;
  const previousLastEventId = Number(state.runStream.lastEventId || 0);
  stopRunTail();
  state.activeRunId = runId;
  if (!preservingExistingRun) {
    state.activeRunEvents = [];
    state.activeRunEventIds = new Set();
    state.activeRunDraft = "";
  }
  state.runStream = {
    controller: null,
    runId,
    lastEventId: preservingExistingRun ? previousLastEventId : 0,
    source: "inline",
  };
  const existing = state.runs.find((run) => run.id === runId) || {};
  state.activeRun = {
    ...existing,
    id: runId,
    session_id: payload.session_id || existing.session_id || state.sessionId,
    mode: payload.mode || existing.mode || "agent",
    status: existing.status || "running",
    updated_at: new Date().toISOString(),
  };
  upsertRunSummary(state.activeRun);
  renderRunInspector();
}

function buildRunTraceEntry(eventName, payload) {
  if (eventName === "meta") {
    const detail = [
      payload.mode ? `mode ${payload.mode}` : "",
      payload.model_route ? `route ${payload.model_route}` : "",
      typeof payload.approved === "boolean" ? (payload.approved ? "approved" : "rejected") : "",
    ]
      .filter(Boolean)
      .join(" · ");
    return {
      id: payload.run_event_id || `meta-${Date.now()}`,
      event: eventName,
      title: payload.approval_id ? `approval · ${payload.approval_id}` : "meta",
      detail: detail || "Run metadata received.",
      kind: "meta",
      raw: payload,
    };
  }
  if (eventName === "done") {
    return {
      id: payload.run_event_id || `done-${Date.now()}`,
      event: eventName,
      title: "done",
      detail: "Stream replay finished.",
      kind: "done",
      raw: payload,
    };
  }
  const kind = String(payload.kind || eventName || "event").trim();
  const label = payload.tool ? `${kind} · ${payload.tool}` : kind;
  const detail =
    String(payload.content || "").trim() ||
    (payload.approval && typeof payload.approval === "object"
      ? String(payload.approval.summary || payload.approval.title || "").trim()
      : "") ||
    (payload.args ? JSON.stringify(payload.args) : "") ||
    (payload.error ? String(payload.error) : "");
  return {
    id: payload.run_event_id || `event-${Date.now()}`,
    event: eventName,
    title: label,
    detail,
    kind,
    step: payload.step,
    tool: payload.tool,
    raw: payload,
  };
}

function updateActiveRunFromEvent(eventName, payload) {
  const runId = String(payload.run_id || state.activeRunId || "").trim();
  if (!runId || state.activeRunId !== runId) {
    return;
  }
  if (payload.run_event_id) {
    state.runStream.lastEventId = Math.max(
      Number(state.runStream.lastEventId || 0),
      Number(payload.run_event_id || 0)
    );
  }
  const patch = {
    id: runId,
    updated_at: new Date().toISOString(),
  };
  if (eventName === "agent_step") {
    const kind = String(payload.kind || "").trim();
    if (kind === "approval_required") {
      patch.status = "blocked";
      if (payload.approval && typeof payload.approval === "object") {
        patch.blocked_on_approval_id = String(payload.approval.id || "").trim();
        patch.blocked_on_kind = String(payload.approval.kind || "").trim();
      }
    } else if (kind === "cancelled") {
      patch.status = "cancelled";
    } else if (kind === "error" || kind === "approval_missing") {
      patch.status = "failed";
      patch.error_text = String(payload.content || "").trim();
    } else if (["final", "fallback", "limit"].includes(kind)) {
      patch.status = "completed";
      patch.final_message = String(payload.content || "").trim();
    } else if (!state.activeRun?.terminal) {
      patch.status = state.activeRun?.status === "blocked" ? "blocked" : "running";
    }
  } else if (eventName === "done" && state.activeRun && !state.activeRun.terminal) {
    patch.status = state.activeRun.status || "completed";
  }
  state.activeRun = { ...(state.activeRun || {}), ...patch };
  upsertRunSummary(state.activeRun);
}

function noteRunEvent(eventName, payload) {
  const runId = String(payload.run_id || state.activeRunId || "").trim();
  if (!runId) {
    return;
  }
  if (!state.activeRunId) {
    state.activeRunId = runId;
  }
  if (state.activeRunId !== runId) {
    return;
  }
  updateActiveRunFromEvent(eventName, payload);
  if (eventName === "token") {
    state.activeRunDraft += String(payload.content || "");
    renderRunInspector();
    return;
  }
  const eventId = Number(payload.run_event_id || 0);
  if (eventId && state.activeRunEventIds.has(eventId)) {
    return;
  }
  if (eventId) {
    state.activeRunEventIds.add(eventId);
  }
  const entry = buildRunTraceEntry(eventName, payload);
  const previous = state.activeRunEvents[state.activeRunEvents.length - 1];
  if (
    previous &&
    entry.kind === "command_chunk" &&
    previous.kind === "command_chunk" &&
    previous.step === entry.step
  ) {
    previous.detail = `${previous.detail}\n${entry.detail}`.trim();
  } else {
    state.activeRunEvents.push(entry);
  }
  renderRunInspector();
}

async function tailRun(runId, { reset = false } = {}) {
  stopRunTail();
  if (reset) {
    state.activeRunEvents = [];
    state.activeRunEventIds = new Set();
    state.activeRunDraft = "";
    renderRunInspector();
  }
  const controller = new AbortController();
  state.runStream = {
    controller,
    runId,
    lastEventId: reset ? 0 : Number(state.runStream.lastEventId || 0),
    source: "tail",
  };
  try {
    const response = await fetch(
      `/api/agent/runs/${encodeURIComponent(runId)}/stream?after_event_id=${encodeURIComponent(
        state.runStream.lastEventId
      )}`,
      { signal: controller.signal }
    );
    await consumeEventStream(response, {
      meta(payload) {
        noteRunEvent("meta", payload);
      },
      agent_step(payload) {
        noteRunEvent("agent_step", payload);
      },
      token(payload) {
        noteRunEvent("token", payload);
      },
      done(payload) {
        noteRunEvent("done", payload);
      },
    });
  } catch (error) {
    if (error?.name !== "AbortError") {
      state.activeRunEvents.push({
        id: `tail-error-${Date.now()}`,
        event: "agent_step",
        title: "tail error",
        detail: String(error?.message || error),
        kind: "error",
        raw: { content: String(error?.message || error) },
      });
      renderRunInspector();
    }
  } finally {
    if (state.runStream.controller === controller) {
      state.runStream = {
        controller: null,
        runId,
        lastEventId: state.runStream.lastEventId,
        source: "",
      };
    }
    await loadActiveRun({ replayStream: false, preserveEvents: true });
  }
}

function collectRunApprovalIds(run, events) {
  const ids = new Set();
  if (run?.blocked_on_approval_id) {
    ids.add(String(run.blocked_on_approval_id));
  }
  for (const entry of events) {
    const approval = entry.raw?.approval;
    if (approval && typeof approval === "object" && approval.id) {
      ids.add(String(approval.id));
    }
    if (entry.raw?.approval_id) {
      ids.add(String(entry.raw.approval_id));
    }
  }
  return ids;
}

function collectPathsFromObject(paths, value) {
  if (!value || typeof value !== "object") {
    return;
  }
  const candidates = [
    value.path,
    value.file,
    value.target_path,
    value.relative_path,
    value.source_path,
    value.destination_path,
  ];
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) {
      paths.add(candidate.trim());
    }
  }
  if (Array.isArray(value.paths)) {
    for (const candidate of value.paths) {
      if (typeof candidate === "string" && candidate.trim()) {
        paths.add(candidate.trim());
      }
    }
  }
}

function filteredRunAuditEntries() {
  if (!state.activeRun) {
    return [];
  }
  const approvalIds = collectRunApprovalIds(state.activeRun, state.activeRunEvents);
  if (!approvalIds.size) {
    return state.runAudit.slice(0, 8);
  }
  return state.runAudit.filter((entry) => approvalIds.has(String(entry.approval_id || "")));
}

function collectRunFiles(run, events, auditEntries) {
  const paths = new Set();
  for (const entry of events) {
    collectPathsFromObject(paths, entry.raw);
    collectPathsFromObject(paths, entry.raw?.approval);
    collectPathsFromObject(paths, entry.raw?.args);
  }
  for (const entry of auditEntries) {
    collectPathsFromObject(paths, entry.details);
  }
  if (run?.blocked_on_approval_id) {
    const pendingPatch = state.workspace.pendingPatches.find(
      (patch) => patch.id === run.blocked_on_approval_id
    );
    if (pendingPatch?.path) {
      paths.add(String(pendingPatch.path));
    }
  }
  return Array.from(paths);
}

function renderRunInspector() {
  const run = state.activeRun;
  elements.runMetaList.innerHTML = "";
  elements.runEventList.innerHTML = "";
  elements.runFileList.innerHTML = "";
  elements.runAuditList.innerHTML = "";
  if (!run) {
    elements.runStatusBadge.className = "badge badge-muted";
    elements.runStatusBadge.textContent = "idle";
    elements.runFinalMessage.textContent = "Select a run to inspect its final answer and live trace.";
    elements.runEventCount.textContent = "0 events";
    elements.runFileCount.textContent = "0 files";
    elements.runAuditCount.textContent = "0 entries";
    elements.tailRunButton.disabled = true;
    elements.cancelRunButton.disabled = true;
    elements.retryRunButton.disabled = true;
    return;
  }

  elements.runStatusBadge.className = `badge badge-muted run-status-${runStatusClass(run.status)}`;
  elements.runStatusBadge.textContent = runStatusLabel(run.status);
  elements.tailRunButton.disabled = false;
  elements.tailRunButton.textContent = run.terminal ? "Replay Stream" : "Reconnect";
  elements.cancelRunButton.disabled = Boolean(run.terminal);
  elements.retryRunButton.disabled = !String(run.user_message || "").trim();

  const metaItems = [
    {
      label: "Prompt",
      value: String(run.user_message || "No prompt recorded.").trim(),
    },
    {
      label: "Lifecycle",
      value: [
        `Run ${shortId(run.id)} · ${run.kind || run.mode || "agent"}`,
        `Created ${formatTimestamp(run.created_at)}`,
        run.started_at ? `Started ${formatTimestamp(run.started_at)}` : "",
        run.completed_at ? `Completed ${formatTimestamp(run.completed_at)}` : `Updated ${formatTimestamp(run.updated_at)}`,
        run.model ? `Model ${run.model}` : "",
      ]
        .filter(Boolean)
        .join("\n"),
    },
  ];
  if (run.blocked_on_approval_id) {
    metaItems.push({
      label: "Blocked",
      value: `Approval ${shortId(run.blocked_on_approval_id)} · ${run.blocked_on_kind || "approval"}`,
    });
  }
  for (const item of metaItems) {
    const node = document.createElement("div");
    node.className = "context-item";
    node.innerHTML = `
      <p class="context-label">${escapeHtml(item.label)}</p>
      <div class="muted patch-summary">${escapeHtml(item.value)}</div>
    `;
    elements.runMetaList.appendChild(node);
  }

  const finalMessage =
    String(state.activeRunDraft || "").trim() ||
    String(run.final_message || "").trim() ||
    String(run.error_text || "").trim() ||
    "Run has not produced a final answer yet.";
  elements.runFinalMessage.textContent = finalMessage;

  const visibleEvents = state.activeRunEvents.slice(-18);
  elements.runEventCount.textContent = `${state.activeRunEvents.length} event${
    state.activeRunEvents.length === 1 ? "" : "s"
  }`;
  if (!visibleEvents.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "Run trace will appear here.";
    elements.runEventList.appendChild(item);
  } else {
    if (state.activeRunEvents.length > visibleEvents.length) {
      const note = document.createElement("div");
      note.className = "context-item muted";
      note.textContent = `Showing the latest ${visibleEvents.length} trace events.`;
      elements.runEventList.appendChild(note);
    }
    for (const entry of visibleEvents) {
      const node = document.createElement("div");
      node.className = "context-item run-event-card";
      node.innerHTML = `
        <div class="patch-header">
          <p class="run-event-title">${escapeHtml(entry.title)}</p>
          <span class="badge badge-muted">${escapeHtml(
            entry.step ? `step ${entry.step}` : entry.event
          )}</span>
        </div>
        <pre class="run-event-output">${escapeHtml(entry.detail || "No detail recorded.")}</pre>
      `;
      elements.runEventList.appendChild(node);
    }
  }

  const auditEntries = filteredRunAuditEntries();
  const filePaths = collectRunFiles(run, state.activeRunEvents, auditEntries);
  elements.runFileCount.textContent = `${filePaths.length} file${filePaths.length === 1 ? "" : "s"}`;
  if (!filePaths.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No file activity traced yet.";
    elements.runFileList.appendChild(item);
  } else {
    for (const path of filePaths) {
      const node = document.createElement("div");
      node.className = "context-item run-file-card";
      node.innerHTML = `
        <p class="context-label">file</p>
        <div class="muted">${escapeHtml(path)}</div>
      `;
      elements.runFileList.appendChild(node);
    }
  }

  elements.runAuditCount.textContent = `${auditEntries.length} entr${auditEntries.length === 1 ? "y" : "ies"}`;
  if (!auditEntries.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "Approval audit for this run will appear here.";
    elements.runAuditList.appendChild(item);
    return;
  }
  for (const entry of auditEntries.slice(0, 8)) {
    const summary =
      String(entry.details?.title || entry.details?.summary || "").trim() ||
      String(entry.details?.command_text || "").trim() ||
      "Approval activity recorded.";
    const node = document.createElement("div");
    node.className = "context-item run-audit-card";
    node.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(entry.action || entry.kind || "audit")}</p>
        <span class="badge badge-muted">${escapeHtml(formatTimestamp(entry.created_at))}</span>
      </div>
      <div class="muted patch-summary">${escapeHtml(summary)}</div>
    `;
    elements.runAuditList.appendChild(node);
  }
}

async function startChatRequest({
  message,
  mode = elements.modeSelect.value,
  attachments = state.attachments,
  sessionId = state.sessionId,
} = {}) {
  const prompt = String(message || "").trim();
  if (!prompt) {
    return;
  }
  const trackActiveRun = mode === "agent";
  elements.sendButton.disabled = true;
  appendMessage("user", prompt);
  elements.messageInput.value = "";
  const assistantNode = appendMessage("assistant", "");
  const assistantBody = assistantNode.querySelector(".message-body");
  elements.emptyState.style.display = "none";

  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      message: prompt,
      fast_mode: elements.fastModeToggle.checked,
      retrieval_k: Number(elements.retrievalRange.value),
      mode,
      attachments,
    }),
  });

  await consumeEventStream(response, {
    meta(payload) {
      state.sessionId = payload.session_id;
      updateMeta(payload);
      if (trackActiveRun && payload.run_id) {
        trackRunMeta(payload);
      }
    },
    agent_step(payload) {
      appendAgentStep(payload);
      if (trackActiveRun) {
        noteRunEvent("agent_step", payload);
      }
    },
    token(payload) {
      assistantBody.textContent += payload.content;
      assistantNode.scrollIntoView({ block: "end", behavior: "smooth" });
      if (trackActiveRun) {
        noteRunEvent("token", payload);
      }
    },
    done(payload) {
      if (trackActiveRun) {
        noteRunEvent("done", payload);
      }
    },
    async error(payload) {
      if (trackActiveRun) {
        noteRunEvent("agent_step", payload);
      }
    },
  });

  assistantBody.textContent = assistantBody.textContent.trim();
  elements.sendButton.disabled = false;
  state.attachments = [];
  renderAttachments();
  await loadSessions();
  await loadMemory();
  await refreshWorkspace();
  if (trackActiveRun) {
    await loadRuns({ selectLatest: true });
    await loadRunAudit();
  }
}

async function saveKnowledge() {
  const name = elements.docNameInput.value.trim();
  const content = elements.docContentInput.value.trim();
  if (!name || !content) {
    return;
  }
  elements.saveKnowledgeButton.disabled = true;
  await fetch("/api/knowledge", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, content }),
  });
  elements.docNameInput.value = "";
  elements.docContentInput.value = "";
  elements.saveKnowledgeButton.disabled = false;
  await loadKnowledge();
}

async function onFilesSelected(event) {
  const files = Array.from(event.target.files || []);
  for (const file of files) {
    const attachment = await fileToAttachment(file);
    if (attachment) {
      state.attachments.push(attachment);
    }
  }
  event.target.value = "";
  renderAttachments();
}

async function uploadWorkspaceBundle(event) {
  const [file] = Array.from(event.target.files || []);
  if (!file) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  const form = new FormData();
  form.append("file", file);
  const targetPath = elements.cloneRepoTargetInput.value.trim();
  if (targetPath) {
    form.append("target_path", targetPath);
  }
  elements.importStatus.textContent = `Uploading ${file.name}...`;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/import/upload`,
    {
      method: "POST",
      body: form,
    }
  );
  const payload = await response.json();
  elements.repoBundleInput.value = "";
  if (!payload.ok) {
    elements.importStatus.textContent = payload.error || "Workspace import failed.";
    await refreshWorkspace();
    return;
  }
  state.sessionId = payload.session_id || sessionId;
  elements.importStatus.textContent = payload.import?.summary || `${file.name} imported.`;
  await loadSessions();
  await refreshWorkspace();
}

async function cloneWorkspaceRepo() {
  const repoUrl = elements.cloneRepoUrlInput.value.trim();
  if (!repoUrl) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  elements.cloneRepoButton.disabled = true;
  elements.importStatus.textContent = `Cloning ${repoUrl}...`;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/import/clone`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        repo_url: repoUrl,
        branch: elements.cloneRepoBranchInput.value.trim() || null,
        target_dir: elements.cloneRepoTargetInput.value.trim() || null,
      }),
    }
  );
  const payload = await response.json();
  elements.cloneRepoButton.disabled = false;
  if (!payload.ok) {
    elements.importStatus.textContent = payload.error || "Repo clone failed.";
    await refreshWorkspace();
    return;
  }
  state.sessionId = payload.session_id || sessionId;
  elements.importStatus.textContent = payload.import?.summary || "Repo cloned.";
  elements.cloneRepoUrlInput.value = "";
  elements.cloneRepoBranchInput.value = "";
  await loadSessions();
  await refreshWorkspace();
}

async function runWorkspaceSearch() {
  const query = elements.searchQueryInput.value.trim();
  if (!query) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  elements.runSearchButton.disabled = true;
  elements.searchStatus.textContent = `Searching for ${query}...`;
  const params = new URLSearchParams({
    query,
    mode: elements.searchModeSelect.value || "text",
  });
  const pathPrefix = elements.searchPathPrefixInput.value.trim();
  if (pathPrefix) {
    params.set("path_prefix", pathPrefix);
  }
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/search?${params.toString()}`
  );
  const payload = await response.json();
  elements.runSearchButton.disabled = false;
  if (!payload.ok) {
    elements.searchStatus.textContent = payload.error || "Workspace search failed.";
    renderWorkspaceSearchResults([]);
    return;
  }
  state.sessionId = payload.session_id || sessionId;
  elements.searchStatus.textContent = `${payload.result_count || 0} result(s) for "${query}".`;
  renderWorkspaceSearchResults(payload.results || []);
}

async function listWorkspaceSymbols() {
  const sessionId = state.sessionId || "scratchpad";
  const params = new URLSearchParams();
  const query = elements.symbolNameInput.value.trim();
  const pathPrefix = elements.symbolPathPrefixInput.value.trim();
  if (query) {
    params.set("query", query);
  }
  if (pathPrefix) {
    params.set("path_prefix", pathPrefix);
  }
  elements.listSymbolsButton.disabled = true;
  elements.symbolStatus.textContent = "Listing workspace symbols...";
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/symbols?${params.toString()}`
  );
  const payload = await response.json();
  elements.listSymbolsButton.disabled = false;
  if (!payload.ok) {
    elements.symbolStatus.textContent = payload.error || "Symbol listing failed.";
    renderSymbols([]);
    return;
  }
  elements.symbolStatus.textContent = `${payload.symbol_count || 0} symbol(s) found.`;
  renderSymbols(payload.symbols || []);
}

async function loadWorkspaceSymbol() {
  const symbol = elements.symbolNameInput.value.trim();
  if (!symbol) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  const params = new URLSearchParams({ symbol });
  const path = elements.symbolPathInput.value.trim();
  if (path) {
    params.set("path", path);
  }
  elements.loadSymbolButton.disabled = true;
  elements.symbolStatus.textContent = `Loading symbol ${symbol}...`;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/symbol?${params.toString()}`
  );
  const payload = await response.json();
  elements.loadSymbolButton.disabled = false;
  if (!payload.ok) {
    elements.symbolStatus.textContent = payload.error || "Symbol read failed.";
    return;
  }
  const symbolPayload = payload.symbol || null;
  state.workspace.selectedSymbol = symbolPayload;
  if (symbolPayload) {
    elements.symbolNameInput.value = symbolPayload.qualname || symbolPayload.name || symbol;
    elements.symbolPathInput.value = symbolPayload.path || path;
    elements.symbolEditor.value = symbolPayload.content || "";
    elements.symbolStatus.textContent = `${symbolPayload.qualname || symbolPayload.name} loaded from ${symbolPayload.path}:${symbolPayload.start_line}-${symbolPayload.end_line}`;
  }
}

async function findSymbolReferences() {
  const symbol = elements.symbolNameInput.value.trim();
  if (!symbol) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  const params = new URLSearchParams({ symbol });
  const pathPrefix = elements.symbolPathPrefixInput.value.trim();
  if (pathPrefix) {
    params.set("path_prefix", pathPrefix);
  }
  elements.findReferencesButton.disabled = true;
  elements.searchStatus.textContent = `Finding references for ${symbol}...`;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/symbol/references?${params.toString()}`
  );
  const payload = await response.json();
  elements.findReferencesButton.disabled = false;
  if (!payload.ok) {
    elements.searchStatus.textContent = payload.error || "Reference search failed.";
    renderWorkspaceSearchResults([]);
    return;
  }
  elements.searchStatus.textContent = `${payload.result_count || 0} reference(s) for "${symbol}".`;
  renderWorkspaceSearchResults(payload.results || []);
}

async function applySymbolEdit() {
  const symbol = elements.symbolNameInput.value.trim();
  const content = elements.symbolEditor.value;
  if (!symbol || !content.trim()) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  elements.applySymbolEditButton.disabled = true;
  elements.symbolStatus.textContent = `Applying symbol edit for ${symbol}...`;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/symbol`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        symbol,
        path: elements.symbolPathInput.value.trim() || null,
        content,
      }),
    }
  );
  const payload = await response.json();
  elements.applySymbolEditButton.disabled = false;
  if (!payload.ok) {
    elements.symbolStatus.textContent = payload.error || "Symbol edit failed.";
    return;
  }
  elements.symbolStatus.textContent =
    `Symbol edit applied to ${payload.path || elements.symbolPathInput.value.trim()}.`;
  await refreshWorkspace();
  await loadWorkspaceSymbol();
}

async function createWorkspaceSnapshot() {
  const sessionId = state.sessionId || "scratchpad";
  elements.createSnapshotButton.disabled = true;
  elements.snapshotStatus.textContent = "Creating workspace snapshot...";
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/snapshots`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        label: elements.snapshotLabelInput.value.trim() || null,
      }),
    }
  );
  const payload = await response.json();
  elements.createSnapshotButton.disabled = false;
  if (!payload.ok) {
    elements.snapshotStatus.textContent = payload.error || "Snapshot creation failed.";
    renderSnapshots(payload.snapshots || []);
    return;
  }
  state.sessionId = payload.session_id || sessionId;
  elements.snapshotLabelInput.value = "";
  elements.snapshotStatus.textContent =
    payload.snapshot?.label
      ? `Snapshot saved: ${payload.snapshot.label}`
      : "Workspace snapshot saved.";
  renderSnapshots(payload.snapshots || []);
  await loadSessions();
  await refreshWorkspace();
}

async function restoreWorkspaceSnapshot(snapshotId, button) {
  const sessionId = state.sessionId || "scratchpad";
  if (!window.confirm("Restore this snapshot and replace the current workspace state?")) {
    return;
  }
  button.disabled = true;
  elements.snapshotStatus.textContent = "Restoring workspace snapshot...";
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/snapshots/${encodeURIComponent(snapshotId)}/restore`,
    {
      method: "POST",
    }
  );
  const payload = await response.json();
  if (!payload.ok) {
    elements.snapshotStatus.textContent = payload.error || "Snapshot restore failed.";
    renderSnapshots(payload.snapshots || []);
    button.disabled = false;
    return;
  }
  elements.snapshotStatus.textContent =
    payload.snapshot?.label
      ? `Snapshot restored: ${payload.snapshot.label}`
      : "Workspace snapshot restored.";
  renderSnapshots(payload.snapshots || []);
  renderWorkspaceSearchResults([]);
  elements.searchStatus.textContent = "Search results will appear here.";
  await refreshWorkspace();
}

async function runCode() {
  const code = elements.codeInput.value.trim();
  if (!code) {
    return;
  }
  elements.runCodeButton.disabled = true;
  elements.codeOutput.textContent = "Running Python...";
  const response = await fetch("/api/execute", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: state.sessionId,
      code,
    }),
  });
  const payload = await response.json();
  if (!state.sessionId && payload.session_id) {
    state.sessionId = payload.session_id;
  }
  const segments = [];
  if (payload.stdout) segments.push(`stdout\n${payload.stdout.trimEnd()}`);
  if (payload.stderr) segments.push(`stderr\n${payload.stderr.trimEnd()}`);
  if (!segments.length) segments.push("No output.");
  if (payload.timed_out) segments.push("Execution timed out.");
  elements.codeOutput.textContent = segments.join("\n\n");
  renderWorkspaceFiles(payload.files || [], payload.sandbox || null);
  await refreshWorkspace();
  elements.runCodeButton.disabled = false;
}

async function runCommand() {
  const raw = elements.commandInput.value.trim();
  if (!raw || !state.exec.shellEnabled) {
    return;
  }
  const command = tokenizeCommand(raw);
  if (!command) {
    elements.commandOutput.textContent = "Command parsing failed. Check your quotes and escapes.";
    return;
  }
  const cwd = elements.commandCwdInput.value.trim();
  elements.runCommandButton.disabled = true;
  elements.commandOutput.textContent = "";

  const response = await fetch("/api/exec/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: state.sessionId,
      command,
      cwd: cwd || null,
      timeout_seconds: state.exec.timeoutSeconds,
    }),
  });

  await consumeEventStream(response, {
    exec_start(payload) {
      if (payload.session_id) {
        state.sessionId = payload.session_id;
      }
      const prefix = payload.cwd ? ` (${payload.cwd})` : "";
      elements.commandOutput.textContent = `$ ${payload.command.join(" ")}${prefix}\n\n`;
    },
    exec_chunk(payload) {
      elements.commandOutput.textContent += payload.content;
    },
    async exec_done(payload) {
      if (!elements.commandOutput.textContent.trim()) {
        elements.commandOutput.textContent = "No output.\n";
      }
      const suffix = payload.timed_out
        ? `\n[command timed out, exit=${payload.returncode}]`
        : `\n[command finished, exit=${payload.returncode}]`;
      elements.commandOutput.textContent += suffix;
      if (payload.session_id) {
        state.sessionId = payload.session_id;
      }
      renderWorkspaceFiles(payload.files || [], payload.sandbox || null);
      elements.runCommandButton.disabled = false;
      await loadSessions();
      await refreshWorkspace();
    },
  });
}

async function resetSandbox() {
  const sessionId = state.sessionId || "scratchpad";
  elements.resetSandboxButton.disabled = true;
  const response = await fetch(`/api/sandbox/${encodeURIComponent(sessionId)}/reset`, {
    method: "POST",
  });
  const payload = await response.json();
  const detail = payload.detail || (payload.removed ? "Sandbox removed." : "No sandbox to remove.");
  elements.commandOutput.textContent = detail;
  await refreshWorkspace();
  elements.resetSandboxButton.disabled = !state.exec.shellEnabled;
}

async function refreshWorkspace() {
  const sessionId = state.sessionId || "scratchpad";
  const [workspaceResponse, reviewResponse] = await Promise.all([
    fetch(`/api/workspace/${encodeURIComponent(sessionId)}`),
    fetch(`/api/workspace/${encodeURIComponent(sessionId)}/review`),
  ]);
  const workspacePayload = await workspaceResponse.json();
  const reviewPayload = await reviewResponse.json();
  renderWorkspaceFiles(workspacePayload.files || [], workspacePayload.sandbox || null);
  renderProjectProfile(workspacePayload.project || null);
  state.workspace.verificationProfile = workspacePayload.verification || null;
  renderImports(workspacePayload.imports || []);
  renderSnapshots(workspacePayload.snapshots || []);
  renderTasks(workspacePayload.tasks || []);
  renderApprovals(workspacePayload.pending_approvals || []);
  renderPendingPatches(workspacePayload.pending_patches || []);
  renderAppliedChanges(workspacePayload.applied_changes || []);
  syncSelectedChange();
  renderWorkspaceReview(reviewPayload);
  renderRunInspector();
  if (workspacePayload.aris) {
    state.aris.status = workspacePayload.aris;
    renderArisStatus(state.aris.status);
  }
  await loadArisRuntime();
}

async function runArisPlan() {
  const goal = elements.arisGoalInput?.value.trim() || "";
  if (!goal) {
    return;
  }
  const focusPaths = (elements.arisFocusPathsInput?.value || "")
    .split(/[\n,]/)
    .map((value) => value.trim())
    .filter(Boolean);
  elements.arisPlanButton.disabled = true;
  elements.arisPlanOutput.textContent = "Running ARIS governed repo plan...";
  const response = await fetch("/api/aris/forge/plan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal, focus_paths: focusPaths }),
  });
  const payload = await response.json();
  state.aris.latestPlan = payload;
  const repoManager = payload.result?.repo_manager || payload.repo_manager || {};
  const summary = repoManager.repo_summary || payload.error || "No Forge plan returned.";
  const planSteps = Array.isArray(repoManager.plan)
    ? repoManager.plan.map((step) => `- ${step.step} (${step.file || "repo"})`).join("\n")
    : "";
  const risks = Array.isArray(repoManager.risks)
    ? repoManager.risks.map((risk) => `- ${risk.file}: ${risk.issue}`).join("\n")
    : "";
  elements.arisPlanOutput.textContent = [summary, risks && `Risks\n${risks}`, planSteps && `Plan\n${planSteps}`]
    .filter(Boolean)
    .join("\n\n");
  elements.arisOutcomeBadge.textContent = payload.ok ? "proposal ready" : "proposal blocked";
  renderArisRoute(payload);
  await loadArisRuntime();
  elements.arisPlanButton.disabled = false;
}

async function triggerArisKill(mode) {
  const reason = window.prompt(
    mode === "hard" ? "Hard kill reason" : "Soft kill reason",
    mode === "hard" ? "manual emergency halt" : "manual pause for review"
  );
  if (!reason) {
    return;
  }
  const path = mode === "hard" ? "/api/aris/kill/hard" : "/api/aris/kill/soft";
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason }),
  });
  const payload = await response.json();
  elements.arisPlanOutput.textContent = payload.kill_switch?.summary || "Kill switch updated.";
  await loadArisRuntime();
}

async function resetArisKillSwitch() {
  const reason = window.prompt("Reset reason", "manual integrity-reviewed reset");
  if (!reason) {
    return;
  }
  const response = await fetch("/api/aris/kill/reset", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason, reseal_integrity: false }),
  });
  const payload = await response.json();
  elements.arisPlanOutput.textContent = payload.kill_switch?.summary || "Kill switch reset requested.";
  await loadArisRuntime();
}

async function runWorkspaceTask() {
  const goal = elements.taskGoalInput.value.trim();
  if (!goal) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  const commands = elements.taskCommandsInput.value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  elements.runTaskButton.disabled = true;
  elements.taskOutput.textContent = "";
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/tasks/run`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: elements.taskTitleInput.value.trim() || null,
        goal,
        cwd: elements.taskCwdInput.value.trim() || null,
        test_commands: commands,
        fast_mode: elements.fastModeToggle.checked,
      }),
    }
  );

  await consumeEventStream(response, {
    meta(payload) {
      if (payload.session_id) {
        state.sessionId = payload.session_id;
      }
      if (payload.task?.summary) {
        elements.taskOutput.textContent = `${payload.task.summary}\n`;
      }
    },
    agent_step(payload) {
      appendAgentStep(payload);
      const label = payload.tool ? `${payload.kind} · ${payload.tool}` : payload.kind || "step";
      const content = payload.content || (payload.args ? JSON.stringify(payload.args) : "");
      elements.taskOutput.textContent += `${label}: ${content}\n`;
    },
    task_result(payload) {
      const task = payload.task || {};
      const summary = task.summary || "Task updated.";
      const note = task.approval_note ? `\n${task.approval_note}` : "";
      elements.taskOutput.textContent += `\n${summary}${note}\n`;
    },
    async done() {
      elements.runTaskButton.disabled = false;
      await loadSessions();
      await refreshWorkspace();
    },
  });
}

async function resolveWorkspaceTask(taskId, approved, button) {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  const action = approved ? "approve" : "reject";
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/tasks/${encodeURIComponent(taskId)}/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note: approved ? "approved in UI" : "needs another pass" }),
    }
  );
  const payload = await response.json();
  elements.taskOutput.textContent = payload.task?.summary || "Task status updated.";
  await refreshWorkspace();
}

async function onSubmit(event) {
  event.preventDefault();
  const message = elements.messageInput.value.trim();
  if (!message) {
    return;
  }
  await startChatRequest({
    message,
    mode: elements.modeSelect.value,
    attachments: state.attachments,
    sessionId: state.sessionId,
  });
}

function appendMessage(role, content) {
  elements.emptyState.style.display = "none";
  const row = document.createElement("div");
  row.className = `message-row ${role}`;
  row.innerHTML = `
    <article class="message-bubble">
      <p class="message-role">${role}</p>
      <p class="message-body"></p>
    </article>
  `;
  row.querySelector(".message-body").textContent = content;
  elements.messageList.appendChild(row);
  row.scrollIntoView({ block: "end", behavior: "smooth" });
  return row;
}

function updateMeta(payload) {
  clearMeta();
  elements.cacheBadge.textContent = payload.cache_hit ? "cache hit" : "live";
  elements.cacheBadge.classList.toggle("badge-muted", !payload.cache_hit);
  if (payload.memory) {
    state.memory = payload.memory;
    renderMemory();
  }
  if (payload.mode) {
    elements.workspaceTitle.textContent =
      elements.workspaceTitle.textContent === "Talk to your model"
        ? `Mode: ${payload.mode}`
        : elements.workspaceTitle.textContent;
  }

  for (const tool of payload.tools || []) {
    const node = document.createElement("div");
    node.className = "context-item";
    node.innerHTML = `
      <p class="context-label">${escapeHtml(tool.name)}</p>
      <div class="muted">${escapeHtml(tool.content)}</div>
    `;
    elements.metaTools.appendChild(node);
  }

  for (const hit of payload.retrieval || []) {
    const node = document.createElement("div");
    node.className = "context-item";
    node.innerHTML = `
      <p class="context-label">${escapeHtml(hit.source)}</p>
      <div class="muted">${escapeHtml(hit.snippet)}</div>
    `;
    elements.metaRetrieval.appendChild(node);
  }

  for (const attachment of payload.attachments || []) {
    const node = document.createElement("div");
    node.className = "context-item";
    node.innerHTML = `
      <p class="context-label">${escapeHtml(attachment.kind)}</p>
      <div class="muted">${escapeHtml(attachment.preview)}</div>
    `;
    elements.metaTools.appendChild(node);
  }
}

function clearMeta() {
  elements.agentTrace.innerHTML = "";
  elements.metaTools.innerHTML = "";
  elements.metaRetrieval.innerHTML = "";
  elements.cacheBadge.textContent = "cold";
  elements.cacheBadge.classList.add("badge-muted");
}

function syncRetrievalValue() {
  elements.retrievalValue.textContent = elements.retrievalRange.value;
}

function renderAttachments() {
  elements.attachmentList.innerHTML = "";
  for (const [index, attachment] of state.attachments.entries()) {
    const chip = document.createElement("div");
    chip.className = "attachment-chip";
    chip.innerHTML = `
      <span>${escapeHtml(attachment.name)}</span>
      <button type="button" data-index="${index}">x</button>
    `;
    chip.querySelector("button").addEventListener("click", () => {
      state.attachments.splice(index, 1);
      renderAttachments();
    });
    elements.attachmentList.appendChild(chip);
  }
}

function renderWorkspaceFiles(files, sandbox = null) {
  elements.workspaceFiles.innerHTML = "";
  elements.workspaceCount.textContent = `${files.length} files`;
  updateSandboxStatus(sandbox);
  if (!files.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "Workspace is empty.";
    elements.workspaceFiles.appendChild(item);
    return;
  }
  for (const file of files) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">file</p>
      <div class="muted">${escapeHtml(file)}</div>
    `;
    elements.workspaceFiles.appendChild(item);
  }
}

function renderProjectProfile(project) {
  state.workspace.projectProfile = project;
  elements.projectMeta.innerHTML = "";
  elements.projectCommands.innerHTML = "";
  const languages = Array.isArray(project?.languages) ? project.languages : [];
  elements.projectLanguageCount.textContent = `${languages.length} languages`;
  if (!project) {
    elements.projectStatus.textContent = "Project detection will appear here.";
    return;
  }
  const frameworks = Array.isArray(project.frameworks) ? project.frameworks : [];
  const packageManagers = Array.isArray(project.package_managers) ? project.package_managers : [];
  const entrypoints = Array.isArray(project.entrypoints) ? project.entrypoints : [];
  const signals = Array.isArray(project.signals) ? project.signals : [];
  elements.projectStatus.textContent = languages.length || frameworks.length || packageManagers.length
    ? `Detected ${languages.join(", ") || "workspace"} project signals.`
    : "No strong project signals detected yet.";

  for (const [label, values] of [
    ["Languages", languages],
    ["Frameworks", frameworks],
    ["Package Managers", packageManagers],
    ["Entrypoints", entrypoints],
  ]) {
    if (!values.length) {
      continue;
    }
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(label)}</p>
      <div class="muted">${escapeHtml(values.join(", "))}</div>
    `;
    elements.projectMeta.appendChild(item);
  }
  for (const [label, values] of [
    ["Install", project.install_commands || []],
    ["Tests", project.test_commands || []],
    ["Lint", project.lint_commands || []],
    ["Run", project.run_commands || []],
  ]) {
    if (!Array.isArray(values) || !values.length) {
      continue;
    }
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(label)}</p>
      <div class="muted">${escapeHtml(values.join(" | "))}</div>
    `;
    elements.projectCommands.appendChild(item);
  }
  if (!elements.taskCommandsInput.value.trim()) {
    const tests = Array.isArray(project.test_commands) ? project.test_commands : [];
    const example = tests[0] || "pytest -q";
    elements.taskCommandsInput.placeholder =
      `One required test command per line, for example:\n${example}`;
  }
  if (signals.length) {
    const item = document.createElement("div");
    item.className = "context-item";
    item.innerHTML = `
      <p class="context-label">Signals</p>
      <div class="muted">${escapeHtml(signals.join(" | "))}</div>
    `;
    elements.projectCommands.appendChild(item);
  }
}

function renderImports(imports) {
  state.workspace.imports = imports;
  elements.importList.innerHTML = "";
  elements.importCount.textContent = `${imports.length} imports`;
  if (!imports.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No repo or bundle imports yet.";
    elements.importList.appendChild(item);
    return;
  }
  for (const entry of imports) {
    const item = document.createElement("div");
    item.className = "context-item import-item";
    const sample = Array.isArray(entry.files_sample) && entry.files_sample.length
      ? entry.files_sample.slice(0, 3).join("\n")
      : "No file sample available.";
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(entry.summary || entry.kind || "import")}</p>
        <span class="badge badge-muted">${escapeHtml(entry.kind || "import")}</span>
      </div>
      <div class="muted patch-summary">${escapeHtml(entry.target_path || ".")}</div>
      <pre class="diff-output">${escapeHtml(sample)}</pre>
    `;
    elements.importList.appendChild(item);
  }
}

function renderWorkspaceSearchResults(results) {
  state.workspace.searchResults = results;
  elements.searchResults.innerHTML = "";
  elements.searchResultCount.textContent = `${results.length} hits`;
  if (!results.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No workspace search results yet.";
    elements.searchResults.appendChild(item);
    return;
  }
  for (const entry of results) {
    const item = document.createElement("div");
    item.className = "context-item search-result-item";
    const location = entry.line ? `${entry.path}:${entry.line}` : entry.path;
    const badge = entry.type === "symbol" && entry.symbol_kind
      ? entry.symbol_kind
      : entry.type || "result";
    const summary = entry.symbol
      ? `${entry.symbol}${entry.signature ? ` · ${entry.signature}` : ""}`
      : entry.snippet || entry.match || location;
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(location)}</p>
        <span class="badge badge-muted">${escapeHtml(badge)}</span>
      </div>
      <div class="muted patch-summary">${escapeHtml(summary)}</div>
    `;
    if (entry.type === "symbol") {
      const actions = document.createElement("div");
      actions.className = "task-actions";
      const load = document.createElement("button");
      load.type = "button";
      load.className = "secondary-button";
      load.textContent = "Load Symbol";
      load.addEventListener("click", () => {
        elements.symbolNameInput.value = entry.symbol || entry.match || "";
        elements.symbolPathInput.value = entry.path || "";
        loadWorkspaceSymbol();
      });
      actions.appendChild(load);
      item.appendChild(actions);
    }
    elements.searchResults.appendChild(item);
  }
}

function renderSymbols(symbols) {
  state.workspace.symbols = symbols;
  elements.symbolList.innerHTML = "";
  elements.symbolCount.textContent = `${symbols.length} symbols`;
  if (!symbols.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No symbols loaded yet.";
    elements.symbolList.appendChild(item);
    return;
  }
  for (const symbol of symbols) {
    const item = document.createElement("div");
    item.className = "context-item search-result-item";
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(symbol.qualname || symbol.name || "symbol")}</p>
        <span class="badge badge-muted">${escapeHtml(symbol.kind || "symbol")}</span>
      </div>
      <div class="muted patch-summary">${escapeHtml(`${symbol.path}:${symbol.start_line}-${symbol.end_line}`)}</div>
      <div class="muted">${escapeHtml(symbol.signature || "")}</div>
    `;
    const actions = document.createElement("div");
    actions.className = "task-actions";
    const load = document.createElement("button");
    load.type = "button";
    load.className = "secondary-button";
    load.textContent = "Load";
    load.addEventListener("click", () => {
      elements.symbolNameInput.value = symbol.qualname || symbol.name || "";
      elements.symbolPathInput.value = symbol.path || "";
      loadWorkspaceSymbol();
    });
    actions.appendChild(load);
    item.appendChild(actions);
    elements.symbolList.appendChild(item);
  }
}

function renderSnapshots(snapshots) {
  state.workspace.snapshots = snapshots;
  elements.snapshotList.innerHTML = "";
  elements.snapshotCount.textContent = `${snapshots.length} saved`;
  if (!snapshots.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No workspace snapshots yet.";
    elements.snapshotList.appendChild(item);
    return;
  }
  for (const snapshot of snapshots) {
    const item = document.createElement("div");
    item.className = "context-item task-item";
    const label = snapshot.label || "Workspace snapshot";
    const availability = snapshot.available === false ? "missing archive" : "available";
    const sample = Array.isArray(snapshot.sample_files) && snapshot.sample_files.length
      ? snapshot.sample_files.slice(0, 3).join("\n")
      : "No visible files recorded.";
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(label)}</p>
        <span class="approval-badges">
          <span class="badge badge-muted">${escapeHtml(availability)}</span>
          <span class="badge badge-muted">${escapeHtml(snapshot.file_count || 0)} files</span>
        </span>
      </div>
      <div class="muted patch-summary">${escapeHtml(snapshot.created_at || "")}</div>
      <pre class="diff-output">${escapeHtml(sample)}</pre>
    `;
    const actions = document.createElement("div");
    actions.className = "task-actions";
    const restore = document.createElement("button");
    restore.type = "button";
    restore.className = "secondary-button";
    restore.textContent = "Restore Snapshot";
    restore.disabled = snapshot.available === false;
    restore.addEventListener("click", () => restoreWorkspaceSnapshot(snapshot.id, restore));
    actions.appendChild(restore);
    item.appendChild(actions);
    elements.snapshotList.appendChild(item);
  }
}

function renderTasks(tasks) {
  state.workspace.tasks = tasks;
  elements.taskList.innerHTML = "";
  elements.taskCount.textContent = `${tasks.length} tasks`;
  if (!tasks.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No workspace tasks yet.";
    elements.taskList.appendChild(item);
    return;
  }
  for (const task of tasks) {
    const item = document.createElement("div");
    item.className = "context-item task-item";
    const note = task.approval_note ? `<div class="muted">${escapeHtml(task.approval_note)}</div>` : "";
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(task.title || "Workspace task")}</p>
        <span class="approval-badges">
          <span class="badge badge-muted">${escapeHtml(task.status || "task")}</span>
          <span class="badge badge-muted">${escapeHtml(task.phase || "phase")}</span>
        </span>
      </div>
      <div class="muted patch-summary">${escapeHtml(task.summary || task.goal || "")}</div>
      ${note}
    `;
    if (task.status === "ready_for_approval") {
      const actions = document.createElement("div");
      actions.className = "task-actions";
      const approve = document.createElement("button");
      approve.type = "button";
      approve.className = "secondary-button";
      approve.textContent = "Approve Task";
      approve.addEventListener("click", () => resolveWorkspaceTask(task.id, true, approve));
      const reject = document.createElement("button");
      reject.type = "button";
      reject.className = "secondary-button";
      reject.textContent = "Needs Changes";
      reject.addEventListener("click", () => resolveWorkspaceTask(task.id, false, reject));
      actions.appendChild(approve);
      actions.appendChild(reject);
      item.appendChild(actions);
    }
    elements.taskList.appendChild(item);
  }
}

function renderApprovals(approvals) {
  state.approvals = approvals;
  const commandApprovals = approvals.filter((approval) => approval.kind !== "patch");
  elements.approvalList.innerHTML = "";
  elements.approvalCount.textContent = `${commandApprovals.length} pending`;
  if (!commandApprovals.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No pending command approvals.";
    elements.approvalList.appendChild(item);
    return;
  }
  for (const approval of commandApprovals) {
    const item = document.createElement("div");
    item.className = "context-item patch-item approval-item";
    const detail = approval.stale_reason || approval.message || approval.summary || "";
    const requestedTier = approval.requested_tier
      ? `<span class="badge badge-muted">${escapeHtml(approval.requested_tier)}</span>`
      : "";
    const runLink = approval.run_id
      ? `<button type="button" class="run-link-button" data-action="run">Run ${escapeHtml(
          shortId(approval.run_id)
        )}</button>`
      : "";
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(approval.title || "Approval required")}</p>
        <span class="approval-badges">
          <span class="badge badge-muted">${escapeHtml(approval.kind || "approval")}</span>
          ${requestedTier}
        </span>
      </div>
      <div class="muted patch-summary">${escapeHtml(approval.summary || "")}</div>
      <pre class="diff-output">${escapeHtml(detail)}</pre>
      <div class="patch-actions">
        ${runLink}
        <button type="button" class="secondary-button" data-action="approve">
          ${approval.resume_available ? "Approve & Resume" : "Approve"}
        </button>
        <button type="button" class="secondary-button danger-button" data-action="reject">
          ${approval.resume_available ? "Reject & Continue" : "Reject"}
        </button>
      </div>
    `;
    const runButton = item.querySelector('[data-action="run"]');
    const approveButton = item.querySelector('[data-action="approve"]');
    const rejectButton = item.querySelector('[data-action="reject"]');
    if (runButton) {
      runButton.addEventListener("click", () => void selectRun(approval.run_id, { replayStream: true }));
    }
    approveButton.addEventListener("click", () => handleApprovalDecision(approval, true, approveButton));
    rejectButton.addEventListener("click", () => handleApprovalDecision(approval, false, rejectButton));
    elements.approvalList.appendChild(item);
  }
}

function renderPendingPatches(patches) {
  state.workspace.pendingPatches = patches;
  elements.patchList.innerHTML = "";
  elements.patchCount.textContent = `${patches.length} pending`;
  if (!patches.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No pending patches.";
    elements.patchList.appendChild(item);
    return;
  }
  for (const patch of patches) {
    const patchApproval = state.approvals.find(
      (approval) => approval.kind === "patch" && approval.id === patch.id
    );
    const hunkCount = Number.isFinite(patch.hunk_count) ? Number(patch.hunk_count) : 0;
    const summary = patchApproval?.stale_reason
      ? `${patch.summary || ""}\n${patchApproval.stale_reason}`.trim()
      : patch.summary || "";
    const runLink = patchApproval?.run_id
      ? `<button type="button" class="run-link-button" data-action="run">Run ${escapeHtml(
          shortId(patchApproval.run_id)
        )}</button>`
      : "";
    const item = document.createElement("div");
    item.className = `context-item patch-item change-item${
      state.workspace.selectedChange?.kind === "pending" &&
      state.workspace.selectedChange?.id === patch.id
        ? " active"
        : ""
    }`;
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(patch.path || "patch")}</p>
        <span class="approval-badges">
          <span class="badge badge-muted">${escapeHtml(patch.operation || "edit")}</span>
          <span class="badge badge-muted">${escapeHtml(patch.source || "agent")}</span>
          <span class="badge badge-muted">${escapeHtml(
            patch.review_complete ? "reviewed" : `${hunkCount} hunk${hunkCount === 1 ? "" : "s"}`
          )}</span>
        </span>
      </div>
      <div class="muted patch-summary">${escapeHtml(summary)}</div>
      <div class="patch-actions">
        ${runLink}
        <button type="button" class="secondary-button" data-action="inspect">Inspect</button>
        <button type="button" class="secondary-button" data-action="apply">
          ${patchApproval?.resume_available ? "Approve & Resume" : "Apply"}
        </button>
        <button type="button" class="secondary-button danger-button" data-action="reject">
          ${patchApproval?.resume_available ? "Reject & Continue" : "Reject"}
        </button>
      </div>
    `;
    item.addEventListener("click", (event) => {
      if (event.target.closest("button")) {
        return;
      }
      setSelectedChange({ kind: "pending", id: patch.id });
    });
    const runButton = item.querySelector('[data-action="run"]');
    const inspectButton = item.querySelector('[data-action="inspect"]');
    const applyButton = item.querySelector('[data-action="apply"]');
    const rejectButton = item.querySelector('[data-action="reject"]');
    if (runButton) {
      runButton.addEventListener("click", () =>
        void selectRun(patchApproval.run_id, { replayStream: true })
      );
    }
    inspectButton.addEventListener("click", () => setSelectedChange({ kind: "pending", id: patch.id }));
    if (patchApproval?.resume_available) {
      applyButton.addEventListener("click", () => handleApprovalDecision(patchApproval, true, applyButton));
      rejectButton.addEventListener("click", () =>
        handleApprovalDecision(patchApproval, false, rejectButton)
      );
    } else {
      applyButton.addEventListener("click", () => applyPendingPatch(patch.id, applyButton));
      rejectButton.addEventListener("click", () => rejectPendingPatch(patch.id, rejectButton));
    }
    elements.patchList.appendChild(item);
  }
}

function verificationPresets() {
  const presets = state.workspace.verificationProfile?.presets;
  return Array.isArray(presets) ? presets : [];
}

function defaultVerificationPreset() {
  const presets = verificationPresets();
  if (!presets.length) {
    return null;
  }
  const defaultId = String(state.workspace.verificationProfile?.default_preset_id || "").trim();
  return (
    presets.find((preset) => String(preset?.id || "").trim() === defaultId) ||
    presets[0] ||
    null
  );
}

function verificationBadgeConfig(verification) {
  if (!verification) {
    return { label: "unverified", className: "badge-muted" };
  }
  if (verification.ok) {
    return { label: "verified", className: "badge-success" };
  }
  return { label: "verify failed", className: "badge-danger" };
}

function buildVerificationMetaMarkup(verification) {
  if (!verification) {
    const presets = verificationPresets();
    const presetSummary = presets.length
      ? `Available presets: ${presets.map((preset) => preset.short_label || preset.label || "Verify").join(" | ")}`
      : "No verification presets were detected for this workspace yet.";
    return `
      <p class="context-label">verification</p>
      <div class="muted patch-summary">No verification output is attached to this change yet.</div>
      <div class="muted verification-note">${escapeHtml(presetSummary)}</div>
    `;
  }
  const badge = verificationBadgeConfig(verification);
  const results = Array.isArray(verification.results) ? verification.results : [];
  const commandCards = results.length
    ? results.map((result) => {
      const commandBadge = verificationBadgeConfig(result.ok ? { ok: true } : { ok: false });
      const outputSegments = [];
      if (result.stdout) {
        outputSegments.push(`stdout\n${result.stdout.trimEnd()}`);
      }
      if (result.stderr) {
        outputSegments.push(`stderr\n${result.stderr.trimEnd()}`);
      }
      if (result.timed_out) {
        outputSegments.push("timed out");
      }
      const outputText = outputSegments.length ? outputSegments.join("\n\n") : "No output.";
      return `
        <div class="verification-command-card">
          <div class="patch-header">
            <p class="context-label">${escapeHtml(result.command || "command")}</p>
            <span class="approval-badges">
              <span class="badge ${escapeHtml(commandBadge.className)}">${escapeHtml(commandBadge.label)}</span>
              <span class="badge badge-muted">${escapeHtml(String(result.returncode ?? 0))}</span>
            </span>
          </div>
          <div class="muted verification-note">${escapeHtml(result.cwd || ".")}</div>
          <pre class="diff-output verification-output">${escapeHtml(outputText)}</pre>
        </div>
      `;
    }).join("")
    : `<div class="muted verification-note">No verification command output was captured.</div>`;
  return `
    <p class="context-label">verification</p>
    <div class="verification-status-row">
      <span class="badge ${escapeHtml(badge.className)}">${escapeHtml(badge.label)}</span>
      <span class="badge badge-muted">${escapeHtml(verification.label || "Verification")}</span>
      <span class="muted verification-note">${escapeHtml(formatTimestamp(verification.created_at))}</span>
    </div>
    <div class="muted patch-summary">${escapeHtml(verification.summary || "")}</div>
    <div class="verification-command-list">${commandCards}</div>
  `;
}

function renderAppliedChanges(changes) {
  state.workspace.appliedChanges = changes;
  elements.changeHistoryList.innerHTML = "";
  elements.historyCount.textContent = `${changes.length} applied`;
  if (!changes.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No applied changes yet.";
    elements.changeHistoryList.appendChild(item);
    return;
  }
  for (const change of changes) {
    const item = document.createElement("div");
    item.className = `context-item patch-item change-item${
      state.workspace.selectedChange?.kind === "applied" &&
      state.workspace.selectedChange?.id === change.id
        ? " active"
        : ""
    }`;
    const rollbackLabel = change.rollback_ready ? "Roll Back" : "Stale";
    const verificationBadge = verificationBadgeConfig(change.verification || null);
    const verificationSummary = change.verification?.summary
      ? `<div class="muted verification-note">${escapeHtml(change.verification.summary)}</div>`
      : `<div class="muted verification-note">No verification stored yet.</div>`;
    item.innerHTML = `
      <div class="patch-header">
        <p class="context-label">${escapeHtml(change.path || "change")}</p>
        <span class="approval-badges">
          <span class="badge badge-muted">${escapeHtml(change.operation || "edit")}</span>
          <span class="badge badge-muted">${escapeHtml(change.source || "api")}</span>
          <span class="badge ${escapeHtml(verificationBadge.className)}">${escapeHtml(verificationBadge.label)}</span>
        </span>
      </div>
      <div class="muted patch-summary">${escapeHtml(change.summary || "")}</div>
      ${verificationSummary}
      <div class="muted change-timestamp">${escapeHtml(formatTimestamp(change.created_at))}</div>
      <div class="patch-actions">
        <button type="button" class="secondary-button" data-action="inspect">Inspect</button>
        <button
          type="button"
          class="secondary-button${change.rollback_ready ? "" : " danger-button"}"
          data-action="rollback"
          ${change.rollback_ready ? "" : "disabled"}
        >
          ${rollbackLabel}
        </button>
      </div>
    `;
    item.addEventListener("click", (event) => {
      if (event.target.closest("button")) {
        return;
      }
      setSelectedChange({ kind: "applied", id: change.id });
    });
    const inspectButton = item.querySelector('[data-action="inspect"]');
    const rollbackButton = item.querySelector('[data-action="rollback"]');
    inspectButton.addEventListener("click", () => setSelectedChange({ kind: "applied", id: change.id }));
    if (change.rollback_ready) {
      rollbackButton.addEventListener("click", () => rollbackAppliedChange(change.id, rollbackButton));
    }
    elements.changeHistoryList.appendChild(item);
  }
}

function syncSelectedChange() {
  const selected = state.workspace.selectedChange;
  if (selected) {
    const current = lookupSelectedChange(selected);
    if (current) {
      setSelectedChange({ kind: current.kind, id: current.id });
      return;
    }
  }
  const nextPatch = state.workspace.pendingPatches[0];
  if (nextPatch) {
    setSelectedChange({ kind: "pending", id: nextPatch.id });
    return;
  }
  const nextChange = state.workspace.appliedChanges[0];
  if (nextChange) {
    setSelectedChange({ kind: "applied", id: nextChange.id });
    return;
  }
  renderSelectedChange(null);
}

function lookupSelectedChange(selection) {
  if (!selection) {
    return null;
  }
  if (selection.kind === "pending") {
    const patch = state.workspace.pendingPatches.find((item) => item.id === selection.id);
    return patch ? { kind: "pending", ...patch } : null;
  }
  if (selection.kind === "applied") {
    const change = state.workspace.appliedChanges.find((item) => item.id === selection.id);
    return change ? { kind: "applied", ...change } : null;
  }
  return null;
}

function setSelectedChange(selection) {
  const resolved = lookupSelectedChange(selection);
  if (!resolved) {
    state.workspace.selectedChange = null;
    state.workspace.selectedPatchLine = null;
    renderSelectedChange(null);
    return;
  }
  if (
    resolved.kind !== "pending" ||
    state.workspace.selectedChange?.kind !== "pending" ||
    state.workspace.selectedChange?.id !== resolved.id
  ) {
    state.workspace.selectedPatchLine = null;
  }
  state.workspace.selectedChange = { kind: resolved.kind, id: resolved.id };
  renderPendingPatches(state.workspace.pendingPatches);
  renderAppliedChanges(state.workspace.appliedChanges);
  renderSelectedChange(resolved);
}

function renderSelectedChange(change) {
  state.workspace.selectedChange = change ? { kind: change.kind, id: change.id } : null;
  state.workspace.selectedChangeToken = change ? `${change.kind}:${change.id}` : null;
  elements.changeInspectorMeta.innerHTML = "";
  elements.changeInspectorActions.innerHTML = "";
  if (!change) {
    elements.changeInspectorDiff.textContent =
      "Select a pending patch or applied change to inspect its diff.";
    elements.changeInspectorContent.textContent =
      "Select a pending patch or applied change to inspect the current file.";
    state.workspace.selectedPatchLine = null;
    return;
  }

  const meta = document.createElement("div");
  meta.className = "context-item";
  const verificationBadge = change.kind === "applied"
    ? verificationBadgeConfig(change.verification || null)
    : null;
  const statusBadge = change.kind === "pending"
    ? "Pending approval"
    : change.rollback_ready
      ? "Rollback ready"
      : "Superseded";
  meta.innerHTML = `
    <p class="context-label">${escapeHtml(change.kind === "pending" ? "pending patch" : "applied change")}</p>
    <div class="change-meta-grid">
      <div><strong>${escapeHtml(change.path || "")}</strong></div>
      <div class="muted">${escapeHtml(change.summary || "")}</div>
      <div class="change-badge-row">
        <span class="badge badge-muted">${escapeHtml(change.operation || "edit")}</span>
        <span class="badge badge-muted">${escapeHtml(change.source || "api")}</span>
        <span class="badge badge-muted">${escapeHtml(statusBadge)}</span>
        ${verificationBadge ? `<span class="badge ${escapeHtml(verificationBadge.className)}">${escapeHtml(verificationBadge.label)}</span>` : ""}
      </div>
      <div class="muted">${escapeHtml(formatTimestamp(change.created_at))}</div>
    </div>
  `;
  elements.changeInspectorMeta.appendChild(meta);

  const openButton = document.createElement("button");
  openButton.type = "button";
  openButton.className = "secondary-button";
  openButton.textContent = "Open In Review";
  openButton.addEventListener("click", async () => {
    if (!change.path) {
      return;
    }
    await selectChangedFile(change.path, { refreshEditor: true });
    elements.changedFileEditor.scrollIntoView({ block: "nearest", behavior: "smooth" });
  });
  elements.changeInspectorActions.appendChild(openButton);

  if (change.kind === "pending") {
    const patchApproval = state.approvals.find(
      (approval) => approval.kind === "patch" && approval.id === change.id
    );
    const defaultPreset = defaultVerificationPreset();
    const applyButton = document.createElement("button");
    applyButton.type = "button";
    applyButton.className = "secondary-button";
    applyButton.textContent = patchApproval?.resume_available ? "Approve & Resume" : "Apply";
    const applyVerifyButton = !patchApproval?.resume_available && defaultPreset
      ? document.createElement("button")
      : null;
    const rejectButton = document.createElement("button");
    rejectButton.type = "button";
    rejectButton.className = "secondary-button danger-button";
    rejectButton.textContent = patchApproval?.resume_available ? "Reject & Continue" : "Reject";
    if (patchApproval?.resume_available) {
      applyButton.addEventListener("click", () => handleApprovalDecision(change.id, true, applyButton));
      rejectButton.addEventListener("click", () => handleApprovalDecision(change.id, false, rejectButton));
    } else {
      applyButton.addEventListener("click", () => applyPendingPatch(change.id, applyButton));
      if (applyVerifyButton && defaultPreset) {
        applyVerifyButton.type = "button";
        applyVerifyButton.className = "secondary-button";
        applyVerifyButton.textContent = `Apply + ${defaultPreset.short_label || "Verify"}`;
        applyVerifyButton.addEventListener("click", () =>
          applyPendingPatch(change.id, applyVerifyButton, defaultPreset.id)
        );
      }
      rejectButton.addEventListener("click", () => rejectPendingPatch(change.id, rejectButton));
    }
    elements.changeInspectorActions.appendChild(applyButton);
    if (applyVerifyButton) {
      elements.changeInspectorActions.appendChild(applyVerifyButton);
    }
    elements.changeInspectorActions.appendChild(rejectButton);
    elements.changeInspectorContent.textContent =
      "Select a pending line to tweak it, or inspect the current file below.";
    renderPendingPatchInspector(change, patchApproval);
  } else {
    state.workspace.selectedPatchLine = null;
    const verificationCard = document.createElement("div");
    verificationCard.className = "context-item verification-card";
    verificationCard.innerHTML = buildVerificationMetaMarkup(change.verification || null);
    elements.changeInspectorMeta.appendChild(verificationCard);
    const presets = verificationPresets();
    for (const preset of presets) {
      const verifyButton = document.createElement("button");
      verifyButton.type = "button";
      verifyButton.className = "secondary-button";
      verifyButton.textContent = change.verification
        ? `Re-Run ${preset.short_label || preset.label || "Verify"}`
        : `Run ${preset.short_label || preset.label || "Verify"}`;
      verifyButton.addEventListener("click", () =>
        verifyAppliedChange(change.id, preset.id, verifyButton)
      );
      elements.changeInspectorActions.appendChild(verifyButton);
    }
    const rollbackButton = document.createElement("button");
    rollbackButton.type = "button";
    rollbackButton.className = `secondary-button${change.rollback_ready ? "" : " danger-button"}`;
    rollbackButton.textContent = change.rollback_ready ? "Roll Back" : "Rollback Unavailable";
    rollbackButton.disabled = !change.rollback_ready;
    if (change.rollback_ready) {
      rollbackButton.addEventListener("click", () => rollbackAppliedChange(change.id, rollbackButton));
    }
    elements.changeInspectorActions.appendChild(rollbackButton);
    elements.changeInspectorDiff.innerHTML = renderDiffMarkup(change.diff || "");
    bindDiffTargets(elements.changeInspectorDiff);
  }
  void loadSelectedChangeFilePreview(change);
}

function renderPendingPatchInspector(change, patchApproval) {
  const hunks = Array.isArray(change.hunks) ? change.hunks : [];
  elements.changeInspectorDiff.innerHTML = "";

  if (!hunks.length) {
    const note = document.createElement("div");
    note.className = "context-item muted";
    note.textContent = change.review_complete
      ? patchApproval?.resume_available
        ? "All hunks have been reviewed. Use the final patch action above to resume the agent."
        : "All hunks have been reviewed."
      : "No hunk details are available for this patch yet.";
    elements.changeInspectorDiff.appendChild(note);
    if (change.diff && !change.review_complete) {
      const fallback = document.createElement("div");
      fallback.className = "diff-viewer";
      fallback.innerHTML = renderDiffMarkup(change.diff);
      elements.changeInspectorDiff.appendChild(fallback);
      bindDiffTargets(elements.changeInspectorDiff);
    }
    return;
  }

  const intro = document.createElement("div");
  intro.className = "context-item muted";
  intro.textContent = "Use hunk actions for broad review, or stage individual line changes inside each hunk.";
  elements.changeInspectorDiff.appendChild(intro);

  let selectedLineContext = null;
  for (const hunk of hunks) {
    const lines = Array.isArray(hunk.lines) ? hunk.lines : [];
    const card = document.createElement("section");
    card.className = "context-item hunk-review-card";
    card.innerHTML = `
      <div class="hunk-review-header">
        <div class="hunk-review-copy">
          <p class="context-label">hunk ${escapeHtml(String((hunk.index ?? 0) + 1))} of ${escapeHtml(String(hunks.length))}</p>
          <p class="muted hunk-review-subtitle">${escapeHtml(hunk.header || "Patch hunk")}</p>
        </div>
        <span class="approval-badges">
          <span class="badge badge-muted">+${escapeHtml(String(hunk.additions ?? 0))}</span>
          <span class="badge badge-muted">-${escapeHtml(String(hunk.deletions ?? 0))}</span>
          <span class="badge badge-muted">${escapeHtml(`${lines.length} line${lines.length === 1 ? "" : "s"}`)}</span>
        </span>
      </div>
      <div class="patch-actions hunk-actions">
        <button type="button" class="secondary-button" data-action="accept-hunk">Accept Hunk</button>
        <button type="button" class="secondary-button danger-button" data-action="reject-hunk">Reject Hunk</button>
      </div>
      <div class="diff-viewer">${renderDiffMarkup(hunk.diff || "")}</div>
      <div class="hunk-line-list"></div>
    `;
    const acceptButton = card.querySelector('[data-action="accept-hunk"]');
    const rejectButton = card.querySelector('[data-action="reject-hunk"]');
    const lineList = card.querySelector(".hunk-line-list");
    acceptButton.addEventListener("click", () =>
      acceptPendingPatchHunk(change.id, hunk.index, acceptButton)
    );
    rejectButton.addEventListener("click", () =>
      rejectPendingPatchHunk(change.id, hunk.index, rejectButton)
    );
    renderHunkLineActions(lineList, change, hunk, lines);
    if (!selectedLineContext) {
      const selectedLine = resolveSelectedPendingPatchLine(change, hunk);
      if (selectedLine) {
        selectedLineContext = { hunk, line: selectedLine };
      }
    }
    bindDiffTargets(card);
    elements.changeInspectorDiff.appendChild(card);
  }

  if (selectedLineContext) {
    renderSelectedPendingLineEditor(
      change,
      selectedLineContext.hunk,
      selectedLineContext.line
    );
  } else if (
    state.workspace.selectedPatchLine &&
    state.workspace.selectedPatchLine.patchId === change.id
  ) {
    state.workspace.selectedPatchLine = null;
  }
}

function renderHunkLineActions(container, change, hunk, lines) {
  container.innerHTML = "";
  if (!lines.length) {
    const empty = document.createElement("div");
    empty.className = "context-item muted";
    empty.textContent = "No individual line actions are available for this hunk.";
    container.appendChild(empty);
    return;
  }

  for (const line of lines) {
    const card = document.createElement("div");
    const active =
      state.workspace.selectedPatchLine?.patchId === change.id &&
      state.workspace.selectedPatchLine?.hunkIndex === hunk.index &&
      state.workspace.selectedPatchLine?.lineIndex === line.index;
    card.className = `line-review-card${active ? " active" : ""}`;
    const beforeLabel = formatLineLabel("old", line.before_line_number);
    const afterLabel = formatLineLabel("new", line.after_line_number);
    card.innerHTML = `
      <div class="line-review-header">
        <div class="line-review-copy">
          <p class="context-label">line ${escapeHtml(String((line.index ?? 0) + 1))} of ${escapeHtml(String(lines.length))}</p>
          <p class="muted line-review-subtitle">${escapeHtml(formatLineActionSummary(line))}</p>
        </div>
        <span class="badge badge-muted">${escapeHtml(line.kind || "change")}</span>
      </div>
      <div class="line-review-grid">
        <div class="line-review-column">
          <p class="context-label">${escapeHtml(beforeLabel)}</p>
          <pre class="agent-step-output line-review-code">${escapeHtml(line.before_text ?? "(no line)")}</pre>
        </div>
        <div class="line-review-column">
          <p class="context-label">${escapeHtml(afterLabel)}</p>
          <pre class="agent-step-output line-review-code">${escapeHtml(line.after_text ?? "(no line)")}</pre>
        </div>
      </div>
      <div class="patch-actions hunk-actions">
        <button type="button" class="secondary-button" data-action="accept-line">Accept Line</button>
        <button type="button" class="secondary-button danger-button" data-action="reject-line">Reject Line</button>
      </div>
      <div class="diff-viewer compact-diff">${renderDiffMarkup(line.diff || "")}</div>
    `;
    card.addEventListener("click", (event) => {
      if (event.target.closest("button")) {
        return;
      }
      setSelectedPendingPatchLine(change.id, hunk.index, line.index);
    });
    const acceptButton = card.querySelector('[data-action="accept-line"]');
    const rejectButton = card.querySelector('[data-action="reject-line"]');
    acceptButton.addEventListener("click", () =>
      acceptPendingPatchLine(change.id, hunk.index, line.index, acceptButton)
    );
    rejectButton.addEventListener("click", () =>
      rejectPendingPatchLine(change.id, hunk.index, line.index, rejectButton)
    );
    bindDiffTargets(card);
    container.appendChild(card);
  }
}

function setSelectedPendingPatchLine(patchId, hunkIndex, lineIndex) {
  state.workspace.selectedPatchLine = { patchId, hunkIndex, lineIndex };
  const current = lookupSelectedChange({ kind: "pending", id: patchId });
  if (current) {
    renderSelectedChange(current);
  }
}

function resolveSelectedPendingPatchLine(change, hunk) {
  if (
    !state.workspace.selectedPatchLine ||
    state.workspace.selectedPatchLine.patchId !== change.id ||
    state.workspace.selectedPatchLine.hunkIndex !== hunk.index
  ) {
    return null;
  }
  return (
    (Array.isArray(hunk.lines) ? hunk.lines : []).find(
      (line) => line.index === state.workspace.selectedPatchLine.lineIndex
    ) || null
  );
}

function renderSelectedPendingLineEditor(change, hunk, line) {
  elements.changeInspectorContent.innerHTML = `
    <div class="line-edit-shell">
      <div class="line-edit-header">
        <div class="line-edit-copy">
          <p class="context-label">selected pending line</p>
          <p class="muted line-review-subtitle">${escapeHtml(
            `${change.path || "file"} · hunk ${(hunk.index ?? 0) + 1} · line ${(line.index ?? 0) + 1}`
          )}</p>
        </div>
        <span class="badge badge-muted">${escapeHtml(line.kind || "change")}</span>
      </div>
      <div class="line-edit-grid">
        <div class="line-edit-column">
          <p class="context-label">${escapeHtml(formatLineLabel("old", line.before_line_number))}</p>
          <textarea class="line-edit-textarea" data-role="before-editor" readonly>${escapeHtml(
            line.before_text ?? ""
          )}</textarea>
        </div>
        <div class="line-edit-column">
          <p class="context-label">${escapeHtml(formatLineLabel("new", line.after_line_number))}</p>
          <textarea class="line-edit-textarea" data-role="after-editor" spellcheck="false">${escapeHtml(
            line.after_text ?? ""
          )}</textarea>
        </div>
      </div>
      <div class="patch-actions hunk-actions">
        <button type="button" class="secondary-button" data-action="save-line">Save Line Draft</button>
        <button type="button" class="secondary-button" data-action="accept-line-draft">Accept Edited Line</button>
        <button type="button" class="secondary-button danger-button" data-action="reset-line">Reset</button>
      </div>
      <div class="line-draft-preview-shell" data-role="draft-preview-shell">
        <div class="line-draft-status">
          <div class="line-draft-copy">
            <p class="context-label" data-role="draft-preview-title">current pending patch</p>
            <p class="muted line-review-subtitle" data-role="draft-preview-detail">
              Edit the new-line text to preview the updated patch before saving.
            </p>
          </div>
          <span class="badge badge-muted" data-role="draft-preview-badge">saved</span>
        </div>
        <div class="diff-viewer compact-diff line-draft-preview" data-role="draft-preview-diff"></div>
      </div>
    </div>
  `;
  const afterEditor = elements.changeInspectorContent.querySelector('[data-role="after-editor"]');
  const saveButton = elements.changeInspectorContent.querySelector('[data-action="save-line"]');
  const acceptButton = elements.changeInspectorContent.querySelector('[data-action="accept-line-draft"]');
  const resetButton = elements.changeInspectorContent.querySelector('[data-action="reset-line"]');
  const previewShell = elements.changeInspectorContent.querySelector('[data-role="draft-preview-shell"]');
  const previewTitle = elements.changeInspectorContent.querySelector('[data-role="draft-preview-title"]');
  const previewDetail = elements.changeInspectorContent.querySelector('[data-role="draft-preview-detail"]');
  const previewBadge = elements.changeInspectorContent.querySelector('[data-role="draft-preview-badge"]');
  const previewDiff = elements.changeInspectorContent.querySelector('[data-role="draft-preview-diff"]');
  const syncDraftPreview = () => {
    const preview = describePendingLineDraft(line, afterEditor.value);
    previewTitle.textContent = preview.title;
    previewDetail.textContent = preview.detail;
    previewBadge.textContent = preview.badge;
    previewBadge.className = `badge ${preview.badgeClass}`;
    previewShell.className = `line-draft-preview-shell${preview.dirty ? " is-dirty" : ""}${preview.invalid ? " is-invalid" : ""}`;
    previewDiff.innerHTML = renderDiffMarkup(preview.diff);
    bindDiffTargets(previewDiff);
    saveButton.disabled = preview.invalid;
    acceptButton.disabled = preview.invalid;
    resetButton.disabled = !preview.dirty;
  };
  afterEditor.addEventListener("input", syncDraftPreview);
  saveButton.addEventListener("click", () =>
    savePendingPatchLineEdit(change.id, hunk.index, line.index, afterEditor.value, saveButton)
  );
  acceptButton.addEventListener("click", () =>
    acceptEditedPendingPatchLine(change.id, hunk.index, line.index, line.after_text ?? "", afterEditor.value, acceptButton)
  );
  resetButton.addEventListener("click", () => {
    afterEditor.value = line.after_text ?? "";
    syncDraftPreview();
    afterEditor.focus();
  });
  syncDraftPreview();
}

function describePendingLineDraft(line, draftText) {
  const persistedText = line.after_text ?? "";
  const dirty = draftText !== persistedText;
  const invalid = /[\r\n]/.test(draftText);
  if (invalid) {
    return {
      dirty: true,
      invalid: true,
      title: "unsaved draft needs cleanup",
      detail: "Line edits must stay on one line. Remove the line break before saving or accepting this draft.",
      badge: "single line only",
      badgeClass: "line-draft-badge-warning",
      diff: buildPendingLineDraftDiff(line, draftText),
    };
  }
  if (!dirty) {
    return {
      dirty: false,
      invalid: false,
      title: "current pending patch",
      detail: "Edit the new-line text to preview the updated patch before saving.",
      badge: "saved",
      badgeClass: "badge-muted",
      diff: line.diff || buildPendingLineDraftDiff(line, persistedText),
    };
  }
  const revertsChange = (line.before_text ?? "") === draftText;
  return {
    dirty: true,
    invalid: false,
    title: revertsChange ? "unsaved draft removes this line change" : "unsaved draft preview",
    detail: revertsChange
      ? "Saving this draft would clear the current line-level change from the pending patch."
      : "This mini diff shows the exact line-level patch that would be saved from the current draft.",
    badge: revertsChange ? "removes change" : "unsaved draft",
    badgeClass: revertsChange ? "line-draft-badge-warning" : "line-draft-badge-live",
    diff: buildPendingLineDraftDiff(line, draftText),
  };
}

function buildPendingLineDraftDiff(line, draftText) {
  const beforeText = line.before_text ?? "";
  const beforeNumber = resolvePendingLineNumber(line.before_line_number, line.after_line_number);
  const afterNumber = resolvePendingLineNumber(line.after_line_number, line.before_line_number);
  const hasBefore = line.before_line_number !== null && line.before_line_number !== undefined;
  const hasAfter = draftText !== "";
  const header = `@@ -${beforeNumber},${hasBefore ? 1 : 0} +${afterNumber},${hasAfter ? 1 : 0} @@`;
  if (!hasBefore && !hasAfter) {
    return `${header}\n No line change remains`;
  }
  if (hasBefore && hasAfter && beforeText === draftText) {
    return `${header}\n ${formatPendingLinePreviewText(draftText)}`;
  }
  const rows = [header];
  if (hasBefore) {
    rows.push(`-${formatPendingLinePreviewText(beforeText)}`);
  }
  if (hasAfter) {
    rows.push(`+${formatPendingLinePreviewText(draftText)}`);
  }
  return rows.join("\n");
}

function resolvePendingLineNumber(primary, fallback) {
  const candidates = [primary, fallback, 1];
  for (const candidate of candidates) {
    const number = Number(candidate);
    if (Number.isFinite(number) && number > 0) {
      return number;
    }
  }
  return 1;
}

function formatPendingLinePreviewText(value) {
  return String(value ?? "").replace(/\r/g, "\\r").replace(/\n/g, "\\n");
}

function renderChangeInspectorFilePreview(payload) {
  const header = `${payload.path} (${payload.total_lines || 0} lines)`;
  elements.changeInspectorContent.innerHTML = `
    <p class="context-label">current file</p>
    <div class="muted line-review-subtitle">${escapeHtml(header)}</div>
    <pre class="agent-step-output line-review-code file-preview-code">${escapeHtml(
      payload.content || ""
    )}</pre>
  `;
}

async function loadSelectedChangeFilePreview(change) {
  if (!change?.path) {
    elements.changeInspectorContent.textContent =
      "Select a pending patch or applied change to inspect the current file.";
    return;
  }
  const token = `${change.kind}:${change.id}`;
  elements.changeInspectorContent.textContent = `Loading ${change.path}...`;
  const sessionId = state.sessionId || "scratchpad";
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/file?path=${encodeURIComponent(change.path)}`
  );
  const payload = await response.json();
  if (state.workspace.selectedChangeToken !== token) {
    return;
  }
  if (!payload.ok) {
    elements.changeInspectorContent.textContent =
      payload.error || "Unable to read the current file contents.";
    return;
  }
  if (
    change.kind === "pending" &&
    state.workspace.selectedPatchLine &&
    state.workspace.selectedPatchLine.patchId === change.id
  ) {
    const refreshed = lookupSelectedChange({ kind: "pending", id: change.id });
    if (!refreshed) {
      return;
    }
    for (const hunk of refreshed.hunks || []) {
      const selectedLine = resolveSelectedPendingPatchLine(refreshed, hunk);
      if (selectedLine) {
        renderSelectedPendingLineEditor(refreshed, hunk, selectedLine);
        return;
      }
    }
  }
  renderChangeInspectorFilePreview(payload);
}

function renderWorkspaceReview(review) {
  const previousSelection = state.workspace.selectedChangedFile;
  state.workspace.review = review;
  elements.reviewSummary.innerHTML = "";
  elements.changedFileList.innerHTML = "";
  if (!review || review.ok === false) {
    state.workspace.selectedChangedFile = null;
    state.workspace.reviewDiffIndex = {};
    elements.reviewCount.textContent = "clean";
    resetSelectedReviewPane({
      fileMessage: "Select a changed file to inspect or edit it.",
      diffMessage: "Select a changed file to focus its diff.",
    });
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No workspace review yet.";
    elements.reviewSummary.appendChild(item);
    return;
  }
  const changedFiles = review.changed_files || [];
  const changedEntries = review.changed_entries || [];
  const normalizedEntries = changedEntries.length
    ? changedEntries
    : changedFiles.map((path) => ({
        path,
        status: "?",
        source: "workspace",
        summary: path,
      }));
  state.workspace.reviewDiffIndex = buildReviewDiffIndex(review);
  elements.reviewCount.textContent = changedFiles.length
    ? `${changedFiles.length} changed`
    : "clean";

  const summaryItem = document.createElement("div");
  summaryItem.className = "context-item";
  summaryItem.innerHTML = `
    <p class="context-label">summary</p>
    <pre class="agent-step-output">${escapeHtml(review.summary || "Workspace looks clean.")}</pre>
  `;
  elements.reviewSummary.appendChild(summaryItem);

  const diffStatItem = document.createElement("div");
  diffStatItem.className = "context-item";
  diffStatItem.innerHTML = `
    <p class="context-label">diff stat</p>
    <pre class="agent-step-output">${escapeHtml(review.diff_stat || "No diff stat available.")}</pre>
  `;
  elements.reviewSummary.appendChild(diffStatItem);

  const selectedPath =
    normalizedEntries.find((entry) => entry.path === previousSelection)?.path ||
    normalizedEntries[0]?.path ||
    null;
  state.workspace.selectedChangedFile = selectedPath;
  renderChangedFiles(normalizedEntries, selectedPath);
  if (selectedPath) {
    void selectChangedFile(selectedPath, { refreshEditor: true });
  } else {
    resetSelectedReviewPane({
      fileMessage: "Select a changed file to inspect or edit it.",
      diffMessage: review.diff || "No unified diff yet.",
    });
  }
}

function updateSandboxStatus(sandbox) {
  const backend = sandbox?.active_backend || sandbox?.backend || "backend";
  elements.sandboxBackendBadge.textContent = backend;
  const detail =
    sandbox?.session?.detail ||
    sandbox?.container?.detail ||
    sandbox?.detail ||
    (sandbox?.status ? `Container status is ${sandbox.status}.` : "");
  const fallback = sandbox?.fallback?.used ? ` Fallback: ${sandbox.fallback.reason}` : "";
  elements.sandboxStatus.textContent =
    detail || fallback
      ? `${detail || "Sandbox ready."}${fallback}`
      : "Shell execution uses the persistent session Docker workspace when available.";
}

function appendAgentStep(payload) {
  const node = document.createElement("div");
  node.className = "context-item";
  const title = payload.kind || "step";
  const label = payload.tool ? `${title} · ${payload.tool}` : title;
  let body = "";
  if (payload.content) {
    body = String(payload.content);
  } else if (payload.args) {
    body = JSON.stringify(payload.args);
  }
  const usePre = body.includes("\n") || payload.kind === "command_chunk" || payload.kind === "command_start";
  const bodyHtml = usePre
    ? `<pre class="agent-step-output">${escapeHtml(body)}</pre>`
    : `<div class="muted">${escapeHtml(body)}</div>`;
  node.innerHTML = `
    <p class="context-label">step ${escapeHtml(payload.step)} · ${escapeHtml(label)}</p>
    ${bodyHtml}
  `;
  elements.agentTrace.appendChild(node);
}

async function applyPendingPatch(patchId, button, verifyPresetId = "") {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patchId)}/apply`,
    { method: "POST" }
  );
  const payload = await response.json();
  await refreshWorkspace();
  if (!payload.ok && payload.error) {
    elements.changeInspectorContent.textContent = payload.error;
    return;
  }
  if (payload.change?.id) {
    if (verifyPresetId) {
      await verifyAppliedChange(payload.change.id, verifyPresetId, button, { buttonAlreadyDisabled: true });
      return;
    }
    setSelectedChange({ kind: "applied", id: payload.change.id });
  }
}

async function verifyAppliedChange(changeId, presetId, button, options = {}) {
  const sessionId = state.sessionId || "scratchpad";
  const keepDisabled = options.buttonAlreadyDisabled === true;
  if (!keepDisabled) {
    button.disabled = true;
  }
  const preset = verificationPresets().find((entry) => String(entry?.id || "") === String(presetId || ""));
  const presetLabel = preset?.label || preset?.short_label || "verification";
  elements.changeInspectorContent.textContent = `Running ${presetLabel}...`;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/changes/${encodeURIComponent(changeId)}/verify`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preset_id: presetId || null,
      }),
    }
  );
  const payload = await response.json();
  await refreshWorkspace();
  if (!keepDisabled) {
    button.disabled = false;
  }
  if (!payload.ok) {
    elements.changeInspectorContent.textContent =
      payload.error || `Unable to run ${presetLabel}.`;
    return;
  }
  if (payload.change?.id) {
    setSelectedChange({ kind: "applied", id: payload.change.id });
  }
}

async function acceptPendingPatchHunk(patchId, hunkIndex, button) {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patchId)}/hunks/${encodeURIComponent(hunkIndex)}/accept`,
    { method: "POST" }
  );
  const payload = await response.json();
  await refreshWorkspace();
  if (!payload.ok && payload.error) {
    elements.changeInspectorContent.textContent = payload.error;
    return;
  }
  if (payload.patch?.id) {
    setSelectedChange({ kind: "pending", id: payload.patch.id });
    return;
  }
  if (payload.change?.id) {
    setSelectedChange({ kind: "applied", id: payload.change.id });
  }
}

async function acceptPendingPatchLine(patchId, hunkIndex, lineIndex, button) {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patchId)}/hunks/${encodeURIComponent(hunkIndex)}/lines/${encodeURIComponent(lineIndex)}/accept`,
    { method: "POST" }
  );
  const payload = await response.json();
  await refreshWorkspace();
  if (!payload.ok && payload.error) {
    elements.changeInspectorContent.textContent = payload.error;
    return;
  }
  if (payload.patch?.id) {
    setSelectedChange({ kind: "pending", id: payload.patch.id });
    return;
  }
  if (payload.change?.id) {
    setSelectedChange({ kind: "applied", id: payload.change.id });
  }
}

async function savePendingPatchLineEdit(patchId, hunkIndex, lineIndex, afterText, button) {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patchId)}/hunks/${encodeURIComponent(hunkIndex)}/lines/${encodeURIComponent(lineIndex)}/edit`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ after_text: afterText }),
    }
  );
  const payload = await response.json();
  if (!payload.ok && payload.error) {
    elements.changeInspectorContent.textContent = payload.error;
    button.disabled = false;
    return;
  }
  state.workspace.selectedPatchLine = { patchId, hunkIndex, lineIndex };
  await refreshWorkspace();
  if (payload.patch?.id) {
    setSelectedChange({ kind: "pending", id: payload.patch.id });
  }
}

async function acceptEditedPendingPatchLine(
  patchId,
  hunkIndex,
  lineIndex,
  originalAfterText,
  nextAfterText,
  button
) {
  button.disabled = true;
  if (nextAfterText !== originalAfterText) {
    const sessionId = state.sessionId || "scratchpad";
    const editResponse = await fetch(
      `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patchId)}/hunks/${encodeURIComponent(hunkIndex)}/lines/${encodeURIComponent(lineIndex)}/edit`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ after_text: nextAfterText }),
      }
    );
    const editPayload = await editResponse.json();
    if (!editPayload.ok && editPayload.error) {
      elements.changeInspectorContent.textContent = editPayload.error;
      button.disabled = false;
      return;
    }
    const stillPending =
      editPayload.patch?.id === patchId ||
      (editPayload.pending_patches || []).some((patch) => patch.id === patchId);
    if (!stillPending) {
      state.workspace.selectedPatchLine = null;
      await refreshWorkspace();
      return;
    }
  }
  await acceptPendingPatchLine(patchId, hunkIndex, lineIndex, button);
}

async function rejectPendingPatch(patchId, button) {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patchId)}/reject`,
    { method: "POST" }
  );
  await refreshWorkspace();
}

async function rejectPendingPatchHunk(patchId, hunkIndex, button) {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patchId)}/hunks/${encodeURIComponent(hunkIndex)}/reject`,
    { method: "POST" }
  );
  const payload = await response.json();
  await refreshWorkspace();
  if (!payload.ok && payload.error) {
    elements.changeInspectorContent.textContent = payload.error;
    return;
  }
  if (payload.patch?.id) {
    setSelectedChange({ kind: "pending", id: payload.patch.id });
  }
}

async function rejectPendingPatchLine(patchId, hunkIndex, lineIndex, button) {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patchId)}/hunks/${encodeURIComponent(hunkIndex)}/lines/${encodeURIComponent(lineIndex)}/reject`,
    { method: "POST" }
  );
  const payload = await response.json();
  await refreshWorkspace();
  if (!payload.ok && payload.error) {
    elements.changeInspectorContent.textContent = payload.error;
    return;
  }
  if (payload.patch?.id) {
    setSelectedChange({ kind: "pending", id: payload.patch.id });
  }
}

async function rollbackAppliedChange(changeId, button) {
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/changes/${encodeURIComponent(changeId)}/rollback`,
    { method: "POST" }
  );
  const payload = await response.json();
  await refreshWorkspace();
  if (payload.change?.id) {
    setSelectedChange({ kind: "applied", id: payload.change.id });
    return;
  }
  if (payload.error) {
    elements.changeInspectorContent.textContent = payload.error;
  }
}

async function handleApprovalDecision(approvalOrId, approved, button) {
  const approval =
    typeof approvalOrId === "string"
      ? state.approvals.find((candidate) => candidate.id === approvalOrId) || { id: approvalOrId }
      : approvalOrId;
  const approvalId = String(approval?.id || "").trim();
  if (!approvalId) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  button.disabled = true;
  if (approval.run_id) {
    state.activeRunId = approval.run_id;
    await loadActiveRun({ replayStream: true, preserveEvents: false });
  }
  const assistantNode = appendMessage("assistant", "");
  const assistantBody = assistantNode.querySelector(".message-body");
  const action = approved ? "approve" : "reject";
  const response = await fetch(
    `/api/agent/${encodeURIComponent(sessionId)}/approvals/${encodeURIComponent(approvalId)}/${action}`,
    { method: "POST" }
  );

  await consumeEventStream(response, {
    meta(payload) {
      if (payload.session_id) {
        state.sessionId = payload.session_id;
      }
      updateMeta(payload);
      if (payload.run_id) {
        trackRunMeta(payload);
      }
    },
    agent_step(payload) {
      appendAgentStep(payload);
      noteRunEvent("agent_step", payload);
    },
    token(payload) {
      assistantBody.textContent += payload.content;
      assistantNode.scrollIntoView({ block: "end", behavior: "smooth" });
      noteRunEvent("token", payload);
    },
    async done(payload) {
      noteRunEvent("done", payload);
      assistantBody.textContent =
        assistantBody.textContent.trim() || (approved ? "Approval processed." : "Rejection processed.");
      await loadSessions();
      await loadMemory();
      await refreshWorkspace();
      await loadRuns();
      await loadRunAudit();
    },
  });
}

function renderDiffMarkup(diff) {
  const text = diff && diff.trim()
    ? diff
    : "Select a pending patch or applied change to inspect its diff.";
  return buildDiffLines(text)
    .map((line) => {
      const left = line.leftNumber === "" ? "" : String(line.leftNumber);
      const right = line.rightNumber === "" ? "" : String(line.rightNumber);
      const targetAttr = Number.isFinite(line.targetLine)
        ? ` data-target-line="${line.targetLine}"`
        : "";
      return `
        <span class="diff-line diff-line-${line.kind}"${targetAttr}>
          <span class="diff-gutter">${escapeHtml(left || " ")}</span>
          <span class="diff-gutter">${escapeHtml(right || " ")}</span>
          <span class="diff-code">${escapeHtml(line.text || " ")}</span>
        </span>
      `;
    })
    .join("");
}

function buildDiffLines(text) {
  const rows = [];
  let leftLine = null;
  let rightLine = null;
  for (const rawLine of text.split("\n")) {
    const line = rawLine || "";
    if (line.startsWith("+++ ") || line.startsWith("--- ") || line.startsWith("diff --git ")) {
      rows.push({ kind: "file", leftNumber: "", rightNumber: "", text: line, targetLine: null });
      continue;
    }
    if (line.startsWith("@@")) {
      const match = line.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
      leftLine = match ? Number(match[1]) : null;
      rightLine = match ? Number(match[2]) : null;
      rows.push({ kind: "meta", leftNumber: "", rightNumber: "", text: line, targetLine: null });
      continue;
    }
    if (line.startsWith("+")) {
      rows.push({
        kind: "add",
        leftNumber: "",
        rightNumber: rightLine ?? "",
        text: line,
        targetLine: rightLine,
      });
      if (rightLine !== null) {
        rightLine += 1;
      }
      continue;
    }
    if (line.startsWith("-")) {
      rows.push({
        kind: "remove",
        leftNumber: leftLine ?? "",
        rightNumber: "",
        text: line,
        targetLine: leftLine,
      });
      if (leftLine !== null) {
        leftLine += 1;
      }
      continue;
    }
    rows.push({
      kind: "context",
      leftNumber: leftLine ?? "",
      rightNumber: rightLine ?? "",
      text: line,
      targetLine: rightLine ?? leftLine,
    });
    if (leftLine !== null) {
      leftLine += 1;
    }
    if (rightLine !== null) {
      rightLine += 1;
    }
  }
  return rows;
}

function bindDiffTargets(container) {
  for (const line of container.querySelectorAll("[data-target-line]")) {
    line.addEventListener("click", () => {
      const targetLine = Number(line.getAttribute("data-target-line"));
      if (!Number.isFinite(targetLine) || targetLine < 1) {
        return;
      }
      focusEditorLine(targetLine);
    });
  }
}

function focusEditorLine(lineNumber) {
  const textarea = elements.changedFileEditor;
  if (textarea.disabled) {
    return;
  }
  const lines = textarea.value.split("\n");
  let cursor = 0;
  for (let index = 0; index < Math.max(0, lineNumber - 1) && index < lines.length; index += 1) {
    cursor += lines[index].length + 1;
  }
  textarea.focus();
  textarea.setSelectionRange(cursor, cursor);
  const lineHeight = Number.parseFloat(getComputedStyle(textarea).lineHeight) || 20;
  textarea.scrollTop = Math.max(0, (lineNumber - 2) * lineHeight);
}

function formatTimestamp(value) {
  if (!value) {
    return "just now";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatLineLabel(prefix, value) {
  return value ? `${prefix} line ${value}` : `${prefix} line`;
}

function formatLineActionSummary(line) {
  const before = line.before_line_number ? `L${line.before_line_number}` : "new";
  const after = line.after_line_number ? `L${line.after_line_number}` : "deleted";
  return `${before} -> ${after}`;
}

function renderChangedFiles(changedEntries, selectedPath) {
  elements.changedFileList.innerHTML = "";
  if (!changedEntries.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No changed files.";
    elements.changedFileList.appendChild(item);
    return;
  }
  for (const entry of changedEntries) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `review-file-button${entry.path === selectedPath ? " active" : ""}`;
    button.innerHTML = `
      <span class="review-file-meta">
        <span class="badge badge-muted">${escapeHtml(entry.status || "?")}</span>
        <span class="badge badge-muted">${escapeHtml(entry.source || "workspace")}</span>
      </span>
      <span class="review-file-body">
        <span class="context-label">${escapeHtml(entry.path || "file")}</span>
        <span class="muted">${escapeHtml(entry.summary || entry.path || "")}</span>
      </span>
    `;
    button.addEventListener("click", () => selectChangedFile(entry.path, { refreshEditor: true }));
    elements.changedFileList.appendChild(button);
  }
}

async function selectChangedFile(path, options = {}) {
  const refreshEditor = options.refreshEditor !== false;
  state.workspace.selectedChangedFile = path;
  renderChangedFiles(reviewEntries(), path);
  updateSelectedDiff(path);
  updateSelectedFileChrome(path);
  if (!refreshEditor) {
    return;
  }
  await loadSelectedFile(path);
}

async function loadSelectedFile(path) {
  const sessionId = state.sessionId || "scratchpad";
  elements.changedFileEditor.value = "";
  elements.changedFileEditor.placeholder = `Loading ${path}...`;
  elements.changedFileEditor.disabled = true;
  elements.stageChangedFileButton.disabled = true;
  const response = await fetch(
    `/api/workspace/${encodeURIComponent(sessionId)}/file?path=${encodeURIComponent(path)}`
  );
  const payload = await response.json();
  if (!payload.ok) {
    elements.changedFileEditor.disabled = false;
    elements.stageChangedFileButton.disabled = false;
    elements.changedFileEditor.value = "";
    elements.changedFileEditor.placeholder =
      payload.error || "Unable to read file. You can still draft contents and stage a full-file patch.";
    return;
  }
  elements.changedFileEditor.disabled = false;
  elements.stageChangedFileButton.disabled = false;
  elements.changedFileEditor.placeholder = "Edit the selected file, then stage a review patch.";
  elements.changedFileEditor.value = payload.content || "";
}

function updateSelectedDiff(path) {
  const diffs = state.workspace.reviewDiffIndex[path] || [];
  elements.selectedDiffLabel.textContent = path || "all changes";
  const diffText = diffs.length
    ? diffs.join("\n\n")
    : state.workspace.review?.diff || "No unified diff yet.";
  elements.reviewDiff.innerHTML = renderDiffMarkup(diffText);
  bindDiffTargets(elements.reviewDiff);
}

function updateSelectedFileChrome(path) {
  elements.selectedFileLabel.textContent = path || "none";
  elements.reloadChangedFileButton.disabled = !path;
  const hasPendingPatch = state.workspace.pendingPatches.some((patch) => patch.path === path);
  elements.stageChangedFileButton.textContent = hasPendingPatch
    ? "Replace Review Patch"
    : "Stage Review Patch";
}

function resetSelectedReviewPane({ fileMessage, diffMessage }) {
  elements.selectedFileLabel.textContent = "none";
  elements.selectedDiffLabel.textContent = "all changes";
  elements.changedFileEditor.value = "";
  elements.changedFileEditor.placeholder = fileMessage;
  elements.changedFileEditor.disabled = true;
  elements.reloadChangedFileButton.disabled = true;
  elements.stageChangedFileButton.disabled = true;
  elements.reviewDiff.innerHTML = renderDiffMarkup(diffMessage);
}

async function reloadSelectedChangedFile() {
  if (!state.workspace.selectedChangedFile) {
    return;
  }
  await loadSelectedFile(state.workspace.selectedChangedFile);
}

async function stageSelectedChangedFile() {
  const path = state.workspace.selectedChangedFile;
  if (!path) {
    return;
  }
  const sessionId = state.sessionId || "scratchpad";
  elements.stageChangedFileButton.disabled = true;
  const existingPatches = state.workspace.pendingPatches.filter((patch) => patch.path === path);
  for (const patch of existingPatches) {
    await fetch(
      `/api/workspace/${encodeURIComponent(sessionId)}/patches/${encodeURIComponent(patch.id)}/reject`,
      { method: "POST" }
    );
  }
  await fetch(`/api/workspace/${encodeURIComponent(sessionId)}/patches/write`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      path,
      content: elements.changedFileEditor.value,
    }),
  });
  await refreshWorkspace();
}

function reviewEntries() {
  const changedEntries = state.workspace.review?.changed_entries || [];
  if (changedEntries.length) {
    return changedEntries;
  }
  const changedFiles = state.workspace.review?.changed_files || [];
  return changedFiles.map((path) => ({
    path,
    status: "?",
    source: "workspace",
    summary: path,
  }));
}

function buildReviewDiffIndex(review) {
  const index = {};
  for (const patch of review.pending_patches || []) {
    if (patch?.path && patch?.diff) {
      appendDiffSection(index, patch.path, patch.diff);
    }
  }
  for (const section of splitGitDiffSections(review.git?.diff || "")) {
    appendDiffSection(index, section.path, section.diff);
  }
  return index;
}

function appendDiffSection(index, path, diff) {
  if (!path || !diff) {
    return;
  }
  if (!index[path]) {
    index[path] = [];
  }
  index[path].push(diff.trim());
}

function splitGitDiffSections(text) {
  if (!text) {
    return [];
  }
  const sections = [];
  let currentPath = null;
  let currentLines = [];
  const flush = () => {
    if (!currentPath || !currentLines.length) {
      currentPath = null;
      currentLines = [];
      return;
    }
    sections.push({ path: currentPath, diff: currentLines.join("\n").trim() });
    currentPath = null;
    currentLines = [];
  };
  for (const line of text.split("\n")) {
    if (line.startsWith("diff --git ")) {
      flush();
      const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
      currentPath = match?.[2] || match?.[1] || null;
      currentLines = [line];
      continue;
    }
    if (!currentLines.length) {
      continue;
    }
    if (!currentPath && line.startsWith("+++ b/")) {
      currentPath = line.slice(6).trim();
    }
    currentLines.push(line);
  }
  flush();
  return sections;
}

async function consumeEventStream(response, handlers) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const lines = part.split("\n");
      let eventName = "message";
      let data = "";
      for (const line of lines) {
        if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        }
        if (line.startsWith("data:")) {
          data += line.slice(5).trim();
        }
      }
      if (!data) {
        continue;
      }
      const payload = JSON.parse(data);
      const handler = handlers[eventName];
      if (handler) {
        await handler(payload);
      }
    }
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function formatBytes(value) {
  const size = Number(value) || 0;
  if (size >= 1000 * 1000) {
    return `${(size / (1000 * 1000)).toFixed(1)} MB`;
  }
  if (size >= 1000) {
    return `${(size / 1000).toFixed(1)} KB`;
  }
  return `${size} B`;
}

function tokenizeCommand(input) {
  const tokens = [];
  let current = "";
  let quote = null;
  let escaped = false;
  for (const char of input) {
    if (escaped) {
      current += char;
      escaped = false;
      continue;
    }
    if (char === "\\") {
      escaped = true;
      continue;
    }
    if (quote) {
      if (char === quote) {
        quote = null;
      } else {
        current += char;
      }
      continue;
    }
    if (char === "'" || char === "\"") {
      quote = char;
      continue;
    }
    if (/\s/.test(char)) {
      if (current) {
        tokens.push(current);
        current = "";
      }
      continue;
    }
    current += char;
  }
  if (escaped || quote) {
    return null;
  }
  if (current) {
    tokens.push(current);
  }
  return tokens.length ? tokens : null;
}

async function fileToAttachment(file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch("/api/attachments/parse", {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    return null;
  }
  const payload = await response.json();
  return payload.attachment;
}

function guessMimeType(name) {
  const lower = name.toLowerCase();
  if (lower.endsWith(".md")) return "text/markdown";
  if (lower.endsWith(".txt")) return "text/plain";
  if (lower.endsWith(".json")) return "application/json";
  if (lower.endsWith(".py")) return "text/x-python";
  return "text/plain";
}

boot();
