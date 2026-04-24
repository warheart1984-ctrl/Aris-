import React, { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

// Single-file ARIS Workspace demo.
// Styling stays inline with shadcn-like primitives so the surface remains portable.

const navigationItems = [
  { id: "workspace", label: "Workspace" },
  { id: "repos", label: "Repos" },
  { id: "tasks", label: "Tasks" },
  { id: "approvals", label: "Approvals" },
  { id: "memory", label: "Memory" },
];

const modeOptions = ["Chat", "Inspect", "Plan", "Build", "Evaluate", "Route", "Memory", "Approval"];
const scopeOptions = [
  "Current Chat",
  "Selected Repo",
  "Selected Task",
  "Workspace",
  "Runtime",
  "Memory Bank",
  "All Context",
];
const targetOptions = ["ARIS Only", "Forge", "ForgeEval", "Runtime", "Memory", "Operator Review"];
const permissionOptions = [
  "Read Only",
  "Suggest Only",
  "Approval Required",
  "Execute Safe Actions",
  "Full Demo Mode",
];
const responseStyleOptions = ["Direct", "Operator", "Technical", "Strategic", "Concise", "Guided"];
const taskTabs = ["All", "Running", "Review", "Done"];

const protectedPatterns = [
  /\bevolving core\b/i,
  /\bevolving engine\b/i,
  /\bevolve the core\b/i,
  /\bmutate the core\b/i,
  /\bself[- ]?modify\b/i,
  /\bself[- ]?rewrite\b/i,
  /\badaptive core\b/i,
];

const seedRepos = [
  {
    id: "repo-aais-main",
    name: "AAIS-main",
    branch: "law-spine/demo-shell",
    path: "C:/workspace/AAIS-main",
    status: "Connected",
    contextHint: "Immutable law and operator routing surfaces are already indexed here.",
    summary: "Best repo for law, routing, and adapter seam inspection.",
    lastUpdate: "2m ago",
  },
  {
    id: "repo-aris-runtime",
    name: "ARIS-runtime",
    branch: "workspace/brain-controls",
    path: "C:/workspace/ARIS-runtime",
    status: "Ready",
    contextHint: "Primary workspace shell, approvals, runtime status, and operator lanes.",
    summary: "Best repo for workspace UI, task orchestration, and governed runtime flow.",
    lastUpdate: "just now",
  },
  {
    id: "repo-repo-ai",
    name: "Repo-AI",
    branch: "repo/indexing-pass",
    path: "C:/workspace/Repo-AI",
    status: "Review",
    contextHint: "Repo connection, repo map, and branch-aware indexing are in review here.",
    summary: "Best repo for repo intelligence and branch-context surfaces.",
    lastUpdate: "9m ago",
  },
];

const seedTasks = [
  {
    id: "AR-104",
    title: "Build repo connection manager",
    repoId: "repo-aais-main",
    status: "Running",
    priority: "High",
    latestUpdate: "Forge is indexing repo seams while ARIS keeps the approval boundary closed.",
    summary: "Establish repo registration, branch awareness, and context handoff into ARIS.",
  },
  {
    id: "AR-118",
    title: "Create task board with approvals",
    repoId: "repo-aris-runtime",
    status: "Review",
    priority: "Critical",
    latestUpdate: "Execution finished. Diff and validation output are waiting in review.",
    summary: "Expose running, review, and done states without letting the worker lane own the voice.",
  },
  {
    id: "AR-127",
    title: "Add branch and environment controls",
    repoId: "repo-aais-main",
    status: "Running",
    priority: "Medium",
    latestUpdate: "Runtime branch controls are mapped and ready for a governed build route.",
    summary: "Make branch, environment, and workspace controls visible from the operator surface.",
  },
  {
    id: "AR-133",
    title: "Expose Forge as worker status only",
    repoId: "repo-aris-runtime",
    status: "Done",
    priority: "High",
    latestUpdate: "Completed. Worker output is visible, but ARIS remains the only speaker.",
    summary: "Keep Forge in execution lanes while ARIS preserves identity and narration.",
  },
  {
    id: "AR-145",
    title: "Inspect protected execution boundaries",
    repoId: "repo-repo-ai",
    status: "Review",
    priority: "Critical",
    latestUpdate: "Protected route checks are staged around Forge, approvals, and locked boundaries.",
    summary: "Verify that no evolving-core path is visible, routable, or callable from the demo.",
  },
];

const seedMessages = [
  {
    id: "msg-1",
    role: "aris",
    content:
      "ARIS workspace is online. I can inspect repos, plan tasks, route work to Forge, send evaluations to ForgeEval, and keep approval flow visible without surfacing protected core paths.",
    meta: "Workspace greeting",
    summary: "ARIS is the operator-facing speaking layer",
    route: ["Jarvis Blueprint", "Operator", "Governance Review", "Outcome"],
    suggestions: ["Inspect Selected Repo", "Plan Selected Task", "Route to Forge"],
    pills: ["Forge Available", "Approval Gated", "Evolving Core Locked"],
    tone: "connected",
  },
  {
    id: "msg-2",
    role: "user",
    content: "Inspect the selected repo, then prep the approval path for the task board.",
    meta: "Operator request",
  },
  {
    id: "msg-3",
    role: "aris",
    content:
      "Repo inspection ready. I found two likely routing seams and one approval-sensitive path in the selected codebase. I can hold the task-board route for approval or send a worker packet to Forge next.",
    meta: "Inspect -> Selected Repo -> ARIS Only",
    summary: "Repo seams surfaced",
    route: ["Jarvis Blueprint", "Operator", "Governance Review", "Outcome"],
    suggestions: ["Route to Forge", "Hold for Operator Review", "Inspect approval packet"],
    pills: ["Inspect", "Selected Repo", "Read Only", "Technical"],
    tone: "review",
  },
];

const seedActivity = [
  {
    id: "activity-1",
    time: "14:12",
    title: "Repo connected",
    detail: "AAIS-main returned a healthy branch map and a clean approval seam inventory.",
    tone: "connected",
  },
  {
    id: "activity-2",
    time: "14:08",
    title: "Review gate ready",
    detail: "AR-118 is waiting in Review with validation complete and apply still closed.",
    tone: "review",
  },
  {
    id: "activity-3",
    time: "14:03",
    title: "Boundary held",
    detail: "Protected routing remains locked away from the workspace surface.",
    tone: "warning",
  },
];

function cn(...values) {
  return values.filter(Boolean).join(" ");
}

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function statusTone(value) {
  const normalized = String(value || "").toLowerCase();
  if (["connected", "ready", "done", "available", "active"].includes(normalized)) {
    return "connected";
  }
  if (["running", "execute safe actions"].includes(normalized)) {
    return "running";
  }
  if (["review", "approval required", "forgeeval", "operator review"].includes(normalized)) {
    return "review";
  }
  if (["critical", "blocked", "locked", "warning"].includes(normalized)) {
    return "warning";
  }
  return "neutral";
}

function priorityTone(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "critical") return "warning";
  if (normalized === "high") return "running";
  return "neutral";
}

function routeForTarget(target) {
  switch (target) {
    case "Forge":
      return ["Jarvis Blueprint", "Operator", "Forge", "Outcome"];
    case "ForgeEval":
      return ["Jarvis Blueprint", "Operator", "ForgeEval", "Outcome"];
    case "Runtime":
      return ["Jarvis Blueprint", "Operator", "Runtime", "Outcome"];
    case "Memory":
      return ["Jarvis Blueprint", "Operator", "Memory", "Outcome"];
    default:
      return ["Jarvis Blueprint", "Operator", "Governance Review", "Outcome"];
  }
}

function primaryActionLabel(target) {
  switch (target) {
    case "Forge":
      return "Route To Forge";
    case "ForgeEval":
      return "Send To ForgeEval";
    case "Runtime":
      return "Run Runtime Check";
    case "Memory":
      return "Store Context";
    case "Operator Review":
      return "Hold For Review";
    default:
      return "Apply Brain State";
  }
}

function protectedRequest(prompt, target) {
  const text = `${String(prompt || "")} ${String(target || "")}`;
  return protectedPatterns.some((pattern) => pattern.test(text));
}

function scopeLabel(brain, repo, task) {
  switch (brain.scope) {
    case "Selected Repo":
      return repo ? repo.name : "the selected repo";
    case "Selected Task":
      return task ? `${task.id} ${task.title}` : "the selected task";
    case "Current Chat":
      return "the current chat";
    case "Workspace":
      return "the workspace";
    case "Runtime":
      return "runtime state";
    case "Memory Bank":
      return "the memory bank";
    default:
      return "all active context";
  }
}

function targetClause(brain) {
  switch (brain.target) {
    case "ARIS Only":
      return "I will keep this inside ARIS and the workspace surface.";
    case "Forge":
      return "Forge is the worker lane, but ARIS remains the speaker and narrator.";
    case "ForgeEval":
      return "ForgeEval is the review lane, so I will frame this as evaluation instead of direct execution.";
    case "Runtime":
      return "I will keep this in runtime inspection and workspace actions.";
    case "Memory":
      return "I will keep this in memory shaping and context anchoring.";
    default:
      return "I will package the next step for operator review instead of direct worker execution.";
  }
}

function permissionClause(permission) {
  switch (permission) {
    case "Read Only":
      return "Nothing will execute from this route.";
    case "Suggest Only":
      return "I will stop at suggestions, notes, and next actions.";
    case "Approval Required":
      return "I will hold the route pending approval.";
    case "Execute Safe Actions":
      return "I can simulate safe demo actions on the selected task.";
    default:
      return "I can widen safe demo actions, but protected routes remain closed.";
  }
}

function styleWrap(base, brain, nextSuggestions) {
  const safeSuggestions = nextSuggestions.slice(0, 3).join(", ").toLowerCase();
  switch (brain.responseStyle) {
    case "Direct":
      return base;
    case "Operator":
      return `${base} I am keeping the operator surface stable and the handoff explicit.`;
    case "Technical":
      return `${base} The route stays observable, approval-aware, and bounded to ${brain.scope.toLowerCase()}.`;
    case "Strategic":
      return `${base} This keeps momentum without widening authority or losing operator visibility.`;
    case "Concise":
      return `${base.split(". ")[0]}.`;
    case "Guided":
      return `${base} I can continue with ${safeSuggestions}, next.`;
    default:
      return base;
  }
}

function suggestionsForDecision(brain) {
  if (brain.target === "Forge") {
    return ["Approve Forge Route", "Inspect Diff Packet", "Shift To ForgeEval"];
  }
  if (brain.target === "ForgeEval") {
    return ["Review Findings", "Route To Forge", "Hold For Operator Review"];
  }
  if (brain.target === "Operator Review") {
    return ["Open Approval Packet", "Inspect Repo", "Plan Next Task"];
  }
  if (brain.mode === "Memory") {
    return ["Store Repo Context", "Link Selected Task", "Return To Planning"];
  }
  return ["Inspect Selected Repo", "Plan Selected Task", "Route To Forge"];
}

function buildDecision({ prompt, brain, repo, task }) {
  const repoName = repo ? repo.name : "the selected repo";
  const taskName = task ? task.title : "the selected task";
  const scopedTo = scopeLabel(brain, repo, task);

  if (protectedRequest(prompt, brain.target)) {
    return {
      blocked: true,
      content:
        "That path is protected and unavailable from this workspace. The evolving core is not exposed to ARIS in demo mode. I can continue through Forge, evaluation, approval flow, or standard workspace actions instead.",
      summary: "Protected route blocked",
      route: ["Jarvis Blueprint", "Operator", "Governance Review", "Outcome"],
      suggestions: ["Route To Forge", "Send To ForgeEval", "Hold For Approval", "Inspect In Read Only", "Plan Next Task"],
      pills: ["Protected Boundary", "Forge Available", "Evolving Core Locked"],
      tone: "warning",
      workerTitle: "Protected Boundary",
      workerStatus: "Locked",
      workerLines: [
        "ARIS refused the protected request before any route could open.",
        "The evolving core is not available from this demo workspace.",
        "Forge, ForgeEval, approvals, and read-only workspace actions remain available.",
      ],
      taskStatus: task ? "Review" : null,
      taskUpdate: task
        ? "Protected route blocked. ARIS offered Forge, ForgeEval, approval flow, and read-only alternatives."
        : null,
      activityTitle: "Protected route blocked",
      activityDetail: "ARIS held the workspace boundary and redirected the operator toward allowed paths.",
    };
  }

  const exampleKey = [brain.mode, brain.scope, brain.target, brain.permission, brain.responseStyle].join("|");

  let baseContent = "";
  let summary = "";

  if (exampleKey === "Inspect|Selected Repo|ARIS Only|Read Only|Technical") {
    baseContent = `Repo inspection ready. I found two likely routing seams and one approval-sensitive path in ${repoName}.`;
    summary = "Repo seams surfaced";
  } else if (exampleKey === "Build|Selected Task|Forge|Approval Required|Operator") {
    baseContent = "This task is ready to route to Forge. I have prepared the execution path and held it pending approval.";
    summary = "Forge route prepared";
  } else if (exampleKey === "Evaluate|Workspace|ForgeEval|Suggest Only|Strategic") {
    baseContent = "I reviewed the workspace flow and found one weak handoff between planning and execution.";
    summary = "Evaluation packet prepared";
  } else {
    switch (brain.mode) {
      case "Chat":
        baseContent = `I am holding the operator conversation on ${scopedTo}. ${targetClause(brain)} ${permissionClause(brain.permission)}`;
        summary = "Operator conversation framed";
        break;
      case "Inspect":
        baseContent = `Inspection frame is active for ${scopedTo}. I found the main routing, approval, and handoff signals around ${repoName}. ${permissionClause(brain.permission)}`;
        summary = "Inspection lane active";
        break;
      case "Plan":
        baseContent = `Planning frame is active for ${scopedTo}. I turned ${taskName} into a staged path with a visible approval checkpoint. ${targetClause(brain)}`;
        summary = "Plan staged";
        break;
      case "Build":
        baseContent =
          brain.target === "Forge"
            ? `I can route ${taskName} to Forge from this workspace. The worker lane stays behind ARIS, and ${permissionClause(brain.permission).toLowerCase()}`
            : `Build framing is active for ${taskName}. I can shape the implementation path here first, then hand it to the selected target when you are ready.`;
        summary = "Build path prepared";
        break;
      case "Evaluate":
        baseContent =
          brain.target === "ForgeEval"
            ? `ForgeEval is available for ${scopedTo}. I can send the packet there and keep the result narrated through ARIS.`
            : `Evaluation frame is active for ${scopedTo}. I can review seams, approvals, and worker handoffs before anything applies.`;
        summary = "Evaluation lane active";
        break;
      case "Route":
        baseContent = `Routing frame is ready. I can hand ${taskName} to ${brain.target} while keeping ARIS as the speaking face and ${permissionClause(brain.permission).toLowerCase()}`;
        summary = "Route mapped";
        break;
      case "Memory":
        baseContent = `Memory framing is active for ${scopedTo}. I can anchor repo, task, and operator context without widening execution scope. ${targetClause(brain)}`;
        summary = "Memory context prepared";
        break;
      case "Approval":
        baseContent = `Approval framing is active for ${taskName}. I summarized the next action, the risk posture, and the exact gate you would open from this workspace.`;
        summary = "Approval packet ready";
        break;
      default:
        baseContent = `I can operate on ${scopedTo} from ARIS and keep the workspace readable while the selected route stays visible.`;
        summary = "Workspace route prepared";
        break;
    }
  }

  const suggestions = suggestionsForDecision(brain);
  const content = styleWrap(baseContent, brain, suggestions);
  let taskStatus = task ? task.status : null;
  let taskUpdate = task ? task.latestUpdate : null;
  let workerStatus = brain.permission === "Approval Required" ? "Review" : brain.target === "Forge" ? "Running" : "Ready";
  let workerTitle = "ARIS Control Lane";
  let workerLines = [`Mode: ${brain.mode}`, `Scope: ${brain.scope}`, `Target: ${brain.target}`];

  if (brain.target === "Forge") {
    workerTitle = "Forge Route";
    if (brain.permission === "Approval Required" || brain.permission === "Suggest Only" || brain.permission === "Read Only") {
      workerStatus = "Review";
      taskStatus = task ? "Review" : null;
      taskUpdate = task ? "ARIS prepared the Forge route and held apply behind approval." : null;
      workerLines = [
        "Forge is available as the worker lane.",
        "ARIS prepared the route and kept apply pending approval.",
        "Evolving core remains locked and unavailable.",
      ];
    } else {
      workerStatus = "Running";
      taskStatus = task ? "Running" : null;
      taskUpdate = task ? "Forge is preparing the task now under the selected demo controls." : null;
      workerLines = [
        "Forge is preparing the task now.",
        "ARIS is narrating the worker lane and keeping the route visible.",
        "Approval and locked-boundary signals remain on screen.",
      ];
    }
  } else if (brain.target === "ForgeEval") {
    workerTitle = "ForgeEval Review";
    workerStatus = "Review";
    taskStatus = task ? "Review" : null;
    taskUpdate = task ? "ForgeEval is reviewing the route and highlighting the weak handoff." : null;
    workerLines = [
      "ForgeEval is reviewing the selected route.",
      "ARIS will narrate the findings and next safe move.",
      "No protected route is exposed during evaluation.",
    ];
  } else if (brain.target === "Operator Review") {
    workerTitle = "Approval Packet";
    workerStatus = "Review";
    taskStatus = task ? "Review" : null;
    taskUpdate = task ? "ARIS packaged the task for operator review and kept execution closed." : null;
    workerLines = [
      "Operator review packet is assembled.",
      "ARIS is holding the approval gate closed until you confirm.",
      "Forge remains available if you want a worker route next.",
    ];
  } else if (brain.target === "Memory") {
    workerTitle = "Memory Context";
    workerStatus = "Ready";
    workerLines = [
      "Memory and context remain available inside ARIS.",
      "No worker route is required for this step.",
      "Protected routes remain invisible and closed.",
    ];
  } else {
    workerStatus = "Ready";
    workerLines = [
      "ARIS is keeping this route inside the workspace shell.",
      "No worker handoff is required for the selected target.",
      "Protected routes remain locked and unavailable.",
    ];
  }

  return {
    blocked: false,
    content,
    summary,
    route: routeForTarget(brain.target),
    suggestions,
    pills: [brain.mode, brain.scope, brain.target, brain.permission, brain.responseStyle],
    tone: statusTone(workerStatus),
    workerTitle,
    workerStatus,
    workerLines,
    taskStatus,
    taskUpdate,
    activityTitle: `${brain.mode} route updated`,
    activityDetail: `${brain.target} is now framed for ${scopedTo} with ${brain.permission.toLowerCase()} active.`,
  };
}

function Badge({ children, tone = "neutral", className }) {
  const tones = {
    neutral: "border-white/10 bg-white/[0.05] text-slate-300",
    connected: "border-emerald-400/30 bg-emerald-400/10 text-emerald-200",
    running: "border-sky-400/30 bg-sky-400/10 text-sky-100",
    review: "border-violet-400/30 bg-violet-400/10 text-violet-100",
    warning: "border-amber-400/30 bg-amber-400/10 text-amber-100",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.18em]",
        tones[tone] || tones.neutral,
        className
      )}
    >
      {children}
    </span>
  );
}

function Button({ children, className, variant = "default", size = "default", ...props }) {
  const variants = {
    default: "bg-[#e0a95a] text-slate-950 hover:bg-[#e8b46d]",
    secondary: "bg-white/[0.08] text-slate-100 hover:bg-white/[0.12]",
    ghost: "bg-transparent text-slate-200 hover:bg-white/[0.08]",
    outline: "border border-white/10 bg-transparent text-slate-100 hover:bg-white/[0.08]",
  };
  const sizes = {
    default: "h-11 px-4 text-sm",
    sm: "h-9 px-3 text-[13px]",
    lg: "h-12 px-5 text-sm",
  };

  return (
    <button
      className={cn(
        "inline-flex items-center justify-center rounded-2xl font-medium transition duration-200 focus:outline-none focus:ring-2 focus:ring-[#e0a95a]/40",
        variants[variant],
        sizes[size],
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function Input({ className, ...props }) {
  return (
    <input
      className={cn(
        "h-11 w-full rounded-2xl border border-white/10 bg-white/[0.04] px-4 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-[#e0a95a]/40 focus:ring-2 focus:ring-[#e0a95a]/20",
        className
      )}
      {...props}
    />
  );
}

function Textarea({ className, ...props }) {
  return (
    <textarea
      className={cn(
        "w-full rounded-[28px] border border-white/10 bg-white/[0.04] px-4 py-3 text-sm text-slate-100 outline-none placeholder:text-slate-500 focus:border-[#e0a95a]/40 focus:ring-2 focus:ring-[#e0a95a]/20",
        className
      )}
      {...props}
    />
  );
}

function SelectField({ label, value, options, onChange }) {
  return (
    <label className="min-w-[180px] flex-1">
      <div className="mb-2 text-[10px] font-medium uppercase tracking-[0.24em] text-slate-500">{label}</div>
      <div className="relative">
        <select
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className="h-11 w-full appearance-none rounded-2xl border border-white/10 bg-[#091219] px-4 pr-10 text-sm text-slate-100 outline-none focus:border-[#e0a95a]/40 focus:ring-2 focus:ring-[#e0a95a]/20"
        >
          {options.map((option) => (
            <option key={option} value={option} className="bg-[#091219]">
              {option}
            </option>
          ))}
        </select>
        <span className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-xs text-slate-500">v</span>
      </div>
    </label>
  );
}

function Panel({ eyebrow, title, subtitle, children, className, aside }) {
  return (
    <section
      className={cn(
        "rounded-[32px] border border-white/10 bg-[#0b141c]/82 p-5 shadow-[0_28px_90px_-45px_rgba(0,0,0,0.8)] backdrop-blur-xl",
        className
      )}
    >
      {(eyebrow || title || subtitle || aside) && (
        <div className="mb-4 flex items-start justify-between gap-4">
          <div className="min-w-0">
            {eyebrow ? (
              <div className="mb-1 text-[11px] font-medium uppercase tracking-[0.24em] text-slate-500">{eyebrow}</div>
            ) : null}
            {title ? (
              <div className="text-[19px] font-semibold text-slate-50" style={{ fontFamily: '"Sora", "Avenir Next", sans-serif' }}>
                {title}
              </div>
            ) : null}
            {subtitle ? <div className="mt-1 text-sm leading-6 text-slate-400">{subtitle}</div> : null}
          </div>
          {aside}
        </div>
      )}
      {children}
    </section>
  );
}

function Metric({ label, value, tone = "neutral" }) {
  const toneMap = {
    neutral: "text-slate-100",
    connected: "text-emerald-200",
    running: "text-sky-200",
    review: "text-violet-200",
    warning: "text-amber-100",
  };

  return (
    <div className="min-w-[128px] rounded-[24px] border border-white/8 bg-white/[0.03] px-4 py-3">
      <div className="text-[11px] uppercase tracking-[0.2em] text-slate-500">{label}</div>
      <div className={cn("mt-2 text-xl font-semibold", toneMap[tone] || toneMap.neutral)}>{value}</div>
    </div>
  );
}

function Marker({ tone = "neutral" }) {
  const tones = {
    neutral: "bg-slate-500",
    connected: "bg-emerald-400",
    running: "bg-sky-400",
    review: "bg-violet-400",
    warning: "bg-amber-400",
  };

  return <span className={cn("h-2.5 w-2.5 rounded-full", tones[tone] || tones.neutral)} />;
}

function WorkerLine({ value }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-white/8 bg-white/[0.03] px-3 py-3">
      <div className="mt-1 h-1.5 w-1.5 rounded-full bg-[#e0a95a]" />
      <div className="text-sm leading-6 text-slate-300">{value}</div>
    </div>
  );
}

function MessageBubble({ message }) {
  const isAris = message.role === "aris";
  const roleLabel = isAris ? "ARIS" : "Operator";

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -14 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      className={cn(
        "rounded-[28px] border px-4 py-4 shadow-[0_18px_60px_-40px_rgba(0,0,0,0.8)]",
        isAris ? "border-[#21384d] bg-[#101a23]" : "border-white/8 bg-white/[0.03]"
      )}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Badge tone={isAris ? "connected" : "neutral"}>{roleLabel}</Badge>
          {message.meta ? <span className="text-xs text-slate-500">{message.meta}</span> : null}
        </div>
        {message.summary ? <Badge tone={message.tone || "review"}>{message.summary}</Badge> : null}
      </div>

      <div className="mt-3 whitespace-pre-wrap text-[15px] leading-7 text-slate-100">{message.content}</div>

      {message.route ? (
        <div className="mt-4 rounded-[22px] border border-white/8 bg-white/[0.03] px-4 py-3">
          <div className="text-[10px] uppercase tracking-[0.24em] text-slate-500">Route</div>
          <div className="mt-2 text-sm text-slate-200">{message.route.join(" -> ")}</div>
        </div>
      ) : null}

      {message.pills?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {message.pills.map((pill) => (
            <Badge key={`${message.id}-${pill}`} tone={statusTone(pill)}>
              {pill}
            </Badge>
          ))}
        </div>
      ) : null}

      {message.suggestions?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {message.suggestions.map((item) => (
            <span
              key={`${message.id}-${item}`}
              className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs text-slate-300"
            >
              {item}
            </span>
          ))}
        </div>
      ) : null}
    </motion.div>
  );
}

function TaskCard({ task, repoName, active, onSelect, onApprove, onQuickRoute }) {
  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2, ease: "easeOut" }}
      onClick={() => onSelect(task)}
      className={cn(
        "w-full rounded-[28px] border p-4 text-left transition duration-200",
        active
          ? "border-[#e0a95a]/50 bg-[#111b24] shadow-[0_18px_60px_-42px_rgba(224,169,90,0.55)]"
          : "border-white/8 bg-white/[0.03] hover:border-white/12 hover:bg-white/[0.05]"
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={statusTone(task.status)}>{task.status}</Badge>
            <Badge tone={priorityTone(task.priority)}>{task.priority}</Badge>
          </div>
          <div className="mt-3 text-lg font-semibold text-slate-50">{task.title}</div>
          <div className="mt-1 text-sm text-slate-400">
            {task.id} on {repoName}
          </div>
        </div>
        <Marker tone={statusTone(task.status)} />
      </div>

      <div className="mt-4 text-sm leading-6 text-slate-300">{task.summary}</div>
      <div className="mt-3 rounded-[20px] border border-white/8 bg-[#0d151d] px-3 py-3 text-sm leading-6 text-slate-400">
        {task.latestUpdate}
      </div>

      <div className="mt-4 flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          variant="secondary"
          onClick={(event) => {
            event.stopPropagation();
            onQuickRoute(task);
          }}
        >
          Route To Forge
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          onClick={(event) => {
            event.stopPropagation();
            onApprove(task);
          }}
        >
          Mark Review Complete
        </Button>
      </div>
    </motion.button>
  );
}

export default function ArisWorkspaceDemo() {
  const [repos, setRepos] = useState(seedRepos);
  const [tasks, setTasks] = useState(seedTasks);
  const [messages, setMessages] = useState(seedMessages);
  const [activity, setActivity] = useState(seedActivity);
  const [activeNav, setActiveNav] = useState("workspace");
  const [repoQuery, setRepoQuery] = useState("");
  const [taskQuery, setTaskQuery] = useState("");
  const [taskTab, setTaskTab] = useState("All");
  const [selectedRepoId, setSelectedRepoId] = useState(seedRepos[1].id);
  const [selectedTaskId, setSelectedTaskId] = useState(seedTasks[1].id);
  const [chatInput, setChatInput] = useState("Inspect the selected repo and hold the next build route for approval.");
  const [brain, setBrain] = useState({
    mode: "Inspect",
    scope: "Selected Repo",
    target: "ARIS Only",
    permission: "Read Only",
    responseStyle: "Technical",
  });
  const [workerState, setWorkerState] = useState({
    title: "Worker Surface",
    status: "Ready",
    lines: [
      "ARIS is active as the speaking layer.",
      "Forge is available as a worker target.",
      "Evolving core remains locked and unavailable from this demo.",
    ],
  });

  const selectedRepo = repos.find((repo) => repo.id === selectedRepoId) || repos[0] || null;
  const selectedTask = tasks.find((task) => task.id === selectedTaskId) || tasks[0] || null;
  const previewDecision = buildDecision({
    prompt: chatInput,
    brain,
    repo: selectedRepo,
    task: selectedTask,
  });

  const filteredRepos = repos.filter((repo) => {
    if (!repoQuery.trim()) return true;
    const value = repoQuery.toLowerCase();
    return [repo.name, repo.branch, repo.path, repo.status, repo.contextHint].join(" ").toLowerCase().includes(value);
  });

  const filteredTasks = tasks.filter((task) => {
    const matchesTab = taskTab === "All" ? true : task.status === taskTab;
    if (!matchesTab) return false;
    if (!taskQuery.trim()) return true;
    const repoName = repos.find((repo) => repo.id === task.repoId)?.name || "";
    return [task.id, task.title, task.summary, task.latestUpdate, repoName]
      .join(" ")
      .toLowerCase()
      .includes(taskQuery.toLowerCase());
  });

  const counts = {
    repos: repos.length,
    running: tasks.filter((task) => task.status === "Running").length,
    review: tasks.filter((task) => task.status === "Review").length,
    done: tasks.filter((task) => task.status === "Done").length,
  };

  const recentTasks = tasks.slice(0, 4);

  const pushActivity = (title, detail, tone = "neutral") => {
    setActivity((current) => [
      {
        id: `activity-${Date.now()}-${Math.random().toString(16).slice(2, 7)}`,
        time: nowLabel(),
        title,
        detail,
        tone,
      },
      ...current,
    ].slice(0, 14));
  };

  const selectRepo = (repo) => {
    setSelectedRepoId(repo.id);
    const repoTask = tasks.find((task) => task.repoId === repo.id);
    if (repoTask) {
      setSelectedTaskId(repoTask.id);
    }
    pushActivity("Repo focused", `${repo.name} is now the active repo in the workspace shell.`, "connected");
  };

  const selectTask = (task) => {
    setSelectedTaskId(task.id);
    setSelectedRepoId(task.repoId);
    pushActivity("Task focused", `${task.id} is now the active task in the ARIS workspace.`, "review");
  };

  const updateTaskState = (taskId, status, latestUpdate) => {
    setTasks((current) =>
      current.map((task) => (task.id === taskId ? { ...task, status, latestUpdate } : task))
    );
  };

  const handleApprovalComplete = (task) => {
    updateTaskState(task.id, "Done", "ARIS closed the review lane and confirmed the demo task as complete.");
    setSelectedTaskId(task.id);
    setSelectedRepoId(task.repoId);
    setWorkerState({
      title: "Approval Closed",
      status: "Done",
      lines: [
        `${task.id} is marked Done from the operator surface.`,
        "ARIS narrated the result and kept the worker lane in the background.",
        "Protected boundaries stayed locked during completion.",
      ],
    });
    pushActivity("Task completed", `${task.id} was marked Done from the demo workspace.`, "connected");
  };

  const simulateQuickForgeRoute = (task) => {
    const repo = repos.find((item) => item.id === task.repoId) || selectedRepo;
    const quickDecision = buildDecision({
      prompt: `Route ${task.title} through Forge from the task board.`,
      brain: {
        ...brain,
        mode: "Build",
        scope: "Selected Task",
        target: "Forge",
        permission: "Approval Required",
        responseStyle: "Operator",
      },
      repo,
      task,
    });
    setSelectedTaskId(task.id);
    setSelectedRepoId(task.repoId);
    setMessages((current) => [
      ...current,
      {
        id: `msg-${Date.now()}-aris-quick`,
        role: "aris",
        content: quickDecision.content,
        meta: "Task board route",
        summary: quickDecision.summary,
        route: quickDecision.route,
        suggestions: quickDecision.suggestions,
        pills: quickDecision.pills,
        tone: quickDecision.tone,
      },
    ]);
    updateTaskState(task.id, quickDecision.taskStatus || "Review", quickDecision.taskUpdate || task.latestUpdate);
    setWorkerState({
      title: quickDecision.workerTitle,
      status: quickDecision.workerStatus,
      lines: quickDecision.workerLines,
    });
    pushActivity("Forge route prepared", `${task.id} is staged for Forge and held behind approval.`, "review");
  };

  const handleAddRepo = () => {
    const label = repoQuery.trim() || `Repo-${repos.length + 1}`;
    const newRepo = {
      id: `repo-${Date.now()}`,
      name: label,
      branch: "workspace/new-connection",
      path: `C:/workspace/${String(label).replace(/\s+/g, "-")}`,
      status: "Ready",
      contextHint: "Fresh repo added to the demo workspace and ready for repo-aware chat.",
      summary: "Fresh connection available for inspection, planning, and approval routing.",
      lastUpdate: "just now",
    };

    setRepos((current) => [newRepo, ...current]);
    setSelectedRepoId(newRepo.id);
    setRepoQuery("");
    pushActivity("Repo added", `${label} was added to the workspace and is ready for ARIS inspection.`, "connected");
  };

  const applyDecisionToTask = (decision, task) => {
    if (!task || !decision.taskStatus) return;

    updateTaskState(task.id, decision.taskStatus, decision.taskUpdate || task.latestUpdate);

    if (decision.taskStatus === "Running") {
      setTimeout(() => {
        updateTaskState(
          task.id,
          "Review",
          "Forge finished the demo-safe run and returned a review packet for ARIS."
        );
        setWorkerState({
          title: "Validation Packet",
          status: "Review",
          lines: [
            "Forge completed the safe demo run.",
            "ARIS is holding the result in review until you approve or re-route it.",
            "Evolving core remains locked and unavailable.",
          ],
        });
        pushActivity("Review packet ready", `${task.id} moved from Running to Review after the Forge lane returned.`, "review");
      }, 1200);
    }
  };

  const handleDispatch = (explicitPrompt) => {
    const prompt = String(explicitPrompt || chatInput || "").trim();
    if (!prompt) return;

    const decision = buildDecision({
      prompt,
      brain,
      repo: selectedRepo,
      task: selectedTask,
    });

    const userMessage = {
      id: `msg-${Date.now()}-user`,
      role: "user",
      content: prompt,
      meta: `${brain.mode} • ${brain.scope} • ${brain.target}`,
    };
    const assistantMessage = {
      id: `msg-${Date.now()}-aris`,
      role: "aris",
      content: decision.content,
      meta: `${brain.permission} • ${brain.responseStyle}`,
      summary: decision.summary,
      route: decision.route,
      suggestions: decision.suggestions,
      pills: [...decision.pills, "Evolving Core Locked"],
      tone: decision.tone,
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);
    setChatInput("");
    setWorkerState({
      title: decision.workerTitle,
      status: decision.workerStatus,
      lines: decision.workerLines,
    });
    pushActivity(decision.activityTitle, decision.activityDetail, decision.tone);
    applyDecisionToTask(decision, selectedTask);
  };

  const workerStatuses = [
    { label: "ARIS", value: "Active", tone: "connected", detail: "Speaking layer and orchestration surface" },
    { label: "Forge", value: "Available", tone: "running", detail: "Worker and execution target" },
    { label: "ForgeEval", value: "Optional", tone: "review", detail: "Evaluation lane when selected" },
    { label: "Evolving Core", value: "Locked", tone: "warning", detail: "Protected and unavailable from demo mode" },
  ];

  const branchHints = selectedRepo
    ? [
        `Branch in view: ${selectedRepo.branch}`,
        `Context hint: ${selectedRepo.contextHint}`,
        "Protected routes remain locked and are not exposed in controls or route lists.",
      ]
    : ["Select a repo to load branch hints and workspace context."];

  const approvalSummary =
    selectedTask?.status === "Review"
      ? "Approval gated. A review packet is waiting in the selected task lane."
      : brain.permission === "Approval Required"
        ? "Approval required on the next worker handoff."
        : "Approval is not required for the current mock route, but protected boundaries remain locked.";

  return (
    <div
      className="min-h-screen bg-[#061018] text-slate-100"
      style={{ fontFamily: '"IBM Plex Sans", "Avenir Next", "Segoe UI", sans-serif' }}
    >
      <div className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-[360px] bg-[radial-gradient(circle_at_top,rgba(224,169,90,0.2),transparent_58%)]" />
        <div className="absolute right-[-120px] top-[16%] h-72 w-72 rounded-full bg-cyan-500/10 blur-3xl" />
        <div className="absolute left-[-100px] bottom-[-120px] h-80 w-80 rounded-full bg-violet-500/10 blur-3xl" />
      </div>

      <div className="relative mx-auto flex min-h-screen max-w-[1860px] flex-col px-4 py-4 sm:px-6">
        <motion.header
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="mb-4 rounded-[34px] border border-white/10 bg-[#0b141c]/88 px-6 py-5 shadow-[0_35px_90px_-48px_rgba(0,0,0,0.82)] backdrop-blur-xl"
        >
          <div className="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
            <div>
              <div
                className="text-[12px] font-medium uppercase tracking-[0.3em] text-[#e0a95a]"
                style={{ fontFamily: '"Sora", "Avenir Next", sans-serif' }}
              >
                ARIS Workspace Demo
              </div>
              <div
                className="mt-2 text-3xl font-semibold text-slate-50 sm:text-[2.35rem]"
                style={{ fontFamily: '"Sora", "Avenir Next", sans-serif' }}
              >
                Brain controls, task routing, and workspace intelligence with ARIS at the front.
              </div>
              <div className="mt-3 max-w-4xl text-sm leading-7 text-slate-400 sm:text-[15px]">
                ARIS remains the speaking layer, reasoning layer, and operator-facing intelligence. Forge is available
                as a worker lane, ForgeEval is available as an evaluation lane, and the evolving core remains locked and
                unavailable from this demo.
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge tone="connected">ARIS Active</Badge>
                <Badge tone="running">Forge Available</Badge>
                <Badge tone="review">ForgeEval Optional</Badge>
                <Badge tone="warning">Evolving Core Locked</Badge>
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              <Metric label="Repos" value={counts.repos} tone="connected" />
              <Metric label="Running" value={counts.running} tone="running" />
              <Metric label="Review" value={counts.review} tone="review" />
              <Metric label="Done" value={counts.done} tone="connected" />
            </div>
          </div>
        </motion.header>

        <div className="grid flex-1 grid-cols-1 gap-4 xl:grid-cols-[290px,minmax(0,1fr),370px]">
          <motion.aside
            initial={{ opacity: 0, x: -18 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.42, delay: 0.05, ease: "easeOut" }}
            className="flex min-h-[320px] flex-col gap-4 rounded-[30px] border border-white/10 bg-[#0b141c]/82 p-4 shadow-[0_28px_80px_-42px_rgba(0,0,0,0.72)] backdrop-blur-xl"
          >
            <Panel eyebrow="Navigation" title="Workspace deck" subtitle="Repos, recent tasks, and branch-aware context stay visible here." className="p-4">
              <div className="space-y-2">
                {navigationItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => setActiveNav(item.id)}
                    className={cn(
                      "flex w-full items-center justify-between rounded-2xl border px-4 py-3 text-left transition",
                      activeNav === item.id
                        ? "border-[#e0a95a]/40 bg-[#111a23] text-slate-50"
                        : "border-white/8 bg-white/[0.03] text-slate-300 hover:bg-white/[0.05]"
                    )}
                  >
                    <span className="text-sm font-medium">{item.label}</span>
                    <Marker tone={activeNav === item.id ? "connected" : "neutral"} />
                  </button>
                ))}
              </div>
            </Panel>

            <Panel eyebrow="Repos" title="Active workspaces" subtitle="Select a repo to set branch and context hints." className="p-4">
              <div className="flex gap-2">
                <Input
                  value={repoQuery}
                  onChange={(event) => setRepoQuery(event.target.value)}
                  placeholder="Search repos or branches"
                />
                <Button type="button" variant="secondary" onClick={handleAddRepo}>
                  Add Repo
                </Button>
              </div>

              <div className="mt-4 space-y-2">
                <AnimatePresence initial={false}>
                  {filteredRepos.map((repo) => (
                    <motion.button
                      key={repo.id}
                      layout
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      onClick={() => selectRepo(repo)}
                      className={cn(
                        "w-full rounded-[24px] border p-4 text-left transition",
                        repo.id === selectedRepoId
                          ? "border-[#e0a95a]/40 bg-[#111a23]"
                          : "border-white/8 bg-white/[0.03] hover:bg-white/[0.05]"
                      )}
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="text-base font-semibold text-slate-50">{repo.name}</div>
                          <div className="mt-1 text-sm text-slate-400">{repo.branch}</div>
                        </div>
                        <Badge tone={statusTone(repo.status)}>{repo.status}</Badge>
                      </div>
                      <div className="mt-3 text-sm leading-6 text-slate-300">{repo.summary}</div>
                      <div className="mt-3 text-xs text-slate-500">{repo.lastUpdate}</div>
                    </motion.button>
                  ))}
                </AnimatePresence>
              </div>
            </Panel>

            <Panel eyebrow="Context" title="Branch hints" subtitle="Repo-level branch and boundary hints for the current workspace." className="p-4">
              <div className="space-y-3">
                {branchHints.map((item) => (
                  <div key={item} className="rounded-[22px] border border-white/8 bg-white/[0.03] px-4 py-3 text-sm leading-6 text-slate-300">
                    {item}
                  </div>
                ))}
              </div>
            </Panel>

            <Panel eyebrow="Recent Tasks" title="Fast access" subtitle="Jump directly into the next likely operator focus." className="p-4">
              <div className="space-y-2">
                {recentTasks.map((task) => (
                  <button
                    key={task.id}
                    type="button"
                    onClick={() => selectTask(task)}
                    className="flex w-full items-center justify-between rounded-2xl border border-white/8 bg-white/[0.03] px-4 py-3 text-left transition hover:bg-white/[0.05]"
                  >
                    <div>
                      <div className="text-sm font-medium text-slate-100">{task.title}</div>
                      <div className="mt-1 text-xs text-slate-500">{task.id}</div>
                    </div>
                    <Badge tone={statusTone(task.status)}>{task.status}</Badge>
                  </button>
                ))}
              </div>
            </Panel>
          </motion.aside>

          <motion.main
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42, delay: 0.08, ease: "easeOut" }}
            className="flex min-w-0 flex-col gap-4"
          >
            <Panel
              eyebrow="Operator Chat"
              title="ARIS conversation deck"
              subtitle="ARIS stays the speaker while the selected brain controls shape how she reasons, routes, and explains."
              aside={<Badge tone={previewDecision.blocked ? "warning" : statusTone(previewDecision.workerStatus)}>{previewDecision.summary}</Badge>}
            >
              <div className="mb-4 flex flex-wrap gap-2">
                <Badge tone="connected">{selectedRepo ? selectedRepo.name : "No repo selected"}</Badge>
                <Badge tone="review">{selectedTask ? selectedTask.id : "No task selected"}</Badge>
                <Badge tone="running">{primaryActionLabel(brain.target)}</Badge>
                <Badge tone="warning">Evolving Core Locked</Badge>
              </div>

              <div className="rounded-[28px] border border-white/8 bg-[#091219] p-4">
                <div className="text-[11px] font-medium uppercase tracking-[0.24em] text-slate-500">Chat Thread</div>
                <div className="mt-4 max-h-[420px] space-y-3 overflow-y-auto pr-1">
                  <AnimatePresence initial={false}>
                    {messages.map((message) => (
                      <MessageBubble key={message.id} message={message} />
                    ))}
                  </AnimatePresence>
                </div>
              </div>

              <div className="mt-5 rounded-[30px] border border-white/8 bg-[#091219] p-4">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div>
                    <div className="text-[11px] font-medium uppercase tracking-[0.24em] text-slate-500">Brain Controls</div>
                    <div className="mt-1 text-sm text-slate-300">
                      These selectors shape ARIS wording, routing, summaries, and safe task progression.
                    </div>
                  </div>
                  <Badge tone={previewDecision.blocked ? "warning" : "connected"}>{brain.target}</Badge>
                </div>

                <div className="grid gap-3 xl:grid-cols-5">
                  <SelectField label="Mode" value={brain.mode} options={modeOptions} onChange={(value) => setBrain((current) => ({ ...current, mode: value }))} />
                  <SelectField label="Scope" value={brain.scope} options={scopeOptions} onChange={(value) => setBrain((current) => ({ ...current, scope: value }))} />
                  <SelectField label="Target" value={brain.target} options={targetOptions} onChange={(value) => setBrain((current) => ({ ...current, target: value }))} />
                  <SelectField label="Permission / Risk" value={brain.permission} options={permissionOptions} onChange={(value) => setBrain((current) => ({ ...current, permission: value }))} />
                  <SelectField label="Response Style" value={brain.responseStyle} options={responseStyleOptions} onChange={(value) => setBrain((current) => ({ ...current, responseStyle: value }))} />
                </div>
              </div>

              <div className="mt-5 rounded-[30px] border border-white/8 bg-[#091219] p-4">
                <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
                  <div className="min-w-0 flex-1">
                    <div className="text-[11px] font-medium uppercase tracking-[0.24em] text-slate-500">Decision Preview</div>
                    <div className="mt-2 text-base font-semibold text-slate-50">{previewDecision.summary}</div>
                    <div className="mt-2 text-sm leading-6 text-slate-300">{previewDecision.content}</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {previewDecision.pills.map((pill) => (
                        <Badge key={`preview-${pill}`} tone={statusTone(pill)}>
                          {pill}
                        </Badge>
                      ))}
                      <Badge tone="warning">Evolving Core Locked</Badge>
                    </div>
                  </div>
                  <div className="min-w-[260px] rounded-[24px] border border-white/8 bg-white/[0.03] px-4 py-4">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Route indicator</div>
                    <div className="mt-3 text-sm leading-7 text-slate-100">{previewDecision.route.join(" -> ")}</div>
                    <div className="mt-4 space-y-2">
                      {previewDecision.suggestions.map((item) => (
                        <div key={item} className="rounded-2xl border border-white/8 bg-[#0d151d] px-3 py-2 text-xs text-slate-300">
                          {item}
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-5">
                <Textarea
                  rows={4}
                  value={chatInput}
                  onChange={(event) => setChatInput(event.target.value)}
                  placeholder="Ask ARIS to inspect, plan, build, evaluate, route, remember, or hold for approval."
                />
                <div className="mt-4 flex flex-wrap gap-3">
                  <Button type="button" size="lg" onClick={() => handleDispatch()}>
                    {primaryActionLabel(brain.target)}
                  </Button>
                  <Button
                    type="button"
                    size="lg"
                    variant="secondary"
                    onClick={() =>
                      handleDispatch(
                        brain.target === "Forge"
                          ? `Route ${selectedTask ? selectedTask.title : "the selected task"} through Forge and keep ARIS as the speaker.`
                          : brain.target === "ForgeEval"
                            ? `Send ${selectedTask ? selectedTask.title : "the selected task"} to ForgeEval and summarize the findings.`
                            : `Use ${brain.mode} mode on ${scopeLabel(brain, selectedRepo, selectedTask)}.`
                      )
                    }
                  >
                    Send Structured Prompt
                  </Button>
                  <Button type="button" size="lg" variant="ghost" onClick={() => setChatInput("The evolving core should handle this next.")}>
                    Test Protected Boundary
                  </Button>
                </div>
              </div>
            </Panel>

            <Panel eyebrow="Task Board" title="Workspace tasks" subtitle="Running, review, and done states stay visible under the ARIS surface.">
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
                <div className="flex flex-wrap gap-2">
                  {taskTabs.map((tab) => {
                    const count = tab === "All" ? tasks.length : tasks.filter((task) => task.status === tab).length;
                    return (
                      <button
                        key={tab}
                        type="button"
                        onClick={() => setTaskTab(tab)}
                        className={cn(
                          "rounded-full border px-4 py-2 text-sm transition",
                          taskTab === tab
                            ? "border-[#e0a95a]/40 bg-[#111a23] text-slate-50"
                            : "border-white/8 bg-white/[0.03] text-slate-300 hover:bg-white/[0.05]"
                        )}
                      >
                        {tab} ({count})
                      </button>
                    );
                  })}
                </div>
                <Input value={taskQuery} onChange={(event) => setTaskQuery(event.target.value)} placeholder="Search tasks, repo, or update" className="max-w-[320px]" />
              </div>

              <div className="mt-4 grid gap-4 xl:grid-cols-2">
                <AnimatePresence initial={false}>
                  {filteredTasks.map((task) => (
                    <TaskCard
                      key={task.id}
                      task={task}
                      repoName={repos.find((repo) => repo.id === task.repoId)?.name || "Workspace"}
                      active={task.id === selectedTaskId}
                      onSelect={selectTask}
                      onApprove={handleApprovalComplete}
                      onQuickRoute={simulateQuickForgeRoute}
                    />
                  ))}
                </AnimatePresence>
              </div>
            </Panel>
          </motion.main>

          <motion.aside
            initial={{ opacity: 0, x: 18 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.42, delay: 0.11, ease: "easeOut" }}
            className="flex min-h-[320px] flex-col gap-4"
          >
            <Panel eyebrow="Selection" title="Workspace context" subtitle="Selected repo and task stay pinned while ARIS speaks from the center surface.">
              <div className="space-y-4">
                <div className="rounded-[24px] border border-white/8 bg-white/[0.03] p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Selected Repo</div>
                      <div className="mt-2 text-lg font-semibold text-slate-50">{selectedRepo ? selectedRepo.name : "No repo selected"}</div>
                    </div>
                    {selectedRepo ? <Badge tone={statusTone(selectedRepo.status)}>{selectedRepo.status}</Badge> : null}
                  </div>
                  {selectedRepo ? (
                    <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                      <div>Branch: {selectedRepo.branch}</div>
                      <div>Path: {selectedRepo.path}</div>
                      <div>{selectedRepo.contextHint}</div>
                    </div>
                  ) : null}
                </div>

                <div className="rounded-[24px] border border-white/8 bg-white/[0.03] p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[11px] uppercase tracking-[0.22em] text-slate-500">Selected Task</div>
                      <div className="mt-2 text-lg font-semibold text-slate-50">{selectedTask ? selectedTask.title : "No task selected"}</div>
                    </div>
                    {selectedTask ? <Badge tone={statusTone(selectedTask.status)}>{selectedTask.status}</Badge> : null}
                  </div>
                  {selectedTask ? (
                    <div className="mt-3 space-y-2 text-sm leading-6 text-slate-300">
                      <div>ID: {selectedTask.id}</div>
                      <div>Priority: {selectedTask.priority}</div>
                      <div>{selectedTask.latestUpdate}</div>
                    </div>
                  ) : null}
                </div>
              </div>
            </Panel>

            <Panel eyebrow="Brain State" title="Active brain controls" subtitle="This card mirrors the current control bar so the reasoning posture is always visible.">
              <div className="grid gap-3 sm:grid-cols-2">
                {[
                  ["Mode", brain.mode],
                  ["Scope", brain.scope],
                  ["Target", brain.target],
                  ["Permission", brain.permission],
                  ["Response Style", brain.responseStyle],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-[22px] border border-white/8 bg-white/[0.03] px-4 py-3">
                    <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">{label}</div>
                    <div className="mt-2 text-sm font-medium text-slate-100">{value}</div>
                  </div>
                ))}
              </div>
              <div className="mt-4 flex flex-wrap gap-2">
                <Badge tone="running">Forge Available</Badge>
                <Badge tone={brain.permission === "Approval Required" ? "review" : "neutral"}>Approval Gated</Badge>
                <Badge tone="warning">Evolving Core Locked</Badge>
              </div>
            </Panel>

            <Panel eyebrow="Approvals" title="Execution and approval state" subtitle="ARIS keeps approval, execution, and worker status visible without giving up the voice.">
              <div className="space-y-3">
                <div className="rounded-[22px] border border-white/8 bg-white/[0.03] px-4 py-4">
                  <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Approval summary</div>
                  <div className="mt-2 text-sm leading-6 text-slate-200">{approvalSummary}</div>
                </div>
                <div className="rounded-[22px] border border-white/8 bg-white/[0.03] px-4 py-4">
                  <div className="text-[10px] uppercase tracking-[0.22em] text-slate-500">Current route</div>
                  <div className="mt-2 text-sm leading-6 text-slate-200">{previewDecision.route.join(" -> ")}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    onClick={() => selectedTask && handleApprovalComplete(selectedTask)}
                  >
                    Approve Selected
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => selectedTask && simulateQuickForgeRoute(selectedTask)}
                  >
                    Route Selected To Forge
                  </Button>
                </div>
              </div>
            </Panel>

            <Panel eyebrow="Worker Status" title={workerState.title} subtitle="Forge and ForgeEval remain tools. ARIS stays the speaker and operator-facing intelligence.">
              <div className="mb-4 flex items-center gap-2">
                <Badge tone={statusTone(workerState.status)}>{workerState.status}</Badge>
                <Badge tone="warning">Evolving Core Locked</Badge>
              </div>

              <div className="space-y-3">
                {workerState.lines.map((line) => (
                  <WorkerLine key={line} value={line} />
                ))}
              </div>

              <div className="mt-5 grid gap-2">
                {workerStatuses.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-start justify-between gap-3 rounded-[22px] border border-white/8 bg-white/[0.03] px-4 py-3"
                  >
                    <div>
                      <div className="text-sm font-medium text-slate-100">{item.label}</div>
                      <div className="mt-1 text-xs leading-5 text-slate-500">{item.detail}</div>
                    </div>
                    <Badge tone={item.tone}>{item.value}</Badge>
                  </div>
                ))}
              </div>
            </Panel>

            <Panel eyebrow="Activity" title="Recent workspace activity" subtitle="Mock decision behavior, route changes, and approval updates stay visible here.">
              <div className="space-y-3">
                {activity.map((entry) => (
                  <div key={entry.id} className="rounded-[22px] border border-white/8 bg-white/[0.03] px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <Marker tone={entry.tone} />
                        <div className="text-sm font-medium text-slate-100">{entry.title}</div>
                      </div>
                      <div className="text-xs text-slate-500">{entry.time}</div>
                    </div>
                    <div className="mt-2 text-sm leading-6 text-slate-400">{entry.detail}</div>
                  </div>
                ))}
              </div>
            </Panel>
          </motion.aside>
        </div>
      </div>
    </div>
  );
}
