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

const uiState = {
  focusedSurface: "eval",
  operator: {
    mode: "Guard",
    scope: "Workspace",
    target: "Forge",
    tier: "Guard",
    voiceEnabled: true,
  },
};

let arisBootHydrationPending = false;
let arisTruthSyncPending = false;

const ARIS_HYDRATION_REASON =
  "ARIS is hydrating law, halls, and governed runtime state before admitting a decision.";
const ARIS_TRUTH_SYNC_REASON =
  "ARIS is resolving governed truth before updating the current decision.";
const ARIS_DECISION_FRESHNESS_MS = 15 * 60 * 1000;

const elements = {
  brandName: document.querySelector("#brandName"),
  providerMode: document.querySelector("#providerMode"),
  modelLabel: document.querySelector("#modelLabel"),
  modelRouterSelect: document.querySelector("#modelRouterSelect"),
  applyModelRouterButton: document.querySelector("#applyModelRouterButton"),
  workspaceTitle: document.querySelector("#workspaceTitle"),
  workspaceHeaderMeta: document.querySelector("#workspaceHeaderMeta"),
  workspaceStateBadgeRow: document.querySelector("#workspaceStateBadgeRow"),
  processLoopBadge: document.querySelector("#processLoopBadge"),
  processLoopHint: document.querySelector("#processLoopHint"),
  processLoopBar: document.querySelector("#processLoopBar"),
  arisRouteCopy: document.querySelector("#arisRouteCopy"),
  evalGate: document.querySelector("#evalGate"),
  evalGateTimestamp: document.querySelector("#evalGateTimestamp"),
  evalGateReason: document.querySelector("#evalGateReason"),
  evalGateTraceButton: document.querySelector("#evalGateTraceButton"),
  evalGateStateStrip: document.querySelector("#evalGateStateStrip"),
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
  taskBoardBadge: document.querySelector("#taskBoardBadge"),
  taskBoardList: document.querySelector("#taskBoardList"),
  taskBoardMeta: document.querySelector("#taskBoardMeta"),
  logsStripBadge: document.querySelector("#logsStripBadge"),
  logsStripList: document.querySelector("#logsStripList"),
  arisSoftKillButton: document.querySelector("#arisSoftKillButton"),
  arisHardKillButton: document.querySelector("#arisHardKillButton"),
  arisResetButton: document.querySelector("#arisResetButton"),
  operatorConsoleBadge: document.querySelector("#operatorConsoleBadge"),
  operatorConsoleSummary: document.querySelector("#operatorConsoleSummary"),
  operatorModeSelect: document.querySelector("#operatorModeSelect"),
  operatorScopeSelect: document.querySelector("#operatorScopeSelect"),
  operatorTargetSelect: document.querySelector("#operatorTargetSelect"),
  operatorTierSelect: document.querySelector("#operatorTierSelect"),
  operatorRunButton: document.querySelector("#operatorRunButton"),
  operatorApproveButton: document.querySelector("#operatorApproveButton"),
  operatorShipButton: document.querySelector("#operatorShipButton"),
  operatorUnlinkButton: document.querySelector("#operatorUnlinkButton"),
  operatorWorkspaceButton: document.querySelector("#operatorWorkspaceButton"),
  operatorApprovalGuardButton: document.querySelector("#operatorApprovalGuardButton"),
  operatorVoiceToggleButton: document.querySelector("#operatorVoiceToggleButton"),
  operatorBugButton: document.querySelector("#operatorBugButton"),
  operatorFeedbackButton: document.querySelector("#operatorFeedbackButton"),
  operatorFeatureButton: document.querySelector("#operatorFeatureButton"),
  operatorFormButton: document.querySelector("#operatorFormButton"),
  chatSurface: document.querySelector("#chatSurface"),
  chatSurfaceMeta: document.querySelector("#chatSurfaceMeta"),
  chatInspectButton: document.querySelector("#chatInspectButton"),
  chatQueueButton: document.querySelector("#chatQueueButton"),
  rightRail: document.querySelector(".right-rail"),
  messageList: document.querySelector("#messageList"),
  emptyState: document.querySelector("#emptyState"),
  sessionList: document.querySelector("#sessionList"),
  sessionCount: document.querySelector("#sessionCount"),
  workspaceRailCount: document.querySelector("#workspaceRailCount"),
  workspaceRailList: document.querySelector("#workspaceRailList"),
  recentTaskRailCount: document.querySelector("#recentTaskRailCount"),
  recentTaskRailList: document.querySelector("#recentTaskRailList"),
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
  arisBootHydrationPending = true;
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
  elements.evalGateTraceButton?.addEventListener("click", () => focusSurface("outcome"));
  elements.arisSoftKillButton?.addEventListener("click", () => triggerArisKill("soft"));
  elements.arisHardKillButton?.addEventListener("click", () => triggerArisKill("hard"));
  elements.arisResetButton?.addEventListener("click", resetArisKillSwitch);
  elements.applyModelRouterButton?.addEventListener("click", applyModelRouterSelection);
  elements.operatorModeSelect?.addEventListener("change", syncOperatorConsoleControls);
  elements.operatorScopeSelect?.addEventListener("change", syncOperatorConsoleControls);
  elements.operatorTargetSelect?.addEventListener("change", previewOperatorTarget);
  elements.operatorTierSelect?.addEventListener("change", syncOperatorConsoleControls);
  elements.operatorRunButton?.addEventListener("click", () => focusSurface(surfaceForOperatorTarget()));
  elements.operatorApproveButton?.addEventListener("click", () => focusSurface("outcome"));
  elements.operatorShipButton?.addEventListener("click", () => focusSurface("review"));
  elements.operatorUnlinkButton?.addEventListener("click", unlinkTaskDraft);
  elements.operatorWorkspaceButton?.addEventListener("click", () => focusSurface("workspace"));
  elements.operatorApprovalGuardButton?.addEventListener("click", applyApprovalGuardMode);
  elements.operatorVoiceToggleButton?.addEventListener("click", toggleOperatorVoice);
  elements.operatorBugButton?.addEventListener("click", prefillBugReport);
  elements.operatorFeedbackButton?.addEventListener("click", prefillFeedbackNote);
  elements.operatorFeatureButton?.addEventListener("click", prefillFeatureRequest);
  elements.operatorFormButton?.addEventListener("click", () => focusSurface("knowledge"));
  elements.chatInspectButton?.addEventListener("click", inspectCurrentSurface);
  elements.chatQueueButton?.addEventListener("click", () => focusSurface("forge"));
  enableOperatorGroupToggles();
  installKeyboardShortcuts();
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
elements.refreshWorkspaceButton.addEventListener("click", () => {
  void refreshWorkspace({ explicitReview: true });
});
  elements.reloadChangedFileButton.addEventListener("click", reloadSelectedChangedFile);
  elements.stageChangedFileButton.addEventListener("click", stageSelectedChangedFile);
  elements.tailRunButton.addEventListener("click", reconnectActiveRun);
  elements.cancelRunButton.addEventListener("click", cancelActiveRun);
  elements.retryRunButton.addEventListener("click", retryActiveRun);
  syncRetrievalValue();
  renderInitialShellState();
  try {
    await Promise.all([loadConfig(), loadSessions(), loadKnowledge(), loadMemory(), loadArisRuntime()]);
  } finally {
    arisBootHydrationPending = false;
    if (!state.aris.status) {
      renderArisStatus(null);
    }
    renderProcessLoopBar();
    syncOperatorConsoleControls();
  }
}

function renderInitialShellState() {
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
  renderTaskBoardDigest();
  renderWorkspaceRail();
  renderRecentTaskRail();
  syncWorkspaceHeaderMeta();
  renderLogsStrip();
  renderProcessLoopBar();
  syncOperatorConsoleControls();
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
  }
  syncExecutionAffordances();
  if (searchConfig.max_results) {
    elements.searchStatus.textContent = `Search up to ${searchConfig.max_results} workspace hits per query.`;
    elements.symbolStatus.textContent = `Symbol tools read up to ${searchConfig.max_results} matching definitions at a time.`;
  }
  if (snapshotConfig.max_total_bytes) {
    elements.snapshotStatus.textContent =
      `Snapshots keep up to ${snapshotConfig.max_snapshots || 0} saves and ${formatBytes(snapshotConfig.max_total_bytes)} per snapshot.`;
  }
  elements.projectStatus.textContent = "Project detection will appear here.";
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

function parseUiTimestamp(value) {
  const text = String(value || "").trim();
  if (!text) {
    return null;
  }
  const timestamp = Date.parse(text);
  return Number.isFinite(timestamp) ? timestamp : null;
}

function arisDecisionFreshnessFloor(status) {
  const startupTimestamp = parseUiTimestamp(status?.kill_switch?.diagnostics?.startup?.initialized_at);
  return Math.max(startupTimestamp || 0, Date.now() - ARIS_DECISION_FRESHNESS_MS);
}

function activeSessionRecord() {
  return state.sessions.find((item) => item.id === state.sessionId) || null;
}

function activeDecisionSessionId() {
  return String(state.sessionId || "scratchpad").trim() || "scratchpad";
}

function decisionMatchesCurrentSession(decision, activeSessionId = activeDecisionSessionId()) {
  if (!decision || typeof decision !== "object") {
    return false;
  }
  if (decision.kind === "runtime_hydration" || decision.kind === "forge_repo_plan") {
    return true;
  }
  const decisionSessionId = String(decision.session_id || "").trim();
  if (!decisionSessionId) {
    return true;
  }
  return decisionSessionId === activeSessionId;
}

function arisCurrentStateFloor(status, activeSession = activeSessionRecord()) {
  const sessionTimestamp = parseUiTimestamp(
    activeSession?.created_at || activeSession?.updated_at
  );
  return Math.max(arisDecisionFreshnessFloor(status), sessionTimestamp || 0);
}

function isRenderableArisDecision(decision, status, options = {}) {
  if (!decision || typeof decision !== "object") {
    return false;
  }
  if (decision.kind === "runtime_hydration") {
    return true;
  }
  const activeSessionId = options.activeSessionId || activeDecisionSessionId();
  const activeSession = options.activeSession || activeSessionRecord();
  if (!decisionMatchesCurrentSession(decision, activeSessionId)) {
    return false;
  }
  const decisionTimestamp = parseUiTimestamp(
    decision.created_at ||
      decision.recorded_at ||
      decision.timestamp
  );
  if (decisionTimestamp == null) {
    return false;
  }
  return decisionTimestamp >= arisCurrentStateFloor(status, activeSession);
}

function resolveLiveArisDecision(status, activity, explicitDecision = null) {
  const activeSession = activeSessionRecord();
  const activeSessionId = activeDecisionSessionId();
  const renderOptions = {
    activeSession,
    activeSessionId,
  };
  if (isRenderableArisDecision(explicitDecision, status, renderOptions)) {
    return explicitDecision;
  }
  if (isRenderableArisDecision(status?.latest_decision, status, renderOptions)) {
    return status.latest_decision;
  }
  const latestActivityDecision = Array.isArray(activity)
    ? activity.find(
        (entry) =>
          entry.kind === "governance_result" ||
          entry.kind === "governance_review" ||
          entry.kind === "forge_repo_plan"
      ) || null
    : null;
  return isRenderableArisDecision(latestActivityDecision, status, renderOptions)
    ? latestActivityDecision
    : null;
}

function currentArisDecision() {
  if (isArisTruthSyncPending()) {
    return buildArisTruthSyncDecision();
  }
  return resolveLiveArisDecision(state.aris.status, state.aris.activity, state.aris.latestDecision);
}

function normalizeArisSystemTruth(statusPayload, healthPayload) {
  const status = statusPayload && typeof statusPayload === "object" ? { ...statusPayload } : {};
  const health = healthPayload && typeof healthPayload === "object" ? healthPayload : {};
  if (typeof status.startup_ready !== "boolean" && typeof health.ok === "boolean") {
    status.startup_ready = health.ok;
  }
  if ((!status.kill_switch || typeof status.kill_switch !== "object") && health.kill_switch) {
    status.kill_switch = health.kill_switch;
  }
  if ((!status.execution_backend || typeof status.execution_backend !== "object") && health.execution_backend) {
    status.execution_backend = health.execution_backend;
  }
  if ((!status.shell_execution || typeof status.shell_execution !== "object") && health.shell_execution) {
    status.shell_execution = health.shell_execution;
  }
  return status;
}

async function getSystemTruthLegacy(sessionId = activeDecisionSessionId()) {
  const [
    statusResponse,
    healthResponse,
    activityResponse,
    discardResponse,
    shameResponse,
    fameResponse,
    mysticResponse,
  ] = await Promise.all([
    fetch("/api/aris/status"),
    fetch("/api/health"),
    fetch(`/api/aris/activity?limit=20&session_id=${encodeURIComponent(sessionId)}`),
    fetch("/api/aris/discards?limit=20"),
    fetch("/api/aris/shame?limit=20"),
    fetch("/api/aris/fame?limit=20"),
    fetch(`/api/aris/mystic/status?session_id=${encodeURIComponent(sessionId)}`),
  ]);
  const statusPayload = await statusResponse.json();
  const healthPayload = await healthResponse.json();
  return {
    status: normalizeArisSystemTruth(statusPayload, healthPayload),
    activity: (await activityResponse.json()).activity || [],
    discards: (await discardResponse.json()).entries || [],
    shames: (await shameResponse.json()).entries || [],
    fame: (await fameResponse.json()).entries || [],
    mysticSession: await mysticResponse.json(),
  };
}

async function getSystemTruth(sessionId = activeDecisionSessionId()) {
  const response = await fetch(
    `/api/aris/truth?session_id=${encodeURIComponent(sessionId)}&activity_limit=20&hall_limit=20`
  );
  if (!response.ok) {
    return getSystemTruthLegacy(sessionId);
  }
  const payload = await response.json();
  if (!payload || payload.ok === false) {
    return getSystemTruthLegacy(sessionId);
  }
  return {
    status: normalizeArisSystemTruth(payload.status || {}, payload.health || {}),
    activity: Array.isArray(payload.activity) ? payload.activity : [],
    discards: Array.isArray(payload.discards) ? payload.discards : [],
    shames: Array.isArray(payload.shames) ? payload.shames : [],
    fame: Array.isArray(payload.fame) ? payload.fame : [],
    mysticSession: payload.mystic_session || null,
  };
}

async function loadArisRuntime() {
  const sessionId = state.sessionId || "scratchpad";
  if (state.aris.status && !isArisBootHydrating()) {
    arisTruthSyncPending = true;
    renderArisStatus(state.aris.status);
  }
  try {
    const truth = await getSystemTruth(sessionId);
    state.aris.status = truth.status;
    state.aris.activity = truth.activity;
    state.aris.discards = truth.discards;
    state.aris.shames = truth.shames;
    state.aris.fame = truth.fame;
    state.aris.mysticSession = truth.mysticSession;
    state.aris.latestDecision = resolveLiveArisDecision(state.aris.status, state.aris.activity, state.aris.latestDecision);
    arisTruthSyncPending = false;
    renderArisStatus(state.aris.status);
    renderMysticSession(state.aris.mysticSession);
    renderArisDiscards(state.aris.discards);
    renderArisShames(state.aris.shames);
    renderArisFame(state.aris.fame);
    renderArisActivity(state.aris.activity);
  } finally {
    arisTruthSyncPending = false;
  }
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
      void Promise.all([refreshWorkspace({ explicitReview: false }), loadRuns({ selectLatest: true }), loadRunAudit()]);
    });
    elements.sessionList.appendChild(item);
  }
  syncWorkspaceHeaderMeta();
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

function isArisBootHydrating() {
  return arisBootHydrationPending && !state.aris.status;
}

function isArisTruthSyncPending() {
  return arisTruthSyncPending && !isArisBootHydrating();
}

function buildArisHydrationDecision() {
  return {
    kind: "runtime_hydration",
    action_type: "runtime_hydration",
    disposition: "hydrating",
    reason: ARIS_HYDRATION_REASON,
    requires_forge_eval: false,
  };
}

function buildArisTruthSyncDecision() {
  return {
    kind: "runtime_sync",
    action_type: "runtime_sync",
    disposition: "syncing",
    reason: ARIS_TRUTH_SYNC_REASON,
    requires_forge_eval: false,
    recorded_at: new Date().toISOString(),
  };
}

function buildArisTruthSyncGateState() {
  return {
    label: "SYNCING",
    tone: "review",
    reason: ARIS_TRUTH_SYNC_REASON,
    timestamp: "Resolving current governed truth...",
  };
}

function buildArisHydrationGateState() {
  return {
    label: "SYNCING",
    tone: "review",
    reason: ARIS_HYDRATION_REASON,
    timestamp: "Loading governed runtime...",
  };
}

function renderArisStatus(status) {
  elements.arisHealthList.innerHTML = "";
  elements.arisGuardrailList.innerHTML = "";
  elements.arisEvaluationList.innerHTML = "";
  if (!status) {
    const hydrating = isArisBootHydrating();
    const gateState = hydrating ? buildArisHydrationGateState() : null;
    if (elements.arisLawBadge) {
      elements.arisLawBadge.textContent = hydrating ? "1001 syncing" : "offline";
    }
    if (elements.arisOutcomeBadge) {
      elements.arisOutcomeBadge.textContent = hydrating ? gateState.label : "idle";
    }
    if (elements.evalGateTimestamp) {
      elements.evalGateTimestamp.textContent = gateState?.timestamp || "No governed decision yet";
    }
    if (elements.evalGateReason) {
      elements.evalGateReason.textContent =
        gateState?.reason ||
        "The evaluation gate remains visible and non-collapsible. No transition is admitted without review.";
    }
    elements.evalGate?.classList.remove("eval-pass", "eval-block", "eval-review");
    if (hydrating) {
      elements.evalGate?.classList.add("eval-review");
      if (elements.arisPlanButton) {
        elements.arisPlanButton.disabled = true;
        elements.arisPlanButton.textContent = "Hydrating Runtime";
      }
      const item = document.createElement("div");
      item.className = "context-item truth-review";
      item.innerHTML = `
        <p class="context-label">Runtime Hydration</p>
        <div class="muted">${escapeHtml(ARIS_HYDRATION_REASON)}</div>
      `;
      elements.arisEvaluationList.appendChild(item);
      renderEvalGateStateStrip({}, buildArisHydrationDecision(), gateState);
      renderArisRoute(buildArisHydrationDecision());
    } else {
      if (elements.evalGateStateStrip) {
        elements.evalGateStateStrip.innerHTML = "";
      }
      renderArisRoute(null);
    }
    renderWorkspaceRail();
    renderRecentTaskRail();
    syncWorkspaceHeaderMeta();
    syncChatSurfaceMeta();
    renderProcessLoopBar();
    syncOperatorConsoleControls();
    syncExecutionAffordances(status);
    return;
  }
  const killSwitch = status.kill_switch || {};
  const shellExecution = status.shell_execution || {};
  const executionBackend = status.execution_backend || {};
  const runtimeMode = status.runtime_mode || status.demo_mode || {};
  const modelRouter = status.model_router || {};
  const lawBadge = status.meta_law_1001_active ? "1001 active" : "1001 offline";
  elements.brandName.textContent = status.system_name || "ARIS";
  elements.workspaceTitle.textContent = status.service_name || "Advanced Repo Intelligence Service";
  document.title = status.system_name || "ARIS";
  elements.modelLabel.textContent = formatModelRouterLabel(modelRouter, status);
  syncModelRouterControl(modelRouter);
  elements.arisLawBadge.textContent = lawBadge;
  const latestDecision = currentArisDecision();
  const gateState = deriveEvalGateState(status, latestDecision);
  elements.arisOutcomeBadge.textContent = gateState.label;
  if (elements.evalGateTimestamp) {
    elements.evalGateTimestamp.textContent = gateState.timestamp;
  }
  if (elements.evalGateReason) {
    elements.evalGateReason.textContent = gateState.reason;
  }
  elements.evalGate?.classList.remove("eval-pass", "eval-block", "eval-review");
  elements.evalGate?.classList.add(`eval-${gateState.tone}`);
  if (elements.arisRouteCopy) {
    elements.arisRouteCopy.textContent = "Route: Input → Forge → Eval → Outcome → Evolve";
  }
  renderEvalGateStateStrip(status, latestDecision, gateState);
  if (elements.arisPlanButton) {
    elements.arisPlanButton.disabled = Boolean(runtimeMode.active);
    elements.arisPlanButton.textContent = runtimeMode.active ? "Forge Unavailable In This Profile" : "Run Governed Plan";
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
    item.className = `context-item ${guardrailToneClass(guardrail)}`;
    item.innerHTML = `
      <p class="context-label">${escapeHtml(guardrail.title || guardrail.id || "guardrail")}</p>
      <div class="muted">${escapeHtml(guardrail.summary || "")}</div>
    `;
    elements.arisGuardrailList.appendChild(item);
  }
  const latest = latestDecision;
  if (!latest) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No governed action has been recorded yet.";
    elements.arisEvaluationList.appendChild(item);
    renderArisRoute(null);
    renderWorkspaceRail();
    renderRecentTaskRail();
    syncWorkspaceHeaderMeta();
    syncChatSurfaceMeta();
    renderProcessLoopBar();
    renderTaskBoardDigest();
    syncOperatorConsoleControls();
    syncExecutionAffordances(status);
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
  if (!evalSections.length && latest.kind === "forge_repo_plan") {
    evalSections.push({
      title: "Repo Plan",
      reason: latest.reason || latest.disposition || (latest.ok ? "Forge repo plan ready for review." : "Forge repo plan failed."),
      passed: latest.ok ? undefined : false,
    });
  }
  if (!evalSections.length && latest.kind === "runtime_sync") {
    evalSections.push({
      title: "Governed Truth Sync",
      reason: latest.reason || ARIS_TRUTH_SYNC_REASON,
    });
  }
  for (const section of evalSections) {
    const item = document.createElement("div");
    item.className = `context-item ${evaluationToneClass(section)}`;
    item.innerHTML = `
      <p class="context-label">${escapeHtml(section.title || section.id || section.mode || "check")}</p>
      <div class="muted">${escapeHtml(section.reason || "")}</div>
    `;
    elements.arisEvaluationList.appendChild(item);
  }
  if (latest.hall_name) {
    const item = document.createElement("div");
    item.className = `context-item ${latest.hall_name === "hall_of_fame" ? "truth-pass" : "truth-block"}`;
    item.innerHTML = `
      <p class="context-label">Disposition Hall</p>
      <div class="muted">${escapeHtml(latest.hall_name)}</div>
    `;
    elements.arisEvaluationList.appendChild(item);
  }
  renderWorkspaceRail();
  renderRecentTaskRail();
  syncWorkspaceHeaderMeta();
  syncChatSurfaceMeta();
  renderProcessLoopBar();
  renderTaskBoardDigest();
  syncOperatorConsoleControls();
  syncExecutionAffordances(status);
}

function deriveEvalGateState(status, latest) {
  const killMode = String(status?.kill_switch?.mode || "nominal").toLowerCase();
  const reason =
    latest?.reason ||
    status?.kill_switch?.summary ||
    "The evaluation gate remains visible and non-collapsible. No transition is admitted without review.";
  if (latest?.kind === "runtime_hydration" || latest?.kind === "runtime_sync" || latest?.disposition === "syncing") {
    return {
      label: "SYNCING",
      tone: "review",
      reason,
      timestamp: formatTimestamp(latest?.created_at || latest?.recorded_at || ""),
    };
  }
  if (latest?.verified || latest?.hall_name === "hall_of_fame") {
    return {
      label: "PASS",
      tone: "pass",
      reason,
      timestamp: formatTimestamp(latest.created_at || latest.recorded_at || ""),
    };
  }
  if (
    killMode !== "nominal" ||
    latest?.hall_name === "hall_of_discard" ||
    latest?.disposition === "blocked" ||
    latest?.disposition === "discarded"
  ) {
    return {
      label: "BLOCK",
      tone: "block",
      reason,
      timestamp: formatTimestamp(latest?.created_at || latest?.recorded_at || ""),
    };
  }
  return {
    label: "REVIEW",
    tone: "review",
    reason,
    timestamp: formatTimestamp(latest?.created_at || latest?.recorded_at || ""),
  };
}

function guardrailToneClass(guardrail) {
  if (guardrail?.passed === false) {
    return "truth-block";
  }
  if (guardrail?.passed === true) {
    return "truth-pass";
  }
  return "truth-review";
}

function evaluationToneClass(section) {
  if (section?.passed === false) {
    return "truth-block";
  }
  if (section?.passed === true) {
    return "truth-pass";
  }
  return "truth-review";
}

function processLoopSteps() {
  if (isArisBootHydrating()) {
    return [
      { id: "input", title: "Input", status: "syncing", detail: state.sessionId ? "session context ready" : "scratchpad context ready" },
      { id: "forge", title: "Forge", status: "syncing", detail: "loading worker state" },
      { id: "eval", title: "Eval", status: "syncing", detail: ARIS_HYDRATION_REASON },
      { id: "outcome", title: "Outcome", status: "syncing", detail: "waiting for latest governed decision" },
      { id: "evolve", title: "Evolve", status: "syncing", detail: "loading classified traces" },
    ];
  }
  const status = state.aris.status || {};
  const latest = currentArisDecision();
  const gateState = deriveEvalGateState(status, latest);
  if (latest?.kind === "runtime_sync") {
    return [
      { id: "input", title: "Input", status: state.sessionId ? "session bound" : "scratchpad", detail: status?.runtime_profile || "workspace" },
      { id: "forge", title: "Forge", status: "syncing", detail: "resolving governed worker truth" },
      { id: "eval", title: "Eval", status: "syncing", detail: ARIS_TRUTH_SYNC_REASON },
      { id: "outcome", title: "Outcome", status: "syncing", detail: "waiting for current governed decision" },
      { id: "evolve", title: "Evolve", status: "syncing", detail: "refreshing classified trace state" },
    ];
  }
  const evolveCount = Number(status?.evolve_engine?.count || 0);
  const forgeStatus = status?.forge?.connected
    ? status?.forge?.provider_configured
      ? "worker ready"
      : "connected / awaiting provider"
    : "worker offline";
  const evalStatus = latest
    ? latest.requires_forge_eval
      ? gateState.label
      : gateState.label === "PASS"
        ? "observed"
        : gateState.label
    : "standby";
  const outcomeStatus = latest?.hall_name
    ? latest.hall_name.replaceAll("_", " ")
    : latest?.disposition || "standby";
  const evolveStatus = status?.evolve_engine?.active ? `${evolveCount} trace${evolveCount === 1 ? "" : "s"}` : "idle";
  return [
    { id: "input", title: "Input", status: state.sessionId ? "session bound" : "scratchpad", detail: status?.runtime_profile || "workspace" },
    { id: "forge", title: "Forge", status: forgeStatus, detail: status?.forge_eval?.connected ? "eval lane connected" : "eval lane offline" },
    { id: "eval", title: "Eval", status: evalStatus, detail: gateState.reason },
    { id: "outcome", title: "Outcome", status: outcomeStatus, detail: latest?.reason || "No governed outcome yet." },
    { id: "evolve", title: "Evolve", status: evolveStatus, detail: status?.evolve_engine?.active ? "classified traces only" : "experience lane offline" },
  ];
}

function renderProcessLoopBar() {
  if (!elements.processLoopBar) {
    return;
  }
  const steps = processLoopSteps();
  elements.processLoopBar.innerHTML = "";
  if (elements.processLoopBadge) {
    elements.processLoopBadge.textContent = `${steps.length} locked steps`;
  }
  if (elements.processLoopHint) {
    elements.processLoopHint.textContent = "Input → Forge → Eval → Outcome → Evolve";
  }
  steps.forEach((step, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `process-loop-step phase-${String(step.status || "idle")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")}${index < steps.length - 1 ? " has-connector" : ""}${
      uiState.focusedSurface === step.id ? " is-focused" : ""
    }${
      step.id === "eval" && deriveEvalGateState(state.aris.status || {}, currentArisDecision()).label === "PASS"
        ? " is-active"
        : ""
    }`;
    button.title = `${step.title}: ${step.status}${step.detail ? ` — ${step.detail}` : ""}`;
    button.innerHTML = `
      <div class="process-loop-kicker">
        <span>${escapeHtml(step.title)}</span>
        <span>${escapeHtml(step.id === "input" ? "01" : step.id === "forge" ? "02" : step.id === "eval" ? "03" : step.id === "outcome" ? "04" : "05")}</span>
      </div>
      <p class="process-loop-title">${escapeHtml(step.status)}</p>
      <div class="process-loop-status">${escapeHtml(step.detail || "")}</div>
    `;
    button.addEventListener("click", () => focusSurface(step.id));
    elements.processLoopBar.appendChild(button);
  });
}

function classifyPromptIntent(prompt, mode = "chat") {
  const normalized = String(prompt || "").toLowerCase();
  if (!normalized) {
    return mode === "agent" ? "Orchestration" : "Conversation";
  }
  if (/(inspect|analy[sz]e|trace|audit|review|search|find|map)/.test(normalized)) {
    return "Inspection";
  }
  if (/(fix|bug|debug|repair|patch|failure|error)/.test(normalized)) {
    return "Bugfix";
  }
  if (/(refactor|rewrite|cleanup|simplif|rename|rebind)/.test(normalized)) {
    return "Refactor";
  }
  if (/(add|create|build|implement|wire|connect|ship)/.test(normalized)) {
    return mode === "agent" ? "Orchestration" : "Feature Build";
  }
  if (/(plan|strategy|roadmap|proposal)/.test(normalized)) {
    return "Planning";
  }
  return mode === "agent" ? "Orchestration" : "Conversation";
}

function summarizeMemoryEntry(entry) {
  if (!entry || typeof entry !== "object") {
    return "";
  }
  return [
    entry.summary,
    entry.name,
    entry.title,
    entry.fact,
    entry.text,
    entry.content,
    entry.preview,
  ]
    .map((value) => formatUiTextBlock(value))
    .find(Boolean) || "";
}

function buildInlineDecisionSnapshot(prompt, mode = elements.modeSelect?.value || "chat") {
  const intent = classifyPromptIntent(prompt, mode);
  const approvals = Array.isArray(state.approvals)
    ? state.approvals.filter((approval) => approval.kind !== "patch")
    : [];
  const pendingPatches = Array.isArray(state.workspace.pendingPatches) ? state.workspace.pendingPatches : [];
  const changedFiles = Array.isArray(state.workspace.review?.changed_files)
    ? state.workspace.review.changed_files
    : [];
  const shames = Array.isArray(state.aris.shames) ? state.aris.shames : [];
  const discards = Array.isArray(state.aris.discards) ? state.aris.discards : [];
  const gateState = deriveEvalGateState(state.aris.status, currentArisDecision());
  const normalized = String(prompt || "").toLowerCase();
  let riskScore = 0.18;
  if (mode === "agent") {
    riskScore += 0.18;
  }
  if (approvals.length) {
    riskScore += 0.14;
  }
  if (pendingPatches.length || changedFiles.length) {
    riskScore += 0.12;
  }
  if (/(runtime|law|kill|lock|integrity|approval|merge|release|deploy|mutation|protected)/.test(normalized)) {
    riskScore += 0.2;
  }
  if (/(repo|workspace|branch|diff|patch|forge|eval)/.test(normalized)) {
    riskScore += 0.08;
  }
  if (discards.length || shames.length) {
    riskScore += 0.06;
  }
  if (gateState.tone === "block") {
    riskScore += 0.12;
  } else if (gateState.tone === "review") {
    riskScore += 0.08;
  }
  const clampedRisk = Math.max(0.08, Math.min(0.94, riskScore));
  const riskLabel = clampedRisk >= 0.67 ? "High" : clampedRisk >= 0.38 ? "Guarded" : "Low";
  const tone = clampedRisk >= 0.67 ? "block" : clampedRisk >= 0.38 ? "review" : "pass";
  const predictedFailure = Math.round(clampedRisk * 100);
  const confidence = Math.round(
    Math.max(
      52,
      Math.min(
        92,
        56 +
          (approvals.length ? 8 : 0) +
          (changedFiles.length ? 6 : 0) +
          (mode === "agent" ? 8 : 0) +
          (state.memory.length ? 4 : 0)
      )
    )
  );
  const why = [];
  if (approvals.length) {
    why.push(`${approvals.length} approval-sensitive path${approvals.length === 1 ? "" : "s"} already pending`);
  }
  if (pendingPatches.length || changedFiles.length) {
    const changeSurfaceCount = Math.max(pendingPatches.length, changedFiles.length);
    why.push(`${changeSurfaceCount} repo-facing change surface${changeSurfaceCount === 1 ? "" : "s"} active`);
  }
  if (/(runtime|law|kill|lock|integrity|mutation|protected)/.test(normalized)) {
    why.push("Touches protected runtime or governance boundaries");
  }
  if (state.aris.status?.kill_switch?.halted) {
    why.push("Kill switch is active, so new execution stays constrained");
  }
  if (!why.length) {
    why.push("Current request stays inside the normal governed workspace lane");
  }
  const memory = [];
  const recentDiscard = discards[0];
  const recentShame = shames[0];
  if (recentDiscard) {
    memory.push(`Recent discard: ${formatUiTextBlock(recentDiscard.reason || recentDiscard.summary || recentDiscard.kind)}`);
  }
  if (recentShame) {
    memory.push(`Recent shame: ${formatUiTextBlock(recentShame.reason || recentShame.summary || recentShame.kind)}`);
  }
  const memoryFact = state.memory.map(summarizeMemoryEntry).find(Boolean);
  if (memoryFact) {
    memory.push(`Memory: ${memoryFact}`);
  }
  return {
    intent,
    riskLabel,
    predictedFailure,
    confidence,
    tone,
    why: why.slice(0, 3),
    memory: memory.slice(0, 2),
    inspectSurface: approvals.length
      ? "outcome"
      : changedFiles.length
        ? "review"
        : gateState.tone === "block"
          ? "eval"
          : "workspace",
    gateLabel: gateState.label,
    routeLabel: gateState.routeLabel,
  };
}

function renderAssistantIntelligence(row, snapshot) {
  if (!row || !snapshot) {
    return;
  }
  const block = row.querySelector(".message-intelligence");
  if (!block) {
    return;
  }
  const whyList = snapshot.why.length
    ? `<ul>${snapshot.why.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
    : `<div class="muted">No elevated constraints detected.</div>`;
  const memoryList = snapshot.memory.length
    ? snapshot.memory
        .map((item) => `<span class="message-memory-chip">${escapeHtml(item)}</span>`)
        .join("")
    : `<span class="message-memory-chip is-muted">No strong memory signal attached.</span>`;
  block.innerHTML = `
    <div class="message-intelligence-header">
      <span class="message-intelligence-title">Decision Intelligence</span>
      <span class="message-intelligence-tone tone-${snapshot.tone}">${escapeHtml(snapshot.riskLabel)}</span>
    </div>
    <div class="message-intelligence-grid">
      <div class="message-intelligence-stat">
        <span class="message-intelligence-label">Intent</span>
        <strong>${escapeHtml(snapshot.intent)}</strong>
      </div>
      <div class="message-intelligence-stat">
        <span class="message-intelligence-label">Predicted Failure</span>
        <strong>${escapeHtml(String(snapshot.predictedFailure))}%</strong>
      </div>
      <div class="message-intelligence-stat">
        <span class="message-intelligence-label">Confidence</span>
        <strong>${escapeHtml(String(snapshot.confidence))}%</strong>
      </div>
      <div class="message-intelligence-stat">
        <span class="message-intelligence-label">Governed Route</span>
        <strong>${escapeHtml(snapshot.routeLabel || snapshot.gateLabel || "Locked")}</strong>
      </div>
    </div>
    <div class="message-intelligence-why">
      <span class="message-intelligence-label">Why</span>
      ${whyList}
    </div>
    <div class="message-intelligence-memory">
      <span class="message-intelligence-label">Memory</span>
      <div class="message-memory-row">${memoryList}</div>
    </div>
  `;
  row.dataset.inspectSurface = snapshot.inspectSurface;
}

function getInlineApprovalTarget() {
  const approvals = Array.isArray(state.approvals)
    ? state.approvals.filter((approval) => approval.kind !== "patch")
    : [];
  if (!approvals.length) {
    return null;
  }
  const activeRunApproval = state.activeRunId
    ? approvals.find((approval) => String(approval.run_id || "") === String(state.activeRunId))
    : null;
  return activeRunApproval || approvals[0];
}

function wireAssistantActions(row) {
  if (!row) {
    return;
  }
  const approve = row.querySelector('[data-message-action="approve"]');
  const reject = row.querySelector('[data-message-action="reject"]');
  const inspect = row.querySelector('[data-message-action="inspect"]');
  approve?.addEventListener("click", async (event) => {
    const approval = getInlineApprovalTarget();
    if (!approval) {
      focusSurface("outcome");
      flashElement(elements.evalGate);
      flashElement(elements.rightRail || elements.evalGate);
      return;
    }
    await handleApprovalDecision(approval, true, event.currentTarget);
  });
  reject?.addEventListener("click", async (event) => {
    const approval = getInlineApprovalTarget();
    if (!approval) {
      focusSurface("eval");
      flashElement(elements.evalGate);
      return;
    }
    await handleApprovalDecision(approval, false, event.currentTarget);
  });
  inspect?.addEventListener("click", () => inspectCurrentSurface(row.dataset.inspectSurface || ""));
}

function syncChatSurfaceMeta() {
  if (!elements.chatSurfaceMeta) {
    return;
  }
  const approvals = Array.isArray(state.approvals)
    ? state.approvals.filter((approval) => approval.kind !== "patch").length
    : 0;
  const taskCount = Array.isArray(state.workspace.tasks) ? state.workspace.tasks.length : 0;
  const meta = [
    `Session ${state.sessionId || "scratchpad"}`,
    `Mode ${elements.modeSelect?.value || "chat"}`,
    approvals ? `${approvals} pending approval` : "Approval lane clear",
    taskCount ? `${taskCount} queued task${taskCount === 1 ? "" : "s"}` : "Queue idle",
  ];
  elements.chatSurfaceMeta.innerHTML = meta
    .map((item) => `<span class="chat-meta-pill">${escapeHtml(item)}</span>`)
    .join("");
}

function inspectCurrentSurface(preferredSurface = "") {
  const fallbackSurface = preferredSurface || uiState.focusedSurface || "outcome";
  focusSurface(fallbackSurface);
  elements.rightRail?.scrollIntoView({ block: "start", behavior: "smooth" });
  flashElement(elements.rightRail || elements.evalGate);
}

function renderTaskBoardDigest() {
  if (!elements.taskBoardList || !elements.taskBoardMeta || !elements.taskBoardBadge) {
    return;
  }
  const tasks = Array.isArray(state.workspace.tasks) ? state.workspace.tasks : [];
  const approvals = Array.isArray(state.approvals) ? state.approvals.filter((approval) => approval.kind !== "patch") : [];
  const changedFiles = Array.isArray(state.workspace.review?.changed_files) ? state.workspace.review.changed_files : [];
  const project = state.workspace.projectProfile || null;
  const cards = [];
  if (tasks.length) {
    cards.push({
      label: "Queue",
      value: `${tasks.length} active`,
      detail: tasks.slice(0, 3).map((task) => `${task.title || "Task"} · ${task.status || "unknown"}`).join(" | "),
      tone: "truth-review",
    });
  }
  if (approvals.length) {
    cards.push({
      label: "Approval",
      value: `${approvals.length} pending`,
      detail: approvals.slice(0, 2).map((approval) => approval.title || approval.kind || "approval").join(" | "),
      tone: approvals.length ? "truth-block" : "truth-pass",
    });
  }
  if (changedFiles.length) {
    cards.push({
      label: "Review",
      value: `${changedFiles.length} changed`,
      detail: state.workspace.review?.summary || "Workspace review is active.",
      tone: "truth-review",
    });
  }
  if (project) {
    cards.push({
      label: "Project",
      value: `${(project.languages || []).length} languages`,
      detail: project.signals?.join(" | ") || "Signals detected.",
      tone: "truth-pass",
    });
  }

  const badgeParts = [];
  if (tasks.length) {
    badgeParts.push(`${tasks.length} running`);
  }
  if (approvals.length) {
    badgeParts.push(`${approvals.length} review`);
  }
  if (changedFiles.length) {
    badgeParts.push(`${changedFiles.length} changed`);
  }
  elements.taskBoardBadge.textContent = badgeParts.join(" • ") || "queue idle";
  elements.taskBoardList.innerHTML = "";
  elements.taskBoardMeta.innerHTML = "";

  if (!cards.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No active queue surfaces yet.";
    elements.taskBoardList.appendChild(item);
  } else {
    for (const card of cards) {
      const item = document.createElement("button");
      item.type = "button";
      item.className = `context-item context-item-button task-strip-card ${card.tone || ""}`;
      item.title = card.detail || card.value || card.label;
      item.innerHTML = `
        <p class="context-label">${escapeHtml(card.label)}</p>
        <div class="task-strip-value">${escapeHtml(card.value)}</div>
        <div class="muted task-strip-detail">${escapeHtml(card.detail || "")}</div>
      `;
      item.addEventListener("click", () =>
        focusSurface(
          card.label === "Queue"
            ? "forge"
            : card.label === "Approval"
              ? "outcome"
              : card.label === "Review"
                ? "review"
                : "workspace"
        )
      );
      elements.taskBoardList.appendChild(item);
    }
  }

  const metaRows = [
    ["Selected Session", state.sessionId || "scratchpad"],
    ["Run Lane", state.activeRun?.status || state.runs[0]?.status || "idle"],
    ["Memory Facts", `${state.memory.length} remembered`],
    ["Knowledge Docs", `${state.knowledge.length} loaded`],
  ];
  for (const [label, value] of metaRows) {
    const item = document.createElement("div");
    item.className = "context-item task-summary-card";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(label)}</p>
      <div class="muted">${escapeHtml(String(value || ""))}</div>
    `;
    elements.taskBoardMeta.appendChild(item);
  }
  renderRecentTaskRail();
  syncChatSurfaceMeta();
}

function renderLogsStrip() {
  if (!elements.logsStripList || !elements.logsStripBadge) {
    return;
  }
  const entries = Array.isArray(state.aris.activity) ? state.aris.activity.slice(0, 5) : [];
  elements.logsStripBadge.textContent = `${entries.length} live`;
  elements.logsStripList.innerHTML = "";
  if (!entries.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No live activity yet.";
    elements.logsStripList.appendChild(item);
    return;
  }
  for (const entry of entries) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `context-item context-item-button ${
      entry.hall_name === "hall_of_fame"
        ? "truth-pass"
        : entry.hall_name === "hall_of_discard" || entry.disposition === "discarded" || entry.disposition === "blocked"
          ? "truth-block"
          : "truth-review"
    }`;
    item.title = `${entry.kind || entry.action_type || "activity"} · ${entry.reason || entry.goal || entry.disposition || ""}`;
    item.innerHTML = `
      <p class="context-label">${escapeHtml(entry.kind || entry.action_type || "activity")}</p>
      <div class="muted">${escapeHtml(entry.reason || entry.goal || entry.disposition || "")}</div>
      <div class="muted">${escapeHtml(formatTimestamp(entry.recorded_at || entry.created_at || ""))}</div>
    `;
    item.addEventListener("click", () => focusSurface("outcome"));
    elements.logsStripList.appendChild(item);
  }
}

function flashElement(element) {
  if (!element) {
    return;
  }
  element.classList.remove("focus-flash");
  void element.offsetWidth;
  element.classList.add("focus-flash");
}

function focusSurface(surface) {
  uiState.focusedSurface = surface;
  const target =
    surface === "input"
      ? elements.messageInput
      : surface === "forge"
        ? elements.taskGoalInput || elements.arisGoalInput
        : surface === "eval"
          ? elements.evalGate
          : surface === "outcome"
            ? elements.arisActivityList
            : surface === "evolve"
              ? elements.memoryList
              : surface === "workspace"
                ? elements.projectMeta
                : surface === "review"
                  ? elements.reviewSummary
                  : surface === "knowledge"
                    ? elements.docContentInput
                    : null;
  if (target?.scrollIntoView) {
    target.scrollIntoView({ behavior: "smooth", block: "center" });
  }
  if (target?.focus) {
    target.focus({ preventScroll: true });
  }
  flashElement(target?.closest?.(".panel") || target);
  renderProcessLoopBar();
}

function syncOperatorConsoleControls() {
  if (!elements.operatorConsoleBadge || !elements.operatorConsoleSummary) {
    return;
  }
  uiState.operator.mode = elements.operatorModeSelect?.value || uiState.operator.mode;
  uiState.operator.scope = elements.operatorScopeSelect?.value || uiState.operator.scope;
  uiState.operator.target = elements.operatorTargetSelect?.value || uiState.operator.target;
  uiState.operator.tier = elements.operatorTierSelect?.value || uiState.operator.tier;
  const targetSurface = surfaceForOperatorTarget();
  elements.operatorConsoleBadge.textContent = `${uiState.operator.mode} · ${uiState.operator.tier}`;
  elements.operatorConsoleSummary.innerHTML = `
    <p class="context-label">Live Operator Frame</p>
    <div class="muted">
      Mode ${escapeHtml(uiState.operator.mode)} · Scope ${escapeHtml(uiState.operator.scope)} · Target ${escapeHtml(uiState.operator.target)} · Tier ${escapeHtml(uiState.operator.tier)}
    </div>
    <div class="muted">
      Voice ${uiState.operator.voiceEnabled ? "enabled" : "muted"} · EvalGate remains dominant · Loop order locked to Input → Forge → Eval → Outcome → Evolve
    </div>
    <div class="muted">
      Target focus lane: ${escapeHtml(targetSurface)} · Alt+1..5 moves across the locked process loop.
    </div>
  `;
  if (elements.operatorRunButton) {
    elements.operatorRunButton.title = `Focus ${targetSurface} lane`;
  }
  if (elements.operatorApproveButton) {
    elements.operatorApproveButton.title = "Focus governed outcome and approval surfaces";
  }
  if (elements.operatorShipButton) {
    elements.operatorShipButton.title = "Focus review and release-facing traces";
  }
  if (elements.operatorWorkspaceButton) {
    elements.operatorWorkspaceButton.title = "Focus workspace and repo surfaces";
  }
}

function surfaceForOperatorTarget() {
  const target = elements.operatorTargetSelect?.value || uiState.operator.target || "Forge";
  if (target === "Eval") {
    return "eval";
  }
  if (target === "Outcome") {
    return "outcome";
  }
  if (target === "Evolve") {
    return "evolve";
  }
  return "forge";
}

function previewOperatorTarget() {
  uiState.operator.target = elements.operatorTargetSelect?.value || uiState.operator.target;
  uiState.focusedSurface = surfaceForOperatorTarget();
  syncOperatorConsoleControls();
  renderProcessLoopBar();
  flashElement(elements.processLoopBar);
}

function enableOperatorGroupToggles() {
  document.querySelectorAll(".operator-group").forEach((group) => {
    const header = group.querySelector(".operator-group-header");
    if (!header || header.dataset.bound === "true") {
      return;
    }
    header.dataset.bound = "true";
    header.tabIndex = 0;
    header.setAttribute("role", "button");
    header.setAttribute("aria-expanded", "true");
    const toggle = () => {
      const collapsed = group.classList.toggle("is-collapsed");
      header.setAttribute("aria-expanded", String(!collapsed));
    };
    header.addEventListener("click", toggle);
    header.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    });
  });
}

function installKeyboardShortcuts() {
  window.addEventListener("keydown", (event) => {
    const target = event.target;
    if (
      !event.altKey ||
      event.defaultPrevented ||
      (target instanceof HTMLElement &&
        target.closest("input, textarea, select, [contenteditable='true']"))
    ) {
      return;
    }
    const surface =
      event.key === "1"
        ? "input"
        : event.key === "2"
          ? "forge"
          : event.key === "3"
            ? "eval"
            : event.key === "4"
              ? "outcome"
              : event.key === "5"
                ? "evolve"
                : "";
    if (!surface) {
      return;
    }
    event.preventDefault();
    focusSurface(surface);
  });
}

function applyApprovalGuardMode() {
  if (elements.operatorModeSelect) {
    elements.operatorModeSelect.value = "Guard";
  }
  if (elements.operatorTierSelect) {
    elements.operatorTierSelect.value = "Guard";
  }
  syncOperatorConsoleControls();
  focusSurface("eval");
}

function toggleOperatorVoice() {
  uiState.operator.voiceEnabled = !uiState.operator.voiceEnabled;
  if (elements.operatorVoiceToggleButton) {
    elements.operatorVoiceToggleButton.textContent = uiState.operator.voiceEnabled ? "Voice On" : "Voice Off";
  }
  if (!uiState.operator.voiceEnabled && "speechSynthesis" in window) {
    window.speechSynthesis.cancel();
  }
  syncOperatorConsoleControls();
}

function unlinkTaskDraft() {
  if (elements.taskTitleInput) {
    elements.taskTitleInput.value = "";
  }
  if (elements.taskGoalInput) {
    elements.taskGoalInput.value = "";
  }
  if (elements.taskCwdInput) {
    elements.taskCwdInput.value = "";
  }
  if (elements.taskCommandsInput) {
    elements.taskCommandsInput.value = "";
  }
  focusSurface("forge");
}

function prefillBugReport() {
  elements.messageInput.value =
    "Bug report:\n- Surface:\n- Expected:\n- Actual:\n- Governance state:\n- Repro steps:\n";
  focusSurface("input");
}

function prefillFeedbackNote() {
  elements.docNameInput.value = "operator-feedback.md";
  elements.docContentInput.value =
    "# Operator Feedback\n\n## What worked\n- \n\n## What hurt comprehension\n- \n\n## Suggested refinement\n- \n";
  focusSurface("knowledge");
}

function prefillFeatureRequest() {
  elements.taskTitleInput.value = "Feature request";
  elements.taskGoalInput.value =
    "Design and stage a governed feature request with visible EvalGate review, operator approval, and trace-safe outcome handling.";
  focusSurface("forge");
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
  const status = state.aris.status || {};
  const gateState = deriveEvalGateState(status, entry || state.aris.latestDecision || null);
  const isHydrating = entry?.kind === "runtime_hydration";
  const isTruthSync = entry?.kind === "runtime_sync";
  const isSyncing = isHydrating || isTruthSync;
  const steps = entry
    ? [
        [
          "Input",
          isSyncing
            ? isHydrating
              ? "boot hydration"
              : "truth sync"
            : `${state.sessionId ? "session bound" : "scratchpad"} · ${entry.action_type || entry.kind || "observed"}`,
          "input",
        ],
        [
          "Forge",
          isSyncing
            ? "syncing"
            : entry.kind === "forge_repo_plan"
              ? entry.ok
                ? "completed"
                : "failed"
              : entry.requires_forge_eval
                ? "worker governed"
                : "proposal lane",
          "forge",
        ],
        ["Eval", isSyncing ? "SYNCING" : entry.requires_forge_eval || gateState.label === "BLOCK" ? gateState.label : "review", "eval"],
        ["Outcome", isSyncing ? "syncing" : entry.hall_name || entry.disposition || "idle", "outcome"],
        [
          "Evolve",
          isSyncing
            ? "syncing"
            : status?.evolve_engine?.active
              ? `${status.evolve_engine.count || 0} classified traces`
              : "idle",
          "evolve",
        ],
      ]
    : [
        ["Input", "standby", "input"],
        ["Forge", "standby", "forge"],
        ["Eval", "standby", "eval"],
        ["Outcome", "standby", "outcome"],
        ["Evolve", "standby", "evolve"],
      ];
  for (const [label, value, surface] of steps) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "context-item context-item-button route-button";
    item.title = `${label}: ${value}`;
    item.innerHTML = `
      <p class="context-label">${escapeHtml(label)}</p>
      <div class="muted">${escapeHtml(String(value || ""))}</div>
    `;
    item.addEventListener("click", () => focusSurface(surface));
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
    const scopeSuffix = entry.historical ? " · historical" : "";
    const scopeReason = entry.historical
      ? entry.scope_reason === "outside_current_session"
        ? "Outside the current session."
        : "Recorded before the current session."
      : "Eligible for current-state derivation.";
    item.innerHTML = `
      <p class="context-label">${escapeHtml(entry.kind || entry.action_type || "activity")}${escapeHtml(scopeSuffix)}</p>
      <div class="muted">${escapeHtml(entry.reason || entry.goal || entry.disposition || "")}</div>
      <div class="muted">${escapeHtml(scopeReason)}</div>
      <div class="muted">${escapeHtml(entry.recorded_at || "")}</div>
    `;
    elements.arisActivityList.appendChild(item);
  }
}

function renderWorkspaceRail() {
  if (!elements.workspaceRailList || !elements.workspaceRailCount) {
    return;
  }
  const status = state.aris.status || {};
  const project = state.workspace.projectProfile || null;
  const items = [];
  if (status.repo_target) {
    items.push({
      label: "Active Repo",
      value: status.repo_target,
      detail: `${status.runtime_profile || "full"} runtime · ${status.startup_ready ? "ready" : "blocked"}`,
      tone: status.startup_ready ? "truth-pass" : "truth-block",
    });
  }
  if (project) {
    const languages = Array.isArray(project.languages) ? project.languages : [];
    const frameworks = Array.isArray(project.frameworks) ? project.frameworks : [];
    items.push({
      label: "Project Profile",
      value: languages.length ? languages.join(", ") : "Signals detected",
      detail: frameworks.length ? `Frameworks: ${frameworks.join(", ")}` : project.signals?.join(" · ") || "Repo signals available",
      tone: "truth-review",
    });
  }
  const executionDetail = status.shell_execution?.detail || status.execution_backend?.docker_detail || "";
  if (status.execution_backend || status.shell_execution) {
    items.push({
      label: "Runtime Lane",
      value: status.shell_execution?.enabled ? status.shell_execution?.active_backend || "ready" : "disabled",
      detail: executionDetail || "Execution lane available.",
      tone: status.shell_execution?.degraded ? "truth-block" : "truth-pass",
    });
  }

  elements.workspaceRailCount.textContent = `${items.length}`;
  elements.workspaceRailList.innerHTML = "";
  if (!items.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No workspace context is active yet.";
    elements.workspaceRailList.appendChild(item);
    return;
  }
  for (const card of items) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = `context-item context-item-button rail-card ${card.tone || ""}`;
    item.title = card.detail || card.value || card.label;
    item.innerHTML = `
      <p class="context-label">${escapeHtml(card.label)}</p>
      <div>${escapeHtml(card.value || "")}</div>
      <div class="muted">${escapeHtml(card.detail || "")}</div>
    `;
    item.addEventListener("click", () => focusSurface("workspace"));
    elements.workspaceRailList.appendChild(item);
  }
}

function renderRecentTaskRail() {
  if (!elements.recentTaskRailList || !elements.recentTaskRailCount) {
    return;
  }
  const tasks = Array.isArray(state.workspace.tasks) ? state.workspace.tasks.slice(0, 4) : [];
  elements.recentTaskRailCount.textContent = `${tasks.length}`;
  elements.recentTaskRailList.innerHTML = "";
  if (!tasks.length) {
    const item = document.createElement("div");
    item.className = "context-item muted";
    item.textContent = "No active workspace tasks yet.";
    elements.recentTaskRailList.appendChild(item);
    return;
  }
  for (const task of tasks) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "context-item context-item-button rail-card";
    item.title = task.summary || task.goal || task.title || "task";
    item.innerHTML = `
      <div class="rail-card-header">
        <p class="context-label">${escapeHtml(task.title || "Workspace task")}</p>
        <span class="badge badge-muted">${escapeHtml(task.status || "task")}</span>
      </div>
      <div class="muted">${escapeHtml(task.summary || task.goal || "")}</div>
      <div class="muted">${escapeHtml(task.phase || "phase unknown")}</div>
    `;
    item.addEventListener("click", () => focusSurface(task.status === "ready_for_approval" ? "outcome" : "forge"));
    elements.recentTaskRailList.appendChild(item);
  }
}

function syncWorkspaceHeaderMeta() {
  if (!elements.workspaceHeaderMeta || !elements.workspaceStateBadgeRow) {
    return;
  }
  const session = state.sessions.find((item) => item.id === state.sessionId);
  const status = state.aris.status || {};
  const gateState = deriveEvalGateState(status, currentArisDecision());
  const metaPills = [
    { tone: "muted", text: session?.title || session?.name || "Scratchpad session" },
    { tone: status.startup_ready ? "pass" : "block", text: status.startup_ready ? "Runtime Ready" : "Runtime Blocked" },
    { tone: gateState.tone, text: `Eval ${gateState.label}` },
  ];
  elements.workspaceHeaderMeta.innerHTML = metaPills
    .map(
      (pill) =>
        `<span class="workspace-meta-pill tone-${escapeHtml(pill.tone)}">${escapeHtml(pill.text)}</span>`
    )
    .join("");

  const statePills = [
    { tone: "muted", text: status.runtime_profile || "full profile" },
    {
      tone: !status.forge?.connected ? "block" : status.forge?.provider_configured ? "pass" : "review",
      text: !status.forge?.connected
        ? "Forge Offline"
        : status.forge?.provider_configured
          ? "Forge Available"
          : "Forge Awaiting Provider",
    },
    {
      tone: status.evolve_engine?.active ? "review" : "muted",
      text: status.evolve_engine?.active ? `${status.evolve_engine.count || 0} evolve traces` : "Evolve idle",
    },
  ];
  if (status.shell_execution?.degraded) {
    statePills.splice(1, 0, {
      tone: "review",
      text: "Runtime Degraded",
    });
  }
  elements.workspaceStateBadgeRow.innerHTML = statePills
    .map(
      (pill) =>
        `<span class="workspace-state-pill tone-${escapeHtml(pill.tone)}">${escapeHtml(pill.text)}</span>`
    )
    .join("");
}

function renderEvalGateStateStrip(status, latest, gateState) {
  if (!elements.evalGateStateStrip) {
    return;
  }
  const isHydrating = latest?.kind === "runtime_hydration";
  const cards = [
    {
      label: "Decision",
      value: gateState.label,
      detail: gateState.timestamp || "Awaiting governed action",
      tone: gateState.tone,
    },
    {
      label: "Outcome Hall",
      value: isHydrating ? "hydrating" : latest?.hall_name ? latest.hall_name.replaceAll("_", " ") : "awaiting hall",
      detail: isHydrating ? "loading latest governed decision" : latest?.disposition || "no disposition yet",
      tone: isHydrating ? "review" : latest?.hall_name === "hall_of_fame" ? "pass" : latest?.hall_name ? "block" : "review",
    },
    {
      label: "Eval Path",
      value: isHydrating ? "Runtime hydration" : latest?.requires_forge_eval ? "Forge Eval required" : "Observation lane",
      detail: isHydrating ? "loading governed surfaces" : latest?.action_type || "No active action",
      tone: isHydrating ? "review" : latest?.requires_forge_eval ? "review" : "muted",
    },
    {
      label: "Evolve",
      value: isHydrating
        ? "syncing"
        : status?.evolve_engine?.active
          ? `${status.evolve_engine.count || 0} classified traces`
          : "offline",
      detail: isHydrating
        ? "loading classified traces"
        : status?.evolve_engine?.active
          ? "classified traces only"
          : "experience lane unavailable",
      tone: isHydrating ? "review" : status?.evolve_engine?.active ? "pass" : "block",
    },
  ];
  elements.evalGateStateStrip.innerHTML = cards
    .map(
      (card) => `
        <div class="eval-state-card tone-${escapeHtml(card.tone)}">
          <p class="context-label">${escapeHtml(card.label)}</p>
          <div>${escapeHtml(card.value)}</div>
          <div class="muted">${escapeHtml(card.detail)}</div>
        </div>
      `
    )
    .join("");
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
  renderWorkspaceRail();
  renderRecentTaskRail();
  syncWorkspaceHeaderMeta();
  renderProcessLoopBar();
  renderTaskBoardDigest();
  syncOperatorConsoleControls();
}

function formatUiTextBlock(value) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value.trim();
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch (_error) {
    return String(value);
  }
}

function buildArisPlanDisplayEntry(payload, goal) {
  const repoManager = payload?.result?.repo_manager || payload?.repo_manager || {};
  const reason = [
    repoManager.repo_summary,
    repoManager.summary,
    payload?.reason,
    payload?.message,
    payload?.error?.message,
    payload?.error,
    payload?.ok ? "Forge repo plan ready for review." : "Forge repo plan failed.",
  ]
    .map((value) => formatUiTextBlock(value))
    .find(Boolean);
  return {
    ...payload,
    kind: payload?.kind || "forge_repo_plan",
    action_type: payload?.action_type || "forge_repo_plan",
    goal: payload?.goal || goal,
    purpose: payload?.purpose || "Generate a governed Forge repo plan without applying changes.",
    target: payload?.target || "Evolving AI repo",
    disposition: payload?.disposition || (payload?.ok ? "proposal_ready" : "blocked"),
    requires_forge_eval: false,
    verified: false,
    reason,
    recorded_at: payload?.recorded_at || new Date().toISOString(),
  };
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
  const assistantNode = appendMessage("assistant", "", {
    intelligence: buildInlineDecisionSnapshot(prompt, mode),
  });
  const assistantBody = assistantNode.querySelector(".message-body");
  elements.emptyState.style.display = "none";
  syncChatSurfaceMeta();

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
  renderAssistantIntelligence(assistantNode, buildInlineDecisionSnapshot(prompt, mode));
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
  renderAssistantIntelligence(assistantNode, buildInlineDecisionSnapshot(prompt, mode));
  syncChatSurfaceMeta();
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
  if (!raw || !state.exec.shellEnabled || state.aris.status?.shell_execution?.degraded) {
    return;
  }
  const command = tokenizeCommand(raw);
  if (!command) {
    elements.commandOutput.textContent = "Command parsing failed. Check your quotes and escapes.";
    return;
  }
  const cwd = elements.commandCwdInput.value.trim();
  elements.runCommandButton.dataset.busy = "true";
  syncExecutionAffordances();
  elements.commandOutput.textContent = "";

  try {
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
        await loadSessions();
        await refreshWorkspace();
      },
    });
  } finally {
    delete elements.runCommandButton.dataset.busy;
    syncExecutionAffordances();
  }
}

async function resetSandbox() {
  const sessionId = state.sessionId || "scratchpad";
  elements.resetSandboxButton.dataset.busy = "true";
  syncExecutionAffordances();
  try {
    const response = await fetch(`/api/sandbox/${encodeURIComponent(sessionId)}/reset`, {
      method: "POST",
    });
    const payload = await response.json();
    const detail = payload.detail || (payload.removed ? "Sandbox removed." : "No sandbox to remove.");
    elements.commandOutput.textContent = detail;
    await refreshWorkspace();
  } finally {
    delete elements.resetSandboxButton.dataset.busy;
    syncExecutionAffordances();
  }
}

function shouldFetchWorkspaceReview(workspacePayload, options = {}) {
  if (options.explicitReview) {
    return true;
  }
  const payload = workspacePayload && typeof workspacePayload === "object" ? workspacePayload : {};
  const gitChanged = Array.isArray(payload.git?.changed_files) ? payload.git.changed_files.length : 0;
  const pendingApprovals = Array.isArray(payload.pending_approvals) ? payload.pending_approvals.length : 0;
  const pendingPatches = Array.isArray(payload.pending_patches) ? payload.pending_patches.length : 0;
  const appliedChanges = Array.isArray(payload.applied_changes) ? payload.applied_changes.length : 0;
  return Boolean(gitChanged || pendingApprovals || pendingPatches || appliedChanges);
}

function buildDeferredWorkspaceReview(workspacePayload) {
  return {
    ok: true,
    deferred: true,
    summary: "Inspection is deferred until there is explicit review intent or bounded workspace context.",
    changed_files: [],
    changed_entries: [],
    diff_stat: "",
    diff: "",
    git: workspacePayload?.git || {},
    pending_patches: workspacePayload?.pending_patches || [],
    files: workspacePayload?.files || [],
  };
}

async function refreshWorkspace(options = {}) {
  const sessionId = state.sessionId || "scratchpad";
  const workspaceResponse = await fetch(`/api/workspace/${encodeURIComponent(sessionId)}`);
  const workspacePayload = await workspaceResponse.json();
  const reviewPayload = shouldFetchWorkspaceReview(workspacePayload, options)
    ? await fetch(`/api/workspace/${encodeURIComponent(sessionId)}/review`).then((response) => response.json())
    : buildDeferredWorkspaceReview(workspacePayload);
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
  state.aris.latestDecision = buildArisPlanDisplayEntry(payload, goal);
  const repoManager = payload.result?.repo_manager || payload.repo_manager || {};
  const summary = [
    repoManager.repo_summary,
    repoManager.summary,
    payload.reason,
    payload.error,
    "No Forge plan returned.",
  ]
    .map((value) => formatUiTextBlock(value))
    .find(Boolean);
  const planSteps = Array.isArray(repoManager.plan)
    ? repoManager.plan
        .map((step) => {
          if (typeof step === "string") {
            return `- ${step}`;
          }
          const label = formatUiTextBlock(step?.step || step?.title || step);
          const scope = step?.file ? ` (${step.file})` : "";
          return label ? `- ${label}${scope}` : "";
        })
        .filter(Boolean)
        .join("\n")
    : "";
  const risks = Array.isArray(repoManager.risks)
    ? repoManager.risks
        .map((risk) => {
          if (typeof risk === "string") {
            return `- ${risk}`;
          }
          const scope = formatUiTextBlock(risk?.file || risk?.target || "repo");
          const issue = formatUiTextBlock(risk?.issue || risk?.reason || risk);
          return issue ? `- ${scope}: ${issue}` : "";
        })
        .filter(Boolean)
        .join("\n")
    : "";
  elements.arisPlanOutput.textContent = [summary, risks && `Risks\n${risks}`, planSteps && `Plan\n${planSteps}`]
    .filter(Boolean)
    .join("\n\n");
  elements.arisOutcomeBadge.textContent = payload.ok ? "proposal ready" : "proposal blocked";
  renderArisStatus(state.aris.status);
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

function appendMessage(role, content, options = {}) {
  elements.emptyState.style.display = "none";
  const row = document.createElement("div");
  row.className = `message-row ${role}`;
  if (role === "assistant") {
    row.innerHTML = `
      <article class="message-bubble message-bubble-assistant">
        <div class="message-header">
          <p class="message-role">${role}</p>
          <span class="message-shell-pill">inline intelligence</span>
        </div>
        <p class="message-body"></p>
        <section class="message-intelligence"></section>
        <div class="message-action-row">
          <button type="button" class="secondary-button" data-message-action="approve">Approve</button>
          <button type="button" class="secondary-button danger-button" data-message-action="reject">Reject</button>
          <button type="button" class="secondary-button" data-message-action="inspect">Inspect</button>
        </div>
      </article>
    `;
    renderAssistantIntelligence(row, options.intelligence || buildInlineDecisionSnapshot(content, elements.modeSelect?.value || "chat"));
    wireAssistantActions(row);
  } else {
    row.innerHTML = `
      <article class="message-bubble">
        <div class="message-header">
          <p class="message-role">${role}</p>
        </div>
        <p class="message-body"></p>
      </article>
    `;
  }
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
    renderWorkspaceRail();
    syncWorkspaceHeaderMeta();
    renderTaskBoardDigest();
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
  renderWorkspaceRail();
  syncWorkspaceHeaderMeta();
  renderTaskBoardDigest();
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
    renderRecentTaskRail();
    syncWorkspaceHeaderMeta();
    renderTaskBoardDigest();
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
  renderRecentTaskRail();
  syncWorkspaceHeaderMeta();
  renderTaskBoardDigest();
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
  if (review.deferred) {
    state.workspace.selectedChangedFile = null;
    state.workspace.reviewDiffIndex = {};
    elements.reviewCount.textContent = "deferred";
    resetSelectedReviewPane({
      fileMessage: "Review details will appear when you explicitly inspect or when the workspace has bounded change context.",
      diffMessage: "Inspection is deferred until review is explicitly requested or the workspace presents bounded review context.",
    });
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

function baseAllowedCommandsHint() {
  return state.exec.allowedCommands.length
    ? `Allowed: ${state.exec.allowedCommands.join(", ")}`
    : "Enter a bounded shell command.";
}

function syncExecutionAffordances(status = state.aris.status) {
  const shellExecution = status?.shell_execution || {};
  const degraded = Boolean(shellExecution.degraded);
  const detail = String(shellExecution.detail || "").trim();
  const shellAvailable = state.exec.shellEnabled && !degraded;
  const commandBusy = elements.runCommandButton?.dataset.busy === "true";
  const resetBusy = elements.resetSandboxButton?.dataset.busy === "true";

  if (elements.commandInput) {
    elements.commandInput.disabled = !shellAvailable;
  }
  if (elements.commandCwdInput) {
    elements.commandCwdInput.disabled = !shellAvailable;
  }
  if (elements.runCommandButton) {
    elements.runCommandButton.disabled = commandBusy || !shellAvailable;
    elements.runCommandButton.title = shellAvailable
      ? ""
      : degraded
        ? "Shell lane is degraded right now."
        : "Shell execution requires the Docker backend.";
  }
  if (elements.resetSandboxButton) {
    elements.resetSandboxButton.disabled = resetBusy || !shellAvailable;
    elements.resetSandboxButton.title = shellAvailable
      ? ""
      : degraded
        ? "Shell lane is degraded right now."
        : "Shell execution requires the Docker backend.";
  }
  if (elements.allowedCommandsHint) {
    if (!state.exec.shellEnabled) {
      elements.allowedCommandsHint.textContent = "Shell execution requires the Docker backend.";
    } else if (degraded) {
      elements.allowedCommandsHint.textContent = `${baseAllowedCommandsHint()} · Shell lane degraded: ${
        detail || "Docker backend unavailable."
      }`;
    } else {
      elements.allowedCommandsHint.textContent = baseAllowedCommandsHint();
    }
  }
  if (elements.commandOutput && !elements.commandOutput.textContent.trim()) {
    if (!state.exec.shellEnabled) {
      elements.commandOutput.textContent = "Shell execution requires the Docker backend.";
    } else if (degraded) {
      elements.commandOutput.textContent = detail
        ? `Shell lane degraded: ${detail}`
        : "Shell lane is degraded right now.";
    }
  }
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
  const assistantNode = appendMessage("assistant", "", {
    intelligence: buildInlineDecisionSnapshot(
      approved ? "Approve current governed change" : "Reject current governed change",
      elements.modeSelect?.value || "chat"
    ),
  });
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
