from __future__ import annotations

from html import escape
import json
import os
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .desktop_support import ArisRuntimeDesktopHost, DesktopChatEvent, DesktopSnapshot, clean_operator_text, select_active_task
from .voice import speak
from .workspace_logic import (
    BRAIN_MODE_OPTIONS,
    BRAIN_PERMISSION_OPTIONS,
    BRAIN_RESPONSE_STYLE_OPTIONS,
    BRAIN_SCOPE_OPTIONS,
    BRAIN_TARGET_OPTIONS,
    DEFAULT_BRAIN_STATE,
    current_brain_state,
    route_for_target,
    seed_workspace_messages,
    workspace_status_pills,
)


def _pretty_json(value: object) -> str:
    return json.dumps(value, indent=2, ensure_ascii=True)


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _profile_brain_defaults(profile_id: str) -> dict[str, str]:
    del profile_id
    defaults = dict(DEFAULT_BRAIN_STATE)
    defaults.update(
        {
            "mode": "Build",
            "scope": "Selected Repo",
            "target": "Forge",
            "permission": "Approval Required",
            "response_style": "Technical",
        }
    )
    return defaults


def _profile_studio_name(profile_id: str) -> str:
    del profile_id
    return "ARIS Studio V2"


def _status_style(status: str) -> str:
    normalized = str(status or "").strip().lower()
    if normalized in {"ready", "live", "active", "enforced", "extracted", "required", "staged", "nominal"}:
        background = "#183927"
        border = "#2f8051"
        foreground = "#ccefd8"
    elif normalized in {"blocked", "stripped", "offline", "missing", "hard", "fail"}:
        background = "#3a181b"
        border = "#8d3943"
        foreground = "#f5c2c9"
    elif normalized in {"degraded", "warning", "soft"}:
        background = "#3b2a10"
        border = "#9b6c1b"
        foreground = "#f7ddb0"
    else:
        background = "#17212a"
        border = "#365068"
        foreground = "#d6e0ea"
    return (
        "QLabel {"
        f"background:{background};"
        f"border:1px solid {border};"
        f"color:{foreground};"
        "border-radius:11px;"
        "padding:5px 10px;"
        "font-size:11px;"
        "font-weight:600;"
        "letter-spacing:0.6px;"
        "}"
    )


def _pill_span(label: str, tone: str = "neutral") -> str:
    colors = {
        "neutral": ("#17212a", "#365068", "#d6e0ea"),
        "connected": ("#183927", "#2f8051", "#ccefd8"),
        "review": ("#2b2140", "#6f55a8", "#e3d8fb"),
        "warning": ("#3b2a10", "#9b6c1b", "#f7ddb0"),
    }
    background, border, foreground = colors.get(tone, colors["neutral"])
    return (
        f"<span style=\"display:inline-block;background:{background};border:1px solid {border};"
        f"color:{foreground};border-radius:11px;padding:5px 10px;margin:0 8px 8px 0;"
        "font-size:11px;font-weight:700;letter-spacing:0.7px;\">"
        f"{escape(label)}</span>"
    )


DESKTOP_HYDRATION_ROUTE = "Input -> Forge -> Eval -> Outcome -> Evolve"
DESKTOP_HYDRATION_REASON = (
    "ARIS Desktop is hydrating law, halls, workspace surfaces, and operator state before "
    "admitting a governed result."
)


def _render_transcript(messages: list[dict[str, Any]], partial_reply: str = "") -> str:
    blocks = [
        "<html><body style=\"background:#0c1217;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;\">"
    ]
    for message in messages:
        role = str(message.get("role", "assistant")).strip().lower() or "assistant"
        content = str(message.get("content", "")).strip()
        created_at = str(message.get("created_at", "")).strip()
        accent = "#e1a95f" if role == "user" else "#93c5fd" if role == "system" else "#edf2f7"
        label = "ARIS" if role == "assistant" else "RUNTIME" if role == "system" else role.upper()
        footer = f"<div style='font-size:11px;color:#7c93aa;margin-top:6px;'>{escape(created_at)}</div>" if created_at else ""
        blocks.append(
            "<div style=\"margin:0 0 18px 0;padding:14px 16px;border:1px solid #21313f;border-radius:16px;background:#111a21;\">"
            f"<div style=\"font-size:11px;letter-spacing:1.5px;font-weight:700;color:{accent};margin-bottom:8px;\">{escape(label)}</div>"
            f"<div style=\"white-space:pre-wrap;line-height:1.5;color:#edf2f7;\">{escape(content)}</div>"
            f"{footer}"
            "</div>"
        )
    if partial_reply:
        blocks.append(
            "<div style=\"margin:0 0 18px 0;padding:14px 16px;border:1px dashed #43617d;border-radius:16px;background:#111a21;\">"
            "<div style=\"font-size:11px;letter-spacing:1.5px;font-weight:700;color:#93c5fd;margin-bottom:8px;\">ARIS</div>"
            f"<div style=\"white-space:pre-wrap;line-height:1.5;color:#edf2f7;\">{escape(partial_reply)}</div>"
            "</div>"
        )
    blocks.append("</body></html>")
    return "".join(blocks)


class ChatWorker(QObject):
    event_received = Signal(object)
    failed = Signal(str)
    finished = Signal(str)

    def __init__(
        self,
        *,
        host: ArisRuntimeDesktopHost,
        session_id: str,
        user_message: str,
        mode: str,
        fast_mode: bool,
    ) -> None:
        super().__init__()
        self.host = host
        self.session_id = session_id
        self.user_message = user_message
        self.mode = mode
        self.fast_mode = fast_mode

    @Slot()
    def run(self) -> None:
        final_session_id = self.session_id
        try:
            for event in self.host.iter_chat_events(
                session_id=self.session_id,
                user_message=self.user_message,
                mode=self.mode,
                fast_mode=self.fast_mode,
            ):
                if event.event == "done":
                    final_session_id = str(event.payload.get("session_id", final_session_id)).strip() or final_session_id
                self.event_received.emit(event)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(final_session_id)


class ApprovalWorker(QObject):
    event_received = Signal(object)
    failed = Signal(str)
    finished = Signal(str)

    def __init__(
        self,
        *,
        host: ArisRuntimeDesktopHost,
        session_id: str,
        approval_id: str,
        approved: bool,
    ) -> None:
        super().__init__()
        self.host = host
        self.session_id = session_id
        self.approval_id = approval_id
        self.approved = approved

    @Slot()
    def run(self) -> None:
        try:
            for event in self.host.iter_approval_events(
                session_id=self.session_id,
                approval_id=self.approval_id,
                approved=self.approved,
            ):
                self.event_received.emit(event)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(self.session_id)


class SnapshotWorker(QObject):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, *, host: ArisRuntimeDesktopHost, session_id: str | None) -> None:
        super().__init__()
        self.host = host
        self.session_id = session_id

    @Slot()
    def run(self) -> None:
        try:
            snapshot = self.host.snapshot(self.session_id)
            if snapshot.session_id is None:
                session_id = self.host.ensure_session()
                snapshot = self.host.snapshot(session_id)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.ready.emit(snapshot)


class ArisRuntimeDesktopWindow(QMainWindow):
    def __init__(self, host: ArisRuntimeDesktopHost) -> None:
        super().__init__()
        self.host = host
        self._runtime_hydrating = False
        self.snapshot: DesktopSnapshot | None = None
        self.current_session_id: str | None = None
        self._transcript_cache: list[dict[str, Any]] = []
        self._stream_base_messages: list[dict[str, Any]] = []
        self._streaming_reply = ""
        self._live_task_stream_lines: list[str] = []
        self._latest_chat_meta: dict[str, Any] = {}
        self._chat_thread: QThread | None = None
        self._chat_worker: ChatWorker | None = None
        self._refresh_thread: QThread | None = None
        self._refresh_worker: SnapshotWorker | None = None
        self._queued_refresh_session_id: str | None = None
        self._workspace_repo_query = ""
        self._workspace_task_query = ""
        self._workspace_task_tab = "All"
        self._workspace_transcript_override: list[dict[str, Any]] = []
        self._workspace_task_overrides: dict[str, dict[str, Any]] = {}
        self._workspace_activity_overrides: list[dict[str, Any]] = []
        self._workspace_worker_override: dict[str, Any] | None = None
        self._selected_workspace_repo_id: str | None = None
        self._selected_workspace_task_id: str | None = None
        self._selected_workspace_file_path: str | None = None
        self._active_workspace_id: str | None = None
        self._workspace_file_search_query = ""
        self._workspace_search_results_cache: list[dict[str, Any]] = []
        self._repo_context_attached = True
        self._linked_task_enabled = True
        self._approval_mode = "Guarded"
        self._inspect_panel_expanded = False
        self._active_run_task_id: str | None = None
        self._loaded_task_memory_task_id: str | None = None
        self._upgrade_status_overrides: dict[str, str] = {}
        self._last_announced_brain_mode = ""
        self._brain_defaults = _profile_brain_defaults(self.host.profile.id)
        self._studio_name = _profile_studio_name(self.host.profile.id)

        self.setWindowTitle(self.host.profile.desktop_title)
        self.resize(1560, 980)
        self.setMinimumSize(1320, 860)
        self._build_ui()
        self._apply_style()

        self.current_session_id = self.host.ensure_session()
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.tabs.setCurrentIndex(0)

        self.refresh_timer = QTimer(self)
        self.refresh_timer.setInterval(15000)
        self.refresh_timer.timeout.connect(self._refresh_if_idle)
        self.refresh_timer.start()

    def _build_ui(self) -> None:
        central = QWidget(self)
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(18, 18, 18, 18)
        root_layout.setSpacing(18)

        rail = QFrame()
        rail.setObjectName("sideRail")
        rail.setFixedWidth(320)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(22, 22, 22, 22)
        rail_layout.setSpacing(14)

        brand = QLabel(self._studio_name)
        brand.setObjectName("brandTitle")
        subtitle = QLabel("operator workspace\nsingle-lane runtime shell")
        subtitle.setObjectName("brandSubtitle")

        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        self.health_badge = QLabel("READY")
        self.mode_badge = QLabel("1001")
        self.kill_badge = QLabel("NOMINAL")
        badge_row.addWidget(self.health_badge)
        badge_row.addWidget(self.mode_badge)
        badge_row.addWidget(self.kill_badge)

        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.new_session_button = QPushButton("Add Repo")
        self.refresh_button = QPushButton("Refresh")
        self.new_session_button.clicked.connect(self._add_workspace)
        self.refresh_button.clicked.connect(lambda: self.refresh_from_runtime(select_session_id=self.current_session_id))
        action_row.addWidget(self.new_session_button)
        action_row.addWidget(self.refresh_button)

        self.session_list = QListWidget()
        self.session_list.itemSelectionChanged.connect(self._on_session_changed)
        project_label = QLabel("Projects")
        project_label.setObjectName("railHeading")
        self.project_list = QListWidget()
        self.project_list.itemSelectionChanged.connect(self._on_sidebar_project_changed)
        task_label = QLabel("Tasks")
        task_label.setObjectName("railHeading")
        self.sidebar_task_list = QListWidget()
        self.sidebar_task_list.itemSelectionChanged.connect(self._on_sidebar_task_changed)

        self.rail_info = QLabel("")
        self.rail_info.setWordWrap(True)
        self.rail_info.setObjectName("railInfo")

        rail_layout.addWidget(brand)
        rail_layout.addWidget(subtitle)
        rail_layout.addLayout(badge_row)
        rail_layout.addLayout(action_row)
        rail_layout.addSpacing(10)
        rail_layout.addWidget(project_label)
        rail_layout.addWidget(self.project_list, 1)
        rail_layout.addWidget(task_label)
        rail_layout.addWidget(self.sidebar_task_list, 1)
        rail_layout.addWidget(self.rail_info)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(16)

        header = QFrame()
        header.setObjectName("heroPanel")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(24, 22, 24, 22)
        header_layout.setSpacing(8)
        self.hero_title = QLabel(self._studio_name)
        self.hero_title.setObjectName("heroTitle")
        self.hero_subtitle = QLabel("")
        self.hero_subtitle.setObjectName("heroSubtitle")
        self.route_label = QLabel("")
        self.route_label.setObjectName("routeLabel")
        header_layout.addWidget(self.hero_title)
        header_layout.addWidget(self.hero_subtitle)
        header_layout.addWidget(self.route_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_operator_tab(), "Studio")
        self.tabs.setTabBarAutoHide(True)

        main_layout.addWidget(header)
        main_layout.addWidget(self.tabs, 1)

        root_layout.addWidget(rail)
        root_layout.addWidget(main, 1)

    def _build_overview_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(16)

        self.overview_summary = QTextBrowser()
        self.overview_summary.setOpenExternalLinks(False)

        feature_splitter = QSplitter(Qt.Horizontal)
        self.feature_tree = QTreeWidget()
        self.feature_tree.setHeaderLabels(["Surface", "Status", "Source", "Detail"])
        self.feature_tree.setRootIsDecorated(False)
        self.feature_tree.setAlternatingRowColors(True)
        self.runtime_inspector = QPlainTextEdit()
        self.runtime_inspector.setReadOnly(True)
        feature_splitter.addWidget(self.feature_tree)
        feature_splitter.addWidget(self.runtime_inspector)
        feature_splitter.setStretchFactor(0, 2)
        feature_splitter.setStretchFactor(1, 3)

        self.target_tree = QTreeWidget()
        self.target_tree.setHeaderLabels(["Target", "Build Host", "Artifact", "Detail"])
        self.target_tree.setRootIsDecorated(False)
        self.target_tree.setAlternatingRowColors(True)

        layout.addWidget(self.overview_summary)
        layout.addWidget(feature_splitter, 1)
        layout.addWidget(self.target_tree, 0)
        return tab

    def _build_labeled_combo(self, label_text: str, options: tuple[str, ...], default_value: str) -> tuple[QWidget, QComboBox]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        label = QLabel(label_text)
        label.setObjectName("microDetail")
        combo = QComboBox()
        combo.addItems(list(options))
        if default_value in options:
            combo.setCurrentText(default_value)
        layout.addWidget(label)
        layout.addWidget(combo)
        return container, combo

    def _build_operator_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        status_strip = QFrame()
        status_strip.setObjectName("composerPanel")
        status_layout = QHBoxLayout(status_strip)
        status_layout.setContentsMargins(18, 14, 18, 14)
        status_layout.setSpacing(14)

        def add_status_field(label_text: str) -> QLabel:
            frame = QFrame()
            frame.setObjectName("statusField")
            field_layout = QVBoxLayout(frame)
            field_layout.setContentsMargins(10, 6, 10, 6)
            field_layout.setSpacing(2)
            label = QLabel(label_text)
            label.setObjectName("microDetail")
            value = QLabel("--")
            value.setObjectName("statusValue")
            field_layout.addWidget(label)
            field_layout.addWidget(value)
            status_layout.addWidget(frame)
            return value

        self.status_brain_value = add_status_field("Mode")
        self.status_tier_value = add_status_field("Access")
        self.status_workspace_value = add_status_field("Workspace")
        self.status_upgrade_value = add_status_field("Review")
        self.status_memory_value = add_status_field("Memory")
        self.status_voice_value = add_status_field("Session")
        status_layout.addStretch(1)
        self.operator_session_label = QLabel("")
        self.operator_session_label.setObjectName("microDetail")
        status_layout.addWidget(self.operator_session_label)

        explorer_panel = QFrame()
        explorer_panel.setObjectName("composerPanel")
        explorer_panel.setMinimumWidth(320)
        explorer_layout = QVBoxLayout(explorer_panel)
        explorer_layout.setContentsMargins(18, 18, 18, 18)
        explorer_layout.setSpacing(10)
        explorer_layout.addWidget(QLabel("Workspaces"))
        selector_row = QHBoxLayout()
        selector_row.setSpacing(8)
        self.workspace_selector = QComboBox()
        self.workspace_selector.currentIndexChanged.connect(self._on_active_workspace_changed)
        self.workspace_add_workspace_button = QPushButton("Add Workspace")
        self.workspace_add_workspace_button.clicked.connect(self._add_workspace)
        selector_row.addWidget(self.workspace_selector, 1)
        selector_row.addWidget(self.workspace_add_workspace_button)
        explorer_layout.addLayout(selector_row)
        self.workspace_file_search = QLineEdit()
        self.workspace_file_search.setPlaceholderText("Search active workspace files")
        self.workspace_file_search.textChanged.connect(self._on_workspace_file_search_changed)
        explorer_layout.addWidget(self.workspace_file_search)
        self.workspace_file_tree = QTreeWidget()
        self.workspace_file_tree.setHeaderLabels(["Path", "Type"])
        self.workspace_file_tree.itemSelectionChanged.connect(self._on_workspace_file_changed)
        explorer_layout.addWidget(self.workspace_file_tree, 4)
        explorer_layout.addWidget(QLabel("Search Results"))
        self.workspace_search_results = QListWidget()
        self.workspace_search_results.itemSelectionChanged.connect(self._on_workspace_search_result_changed)
        self.workspace_search_results.setFixedHeight(140)
        explorer_layout.addWidget(self.workspace_search_results)
        file_action_row = QHBoxLayout()
        file_action_row.setSpacing(8)
        self.workspace_open_file_button = QPushButton("Open")
        self.workspace_open_file_button.clicked.connect(self._open_selected_workspace_target)
        self.workspace_copy_path_button = QPushButton("Copy Path")
        self.workspace_copy_path_button.clicked.connect(lambda: self._run_workspace_file_action("copy_path"))
        self.workspace_send_to_aris_button = QPushButton("Send To ARIS")
        self.workspace_send_to_aris_button.clicked.connect(lambda: self._run_workspace_file_action("send_to_aris"))
        self.workspace_inspect_file_button = QPushButton("Inspect")
        self.workspace_inspect_file_button.clicked.connect(lambda: self._run_workspace_file_action("inspect"))
        self.workspace_use_in_task_button = QPushButton("Use In Task")
        self.workspace_use_in_task_button.clicked.connect(lambda: self._run_workspace_file_action("use_in_task"))
        for button in (
            self.workspace_open_file_button,
            self.workspace_copy_path_button,
            self.workspace_send_to_aris_button,
            self.workspace_inspect_file_button,
            self.workspace_use_in_task_button,
        ):
            file_action_row.addWidget(button)
        explorer_layout.addLayout(file_action_row)
        explorer_layout.addWidget(QLabel("Workspace Notes"))
        self.workspace_recent_tasks = QPlainTextEdit()
        self.workspace_recent_tasks.setReadOnly(True)
        self.workspace_recent_tasks.setFixedHeight(120)
        explorer_layout.addWidget(self.workspace_recent_tasks)
        self.workspace_repo_footer = QLabel("")
        self.workspace_repo_footer.setWordWrap(True)
        self.workspace_repo_footer.setObjectName("microDetail")
        explorer_layout.addWidget(self.workspace_repo_footer)

        center_panel = QFrame()
        center_panel.setObjectName("composerPanel")
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(18, 18, 18, 18)
        center_layout.setSpacing(12)
        center_layout.addWidget(QLabel("Operator Run Loop"))
        self.task_lane_summary = QLabel("")
        self.task_lane_summary.setWordWrap(True)
        self.task_lane_summary.setObjectName("microDetail")
        center_layout.addWidget(self.task_lane_summary)

        chat_panel = QFrame()
        chat_panel.setObjectName("composerPanel")
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.setContentsMargins(16, 16, 16, 16)
        chat_layout.setSpacing(10)
        chat_header = QHBoxLayout()
        chat_header.setSpacing(10)
        chat_header.addWidget(QLabel("Task Intake"))
        chat_header.addStretch(1)
        self.workspace_brain_pills = QLabel("")
        self.workspace_brain_pills.setWordWrap(True)
        self.workspace_brain_pills.setObjectName("microDetail")
        chat_layout.addLayout(chat_header)

        selectors_row = QHBoxLayout()
        selectors_row.setSpacing(10)
        mode_wrap, self.brain_mode = self._build_labeled_combo(
            "Mode", BRAIN_MODE_OPTIONS, self._brain_defaults["mode"]
        )
        scope_wrap, self.brain_scope = self._build_labeled_combo(
            "Scope", BRAIN_SCOPE_OPTIONS, self._brain_defaults["scope"]
        )
        target_wrap, self.brain_target = self._build_labeled_combo(
            "Target", BRAIN_TARGET_OPTIONS, self._brain_defaults["target"]
        )
        permission_wrap, self.brain_permission = self._build_labeled_combo(
            "Tier", BRAIN_PERMISSION_OPTIONS, self._brain_defaults["permission"]
        )
        style_wrap, self.brain_response_style = self._build_labeled_combo(
            "Voice", BRAIN_RESPONSE_STYLE_OPTIONS, self._brain_defaults["response_style"]
        )
        for widget in (mode_wrap, scope_wrap, target_wrap, permission_wrap, style_wrap):
            selectors_row.addWidget(widget, 1)
        chat_layout.addLayout(selectors_row)
        for combo in (
            self.brain_mode,
            self.brain_scope,
            self.brain_target,
            self.brain_permission,
            self.brain_response_style,
        ):
            combo.currentTextChanged.connect(self._on_brain_controls_changed)

        self.repo_context_button = QPushButton("Detach Workspace Context")
        self.repo_context_button.clicked.connect(self._toggle_repo_context)
        self.link_task_button = QPushButton("Unlink Task")
        self.link_task_button.clicked.connect(self._toggle_link_task)
        self.approval_mode_button = QPushButton("Approval Mode: Guarded")
        self.approval_mode_button.clicked.connect(self._toggle_approval_mode)
        self.feedback_bug_button = QPushButton("Report Bug")
        self.feedback_bug_button.clicked.connect(lambda: self._collect_feedback("bug"))
        self.feedback_general_button = QPushButton("Give Feedback")
        self.feedback_general_button.clicked.connect(lambda: self._collect_feedback("confusing"))
        self.feedback_feature_button = QPushButton("Request Feature")
        self.feedback_feature_button.clicked.connect(lambda: self._collect_feedback("feature_request"))
        self.feedback_form_button = QPushButton("Open Form")
        self.feedback_form_button.clicked.connect(self._open_feedback_form)

        self.workspace_route_summary = QLabel("")
        self.workspace_route_summary.setWordWrap(True)
        self.workspace_route_summary.setObjectName("microDetail")
        self.workspace_prompt_context = QLabel("")
        self.workspace_prompt_context.setWordWrap(True)
        self.workspace_prompt_context.setObjectName("microDetail")

        composer = QFrame()
        composer.setObjectName("composerPanel")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(12, 12, 12, 12)
        composer_layout.setSpacing(8)
        composer_layout.addWidget(QLabel("Create Or Continue A Task"))
        self.chat_input = QPlainTextEdit()
        self.chat_input.setPlaceholderText(
            "Describe the task you want ARIS to run, inspect, or route through the governed runtime."
        )
        self.chat_input.setFixedHeight(110)
        self.send_button = QPushButton(self._send_button_label())
        self.send_button.clicked.connect(self._start_chat)
        composer_layout.addWidget(self.chat_input)
        composer_layout.addWidget(self.send_button, 0, Qt.AlignRight)
        chat_layout.addWidget(composer)

        operator_console_panel = QFrame()
        operator_console_panel.setObjectName("composerPanel")
        operator_console_layout = QVBoxLayout(operator_console_panel)
        operator_console_layout.setContentsMargins(16, 16, 16, 16)
        operator_console_layout.setSpacing(10)
        operator_console_layout.addWidget(QLabel("Operator Console"))
        operator_console_summary = QLabel(
            "Secondary surfaces stay here: operator configuration, transcript, run details, workspace tools, and logs."
        )
        operator_console_summary.setObjectName("microDetail")
        operator_console_summary.setWordWrap(True)
        operator_console_layout.addWidget(operator_console_summary)
        operator_console_layout.addLayout(selectors_row)
        operator_console_layout.addWidget(self.workspace_brain_pills)
        operator_console_layout.addWidget(self.workspace_route_summary)
        operator_console_layout.addWidget(self.workspace_prompt_context)

        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        chip_row.addWidget(self.repo_context_button)
        chip_row.addWidget(self.link_task_button)
        chip_row.addWidget(self.approval_mode_button)
        chip_row.addStretch(1)
        operator_console_layout.addLayout(chip_row)

        feedback_row = QHBoxLayout()
        feedback_row.setSpacing(8)
        feedback_row.addWidget(self.feedback_bug_button)
        feedback_row.addWidget(self.feedback_general_button)
        feedback_row.addWidget(self.feedback_feature_button)
        feedback_row.addWidget(self.feedback_form_button)
        operator_console_layout.addLayout(feedback_row)

        transcript_label = QLabel("Conversation Record")
        transcript_label.setObjectName("microDetail")
        operator_console_layout.addWidget(transcript_label)
        self.chat_output = QTextBrowser()
        self.chat_output.setOpenExternalLinks(False)
        self.chat_output.setMinimumHeight(180)
        operator_console_layout.addWidget(self.chat_output, 1)

        center_layout.addWidget(chat_panel, 1)
        center_layout.addWidget(self._build_primary_task_lane(), 3)

        self.inspect_summary_label = QLabel(
            "Inspect keeps workspace tools, governance, transcript, and logs secondary until you deliberately open them."
        )
        self.inspect_summary_label.setWordWrap(True)
        self.inspect_summary_label.setObjectName("microDetail")
        center_layout.addWidget(self.inspect_summary_label)
        self.inspect_toggle_button = QPushButton("Inspect ▼")
        self.inspect_toggle_button.clicked.connect(self._toggle_inspect_panel)
        center_layout.addWidget(self.inspect_toggle_button, 0, Qt.AlignLeft)

        self.inspect_panel = QFrame()
        self.inspect_panel.setObjectName("statusField")
        self.inspect_panel.setVisible(False)
        inspect_layout = QVBoxLayout(self.inspect_panel)
        inspect_layout.setContentsMargins(12, 12, 12, 12)
        inspect_layout.setSpacing(10)
        self.inspect_tabs = QTabWidget()
        inspect_layout.addWidget(self.inspect_tabs, 1)

        event_panel = QFrame()
        event_panel.setObjectName("composerPanel")
        event_layout = QVBoxLayout(event_panel)
        event_layout.setContentsMargins(18, 14, 18, 18)
        event_layout.setSpacing(8)
        event_header = QHBoxLayout()
        event_header.setSpacing(8)
        event_header.addWidget(QLabel("Events And Logs"))
        event_header.addStretch(1)
        self.event_stream_status = QLabel("Runtime stream online")
        self.event_stream_status.setObjectName("microDetail")
        event_header.addWidget(self.event_stream_status)
        event_layout.addLayout(event_header)
        self.workspace_activity_feed = QPlainTextEdit()
        self.workspace_activity_feed.setReadOnly(True)
        event_layout.addWidget(self.workspace_activity_feed, 1)

        self.studio_surface_tabs = QTabWidget()
        self.studio_surface_tabs.addTab(self._build_studio_governance_surface(), "Governance")
        self.studio_surface_tabs.addTab(self._build_studio_memory_surface(), "Memory")
        self.studio_surface_tabs.addTab(self._build_studio_upgrades_surface(), "Upgrades")
        self.studio_surface_tabs.addTab(self._build_studio_runtime_surface(), "Runtime")
        self.studio_surface_tabs.addTab(self._build_studio_replay_surface(), "Replay")
        self.studio_surface_tabs.addTab(self._build_studio_file_viewer_surface(), "File Viewer")

        self.inspect_operator_panel = operator_console_panel
        self.inspect_workspace_panel = explorer_panel
        self.inspect_surface_panel = self.studio_surface_tabs
        self.inspect_activity_panel = event_panel
        self.inspect_tabs.addTab(self.inspect_operator_panel, "Operator Console")
        self.inspect_tabs.addTab(self.inspect_workspace_panel, "Workspaces")
        self.inspect_tabs.addTab(self.inspect_surface_panel, "Inspect Surfaces")
        self.inspect_tabs.addTab(self.inspect_activity_panel, "Activity")
        center_layout.addWidget(self.inspect_panel, 2)

        layout.addWidget(status_strip)
        changes_panel = QFrame()
        changes_panel.setObjectName("composerPanel")
        changes_panel.setMinimumWidth(340)
        changes_layout = QVBoxLayout(changes_panel)
        changes_layout.setContentsMargins(18, 18, 18, 18)
        changes_layout.setSpacing(10)
        changes_layout.addWidget(QLabel("Changes"))
        self.workspace_changes_summary = QLabel("No workspace changes are waiting right now.")
        self.workspace_changes_summary.setWordWrap(True)
        self.workspace_changes_summary.setObjectName("microDetail")
        changes_layout.addWidget(self.workspace_changes_summary)
        self.workspace_changes_list = QListWidget()
        self.workspace_changes_list.itemSelectionChanged.connect(self._on_workspace_change_selected)
        changes_layout.addWidget(self.workspace_changes_list, 1)
        changes_layout.addWidget(QLabel("Diff Preview"))
        self.workspace_diff_preview = QPlainTextEdit()
        self.workspace_diff_preview.setReadOnly(True)
        changes_layout.addWidget(self.workspace_diff_preview, 2)

        body_row = QHBoxLayout()
        body_row.setSpacing(14)
        body_row.addWidget(center_panel, 5)
        body_row.addWidget(changes_panel, 3)
        layout.addLayout(body_row, 1)
        return tab

    def _build_studio_governance_surface(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        summary_splitter = QSplitter(Qt.Horizontal)
        self.workspace_selected_repo = QTextBrowser()
        self.workspace_selected_repo.setOpenExternalLinks(False)
        self.workspace_selected_task = QTextBrowser()
        self.workspace_selected_task.setOpenExternalLinks(False)
        summary_splitter.addWidget(self.workspace_selected_repo)
        summary_splitter.addWidget(self.workspace_selected_task)
        summary_splitter.setStretchFactor(0, 1)
        summary_splitter.setStretchFactor(1, 1)

        management_splitter = QSplitter(Qt.Horizontal)
        repo_panel = QFrame()
        repo_panel.setObjectName("composerPanel")
        repo_layout = QVBoxLayout(repo_panel)
        repo_layout.setContentsMargins(14, 14, 14, 14)
        repo_layout.setSpacing(8)
        repo_layout.addWidget(QLabel("Repo Context"))
        self.workspace_repo_search = QLineEdit()
        self.workspace_repo_search.setPlaceholderText("Search repos, branch, status")
        self.workspace_repo_search.textChanged.connect(self._on_workspace_repo_search_changed)
        repo_layout.addWidget(self.workspace_repo_search)
        self.workspace_repo_list = QListWidget()
        self.workspace_repo_list.itemSelectionChanged.connect(self._on_workspace_repo_changed)
        repo_layout.addWidget(self.workspace_repo_list, 1)
        self.workspace_repo_governance_footer = QLabel("")
        self.workspace_repo_governance_footer.setWordWrap(True)
        self.workspace_repo_governance_footer.setObjectName("microDetail")
        repo_layout.addWidget(self.workspace_repo_governance_footer)

        task_panel = QFrame()
        task_panel.setObjectName("composerPanel")
        task_layout = QVBoxLayout(task_panel)
        task_layout.setContentsMargins(14, 14, 14, 14)
        task_layout.setSpacing(8)
        task_header = QHBoxLayout()
        task_header.setSpacing(8)
        task_header.addWidget(QLabel("Task Queue"))
        task_header.addStretch(1)
        self.workspace_task_search = QLineEdit()
        self.workspace_task_search.setPlaceholderText("Filter tasks")
        self.workspace_task_search.textChanged.connect(self._on_workspace_task_search_changed)
        task_header.addWidget(self.workspace_task_search, 1)
        task_layout.addLayout(task_header)
        task_tab_row = QHBoxLayout()
        task_tab_row.setSpacing(8)
        self.task_tab_buttons = {}
        for label in ("All", "Running", "Pending", "Blocked", "Done"):
            button = QPushButton(label)
            button.clicked.connect(lambda _checked=False, value=label: self._set_workspace_task_tab(value))
            self.task_tab_buttons[label] = button
            task_tab_row.addWidget(button)
        task_tab_row.addStretch(1)
        task_layout.addLayout(task_tab_row)
        self.workspace_task_list = QListWidget()
        self.workspace_task_list.itemSelectionChanged.connect(self._on_workspace_task_changed)
        task_layout.addWidget(self.workspace_task_list, 1)
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self.workspace_run_button = QPushButton("Run")
        self.workspace_run_button.clicked.connect(self._run_workspace_task)
        self.workspace_approve_button = QPushButton("Approve")
        self.workspace_approve_button.clicked.connect(self._approve_workspace_task)
        self.workspace_reject_button = QPushButton("Reject")
        self.workspace_reject_button.clicked.connect(self._reject_workspace_task)
        self.workspace_logs_button = QPushButton("Inspect")
        self.workspace_logs_button.clicked.connect(self._show_workspace_logs)
        self.workspace_ship_button = QPushButton("Ship Release")
        self.workspace_ship_button.clicked.connect(self._ship_release)
        action_row.addWidget(self.workspace_run_button)
        action_row.addWidget(self.workspace_approve_button)
        action_row.addWidget(self.workspace_reject_button)
        action_row.addWidget(self.workspace_logs_button)
        action_row.addWidget(self.workspace_ship_button)
        task_layout.addLayout(action_row)

        management_splitter.addWidget(repo_panel)
        management_splitter.addWidget(task_panel)
        management_splitter.setStretchFactor(0, 3)
        management_splitter.setStretchFactor(1, 5)

        layout.addWidget(summary_splitter, 3)
        layout.addWidget(management_splitter, 5)
        return tab

    def _build_studio_memory_surface(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.workspace_brain_state = QTextBrowser()
        self.workspace_brain_state.setOpenExternalLinks(False)
        self.workspace_brain_state.setFixedHeight(220)
        memory_editor_grid = QGridLayout()
        memory_editor_grid.setHorizontalSpacing(10)
        memory_editor_grid.setVerticalSpacing(8)
        self.task_memory_goals = QPlainTextEdit()
        self.task_memory_goals.setPlaceholderText("Goals: one line per goal")
        self.task_memory_goals.setFixedHeight(76)
        self.task_memory_constraints = QPlainTextEdit()
        self.task_memory_constraints.setPlaceholderText("Constraints: one line per constraint")
        self.task_memory_constraints.setFixedHeight(76)
        self.task_memory_do_not_touch = QPlainTextEdit()
        self.task_memory_do_not_touch.setPlaceholderText("Do not touch: one line per protected area")
        self.task_memory_do_not_touch.setFixedHeight(76)
        self.task_memory_notes = QPlainTextEdit()
        self.task_memory_notes.setPlaceholderText("Notes: one line per note")
        self.task_memory_notes.setFixedHeight(76)
        memory_editor_grid.addWidget(QLabel("Goals"), 0, 0)
        memory_editor_grid.addWidget(QLabel("Constraints"), 0, 1)
        memory_editor_grid.addWidget(self.task_memory_goals, 1, 0)
        memory_editor_grid.addWidget(self.task_memory_constraints, 1, 1)
        memory_editor_grid.addWidget(QLabel("Do Not Touch"), 2, 0)
        memory_editor_grid.addWidget(QLabel("Notes"), 2, 1)
        memory_editor_grid.addWidget(self.task_memory_do_not_touch, 3, 0)
        memory_editor_grid.addWidget(self.task_memory_notes, 3, 1)
        self.task_memory_save_button = QPushButton("Save Task Memory")
        self.task_memory_save_button.clicked.connect(self._save_task_memory)
        self.studio_memory_view = QPlainTextEdit()
        self.studio_memory_view.setReadOnly(True)
        layout.addWidget(self.workspace_brain_state)
        layout.addLayout(memory_editor_grid)
        layout.addWidget(self.task_memory_save_button, 0, Qt.AlignRight)
        layout.addWidget(self.studio_memory_view, 1)
        return tab

    def _build_studio_upgrades_surface(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.studio_upgrade_list = QListWidget()
        self.studio_upgrade_list.itemSelectionChanged.connect(self._on_upgrade_selected)
        self.studio_upgrade_summary = QTextBrowser()
        self.studio_upgrade_summary.setOpenExternalLinks(False)
        self.studio_upgrade_summary.setFixedHeight(180)
        upgrade_actions = QHBoxLayout()
        upgrade_actions.setSpacing(8)
        self.accept_upgrade_button = QPushButton("Accept Upgrade")
        self.accept_upgrade_button.clicked.connect(lambda: self._set_upgrade_status("Accepted"))
        self.reject_upgrade_button = QPushButton("Reject Upgrade")
        self.reject_upgrade_button.clicked.connect(lambda: self._set_upgrade_status("Rejected"))
        upgrade_actions.addWidget(self.accept_upgrade_button)
        upgrade_actions.addWidget(self.reject_upgrade_button)
        upgrade_actions.addStretch(1)
        layout.addWidget(self.studio_upgrade_summary)
        layout.addLayout(upgrade_actions)
        layout.addWidget(self.studio_upgrade_list, 1)
        return tab

    def _build_studio_runtime_surface(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.workspace_worker_status = QTextBrowser()
        self.workspace_worker_status.setOpenExternalLinks(False)
        self.workspace_worker_output = QPlainTextEdit()
        self.workspace_worker_output.setReadOnly(True)
        layout.addWidget(self.workspace_worker_status)
        layout.addWidget(self.workspace_worker_output, 1)
        return tab

    def _build_studio_replay_surface(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.workspace_replay_summary = QTextBrowser()
        self.workspace_replay_summary.setOpenExternalLinks(False)
        self.workspace_replay_summary.setFixedHeight(160)
        replay_splitter = QSplitter(Qt.Horizontal)
        self.workspace_replay_timeline = QPlainTextEdit()
        self.workspace_replay_timeline.setReadOnly(True)
        self.workspace_branch_summary = QPlainTextEdit()
        self.workspace_branch_summary.setReadOnly(True)
        replay_splitter.addWidget(self.workspace_replay_timeline)
        replay_splitter.addWidget(self.workspace_branch_summary)
        replay_splitter.setStretchFactor(0, 3)
        replay_splitter.setStretchFactor(1, 2)
        layout.addWidget(self.workspace_replay_summary)
        layout.addWidget(replay_splitter, 1)
        return tab

    def _build_studio_file_viewer_surface(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        self.studio_file_meta = QLabel("Select a file inside a registered workspace.")
        self.studio_file_meta.setWordWrap(True)
        self.studio_file_meta.setObjectName("microDetail")
        self.studio_file_preview = QPlainTextEdit()
        self.studio_file_preview.setReadOnly(True)
        layout.addWidget(self.studio_file_meta)
        layout.addWidget(self.studio_file_preview, 1)
        return tab

    def _build_primary_task_lane(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("composerPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        header.addWidget(QLabel("ACTIVE RUN"))
        header.addStretch(1)
        self.queue_toggle_button = QPushButton("Running (0) • Pending (0) • Blocked (0) • Done (0) ▼")
        self.queue_toggle_button.clicked.connect(self._toggle_queue_strip)
        header.addWidget(self.queue_toggle_button)
        layout.addLayout(header)

        self.active_run_title = QLabel("No active run.")
        self.active_run_title.setObjectName("heroSubtitle")
        self.active_run_status = QLabel("")
        self.active_run_status.setObjectName("microDetail")
        self.active_run_card = QTextBrowser()
        self.active_run_card.setOpenExternalLinks(False)
        self.active_run_card.setMinimumHeight(260)
        self.active_run_card.setMaximumHeight(380)
        layout.addWidget(self.active_run_title)
        layout.addWidget(self.active_run_status)
        layout.addWidget(self.active_run_card)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.home_run_button = QPushButton("Run Task")
        self.home_run_button.clicked.connect(self._run_active_workspace_task)
        self.home_run_button.setVisible(False)
        self.home_approve_button = QPushButton("Approve")
        self.home_approve_button.clicked.connect(self._approve_active_run)
        self.home_reject_button = QPushButton("Reject")
        self.home_reject_button.clicked.connect(self._reject_active_run)
        self.home_inspect_button = QPushButton("Inspect")
        self.home_inspect_button.clicked.connect(self._inspect_active_run)
        self.home_cancel_button = QPushButton("Cancel")
        self.home_cancel_button.clicked.connect(self._cancel_active_run)
        self.home_cancel_button.setVisible(False)
        actions.addWidget(self.home_approve_button)
        actions.addWidget(self.home_reject_button)
        actions.addWidget(self.home_inspect_button)
        actions.addWidget(self.home_cancel_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.task_queue_frame = QFrame()
        self.task_queue_frame.setObjectName("statusField")
        self.task_queue_frame.setVisible(False)
        queue_layout = QVBoxLayout(self.task_queue_frame)
        queue_layout.setContentsMargins(12, 12, 12, 12)
        queue_layout.setSpacing(10)

        queue_header = QHBoxLayout()
        queue_header.setSpacing(8)
        self.task_queue_caption = QLabel("Queue details for the current run lane.")
        self.task_queue_caption.setObjectName("microDetail")
        queue_header.addWidget(self.task_queue_caption)
        queue_header.addStretch(1)
        queue_layout.addLayout(queue_header)

        columns = QHBoxLayout()
        columns.setSpacing(10)
        self.running_queue_label = QLabel("Running")
        self.running_queue_label.setObjectName("railHeading")
        self.running_queue_list = QListWidget()
        self.running_queue_list.itemSelectionChanged.connect(self._on_primary_task_list_changed)
        self.pending_queue_label = QLabel("Pending")
        self.pending_queue_label.setObjectName("railHeading")
        self.pending_queue_list = QListWidget()
        self.pending_queue_list.itemSelectionChanged.connect(self._on_primary_task_list_changed)
        self.done_queue_label = QLabel("Blocked")
        self.done_queue_label.setObjectName("railHeading")
        self.done_queue_list = QListWidget()
        self.done_queue_list.itemSelectionChanged.connect(self._on_primary_task_list_changed)
        self.completed_queue_label = QLabel("Done")
        self.completed_queue_label.setObjectName("railHeading")
        self.completed_queue_list = QListWidget()
        self.completed_queue_list.itemSelectionChanged.connect(self._on_primary_task_list_changed)

        for title, widget in (
            (self.running_queue_label, self.running_queue_list),
            (self.pending_queue_label, self.pending_queue_list),
            (self.done_queue_label, self.done_queue_list),
            (self.completed_queue_label, self.completed_queue_list),
        ):
            column = QFrame()
            column.setObjectName("statusField")
            column_layout = QVBoxLayout(column)
            column_layout.setContentsMargins(10, 10, 10, 10)
            column_layout.setSpacing(8)
            column_layout.addWidget(title)
            column_layout.addWidget(widget, 1)
            columns.addWidget(column, 1)
        queue_layout.addLayout(columns)

        layout.addWidget(self.task_queue_frame, 1)
        return panel

    def _build_governance_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.kill_reason = QLineEdit()
        self.kill_reason.setPlaceholderText("Containment reason or manual override note")
        self.kill_soft_button = QPushButton("Soft Kill")
        self.kill_hard_button = QPushButton("Hard Kill")
        self.kill_reset_button = QPushButton("Reset")
        self.kill_soft_button.clicked.connect(self._activate_soft_kill)
        self.kill_hard_button.clicked.connect(self._activate_hard_kill)
        self.kill_reset_button.clicked.connect(self._reset_kill_switch)
        controls.addWidget(self.kill_reason, 1)
        controls.addWidget(self.kill_soft_button)
        controls.addWidget(self.kill_hard_button)
        controls.addWidget(self.kill_reset_button)

        self.kill_summary = QTextBrowser()
        self.kill_summary.setOpenExternalLinks(False)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)
        self.activity_text = QPlainTextEdit()
        self.activity_text.setReadOnly(True)
        self.discards_text = QPlainTextEdit()
        self.discards_text.setReadOnly(True)
        self.fame_text = QPlainTextEdit()
        self.fame_text.setReadOnly(True)
        self.shame_text = QPlainTextEdit()
        self.shame_text.setReadOnly(True)
        grid.addWidget(QLabel("Recent Activity"), 0, 0)
        grid.addWidget(QLabel("Hall Of Discard"), 0, 1)
        grid.addWidget(self.activity_text, 1, 0)
        grid.addWidget(self.discards_text, 1, 1)
        grid.addWidget(QLabel("Hall Of Fame"), 2, 0)
        grid.addWidget(QLabel("Hall Of Shame"), 2, 1)
        grid.addWidget(self.fame_text, 3, 0)
        grid.addWidget(self.shame_text, 3, 1)
        grid.setRowStretch(1, 1)
        grid.setRowStretch(3, 1)

        layout.addLayout(controls)
        layout.addWidget(self.kill_summary)
        layout.addLayout(grid, 1)
        return tab

    def _build_workspace_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        self.workspace_session_label = QLabel("")
        self.workspace_session_label.setObjectName("microDetail")
        self.workspace_project_path = QLineEdit()
        self.workspace_project_path.setReadOnly(True)
        self.workspace_project_path.setPlaceholderText("No project selected.")
        self.workspace_project_path.setClearButtonEnabled(False)
        self.workspace_load_project_button = QPushButton("Load Project")
        self.workspace_load_project_button.clicked.connect(self._load_project)
        self.workspace_project_note = QLabel(
            "Only explicitly selected folders are used as the current project. No automatic filesystem scan runs here."
        )
        self.workspace_project_note.setWordWrap(True)
        self.workspace_project_note.setObjectName("microDetail")

        project_row = QHBoxLayout()
        project_row.setSpacing(10)
        project_row.addWidget(QLabel("Current Project"))
        project_row.addWidget(self.workspace_project_path, 1)
        project_row.addWidget(self.workspace_load_project_button)

        splitter = QSplitter(Qt.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_layout.addWidget(QLabel("Project / Git / Verification"))
        self.workspace_summary = QPlainTextEdit()
        self.workspace_summary.setReadOnly(True)
        left_layout.addWidget(self.workspace_summary, 1)
        left_layout.addWidget(QLabel("Pending Approvals"))
        self.workspace_approvals = QPlainTextEdit()
        self.workspace_approvals.setReadOnly(True)
        left_layout.addWidget(self.workspace_approvals, 1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        right_layout.addWidget(QLabel("Repo Map"))
        self.workspace_repo_map = QPlainTextEdit()
        self.workspace_repo_map.setReadOnly(True)
        right_layout.addWidget(self.workspace_repo_map, 1)
        right_layout.addWidget(QLabel("Files / Sandbox"))
        self.workspace_files = QPlainTextEdit()
        self.workspace_files.setReadOnly(True)
        right_layout.addWidget(self.workspace_files, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 5)

        layout.addWidget(self.workspace_session_label)
        layout.addLayout(project_row)
        layout.addWidget(self.workspace_project_note)
        layout.addWidget(splitter, 1)
        return tab

    def _build_mystic_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(14)

        self.mystic_status = QTextBrowser()
        self.mystic_status.setOpenExternalLinks(False)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.mystic_tick_button = QPushButton("Check In")
        self.mystic_break_button = QPushButton("I Took A Break")
        self.mystic_ack_button = QPushButton("Acknowledge")
        self.mystic_mute_button = QPushButton("Mute 10m")
        self.mystic_tick_button.clicked.connect(self._mystic_tick)
        self.mystic_break_button.clicked.connect(self._mystic_break)
        self.mystic_ack_button.clicked.connect(self._mystic_acknowledge)
        self.mystic_mute_button.clicked.connect(self._mystic_mute)
        controls.addWidget(self.mystic_tick_button)
        controls.addWidget(self.mystic_break_button)
        controls.addWidget(self.mystic_ack_button)
        controls.addWidget(self.mystic_mute_button)
        controls.addStretch(1)

        self.mystic_input = QPlainTextEdit()
        self.mystic_input.setPlaceholderText("Ask Mystic Reflection to read the current operator state, mood, or pattern.")
        self.mystic_input.setFixedHeight(100)
        self.mystic_read_button = QPushButton("Run Mystic Reflection")
        self.mystic_read_button.clicked.connect(self._run_mystic_read)
        self.mystic_output = QPlainTextEdit()
        self.mystic_output.setReadOnly(True)

        layout.addWidget(self.mystic_status)
        layout.addLayout(controls)
        layout.addWidget(self.mystic_input)
        layout.addWidget(self.mystic_read_button, 0, Qt.AlignRight)
        layout.addWidget(self.mystic_output, 1)
        return tab

    def _apply_style(self) -> None:
        font = QFont("Trebuchet MS", 10)
        QApplication.instance().setFont(font)
        self.setStyleSheet(
            """
            QWidget {
                background: #0c1217;
                color: #edf2f7;
                font-size: 13px;
            }
            QFrame#sideRail {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #101922, stop:1 #0f151b);
                border: 1px solid #1e2d39;
                border-radius: 24px;
            }
            QFrame#heroPanel, QFrame#composerPanel {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #111a21, stop:1 #14222d);
                border: 1px solid #223644;
                border-radius: 24px;
            }
            QFrame#statusField {
                background: #10171e;
                border: 1px solid #233340;
                border-radius: 16px;
            }
            QLabel#brandTitle {
                font-size: 34px;
                font-weight: 700;
                color: #f4dfbc;
                letter-spacing: 0.5px;
            }
            QLabel#brandSubtitle {
                color: #9bb1c8;
                font-size: 13px;
                line-height: 1.3;
            }
            QLabel#railHeading {
                color: #f4dfbc;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 1.4px;
                text-transform: uppercase;
            }
            QLabel#railInfo, QLabel#microDetail {
                color: #8ea4bb;
                font-size: 12px;
            }
            QLabel#heroTitle {
                font-size: 31px;
                font-weight: 700;
                color: #f4dfbc;
            }
            QLabel#heroSubtitle {
                color: #c5d2df;
                font-size: 14px;
            }
            QLabel#routeLabel {
                color: #8ea4bb;
                font-size: 12px;
                letter-spacing: 0.8px;
            }
            QLabel#statusValue {
                color: #f4dfbc;
                font-size: 15px;
                font-weight: 700;
            }
            QPushButton {
                background: #d59b4a;
                color: #11151a;
                border: none;
                border-radius: 14px;
                padding: 10px 15px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #e6af60;
            }
            QPushButton:disabled {
                background: #31404d;
                color: #8ea4bb;
            }
            QLineEdit, QPlainTextEdit, QTextBrowser, QListWidget, QTreeWidget, QComboBox {
                background: #10171e;
                border: 1px solid #233340;
                border-radius: 16px;
                padding: 11px;
                selection-background-color: #d59b4a;
                selection-color: #11151a;
            }
            QListWidget::item {
                padding: 10px 8px;
                border-radius: 12px;
            }
            QListWidget::item:selected {
                background: #1b2a35;
                color: #f4dfbc;
            }
            QTabWidget::pane {
                border: 1px solid #1f2c37;
                border-radius: 18px;
                background: #0f151b;
                top: -1px;
            }
            QTabBar::tab {
                background: #121a21;
                color: #9bb1c8;
                border: 1px solid #22313d;
                padding: 10px 18px;
                margin-right: 6px;
                border-top-left-radius: 12px;
                border-top-right-radius: 12px;
            }
            QTabBar::tab:selected {
                background: #18232d;
                color: #f4dfbc;
                border-color: #375068;
            }
            QCheckBox {
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            """
        )

    def _refresh_if_idle(self) -> None:
        if self._chat_thread is None and self._refresh_thread is None:
            self.refresh_from_runtime(select_session_id=self.current_session_id)

    def refresh_from_runtime(self, *, select_session_id: str | None = None) -> None:
        target_session_id = select_session_id or self.current_session_id
        if self._refresh_thread is not None:
            self._queued_refresh_session_id = target_session_id
            self._set_runtime_hydrating(target_session_id)
            return
        self._set_runtime_hydrating(target_session_id)
        self._set_runtime_interaction_enabled(False)
        thread = QThread(self)
        worker = SnapshotWorker(host=self.host, session_id=target_session_id)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.ready.connect(self._on_runtime_snapshot_ready)
        worker.failed.connect(self._on_runtime_snapshot_failed)
        worker.ready.connect(thread.quit)
        worker.failed.connect(thread.quit)
        thread.finished.connect(self._on_runtime_refresh_finished)
        thread.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        self._refresh_thread = thread
        self._refresh_worker = worker
        thread.start()

    def _set_runtime_hydrating(self, session_id: str | None) -> None:
        self._runtime_hydrating = True
        session_label = str(session_id or self.current_session_id or "pending").strip() or "pending"
        self.health_badge.setText("SYNCING")
        self.health_badge.setStyleSheet(_status_style("warning"))
        self.mode_badge.setText("1001 SYNC")
        self.mode_badge.setStyleSheet(_status_style("warning"))
        self.kill_badge.setText("SYNCING")
        self.kill_badge.setStyleSheet(_status_style("warning"))
        self.hero_title.setText(self._studio_name)
        self.hero_subtitle.setText(
            "ARIS Desktop is hydrating governed runtime state before presenting the latest decision."
        )
        self.route_label.setText(f"Route: {DESKTOP_HYDRATION_ROUTE} | SYNCING")
        self.rail_info.setText(
            "Hydrating desktop host\n"
            "Loading governed snapshot, halls, and workspace surfaces..."
        )
        self.operator_session_label.setText(f"Session: {session_label} (syncing)")
        self.workspace_route_summary.setText(f"Route: {DESKTOP_HYDRATION_ROUTE}")
        self.workspace_prompt_context.setText(DESKTOP_HYDRATION_REASON)
        self.workspace_brain_pills.setText(
            "<html><body style='margin:0;padding:0;'>"
            f"{_pill_span('Runtime Syncing', 'review')}"
            f"{_pill_span('Forge State Loading', 'review')}"
            f"{_pill_span('Evolving Core Gate Preserved', 'warning')}"
            "</body></html>"
        )
        self.workspace_selected_repo.setHtml(self._hydration_card("Repo Context", "Loading selected repo and branch state."))
        self.workspace_selected_task.setHtml(self._hydration_card("Task Board", "Loading active governed task state."))
        self.workspace_brain_state.setHtml(self._hydration_card("Brain State", "Loading mode, scope, target, and permission state."))
        self.active_run_title.setText("Hydrating active run...")
        self.active_run_status.setText("Loading governed task focus.")
        self.active_run_card.setHtml(self._hydration_card("Active Run", "Loading the currently focused governed run."))
        self.task_lane_summary.setText("Hydrating queue state...")
        self.workspace_worker_status.setHtml(
            self._hydration_card("Worker / Protection Status", "Loading Forge, ForgeEval, and governance lane availability.")
        )
        self.workspace_changes_summary.setText("Loading workspace changes...")
        self.workspace_diff_preview.setPlainText("Hydrating diff preview...")
        self.event_stream_status.setText("Runtime stream hydrating...")
        self.workspace_recent_tasks.setPlainText("Hydrating governed tasks...")
        self.workspace_activity_feed.setPlainText("Hydrating recent governed activity...")
        self.workspace_worker_output.setPlainText("Hydrating worker lane state...")
        self.workspace_replay_summary.setHtml(self._hydration_card("Replay", "Loading replay and branch records."))
        self.workspace_replay_timeline.setPlainText("Hydrating replay timeline...")
        self.workspace_branch_summary.setPlainText("Hydrating branch records...")
        self.status_brain_value.setText("SYNCING")
        self.status_tier_value.setText("SYNCING")
        self.status_workspace_value.setText("SYNCING")
        self.status_upgrade_value.setText("SYNCING")
        self.status_memory_value.setText("SYNCING")
        self.status_voice_value.setText("SYNCING")
        self._set_optional_text("workspace_session_label", f"Current governed workspace session: {session_label} (syncing)")
        self._set_optional_html("kill_summary", self._hydration_card("Governance Cockpit", DESKTOP_HYDRATION_REASON))
        self._set_optional_html(
            "overview_summary",
            self._hydration_card("UL Runtime Overview", "Loading identity, law, adapter, and runtime ledger surfaces."),
        )
        self._set_optional_html(
            "mystic_status",
            self._hydration_card("Mystic Sustainment", "Loading sustainment and reflection state."),
        )
        self._set_optional_plain_text("activity_text", "Hydrating activity ledger...")
        self._set_optional_plain_text("discards_text", "Hydrating Hall of Discard...")
        self._set_optional_plain_text("fame_text", "Hydrating Hall of Fame...")
        self._set_optional_plain_text("shame_text", "Hydrating Hall of Shame...")
        self._set_optional_plain_text("workspace_summary", "Hydrating workspace summary...")
        self._set_optional_plain_text("workspace_approvals", "Hydrating pending approvals...")
        self._set_optional_plain_text("workspace_repo_map", "Hydrating repo map...")
        self._set_optional_plain_text("workspace_files", "Hydrating files and sandbox...")
        self._set_optional_plain_text("runtime_inspector", "Hydrating UL runtime inspector...")
        self._set_optional_plain_text("mystic_output", "Hydrating Mystic runtime...")
        self._clear_optional_tree("feature_tree")
        self._clear_optional_tree("target_tree")
        for widget in (
            self.running_queue_list,
            self.pending_queue_list,
            self.done_queue_list,
            self.completed_queue_list,
            self.workspace_changes_list,
            self.project_list,
            self.sidebar_task_list,
        ):
            widget.blockSignals(True)
            widget.clear()
            widget.blockSignals(False)

    def _set_runtime_interaction_enabled(self, enabled: bool) -> None:
        for attribute in (
            "send_button",
            "home_run_button",
            "home_approve_button",
            "home_reject_button",
            "home_inspect_button",
            "home_cancel_button",
            "queue_toggle_button",
            "inspect_toggle_button",
            "workspace_run_button",
            "workspace_approve_button",
            "workspace_reject_button",
            "workspace_logs_button",
            "workspace_ship_button",
        ):
            widget = getattr(self, attribute, None)
            if widget is not None:
                widget.setEnabled(enabled)

    @Slot(object)
    def _on_runtime_snapshot_ready(self, snapshot: DesktopSnapshot) -> None:
        self._runtime_hydrating = False
        self._live_task_stream_lines = []
        self.snapshot = snapshot
        self.current_session_id = snapshot.session_id
        self._transcript_cache = list(snapshot.transcript)
        self._populate_session_list(snapshot)
        self._update_header(snapshot)
        self._update_operator(snapshot)
        self._set_runtime_interaction_enabled(True)
        if not getattr(self, "_ready_announced", False):
            self._ready_announced = True
            speak("ARIS is ready.", "system_ready")

    @Slot(str)
    def _on_runtime_snapshot_failed(self, message: str) -> None:
        self._runtime_hydrating = False
        self.health_badge.setText("BLOCKED")
        self.health_badge.setStyleSheet(_status_style("blocked"))
        self.mode_badge.setText("1001")
        self.mode_badge.setStyleSheet(_status_style("warning"))
        self.kill_badge.setText("ERROR")
        self.kill_badge.setStyleSheet(_status_style("blocked"))
        self.hero_subtitle.setText(f"Runtime refresh failed: {message}")
        self.route_label.setText(f"Route: {DESKTOP_HYDRATION_ROUTE} | BLOCKED")
        self.event_stream_status.setText("Runtime stream blocked")
        self.workspace_prompt_context.setText(f"Runtime refresh failed: {message}")
        self.workspace_worker_output.setPlainText(f"Runtime refresh failed:\n{message}")
        self._set_runtime_interaction_enabled(True)

    @Slot()
    def _on_runtime_refresh_finished(self) -> None:
        self._refresh_worker = None
        self._refresh_thread = None
        queued_session_id = self._queued_refresh_session_id
        self._queued_refresh_session_id = None
        if queued_session_id is not None and queued_session_id != self.current_session_id:
            QTimer.singleShot(
                0,
                lambda session_id=queued_session_id: self.refresh_from_runtime(
                    select_session_id=session_id
                ),
            )
        elif queued_session_id is not None and self.snapshot is None:
            QTimer.singleShot(
                0,
                lambda session_id=queued_session_id: self.refresh_from_runtime(
                    select_session_id=session_id
                ),
            )

    def _hydration_card(self, title: str, body: str) -> str:
        return (
            "<html><body style=\"background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;\">"
            "<div style=\"padding:4px 2px;\">"
            f"<div style=\"font-size:18px;font-weight:700;color:#f4dfbc;\">{escape(title)}</div>"
            f"<div style=\"margin-top:10px;line-height:1.5;color:#c5d2df;\">{escape(body)}</div>"
            "</div></body></html>"
        )

    def _set_optional_text(self, attribute: str, value: str) -> None:
        widget = getattr(self, attribute, None)
        if widget is not None:
            widget.setText(value)

    def _set_optional_plain_text(self, attribute: str, value: str) -> None:
        widget = getattr(self, attribute, None)
        if widget is not None:
            widget.setPlainText(value)

    def _set_optional_html(self, attribute: str, value: str) -> None:
        widget = getattr(self, attribute, None)
        if widget is not None:
            widget.setHtml(value)

    def _clear_optional_tree(self, attribute: str) -> None:
        widget = getattr(self, attribute, None)
        if widget is not None:
            widget.clear()

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.refresh_timer.stop()
        if self._refresh_thread is not None:
            self._refresh_thread.quit()
            self._refresh_thread.wait(2000)
        if self._chat_thread is not None:
            self._chat_thread.quit()
            self._chat_thread.wait(2000)
        super().closeEvent(event)

    def _populate_session_list(self, snapshot: DesktopSnapshot) -> None:
        self.session_list.blockSignals(True)
        self.session_list.clear()
        for session in snapshot.sessions:
            title = str(session.get("title", "Untitled")).strip() or "Untitled"
            preview = str(session.get("preview", "")).strip()
            count = int(session.get("message_count", 0))
            item = QListWidgetItem(f"{title}\n{preview or 'No messages yet'}")
            item.setData(Qt.UserRole, str(session.get("id", "")).strip())
            item.setToolTip(f"{title}\nMessages: {count}")
            self.session_list.addItem(item)
            if str(session.get("id", "")).strip() == snapshot.session_id:
                self.session_list.setCurrentItem(item)
        self.session_list.blockSignals(False)
        surface = self._workspace_surface(snapshot)
        repos = [item for item in list(surface.get("repos", [])) if isinstance(item, dict)]
        tasks = [item for item in list(surface.get("tasks", [])) if isinstance(item, dict)]
        self.project_list.blockSignals(True)
        self.project_list.clear()
        for repo in repos:
            item = QListWidgetItem(
                f"{repo.get('name', 'Workspace')}\n"
                f"{clean_operator_text(repo.get('detail', '')) or repo.get('branch', 'workspace')}"
            )
            item.setData(Qt.UserRole, str(repo.get("id", "")).strip())
            item.setToolTip(str(repo.get("path", "")).strip())
            self.project_list.addItem(item)
            if str(repo.get("id", "")).strip() == self._selected_workspace_repo_id:
                self.project_list.setCurrentItem(item)
        self.project_list.blockSignals(False)
        self.sidebar_task_list.blockSignals(True)
        self.sidebar_task_list.clear()
        for task in tasks[:12]:
            item = QListWidgetItem(
                f"{task.get('title', 'Task')}\n"
                f"{task.get('status', 'Blocked')} · {task.get('priority', 'P2')}"
            )
            item.setData(Qt.UserRole, str(task.get("id", "")).strip())
            item.setToolTip(clean_operator_text(task.get("latest_update", "")) or str(task.get("summary", "")).strip())
            self.sidebar_task_list.addItem(item)
            if str(task.get("id", "")).strip() == self._selected_workspace_task_id:
                self.sidebar_task_list.setCurrentItem(item)
        self.sidebar_task_list.blockSignals(False)
        self.rail_info.setText(
            f"{len(repos)} projects in view\n"
            f"{len(tasks)} tasks in queue\n"
            f"Native targets: {', '.join(item.label for item in snapshot.packaging_targets)}"
        )

    def _update_header(self, snapshot: DesktopSnapshot) -> None:
        status = snapshot.status
        kill_switch = _dict(status.get("kill_switch"))
        surface = self._workspace_surface(snapshot)
        bridge = _dict(surface.get("operator_bridge"))
        self.setWindowTitle(self.host.profile.desktop_title)
        self.hero_title.setText(self._studio_name)
        self.hero_subtitle.setText(str(bridge.get("header_title", self._studio_name)).strip())
        self.route_label.setText(
            f"{bridge.get('header_status', 'Status: Idle')} • {bridge.get('header_mode', 'Mode: Auto')}"
        )

        health_status = "READY" if snapshot.health.get("ok") else "BLOCKED"
        self.health_badge.setText(health_status)
        self.health_badge.setStyleSheet(_status_style("ready" if snapshot.health.get("ok") else "blocked"))
        self.mode_badge.setText(str(status.get("law_mode", "unknown")).upper())
        self.mode_badge.setStyleSheet(_status_style("enforced"))
        self.kill_badge.setText(str(kill_switch.get("mode", "unknown")).upper())
        self.kill_badge.setStyleSheet(_status_style(str(kill_switch.get("mode", "unknown"))))

    def _update_overview(self, snapshot: DesktopSnapshot) -> None:
        status = snapshot.status
        ul_runtime = _dict(status.get("ul_runtime"))
        primitive_inventory = _dict(ul_runtime.get("primitive_inventory"))
        substrate = _dict(ul_runtime.get("substrate"))
        runtime_mode = _dict(status.get("runtime_mode") or status.get("demo_mode"))
        kill_switch = _dict(status.get("kill_switch"))
        shell_execution = _dict(status.get("shell_execution"))
        model_router = _dict(status.get("model_router"))
        model_systems = [
            f"{str(item.get('label', item.get('id', 'system'))).strip()}: {str(item.get('model', 'unknown')).strip()}"
            for item in list(model_router.get("systems", []))
            if isinstance(item, dict)
        ]

        summary_html = f"""
        <html><body style="background:#0f151b;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
        <div style="padding:8px 4px;">
          <div style="font-size:28px;font-weight:700;color:#f4dfbc;">Extracted UL Runtime, hosted as desktop</div>
          <div style="margin-top:8px;color:#a9bdd0;line-height:1.5;">
This window is a declared host over the existing ARIS V2 service. UL remains the identity source,
            CISIV remains the staged governance model, the Universal Adapter Protocol remains the binding layer,
            and the Law of Speech remains <b>0001 -&gt; 1000 -&gt; 1001</b>.
          </div>
          <div style="margin-top:16px;padding:14px 16px;border:1px solid #233340;border-radius:18px;background:#111a21;">
            <div><b>Identity source:</b> {escape(str(primitive_inventory.get("identity_source", "UL")))}</div>
            <div><b>Governance:</b> {escape(str(primitive_inventory.get("governance_model", "CISIV")))}</div>
            <div><b>Binding layer:</b> {escape(str(primitive_inventory.get("binding_layer", "Universal Adapter Protocol")))}</div>
            <div><b>Speech chain:</b> {escape(" -> ".join(primitive_inventory.get("speech_chain", [])))}</div>
            <div><b>Kill switch:</b> {escape(str(kill_switch.get("summary", "ARIS is nominal.")))}</div>
            <div><b>Shell execution:</b> requested {escape(str(shell_execution.get("requested_backend", "unknown")))} /
              active {escape(str(shell_execution.get("active_backend", "unknown")))}</div>
            <div><b>Runtime route:</b> {escape(" -> ".join(str(item) for item in runtime_mode.get("route", [])))}</div>
            <div><b>Model router:</b> {escape(str(model_router.get("mode", "auto")))}
              {escape(f" ({str(model_router.get('pinned_system', '')).replace('_', ' ')})" if model_router.get("pinned_system") else "")}</div>
            <div><b>Model systems:</b> {escape("; ".join(model_systems) or "Unavailable")}</div>
            <div><b>Foundation entries:</b> {escape(", ".join(str(item) for item in substrate.get("foundation_entries", [])))}</div>
          </div>
        </div></body></html>
        """
        self.overview_summary.setHtml(summary_html)

        self.feature_tree.clear()
        for feature in snapshot.features:
            item = QTreeWidgetItem([feature.label, feature.status, feature.source, feature.detail])
            self.feature_tree.addTopLevelItem(item)
        for column in range(4):
            self.feature_tree.resizeColumnToContents(column)

        inspector_payload = {
            "primitive_inventory": primitive_inventory,
            "substrate": substrate,
            "bootstrap": ul_runtime.get("bootstrap", {}),
            "runtime_law": status.get("runtime_law", {}),
            "model_router": model_router,
        }
        self.runtime_inspector.setPlainText(_pretty_json(inspector_payload))

        self.target_tree.clear()
        for target in snapshot.packaging_targets:
            self.target_tree.addTopLevelItem(
                QTreeWidgetItem([target.label, target.build_os, target.artifact, target.detail])
            )
        for column in range(4):
            self.target_tree.resizeColumnToContents(column)

    def _workspace_surface(self, snapshot: DesktopSnapshot) -> dict[str, Any]:
        base = snapshot.workspace_surface or {}
        repos = [dict(item) for item in list(base.get("repos", []))]
        tasks: list[dict[str, Any]] = []
        for item in list(base.get("tasks", [])):
            if not isinstance(item, dict):
                continue
            merged = dict(item)
            override = self._workspace_task_overrides.get(str(merged.get("id", "")).strip(), {})
            merged.update(override)
            tasks.append(merged)
        activity = [dict(item) for item in list(base.get("activity", [])) if isinstance(item, dict)]
        if self._workspace_activity_overrides:
            activity = [dict(item) for item in self._workspace_activity_overrides] + activity
        worker = dict(_dict(base.get("worker")))
        if self._workspace_worker_override is not None:
            worker = dict(self._workspace_worker_override)
        upgrades: list[dict[str, Any]] = []
        for item in list(base.get("upgrades", [])):
            if not isinstance(item, dict):
                continue
            merged = dict(item)
            override_status = self._upgrade_status_overrides.get(str(merged.get("id", "")).strip())
            if override_status:
                merged["status"] = override_status
            upgrades.append(merged)
        surface = {
            "session_id": base.get("session_id", snapshot.session_id),
            "repos": repos,
            "tasks": tasks,
            "activity": activity[:12],
            "worker": worker,
            "approval_count": int(base.get("approval_count", 0) or 0),
            "pending_approvals": [dict(item) for item in list(base.get("pending_approvals", [])) if isinstance(item, dict)],
            "agent_runs": [dict(item) for item in list(base.get("agent_runs", [])) if isinstance(item, dict)],
            "approval_audit": [dict(item) for item in list(base.get("approval_audit", [])) if isinstance(item, dict)],
            "workspaces": [dict(item) for item in list(base.get("workspaces", [])) if isinstance(item, dict)],
            "active_workspace": dict(_dict(base.get("active_workspace"))),
            "file_explorer": dict(_dict(base.get("file_explorer"))),
            "event_stream": [dict(item) for item in list(base.get("event_stream", [])) if isinstance(item, dict)],
            "feedback": dict(_dict(base.get("feedback"))),
            "review": dict(_dict(base.get("review"))),
            "operator_bridge": dict(_dict(base.get("operator_bridge"))),
            "bridge_intelligence": dict(_dict(base.get("bridge_intelligence"))),
            "task_memory": dict(_dict(base.get("task_memory"))),
            "replay": dict(_dict(base.get("replay"))),
            "branches": [dict(item) for item in list(base.get("branches", [])) if isinstance(item, dict)],
            "upgrades": upgrades,
        }
        self._ensure_workspace_selection(surface)
        return surface

    def _workspace_messages(self, snapshot: DesktopSnapshot) -> list[dict[str, Any]]:
        if self._workspace_transcript_override:
            return [dict(item) for item in self._workspace_transcript_override]
        transcript = [dict(item) for item in snapshot.transcript if isinstance(item, dict)]
        return transcript or seed_workspace_messages()

    def _current_brain_state_payload(self) -> dict[str, str]:
        controls = {
            "mode": self.brain_mode.currentText() if hasattr(self, "brain_mode") else "",
            "scope": self.brain_scope.currentText() if hasattr(self, "brain_scope") else "",
            "target": self.brain_target.currentText() if hasattr(self, "brain_target") else "",
            "permission": self.brain_permission.currentText() if hasattr(self, "brain_permission") else "",
            "response_style": (
                self.brain_response_style.currentText() if hasattr(self, "brain_response_style") else ""
            ),
        }
        return current_brain_state(controls)

    def _chat_mode_for_brain(self, brain: dict[str, str]) -> str:
        mode = str(brain.get("mode", "")).strip().lower()
        if mode in {"build", "route", "approval"} and getattr(self.host, "_workers_started", False):
            return "agent"
        if mode in {"build", "route", "approval"}:
            return "deep"
        if mode in {"inspect", "plan", "evaluate", "memory"}:
            return "deep"
        return "chat"

    def _fast_mode_for_brain(self, brain: dict[str, str], *, chat_mode: str) -> bool:
        if chat_mode == "agent":
            return False
        permission = str(brain.get("permission", "")).strip().lower()
        return permission in {"read only", "suggest only"}

    def _send_button_label(self) -> str:
        brain = self._current_brain_state_payload()
        chat_mode = self._chat_mode_for_brain(brain)
        return "Run Task" if chat_mode == "agent" else "Ask ARIS"

    def _workspace_selected_context(self, surface: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        repos = [item for item in surface.get("repos", []) if isinstance(item, dict)]
        tasks = [item for item in surface.get("tasks", []) if isinstance(item, dict)]
        selected_repo = next(
            (item for item in repos if str(item.get("id", "")).strip() == self._selected_workspace_repo_id),
            repos[0] if repos else None,
        )
        selected_task = next(
            (item for item in tasks if str(item.get("id", "")).strip() == self._selected_workspace_task_id),
            tasks[0] if tasks else None,
        )
        return selected_repo, selected_task

    def _workspace_recent_tasks_text(self, surface: dict[str, Any]) -> str:
        tasks = [item for item in surface.get("tasks", []) if isinstance(item, dict)]
        selected_repo_id = str(self._selected_workspace_repo_id or "").strip()
        recent = [
            task
            for task in tasks
            if str(task.get("repo_id", "")).strip() == selected_repo_id
        ] or tasks
        lines: list[str] = []
        for task in recent[:4]:
            lines.append(
                f"{task.get('id', 'task')}  {task.get('status', 'Blocked')}  {task.get('priority', 'P2')}\n"
                f"{task.get('title', 'Task')}"
            )
        return "\n\n".join(lines)

    def _ensure_workspace_selection(self, surface: dict[str, Any]) -> None:
        repos = [item for item in surface.get("repos", []) if isinstance(item, dict)]
        tasks = [item for item in surface.get("tasks", []) if isinstance(item, dict)]
        repo_ids = {str(item.get("id", "")).strip() for item in repos}
        if not self._selected_workspace_repo_id or self._selected_workspace_repo_id not in repo_ids:
            self._selected_workspace_repo_id = str(repos[0].get("id", "")).strip() if repos else None
        task_ids = {str(item.get("id", "")).strip() for item in tasks}
        active_task = self._select_active_run(tasks)
        if active_task is not None:
            active_task_id = str(active_task.get("id", "")).strip()
            active_task_status = str(active_task.get("status", "")).strip()
            current_task = next(
                (item for item in tasks if str(item.get("id", "")).strip() == self._selected_workspace_task_id),
                None,
            )
            current_status = str(current_task.get("status", "")).strip() if isinstance(current_task, dict) else ""
            if (
                not self._selected_workspace_task_id
                or self._selected_workspace_task_id not in task_ids
                or (active_task_status == "Running" and current_status != "Running")
            ):
                self._selected_workspace_task_id = active_task_id
        if not self._selected_workspace_task_id or self._selected_workspace_task_id not in task_ids:
            selected_repo_id = self._selected_workspace_repo_id
            selected_task = next(
                (
                    item
                    for item in tasks
                    if str(item.get("repo_id", "")).strip() == selected_repo_id
                ),
                tasks[0] if tasks else None,
            )
            self._selected_workspace_task_id = (
                str(selected_task.get("id", "")).strip() if isinstance(selected_task, dict) else None
            )

    def _workspace_task_counts(self, tasks: list[dict[str, Any]]) -> dict[str, int]:
        counts = {"All": len(tasks), "Running": 0, "Pending": 0, "Blocked": 0, "Done": 0}
        for task in tasks:
            status = str(task.get("status", "")).strip()
            if status in counts:
                counts[status] += 1
        return counts

    def _select_active_run(self, tasks: list[dict[str, Any]]) -> dict[str, Any] | None:
        return select_active_task(tasks)

    def _task_card_html(self, task: dict[str, Any] | None) -> str:
        if not isinstance(task, dict):
            return "<html><body style='color:#edf2f7;'>No active run is selected.</body></html>"
        approval_id = str(task.get("approval_id", "")).strip()
        task_type = str(task.get("task_type", "task")).strip() or "task"
        queue_name = str(task.get("queue_name", "OPERATOR")).strip() or "OPERATOR"
        dependencies = [str(entry).strip() for entry in list(task.get("depends_on", [])) if str(entry).strip()]
        review_gate = str(task.get("review_gate", "")).strip() or "none"
        return f"""
        <html><body style="background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
        <div style="padding:4px 2px;">
          <div style="font-size:20px;font-weight:700;color:#f4dfbc;">{escape(str(task.get("title", "Task")))}</div>
          <div style="margin-top:6px;color:#8ea4bb;">{escape(str(task.get('id', 'task')))}</div>
          <div style="margin-top:12px;"><b>Status:</b> {escape(str(task.get('status', 'Blocked')))}</div>
          <div><b>Priority:</b> {escape(str(task.get('priority', 'P2')))}</div>
          <div><b>Queue:</b> {escape(queue_name.replace('_', ' ').title())}</div>
          <div><b>Dependencies:</b> {escape(str(len(dependencies)))}</div>
          <div><b>Source:</b> {escape(task_type.replace("_", " ").title())}</div>
          <div><b>Review Gate:</b> {escape(review_gate.replace('_', ' ').title())}</div>
          <div><b>Approval:</b> {escape(approval_id or "Not waiting on approval")}</div>
          <div style="margin-top:10px;line-height:1.5;"><b>Prompt:</b><br>{escape(str(task.get('summary', '')))}</div>
          <div style="margin-top:10px;color:#c5d2df;"><b>Latest:</b> {escape(str(task.get('latest_update', '')))}</div>
        </div></body></html>
        """

    def _task_stream_html(self, bridge: dict[str, Any], task: dict[str, Any] | None) -> str:
        intelligence = _dict(bridge.get("intelligence"))
        lines = self._live_task_stream_lines or [
            str(item).strip() for item in list(bridge.get("stream_lines", [])) if str(item).strip()
        ]
        if not lines and isinstance(task, dict):
            latest = clean_operator_text(task.get("latest_update", "")) or clean_operator_text(task.get("summary", ""))
            if latest:
                lines = [f"[Now] {latest}"]
        if not lines:
            lines = ["[Now] No governed run activity is available yet."]
        rendered_lines = "".join(
            f"<div style=\"margin:0 0 10px 0;line-height:1.55;color:#d8e4ef;\">{escape(line)}</div>"
            for line in lines
        )
        affected_modules = ", ".join(str(item) for item in list(intelligence.get("affected_modules", []))[:6])
        approval_summary = _dict(intelligence.get("approval_summary"))
        decision = _dict(intelligence.get("decision"))
        chain = _dict(decision.get("chain"))
        task_memory = _dict(intelligence.get("task_memory"))
        task_memory_lines = []
        for field, label in (
            ("goals", "Goals"),
            ("constraints", "Constraints"),
            ("do_not_touch", "Do Not Touch"),
        ):
            values = [str(item) for item in list(task_memory.get(field, [])) if str(item).strip()]
            if values:
                task_memory_lines.append(
                    f"<div style=\"margin-top:6px;color:#8ea4bb;\"><b>{escape(label)}:</b> {escape('; '.join(values[:3]))}</div>"
                )
        intelligence_block = ""
        if intelligence:
            intelligence_block = f"""
            <div style="margin:0 0 14px 0;padding:12px 14px;border:1px solid #223644;border-radius:16px;background:#0f171e;">
              <div style="font-size:13px;font-weight:700;color:#f4dfbc;">Decision Intelligence</div>
              <div style="margin-top:8px;color:#d8e4ef;"><b>Intent:</b> {escape(str(intelligence.get('intent', 'general')).title())}</div>
              <div style="color:#d8e4ef;"><b>Risk:</b> {escape(str(intelligence.get('risk', 'low')).title())}</div>
              <div style="color:#d8e4ef;"><b>Affected modules:</b> {escape(affected_modules or 'none detected')}</div>
              <div style="margin-top:6px;color:#8ea4bb;"><b>Expected success:</b> {round(float(chain.get('mean', 0.0)) * 100)}% • range {round(float(chain.get('low', 0.0)) * 100)}–{round(float(chain.get('high', 0.0)) * 100)}%</div>
              <div style="margin-top:8px;color:#c5d2df;line-height:1.45;">{escape(str(approval_summary.get('summary', '')))}</div>
              {''.join(task_memory_lines)}
            </div>
            """
        return f"""
        <html><body style="background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
        <div style="padding:8px 10px;">
          {intelligence_block}
          {rendered_lines}
        </div></body></html>
        """

    def _append_live_task_stream_line(self, message: object, *, timestamp: object = "Now") -> None:
        cleaned = clean_operator_text(message)
        if not cleaned:
            return
        stamp = str(timestamp or "Now").strip() or "Now"
        self._live_task_stream_lines.append(f"[{stamp}] {cleaned}")
        self._live_task_stream_lines = self._live_task_stream_lines[-10:]
        surface = self._workspace_surface(self.snapshot) if self.snapshot is not None else {}
        bridge = {
            "stream_lines": self._live_task_stream_lines,
            "intelligence": _dict(_dict(surface.get("operator_bridge")).get("intelligence")),
        }
        self.active_run_card.setHtml(self._task_stream_html(bridge, self._active_workspace_task()))

    def _queue_item_text(self, task: dict[str, Any]) -> str:
        priority = str(task.get("priority", "P2")).strip()
        status = str(task.get("status", "Blocked")).strip()
        dependency_count = len([str(entry).strip() for entry in list(task.get("depends_on", [])) if str(entry).strip()])
        return (
            f"{task.get('title', 'Task')}\n"
            f"{task.get('id', 'task')} · {priority} · deps:{dependency_count} · {status}\n"
            f"{task.get('latest_update', '')}"
        )

    def _populate_primary_task_lane(self, tasks: list[dict[str, Any]]) -> None:
        surface = self._workspace_surface(self.snapshot) if self.snapshot is not None else {}
        bridge = _dict(surface.get("operator_bridge"))
        running = [task for task in tasks if str(task.get("status", "")).strip() == "Running"]
        pending = [task for task in tasks if str(task.get("status", "")).strip() == "Pending"]
        blocked = [task for task in tasks if str(task.get("status", "")).strip() == "Blocked"]
        done = [task for task in tasks if str(task.get("status", "")).strip() == "Done"]

        self.running_queue_label.setText(f"Running ({len(running)})")
        self.pending_queue_label.setText(f"Pending ({len(pending)})")
        self.done_queue_label.setText(f"Blocked ({len(blocked)})")
        self.completed_queue_label.setText(f"Done ({len(done)})")
        queue_counts = f"Running ({len(running)}) • Pending ({len(pending)}) • Blocked ({len(blocked)}) • Done ({len(done)})"
        queue_suffix = "▲" if self.task_queue_frame.isVisible() else "▼"
        self.queue_toggle_button.setText(f"{queue_counts} {queue_suffix}")
        self.task_queue_caption.setText("Queue strip stays secondary until you expand it.")

        for widget, items in (
            (self.running_queue_list, running),
            (self.pending_queue_list, pending),
            (self.done_queue_list, blocked),
            (self.completed_queue_list, done),
        ):
            widget.blockSignals(True)
            widget.clear()
            for task in items[:8]:
                item = QListWidgetItem(self._queue_item_text(task))
                item.setData(Qt.UserRole, str(task.get("id", "")).strip())
                item.setToolTip(str(task.get("summary", "")).strip())
                widget.addItem(item)
                if str(task.get("id", "")).strip() == self._selected_workspace_task_id:
                    widget.setCurrentItem(item)
            widget.blockSignals(False)

        active_task = self._select_active_run(tasks)
        if active_task is not None:
            self._active_run_task_id = str(active_task.get("id", "")).strip() or None
            self.active_run_title.setText(str(bridge.get("header_title", active_task.get("title", "Current Task"))).strip())
            header_status = str(bridge.get("header_status", f"Status: {active_task.get('status', 'Blocked')}")).strip()
            header_mode = str(bridge.get("header_mode", "Mode: Auto")).strip()
            self.active_run_status.setText(
                f"{header_status} • {header_mode}"
            )
        else:
            self._active_run_task_id = None
            self.active_run_title.setText(str(bridge.get("header_title", "No active run.")).strip())
            self.active_run_status.setText(str(bridge.get("header_status", "Queue is empty.")).strip())
        self.active_run_card.setHtml(self._task_stream_html(bridge, active_task))
        active_status = str((active_task or {}).get("status", "")).strip()
        active_task_type = str((active_task or {}).get("task_type", "")).strip()
        active_approval_id = str((active_task or {}).get("approval_id", "")).strip()
        active_review_gate = str((active_task or {}).get("review_gate", "")).strip()
        active_run_id = self._task_run_id(active_task)
        active_review_enabled = bool(active_approval_id) or active_review_gate == "operator_review"
        self.home_run_button.setVisible(False)
        self.home_approve_button.setEnabled(active_task is not None and active_review_enabled)
        self.home_reject_button.setEnabled(active_task is not None and active_review_enabled)
        self.home_inspect_button.setEnabled(active_task is not None)
        cancel_visible = active_task is not None and active_status == "Running"
        self.home_cancel_button.setVisible(cancel_visible)
        self.home_cancel_button.setEnabled(
            cancel_visible and bool(active_run_id) and active_task_type in {"agent_run", "orchestrated"}
        )

    def _toggle_queue_strip(self) -> None:
        showing = not self.task_queue_frame.isVisible()
        self.task_queue_frame.setVisible(showing)
        if self.snapshot is not None:
            self._populate_primary_task_lane(list(self._workspace_surface(self.snapshot).get("tasks", [])))

    def _toggle_inspect_panel(self) -> None:
        self._set_inspect_panel_visible(not self._inspect_panel_expanded)

    def _set_inspect_panel_visible(self, visible: bool) -> None:
        self._inspect_panel_expanded = visible
        self.inspect_panel.setVisible(visible)
        self.inspect_toggle_button.setText("Inspect ▲" if visible else "Inspect ▼")

    def _show_inspect_panel(self, *, tab: str | None = None, surface_tab_index: int | None = None) -> None:
        self._set_inspect_panel_visible(True)
        if tab == "operator" and hasattr(self, "inspect_operator_panel"):
            self.inspect_tabs.setCurrentWidget(self.inspect_operator_panel)
        elif tab == "workspaces" and hasattr(self, "inspect_workspace_panel"):
            self.inspect_tabs.setCurrentWidget(self.inspect_workspace_panel)
        elif tab == "activity" and hasattr(self, "inspect_activity_panel"):
            self.inspect_tabs.setCurrentWidget(self.inspect_activity_panel)
        else:
            self.inspect_tabs.setCurrentWidget(self.inspect_surface_panel)
            if surface_tab_index is not None:
                self.studio_surface_tabs.setCurrentIndex(surface_tab_index)

    def _on_primary_task_list_changed(self) -> None:
        widget = self.sender()
        if not isinstance(widget, QListWidget):
            return
        item = widget.currentItem()
        if item is None:
            return
        task_id = str(item.data(Qt.UserRole) or "").strip()
        if not task_id:
            return
        self._selected_workspace_task_id = task_id
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _populate_workspace_selector(self, workspaces: list[dict[str, Any]], active_workspace: dict[str, Any]) -> None:
        self.workspace_selector.blockSignals(True)
        self.workspace_selector.clear()
        active_id = str(active_workspace.get("id", "")).strip()
        for workspace in workspaces:
            label = (
                f"{workspace.get('name', 'Workspace')}  "
                f"[{workspace.get('type', 'project')}]  "
                f"{workspace.get('status', 'active')}"
            )
            self.workspace_selector.addItem(label, str(workspace.get("id", "")).strip())
        index = self.workspace_selector.findData(active_id)
        if index >= 0:
            self.workspace_selector.setCurrentIndex(index)
        self.workspace_selector.blockSignals(False)

    def _build_tree_item(self, node: dict[str, Any]) -> QTreeWidgetItem:
        item = QTreeWidgetItem(
            [
                str(node.get("relative_path", node.get("name", "item"))),
                str(node.get("type", "file")),
            ]
        )
        item.setData(0, Qt.UserRole, str(node.get("path", "")).strip())
        for child in list(node.get("children", [])):
            if isinstance(child, dict):
                item.addChild(self._build_tree_item(child))
        return item

    def _populate_workspace_file_tree(self, surface: dict[str, Any]) -> None:
        file_explorer = _dict(surface.get("file_explorer"))
        tree_root = _dict(file_explorer.get("tree"))
        self.workspace_file_tree.blockSignals(True)
        self.workspace_file_tree.clear()
        if tree_root:
            root_item = self._build_tree_item(tree_root)
            self.workspace_file_tree.addTopLevelItem(root_item)
            self.workspace_file_tree.expandItem(root_item)
            for column in range(2):
                self.workspace_file_tree.resizeColumnToContents(column)
            if self._selected_workspace_file_path:
                for item in self.workspace_file_tree.findItems("*", Qt.MatchWildcard | Qt.MatchRecursive, 0):
                    if str(item.data(0, Qt.UserRole) or "").strip() == self._selected_workspace_file_path:
                        self.workspace_file_tree.setCurrentItem(item)
                        break
        self.workspace_file_tree.blockSignals(False)

    def _populate_workspace_search_results(self) -> None:
        self.workspace_search_results.blockSignals(True)
        self.workspace_search_results.clear()
        for item in self._workspace_search_results_cache:
            result = QListWidgetItem(
                f"{item.get('relative_path', item.get('name', 'file'))}\n{item.get('snippet', '')}".strip()
            )
            result.setData(Qt.UserRole, str(item.get("path", "")).strip())
            self.workspace_search_results.addItem(result)
        self.workspace_search_results.blockSignals(False)

    def _update_status_strip(self, surface: dict[str, Any], brain: dict[str, str]) -> None:
        active_workspace = _dict(surface.get("active_workspace"))
        upgrades = [item for item in list(surface.get("upgrades", [])) if isinstance(item, dict)]
        latest_upgrade = upgrades[0] if upgrades else {}
        recent_events = [item for item in list(surface.get("event_stream", [])) if isinstance(item, dict)]
        self.status_brain_value.setText(brain["mode"])
        self.status_tier_value.setText(brain["permission"])
        self.status_workspace_value.setText(str(active_workspace.get("name", "No workspace")))
        self.status_upgrade_value.setText(str(latest_upgrade.get("status", "Review")))
        self.status_memory_value.setText(f"{len(self._workspace_messages(self.snapshot)) if self.snapshot else 0} msgs")
        self.status_voice_value.setText(str(self.current_session_id or "pending")[:8].upper())
        self.event_stream_status.setText(
            f"{len(recent_events)} recent event(s) tracked in the local runtime lane."
        )

    def _update_memory_surface(self, snapshot: DesktopSnapshot, surface: dict[str, Any]) -> None:
        active_workspace = _dict(surface.get("active_workspace"))
        file_explorer = _dict(surface.get("file_explorer"))
        selected_file = _dict(file_explorer.get("selected_file"))
        selected_task = self._selected_workspace_task() or self._active_workspace_task() or {}
        task_memory = _dict(surface.get("task_memory"))
        if isinstance(selected_task, dict) and str(selected_task.get("id", "")).strip():
            task_memory = self.host.task_memory(
                str(selected_task.get("id", "")).strip(),
                title=str(selected_task.get("title", "")).strip(),
            )
        current_task_memory_id = str(task_memory.get("task_id", "")).strip()
        should_hydrate_editors = (
            current_task_memory_id != self._loaded_task_memory_task_id
            or not any(
                editor.hasFocus()
                for editor in (
                    self.task_memory_goals,
                    self.task_memory_constraints,
                    self.task_memory_do_not_touch,
                    self.task_memory_notes,
                )
            )
        )
        if should_hydrate_editors:
            self._loaded_task_memory_task_id = current_task_memory_id or self._loaded_task_memory_task_id
            self.task_memory_goals.setPlainText("\n".join(str(item) for item in list(task_memory.get("goals", []))))
            self.task_memory_constraints.setPlainText("\n".join(str(item) for item in list(task_memory.get("constraints", []))))
            self.task_memory_do_not_touch.setPlainText("\n".join(str(item) for item in list(task_memory.get("do_not_touch", []))))
            self.task_memory_notes.setPlainText("\n".join(str(item) for item in list(task_memory.get("notes", []))))
        memory_payload = {
            "session_id": snapshot.session_id,
            "runtime_profile": snapshot.status.get("runtime_profile"),
            "active_workspace": active_workspace,
            "selected_task": selected_task,
            "task_memory": task_memory,
            "bridge_intelligence": surface.get("bridge_intelligence", {}),
            "selected_file": selected_file,
            "recent_events": list(surface.get("event_stream", []))[:8],
            "mystic": snapshot.mystic or {},
        }
        self.studio_memory_view.setPlainText(_pretty_json(memory_payload))

    def _update_replay_surface(self, surface: dict[str, Any]) -> None:
        replay = _dict(surface.get("replay"))
        branches = [item for item in list(surface.get("branches", [])) if isinstance(item, dict)]
        intelligence = _dict(surface.get("bridge_intelligence"))
        decision = _dict(intelligence.get("decision"))
        strategy = _dict(decision.get("strategy"))
        counterfactual = _dict(decision.get("counterfactual"))
        summary_html = f"""
        <html><body style="background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
        <div style="padding:4px 2px;">
          <div style="font-size:18px;font-weight:700;color:#f4dfbc;">Replay And Branching</div>
          <div style="margin-top:10px;"><b>Replay:</b> {escape(str(replay.get('summary', 'No replay summary.')))}</div>
          <div><b>Counterfactual:</b> {escape(str(counterfactual.get('reason', 'No alternative path recorded yet.')))}</div>
          <div><b>Strategy:</b> {escape(str(strategy.get('id', 'pending')))} • Gen {escape(str(strategy.get('generation', 0)))}</div>
        </div></body></html>
        """
        self.workspace_replay_summary.setHtml(summary_html)
        timeline_lines = []
        for item in list(replay.get("timeline", []))[-24:]:
            event = _dict(item)
            timeline_lines.append(
                f"{event.get('seq', 0):>2} | {event.get('time', 'Now')} | {event.get('scope', 'run')} | {event.get('label', '')}\n{event.get('detail', '')}"
            )
        self.workspace_replay_timeline.setPlainText(
            "\n\n".join(timeline_lines) if timeline_lines else "No replay timeline is available yet."
        )
        branch_lines = []
        for branch in branches:
            branch_lines.append(
                "\n".join(
                    [
                        f"{branch.get('title', 'Branch')} [{branch.get('state', 'review')}]",
                        f"Intent: {branch.get('intent', 'general')} • Risk: {branch.get('risk', 'low')}",
                        f"Reason: {branch.get('reason', '')}",
                        "Modules: " + ", ".join(str(item) for item in list(branch.get("affected_modules", []))[:6]),
                    ]
                )
            )
        self.workspace_branch_summary.setPlainText(
            "\n\n".join(branch_lines) if branch_lines else "No branch records are available yet."
        )

    def _update_upgrade_surface(self, surface: dict[str, Any]) -> None:
        upgrades = [item for item in list(surface.get("upgrades", [])) if isinstance(item, dict)]
        self.studio_upgrade_list.blockSignals(True)
        self.studio_upgrade_list.clear()
        for item in upgrades:
            row = QListWidgetItem(
                f"{item.get('title', 'Upgrade')}\n{item.get('status', 'Review')} · {item.get('summary', '')}"
            )
            row.setData(Qt.UserRole, str(item.get("id", "")).strip())
            self.studio_upgrade_list.addItem(row)
        self.studio_upgrade_list.blockSignals(False)
        if upgrades:
            if self.studio_upgrade_list.currentRow() < 0:
                self.studio_upgrade_list.setCurrentRow(0)
            self._on_upgrade_selected()
        else:
            self.studio_upgrade_summary.setHtml("<html><body style='color:#edf2f7;'>No upgrades staged.</body></html>")

    def _update_file_viewer(self, surface: dict[str, Any]) -> None:
        selected_file = _dict(_dict(surface.get("file_explorer")).get("selected_file"))
        if not selected_file:
            self.studio_file_meta.setText("Select a file inside a registered workspace.")
            self.studio_file_preview.clear()
            return
        self.studio_file_meta.setText(
            f"{selected_file.get('relative_path', 'file')}  "
            f"({'binary' if selected_file.get('binary') else selected_file.get('type', 'file')})"
        )
        self.studio_file_preview.setPlainText(str(selected_file.get("content", "")))

    def _populate_changes_panel(self, surface: dict[str, Any]) -> None:
        bridge = _dict(surface.get("operator_bridge"))
        changes = [item for item in list(bridge.get("changes", [])) if isinstance(item, dict)]
        self.workspace_changes_summary.setText(
            clean_operator_text(bridge.get("changes_summary", "")) or "No workspace changes are waiting right now."
        )
        self.workspace_changes_list.blockSignals(True)
        self.workspace_changes_list.clear()
        for change in changes:
            item = QListWidgetItem(
                f"{change.get('path', 'workspace change')}\n"
                f"{change.get('status', '?')} · {clean_operator_text(change.get('summary', ''))}"
            )
            item.setData(Qt.UserRole, dict(change))
            item.setToolTip(clean_operator_text(change.get("summary", "")))
            self.workspace_changes_list.addItem(item)
        self.workspace_changes_list.blockSignals(False)
        if self.workspace_changes_list.count() > 0:
            self.workspace_changes_list.setCurrentRow(0)
            selected = self.workspace_changes_list.currentItem()
            payload = _dict(selected.data(Qt.UserRole)) if selected is not None else {}
            self.workspace_diff_preview.setPlainText(
                str(payload.get("diff", "")).strip() or clean_operator_text(payload.get("summary", ""))
            )
        else:
            self.workspace_diff_preview.setPlainText("No diff is available for the current workspace state.")

    def _on_workspace_change_selected(self) -> None:
        item = self.workspace_changes_list.currentItem()
        if item is None:
            self.workspace_diff_preview.setPlainText("No diff is available for the current workspace state.")
            return
        payload = _dict(item.data(Qt.UserRole))
        self.workspace_diff_preview.setPlainText(
            str(payload.get("diff", "")).strip() or clean_operator_text(payload.get("summary", ""))
        )

    def _populate_workspace_repos(self, repos: list[dict[str, Any]]) -> None:
        filtered = []
        query = self._workspace_repo_query.strip().lower()
        for repo in repos:
            haystack = " ".join(
                [
                    str(repo.get("name", "")),
                    str(repo.get("path", "")),
                    str(repo.get("branch", "")),
                    str(repo.get("status", "")),
                    str(repo.get("detail", "")),
                ]
            ).lower()
            if not query or query in haystack:
                filtered.append(repo)

        self.workspace_repo_list.blockSignals(True)
        self.workspace_repo_list.clear()
        for repo in filtered:
            item = QListWidgetItem(
                f"{repo.get('name', 'Repo')}\n"
                f"{repo.get('branch', 'workspace')} · {repo.get('status', 'Connected')}\n"
                f"{repo.get('detail', '')}"
            )
            item.setData(Qt.UserRole, str(repo.get("id", "")).strip())
            item.setToolTip(str(repo.get("path", "")).strip())
            self.workspace_repo_list.addItem(item)
            if str(repo.get("id", "")).strip() == self._selected_workspace_repo_id:
                self.workspace_repo_list.setCurrentItem(item)
        self.workspace_repo_list.blockSignals(False)
        footer_text = f"{len(repos)} repos in scope. Add Workspace keeps ARIS bounded to registered roots."
        self.workspace_repo_footer.setText(footer_text)
        self.workspace_repo_governance_footer.setText(footer_text)

    def _populate_workspace_tasks(self, repos: list[dict[str, Any]], tasks: list[dict[str, Any]]) -> None:
        counts = self._workspace_task_counts(tasks)
        for label, button in self.task_tab_buttons.items():
            button.setText(f"{label} ({counts.get(label, 0)})")

        repo_names = {str(item.get("id", "")).strip(): str(item.get("name", "")).strip() for item in repos}
        query = self._workspace_task_query.strip().lower()
        filtered: list[dict[str, Any]] = []
        for task in tasks:
            status = str(task.get("status", "")).strip()
            if self._workspace_task_tab != "All" and status != self._workspace_task_tab:
                continue
            haystack = " ".join(
                [
                    str(task.get("title", "")),
                    str(task.get("id", "")),
                    str(task.get("summary", "")),
                    str(task.get("latest_update", "")),
                    repo_names.get(str(task.get("repo_id", "")).strip(), ""),
                ]
            ).lower()
            if query and query not in haystack:
                continue
            filtered.append(task)

        self.workspace_task_list.blockSignals(True)
        self.workspace_task_list.clear()
        for task in filtered:
            repo_name = repo_names.get(str(task.get("repo_id", "")).strip(), "Workspace")
            item = QListWidgetItem(
                f"{task.get('title', 'Task')}\n"
                f"{task.get('id', 'task')} · {repo_name} · {task.get('status', 'Blocked')} · {task.get('priority', 'P2')}\n"
                f"{task.get('latest_update', '')}"
            )
            item.setData(Qt.UserRole, str(task.get("id", "")).strip())
            item.setToolTip(str(task.get("summary", "")).strip())
            self.workspace_task_list.addItem(item)
            if str(task.get("id", "")).strip() == self._selected_workspace_task_id:
                self.workspace_task_list.setCurrentItem(item)
        self.workspace_task_list.blockSignals(False)

    def _update_workspace_context_panel(self, snapshot: DesktopSnapshot, surface: dict[str, Any]) -> None:
        repos = [item for item in surface.get("repos", []) if isinstance(item, dict)]
        tasks = [item for item in surface.get("tasks", []) if isinstance(item, dict)]
        selected_repo, selected_task = self._workspace_selected_context(surface)
        if selected_task is not None:
            self._selected_workspace_repo_id = str(selected_task.get("repo_id", "")).strip() or self._selected_workspace_repo_id

        brain = self._current_brain_state_payload()
        active_workspace = _dict(surface.get("active_workspace"))
        status = snapshot.status
        forge = _dict(status.get("forge"))
        forge_eval = _dict(status.get("forge_eval"))
        evolving_engine = _dict(status.get("evolving_engine"))
        model_router = _dict(status.get("model_router"))
        pinned_system = str(model_router.get("pinned_system", "")).strip()
        router_description = str(model_router.get("mode", "auto"))
        if pinned_system:
            router_description += f" pinned to {pinned_system.replace('_', ' ')}"
        route = route_for_target(brain["target"])
        brain_pills = "".join(
            [
                _pill_span(
                    (
                        f"Router Pinned: {pinned_system.replace('_', ' ').title()}"
                        if pinned_system
                        else f"Router: {str(model_router.get('mode', 'auto')).upper()}"
                    ),
                    "review" if pinned_system else "connected",
                ),
                _pill_span(
                    "Forge Available" if forge.get("connected") else "Forge Offline",
                    "connected" if forge.get("connected") else "blocked",
                ),
                _pill_span(
                    "Approval Gated"
                    if brain["permission"] in {"Approval Required", "Suggest Only", "Read Only"}
                    else "Governed Workspace Actions",
                    "review" if brain["permission"] in {"Approval Required", "Suggest Only", "Read Only"} else "connected",
                ),
                _pill_span(
                    "Evolving Runtime Active" if evolving_engine.get("active") else "Evolving Core Locked",
                    "connected" if evolving_engine.get("active") else "warning",
                ),
            ]
        )

        self.operator_session_label.setText(f"Session: {snapshot.session_id}")
        repo_name = str(selected_repo.get("name", "No repo selected")).strip() if isinstance(selected_repo, dict) else "No repo selected"
        task_name = str(selected_task.get("title", "No task selected")).strip() if isinstance(selected_task, dict) else "No task selected"
        self.workspace_prompt_context.setText(
            f"ARIS is speaking in {brain['mode']} mode across {brain['scope'].lower()}. "
            f"Active workspace: {active_workspace.get('name', 'No workspace')} ({active_workspace.get('type', 'workspace')}). "
            f"Selected repo: {repo_name}. "
            f"Selected task: {task_name}. "
            f"Target is {brain['target']}, permission is {brain['permission'].lower()}, model routing is "
            f"{router_description}, and the evolving-runtime path is "
            f"{'admitted through UL' if evolving_engine.get('active') else 'still locked'}."
        )
        self.workspace_brain_pills.setText(f"<html><body style='margin:0;padding:0;'>{brain_pills}</body></html>")
        self.workspace_route_summary.setText("Route: " + " -> ".join(route))
        self.workspace_recent_tasks.setPlainText(self._workspace_recent_tasks_text(surface))

        if isinstance(selected_repo, dict):
            repo_html = f"""
            <html><body style="background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
            <div style="padding:4px 2px;">
              <div style="font-size:20px;font-weight:700;color:#f4dfbc;">{escape(str(selected_repo.get("name", "Repo")))}</div>
              <div style="margin-top:6px;color:#8ea4bb;">{escape(str(selected_repo.get('path', '')))}</div>
              <div style="margin-top:12px;"><b>Branch:</b> {escape(str(selected_repo.get('branch', 'workspace')))}</div>
              <div><b>Status:</b> {escape(str(selected_repo.get('status', 'Connected')))}</div>
              <div><b>Last sync:</b> {escape(str(selected_repo.get('last_sync', 'Now')))}</div>
              <div style="margin-top:10px;line-height:1.5;">{escape(str(selected_repo.get('detail', '')))}</div>
            </div></body></html>
            """
        else:
            repo_html = "<html><body style='color:#edf2f7;'>No repo selected.</body></html>"
        self.workspace_selected_repo.setHtml(repo_html)

        task_html = self._task_card_html(selected_task)
        self.workspace_selected_task.setHtml(task_html)

        status_pills_html = "".join(
            _pill_span(label, "neutral")
            for label in workspace_status_pills(brain)
        )
        brain_html = f"""
        <html><body style="background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
        <div style="padding:4px 2px;">
          <div style="font-size:18px;font-weight:700;color:#f4dfbc;">Brain State</div>
          <div style="margin-top:10px;"><b>Mode:</b> {escape(brain['mode'])}</div>
          <div><b>Scope:</b> {escape(brain['scope'])}</div>
          <div><b>Target:</b> {escape(brain['target'])}</div>
          <div><b>Permission:</b> {escape(brain['permission'])}</div>
          <div><b>Response Style:</b> {escape(brain['response_style'])}</div>
          <div style="margin-top:12px;color:#8ea4bb;">{" -> ".join(escape(item) for item in route)}</div>
          <div style="margin-top:12px;">{status_pills_html}</div>
        </div></body></html>
        """
        self.workspace_brain_state.setHtml(brain_html)

        worker = _dict(surface.get("worker"))
        lines = [str(item) for item in worker.get("lines", [])]
        worker_text = f"{worker.get('title', 'Worker Surface')} [{worker.get('status', 'Ready')}]\n\n" + "\n".join(lines)
        self.workspace_worker_output.setPlainText(worker_text.strip())

        worker_status_html = f"""
        <html><body style="background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
        <div style="padding:4px 2px;">
          <div style="font-size:18px;font-weight:700;color:#f4dfbc;">Worker / Protection Status</div>
          <div style="margin-top:10px;"><b>ARIS:</b> Active</div>
          <div><b>Forge route:</b> {"Available" if forge.get("connected") else "Unavailable"}</div>
          <div><b>ForgeEval route:</b> {"Available" if forge_eval.get("connected") else "Unavailable"}</div>
          <div><b>Evolving core:</b> {"Admitted through UL runtime" if evolving_engine.get("active") else "Locked and unavailable"}</div>
          <div><b>Current worker lane:</b> {escape(str(worker.get('title', 'Worker Surface')))}</div>
          <div><b>Current state:</b> {escape(str(worker.get('status', 'Ready')))}</div>
        </div></body></html>
        """
        self.workspace_worker_status.setHtml(worker_status_html)

        event_items = [item for item in list(surface.get("event_stream", [])) if isinstance(item, dict)] or [
            item for item in list(surface.get("activity", [])) if isinstance(item, dict)
        ]
        activity_lines = []
        for item in event_items[:12]:
            if not isinstance(item, dict):
                continue
            activity_lines.append(
                f"{item.get('timestamp', item.get('time', 'Now'))}  {item.get('title', item.get('label', 'Activity'))}\n"
                f"{item.get('detail', '')}"
            )
        self.workspace_activity_feed.setPlainText("\n\n".join(activity_lines))
        buttons_enabled = isinstance(selected_task, dict)
        task_status = str(selected_task.get("status", "")).strip() if isinstance(selected_task, dict) else ""
        task_type = str(selected_task.get("task_type", "")).strip() if isinstance(selected_task, dict) else ""
        approval_id = str(selected_task.get("approval_id", "")).strip() if isinstance(selected_task, dict) else ""
        review_gate = str(selected_task.get("review_gate", "")).strip() if isinstance(selected_task, dict) else ""
        run_enabled = buttons_enabled and task_status not in {"Running", "Blocked"}
        if task_type == "orchestrated" and task_status in {"Pending", "Blocked"}:
            run_enabled = False
        if approval_id or review_gate == "operator_review":
            run_enabled = False
        self.workspace_run_button.setEnabled(run_enabled)
        review_enabled = bool(approval_id) or review_gate == "operator_review"
        self.workspace_approve_button.setEnabled(buttons_enabled and review_enabled)
        self.workspace_reject_button.setEnabled(buttons_enabled and review_enabled)
        self.workspace_logs_button.setEnabled(buttons_enabled)
        self.workspace_ship_button.setEnabled(True)
        self._populate_primary_task_lane(tasks)
        counts = self._workspace_task_counts(tasks)
        self.task_lane_summary.setText(
            "Enter task -> watch run -> inspect -> approve or reject. "
            f"Queue strip: {counts.get('Running', 0)} running · "
            f"{counts.get('Pending', 0)} pending · "
            f"{counts.get('Blocked', 0)} blocked · {counts.get('Done', 0)} done."
        )
        self._update_status_strip(surface, brain)

    def _update_operator(self, snapshot: DesktopSnapshot) -> None:
        surface = self._workspace_surface(snapshot)
        self.chat_output.setHtml(_render_transcript(self._workspace_messages(snapshot)))
        self._active_workspace_id = str(_dict(surface.get("active_workspace")).get("id", "")).strip() or self._active_workspace_id
        self._populate_workspace_selector(
            list(surface.get("workspaces", [])),
            _dict(surface.get("active_workspace")),
        )
        self._populate_workspace_repos(list(surface.get("repos", [])))
        self._populate_workspace_tasks(list(surface.get("repos", [])), list(surface.get("tasks", [])))
        self._populate_workspace_file_tree(surface)
        self._populate_workspace_search_results()
        self._update_workspace_context_panel(snapshot, surface)
        self._update_memory_surface(snapshot, surface)
        self._update_upgrade_surface(surface)
        self._update_replay_surface(surface)
        self._update_file_viewer(surface)
        self._populate_changes_panel(surface)

    def _on_workspace_repo_search_changed(self, text: str) -> None:
        self._workspace_repo_query = str(text or "")
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _on_workspace_task_search_changed(self, text: str) -> None:
        self._workspace_task_query = str(text or "")
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _set_workspace_task_tab(self, label: str) -> None:
        self._workspace_task_tab = label
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _on_brain_controls_changed(self, _value: str) -> None:
        current_mode = self.brain_mode.currentText() if hasattr(self, "brain_mode") else ""
        if current_mode and current_mode != self._last_announced_brain_mode:
            if self._last_announced_brain_mode:
                speak(f"Switching to {current_mode} mode.", "brain_switch")
            self._last_announced_brain_mode = current_mode
        if hasattr(self, "send_button") and self._chat_thread is None:
            self.send_button.setText(self._send_button_label())
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _on_sidebar_project_changed(self) -> None:
        item = self.project_list.currentItem()
        if item is None:
            return
        repo_id = str(item.data(Qt.UserRole) or "").strip()
        if not repo_id:
            return
        self._selected_workspace_repo_id = repo_id
        if self.snapshot is not None:
            surface = self._workspace_surface(self.snapshot)
            tasks = [
                task for task in list(surface.get("tasks", []))
                if isinstance(task, dict) and str(task.get("repo_id", "")).strip() == repo_id
            ]
            if tasks:
                self._selected_workspace_task_id = str(tasks[0].get("id", "")).strip()
            self._update_operator(self.snapshot)

    def _on_sidebar_task_changed(self) -> None:
        item = self.sidebar_task_list.currentItem()
        if item is None:
            return
        task_id = str(item.data(Qt.UserRole) or "").strip()
        if not task_id:
            return
        self._selected_workspace_task_id = task_id
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _on_workspace_repo_changed(self) -> None:
        item = self.workspace_repo_list.currentItem()
        if item is None:
            return
        repo_id = str(item.data(Qt.UserRole) or "").strip()
        if not repo_id:
            return
        self._selected_workspace_repo_id = repo_id
        if self.snapshot is not None:
            surface = self._workspace_surface(self.snapshot)
            tasks = [task for task in list(surface.get("tasks", [])) if str(task.get("repo_id", "")).strip() == repo_id]
            if tasks:
                self._selected_workspace_task_id = str(tasks[0].get("id", "")).strip()
            self._update_workspace_context_panel(self.snapshot, surface)

    def _on_workspace_task_changed(self) -> None:
        item = self.workspace_task_list.currentItem()
        if item is None:
            return
        task_id = str(item.data(Qt.UserRole) or "").strip()
        if not task_id:
            return
        self._selected_workspace_task_id = task_id
        if self.snapshot is not None:
            surface = self._workspace_surface(self.snapshot)
            task = next(
                (entry for entry in list(surface.get("tasks", [])) if str(entry.get("id", "")).strip() == task_id),
                None,
            )
            if isinstance(task, dict):
                self._selected_workspace_repo_id = str(task.get("repo_id", "")).strip() or self._selected_workspace_repo_id
            self._update_workspace_context_panel(self.snapshot, surface)

    def _on_active_workspace_changed(self) -> None:
        workspace_id = str(self.workspace_selector.currentData() or "").strip()
        if not workspace_id or workspace_id == self._active_workspace_id:
            return
        self.host.activate_workspace(workspace_id)
        self._active_workspace_id = workspace_id
        self._selected_workspace_file_path = None
        self._workspace_search_results_cache = []
        self.refresh_from_runtime(select_session_id=self.current_session_id)

    def _add_workspace(self) -> None:
        current_index = self.tabs.currentIndex()
        workspace = self.host.select_and_add_workspace()
        if workspace is None:
            return
        self._active_workspace_id = str(workspace.get("id", "")).strip() or self._active_workspace_id
        self._workspace_add_activity(
            "Workspace added",
            f"{workspace.get('name', 'Workspace')} was added to the registry and made active.",
            "connected",
        )
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.tabs.setCurrentIndex(current_index)

    def _on_workspace_file_search_changed(self, text: str) -> None:
        self._workspace_file_search_query = str(text or "")
        if not self._workspace_file_search_query.strip():
            self._workspace_search_results_cache = []
            self._populate_workspace_search_results()
            return
        self._workspace_search_results_cache = self.host.search_workspace(
            self._workspace_file_search_query,
            workspace_id=self._active_workspace_id,
        )
        self._populate_workspace_search_results()

    def _selected_workspace_target_path(self) -> str | None:
        search_item = self.workspace_search_results.currentItem()
        if search_item is not None:
            search_path = str(search_item.data(Qt.UserRole) or "").strip()
            if search_path:
                return search_path
        tree_item = self.workspace_file_tree.currentItem()
        if tree_item is not None:
            tree_path = str(tree_item.data(0, Qt.UserRole) or "").strip()
            if tree_path:
                return tree_path
        return self._selected_workspace_file_path

    def _on_workspace_file_changed(self) -> None:
        selected_path = self._selected_workspace_target_path()
        if not selected_path:
            return
        self._selected_workspace_file_path = selected_path
        self.host.preview_workspace_target(selected_path, workspace_id=self._active_workspace_id)
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.studio_surface_tabs.setCurrentIndex(4)

    def _on_workspace_search_result_changed(self) -> None:
        selected_path = self._selected_workspace_target_path()
        if not selected_path:
            return
        self._selected_workspace_file_path = selected_path
        self.host.preview_workspace_target(selected_path, workspace_id=self._active_workspace_id)
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.studio_surface_tabs.setCurrentIndex(4)

    def _open_selected_workspace_target(self) -> None:
        selected_path = self._selected_workspace_target_path()
        if not selected_path:
            return
        self._selected_workspace_file_path = selected_path
        self.host.preview_workspace_target(selected_path, workspace_id=self._active_workspace_id)
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.studio_surface_tabs.setCurrentIndex(4)

    def _run_workspace_file_action(self, action_name: str) -> None:
        selected_path = self._selected_workspace_target_path()
        if not selected_path:
            return
        payload = self.host.workspace_action(action_name, selected_path, workspace_id=self._active_workspace_id)
        if action_name == "copy_path":
            QApplication.clipboard().setText(str(payload.get("path", "")))
        elif action_name == "send_to_aris":
            prompt = str(_dict(payload.get("payload")).get("prompt", "")).strip()
            if prompt:
                self.chat_input.setPlainText(prompt)
        elif action_name == "open":
            self._selected_workspace_file_path = str(payload.get("path", "")).strip() or self._selected_workspace_file_path
            self.host.preview_workspace_target(self._selected_workspace_file_path, workspace_id=self._active_workspace_id)
            self.refresh_from_runtime(select_session_id=self.current_session_id)
            self.studio_surface_tabs.setCurrentIndex(4)
        self.workspace_worker_output.setPlainText(_pretty_json(payload))
        self._workspace_add_activity(
            f"File action: {action_name}",
            str(payload.get("summary", "Workspace file action completed.")),
            "connected" if action_name in {"open", "send_to_aris", "use_in_task"} else "neutral",
        )
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _collect_feedback(self, feedback_type: str) -> None:
        if self.snapshot is None:
            return
        normalized_feedback_type = feedback_type
        if feedback_type == "confusing":
            selected_type, accepted_type = QInputDialog.getItem(
                self,
                "Feedback Type",
                "Classify this feedback:",
                ["confusing", "impressive"],
                0,
                False,
            )
            if not accepted_type or not str(selected_type or "").strip():
                return
            normalized_feedback_type = str(selected_type).strip().lower()
        prompt_title = {
            "bug": "Report Bug",
            "confusing": "Give Feedback",
            "impressive": "Share What Worked",
            "feature_request": "Request Feature",
        }.get(normalized_feedback_type, "Give Feedback")
        note, accepted = QInputDialog.getMultiLineText(
            self,
            prompt_title,
            "Tell ARIS what happened. Recent runtime context will be attached automatically.",
        )
        if not accepted or not str(note or "").strip():
            return
        surface = self._workspace_surface(self.snapshot)
        active_workspace = _dict(surface.get("active_workspace"))
        worker = _dict(surface.get("worker"))
        logs = [{"kind": "worker", "detail": str(line)} for line in list(worker.get("lines", []))]
        payload = self.host.submit_feedback(
            feedback_type=normalized_feedback_type,
            user_note=str(note).strip(),
            active_brain=self.brain_mode.currentText(),
            active_tier=self.brain_permission.currentText(),
            active_workspace=str(active_workspace.get("name", "No workspace")),
            recent_logs=logs,
        )
        self.workspace_worker_output.setPlainText(_pretty_json(payload.get("packet", {})))
        self._workspace_add_activity(
            "Feedback captured",
            f"{normalized_feedback_type} packet exported to {payload.get('path', 'feedback path')}.",
            "connected",
        )
        if self.snapshot is not None:
            self.refresh_from_runtime(select_session_id=self.current_session_id)
        QMessageBox.information(self, prompt_title, _pretty_json(payload))

    def _open_feedback_form(self) -> None:
        if self.snapshot is None:
            return
        surface = self._workspace_surface(self.snapshot)
        feedback_payload = _dict(surface.get("feedback"))
        target_url = str(feedback_payload.get("external_form_url", "")).strip()
        if not target_url:
            QMessageBox.information(
                self,
                "Feedback Form",
                "No external feedback form URL is configured. In-app export remains available.",
            )
            return
        QDesktopServices.openUrl(QUrl(target_url))

    def _on_upgrade_selected(self) -> None:
        if self.snapshot is None:
            return
        surface = self._workspace_surface(self.snapshot)
        upgrade_id = ""
        item = self.studio_upgrade_list.currentItem()
        if item is not None:
            upgrade_id = str(item.data(Qt.UserRole) or "").strip()
        selected_upgrade = next(
            (
                entry
                for entry in list(surface.get("upgrades", []))
                if str(entry.get("id", "")).strip() == upgrade_id
            ),
            _dict(list(surface.get("upgrades", []))[0]) if surface.get("upgrades") else {},
        )
        if not selected_upgrade:
            self.studio_upgrade_summary.setHtml("<html><body style='color:#edf2f7;'>No upgrade selected.</body></html>")
            return
        self.studio_upgrade_summary.setHtml(
            f"""
            <html><body style="background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
            <div style="padding:6px 4px;">
              <div style="font-size:20px;font-weight:700;color:#f4dfbc;">{escape(str(selected_upgrade.get("title", "Upgrade")))}</div>
              <div style="margin-top:8px;"><b>Status:</b> {escape(str(selected_upgrade.get("status", "Review")))}</div>
              <div style="margin-top:10px;line-height:1.5;">{escape(str(selected_upgrade.get("summary", "")))}</div>
            </div></body></html>
            """
        )

    def _set_upgrade_status(self, status_label: str) -> None:
        item = self.studio_upgrade_list.currentItem()
        if item is None:
            return
        upgrade_id = str(item.data(Qt.UserRole) or "").strip()
        if not upgrade_id:
            return
        self._upgrade_status_overrides[upgrade_id] = status_label
        self._workspace_add_activity(
            f"Upgrade {status_label.lower()}",
            f"{upgrade_id} moved to {status_label} by operator decision.",
            "connected" if status_label == "Accepted" else "warning",
        )
        speak(
            "Upgrade accepted." if status_label == "Accepted" else "Upgrade rejected. Stability not preserved.",
            "upgrade_accepted" if status_label == "Accepted" else "upgrade_rejected",
        )
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _toggle_repo_context(self) -> None:
        self._repo_context_attached = not self._repo_context_attached
        self.repo_context_button.setText(
            "Detach Workspace Context" if self._repo_context_attached else "Attach Workspace Context"
        )
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _toggle_link_task(self) -> None:
        self._linked_task_enabled = not self._linked_task_enabled
        self.link_task_button.setText("Unlink Task" if self._linked_task_enabled else "Link Task")
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _toggle_approval_mode(self) -> None:
        self._approval_mode = "Fast Track" if self._approval_mode == "Guarded" else "Guarded"
        self.approval_mode_button.setText(f"Approval Mode: {self._approval_mode}")
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _save_task_memory(self) -> None:
        task = self._selected_workspace_task() or self._active_workspace_task()
        if not isinstance(task, dict):
            QMessageBox.information(self, self.host.profile.desktop_title, "No task is selected for task memory.")
            return
        record = self.host.save_task_memory(
            task_id=str(task.get("id", "")).strip(),
            title=str(task.get("title", "Task")).strip(),
            goals=[line.strip() for line in self.task_memory_goals.toPlainText().splitlines() if line.strip()],
            constraints=[line.strip() for line in self.task_memory_constraints.toPlainText().splitlines() if line.strip()],
            notes=[line.strip() for line in self.task_memory_notes.toPlainText().splitlines() if line.strip()],
            do_not_touch=[line.strip() for line in self.task_memory_do_not_touch.toPlainText().splitlines() if line.strip()],
        )
        self._loaded_task_memory_task_id = str(record.get("task_id", "")).strip() or self._loaded_task_memory_task_id
        self._workspace_add_activity(
            "Task memory saved",
            f"Structured memory for {task.get('title', 'Task')} was updated.",
            "connected",
        )
        self.workspace_worker_output.setPlainText(_pretty_json(record))
        if self.snapshot is not None:
            self.refresh_from_runtime(select_session_id=self.current_session_id)

    def _workspace_add_activity(self, label: str, detail: str, tone: str = "neutral") -> None:
        self._workspace_activity_overrides.insert(
            0,
            {
                "id": f"ui-{len(self._workspace_activity_overrides) + 1}",
                "time": "Now",
                "label": label,
                "detail": detail,
                "tone": tone,
            },
        )
        self._workspace_activity_overrides = self._workspace_activity_overrides[:12]

    def _reset_workspace_runtime_state(self) -> None:
        self._workspace_transcript_override = []
        self._workspace_task_overrides.clear()
        self._workspace_activity_overrides.clear()
        self._workspace_worker_override = None
        self._selected_workspace_repo_id = None
        self._selected_workspace_task_id = None
        self._loaded_task_memory_task_id = None
        self._latest_chat_meta = {}

    def _selected_workspace_task(self) -> dict[str, Any] | None:
        if self.snapshot is None:
            return None
        surface = self._workspace_surface(self.snapshot)
        _selected_repo, selected_task = self._workspace_selected_context(surface)
        return selected_task if isinstance(selected_task, dict) else None

    def _active_workspace_task(self) -> dict[str, Any] | None:
        if self.snapshot is None or not self._active_run_task_id:
            return None
        surface = self._workspace_surface(self.snapshot)
        for task in list(surface.get("tasks", [])):
            if isinstance(task, dict) and str(task.get("id", "")).strip() == self._active_run_task_id:
                return task
        return None

    def _task_run_id(self, task: dict[str, Any] | None) -> str:
        if not isinstance(task, dict):
            return ""
        task_type = str(task.get("task_type", "")).strip()
        if task_type == "agent_run":
            return str(task.get("run_id", "")).strip() or str(task.get("id", "")).strip()
        return str(task.get("linked_run_id", "")).strip() or str(task.get("run_id", "")).strip()

    def _run_active_workspace_task(self) -> None:
        self._run_task_entry(self._active_workspace_task())

    def _approve_active_run(self) -> None:
        self._approve_task_entry(self._active_workspace_task())

    def _reject_active_run(self) -> None:
        self._reject_task_entry(self._active_workspace_task())

    def _inspect_active_run(self) -> None:
        self._show_logs_for_task(self._active_workspace_task())

    def _cancel_active_run(self) -> None:
        self._cancel_task_entry(self._active_workspace_task())

    def _begin_runtime_worker(self, worker: QObject, *, button_text: str) -> None:
        self._streaming_reply = ""
        self.send_button.setEnabled(False)
        self.send_button.setText(button_text)
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)  # type: ignore[arg-type]
        getattr(worker, "event_received").connect(self._on_chat_event)
        getattr(worker, "failed").connect(self._on_chat_failed)
        getattr(worker, "finished").connect(self._on_chat_finished)
        getattr(worker, "finished").connect(thread.quit)
        getattr(worker, "failed").connect(thread.quit)
        thread.finished.connect(self._cleanup_chat_thread)
        self._chat_thread = thread
        self._chat_worker = worker  # type: ignore[assignment]
        thread.start()

    def _start_runtime_chat(
        self,
        *,
        prompt: str,
        chat_mode: str,
        fast_mode: bool,
    ) -> None:
        session_id = self.current_session_id or self.host.ensure_session()
        base_messages = self._workspace_messages(self.snapshot) if self.snapshot is not None else seed_workspace_messages()
        self._stream_base_messages = [dict(item) for item in base_messages[-15:]]
        self._stream_base_messages.append({"role": "user", "content": prompt, "created_at": ""})
        self._live_task_stream_lines = ["[Now] Starting task..."]
        self.chat_output.setHtml(_render_transcript(self._stream_base_messages))
        self.workspace_worker_output.setPlainText(
            _pretty_json(
                {
                    "mode": chat_mode,
                    "fast_mode": fast_mode,
                    "session_id": session_id,
                    "status": "queued",
                    "message": prompt,
                }
            )
        )
        self._workspace_add_activity(
            "Task dispatched",
            f"ARIS started a governed {chat_mode} run in session {session_id}.",
            "connected",
        )
        worker = ChatWorker(
            host=self.host,
            session_id=session_id,
            user_message=prompt,
            mode=chat_mode,
            fast_mode=fast_mode,
        )
        self._begin_runtime_worker(worker, button_text="Running...")

    def _start_approval_resolution(self, *, approval_id: str, approved: bool) -> None:
        session_id = self.current_session_id or self.host.ensure_session()
        decision_label = "approved" if approved else "rejected"
        self._live_task_stream_lines = [
            f"[Now] Review decision queued for {approval_id}.",
            f"[Now] Changes were {decision_label} by the operator.",
        ]
        self.workspace_worker_output.setPlainText(
            _pretty_json(
                {
                    "mode": "agent_resume",
                    "session_id": session_id,
                    "approval_id": approval_id,
                    "decision": decision_label,
                    "status": "queued",
                }
            )
        )
        self._workspace_add_activity(
            "Approval decision sent",
            f"ARIS {decision_label} approval {approval_id} and resumed the governed run path.",
            "warning" if not approved else "connected",
        )
        worker = ApprovalWorker(
            host=self.host,
            session_id=session_id,
            approval_id=approval_id,
            approved=approved,
        )
        self._begin_runtime_worker(
            worker,
            button_text="Approving..." if approved else "Rejecting...",
        )

    def _task_intelligence(self, task: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(task, dict):
            return {}
        surface = self._workspace_surface(self.snapshot) if self.snapshot is not None else {}
        run_id = self._task_run_id(task)
        run_payload = self.host.get_agent_run(run_id) if run_id else {}
        run_events = self.host.list_agent_run_events(run_id, limit=40) if run_id else []
        return self.host.bridge_intelligence.build_for_task(
            task=task,
            review=_dict(surface.get("review")),
            run=run_payload,
            run_events=run_events,
            local_events=list(surface.get("event_stream", [])),
        )

    def _run_task_entry(self, selected_task: dict[str, Any] | None) -> None:
        if selected_task is None:
            return
        if self._chat_thread is not None:
            return
        selected_task_type = str(selected_task.get("task_type", "")).strip()
        selected_task_status = str(selected_task.get("status", "")).strip()
        if selected_task_type == "orchestrated" and selected_task_status in {"Pending", "Running", "Blocked"}:
            self._workspace_add_activity(
                "Queue focus updated",
                f"{selected_task.get('title', 'Task')} is already in the governed queue.",
                "neutral",
            )
            self.refresh_from_runtime(select_session_id=self.current_session_id)
            return
        surface = self._workspace_surface(self.snapshot) if self.snapshot is not None else {}
        selected_repo, _ = self._workspace_selected_context(surface)
        brain = self._current_brain_state_payload()
        prompt_lines = [
            f"Task: {str(selected_task.get('title', 'Workspace task')).strip()}",
            f"Summary: {str(selected_task.get('summary', '')).strip() or str(selected_task.get('latest_update', '')).strip()}",
        ]
        if isinstance(selected_repo, dict):
            prompt_lines.append(f"Repo: {str(selected_repo.get('name', 'Workspace')).strip()}")
            prompt_lines.append(f"Branch: {str(selected_repo.get('branch', 'workspace')).strip()}")
        for line in self.host.task_prompt_context(str(selected_task.get("id", "")).strip()):
            prompt_lines.append(line)
        prompt_lines.append(
            "Operate through the governed ARIS runtime, keep execution bounded, and surface any approvals instead of bypassing them."
        )
        if getattr(self.host, "_workers_started", False):
            item = self.host.enqueue_operator_task(
                session_id=self.current_session_id,
                title=str(selected_task.get("title", "Workspace task")).strip(),
                prompt="\n".join(line for line in prompt_lines if line.strip()),
                priority=1 if str(selected_task.get("priority", "P2")).strip() == "P1" else 2,
                source="workspace_task",
                metadata={
                    "selected_repo_id": str((selected_repo or {}).get("id", "")).strip(),
                    "selected_task_id": str(selected_task.get("id", "")).strip(),
                },
            )
            self._workspace_add_activity(
                "Task queued",
                f"{item.get('title', 'Task')} is now queued in the governed worker lane.",
                "connected",
            )
            self.refresh_from_runtime(select_session_id=self.current_session_id)
            return
        chat_mode = self._chat_mode_for_brain(brain)
        self._start_runtime_chat(
            prompt="\n".join(line for line in prompt_lines if line.strip()),
            chat_mode=chat_mode,
            fast_mode=False,
        )

    def _run_workspace_task(self) -> None:
        self._run_task_entry(self._selected_workspace_task())

    def _approve_task_entry(self, selected_task: dict[str, Any] | None) -> None:
        if selected_task is None or self._chat_thread is not None:
            return
        approval_id = str(selected_task.get("approval_id", "")).strip()
        review_gate = str(selected_task.get("review_gate", "")).strip()
        task_id = str(selected_task.get("id", "")).strip()
        intelligence = self._task_intelligence(selected_task)
        approval_summary = _dict(intelligence.get("approval_summary"))
        summary_text = str(approval_summary.get("summary", selected_task.get("latest_update", ""))).strip()
        if review_gate == "operator_review" and task_id:
            confirmed = QMessageBox.question(
                self,
                "Approve Changes",
                (
                    f"Approve adoption for {selected_task.get('title', 'this task')}?\n\n"
                    f"{summary_text}\n\n"
                    "This is a governed self-improvement result and will be recorded before admission."
                ),
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                return
            self.host.resolve_operator_review(task_id=task_id, approved=True)
            self._workspace_add_activity(
                "Self-improvement approved",
                f"{selected_task.get('title', 'Task')} was approved for adoption.",
                "connected",
            )
            self.refresh_from_runtime(select_session_id=self.current_session_id)
            return
        if not approval_id:
            QMessageBox.information(
                self,
                self.host.profile.desktop_title,
                "The selected task is not waiting on an approval gate.",
            )
            return
        confirmed = QMessageBox.question(
            self,
            "Approve Changes",
            (
                f"Approve changes for {selected_task.get('title', 'this task')}?\n\n"
                f"Approval: {approval_id}\n"
                f"{summary_text}\n\n"
                "Use View Diff / Inspect first if you want the full run record."
            ),
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self._start_approval_resolution(approval_id=approval_id, approved=True)

    def _approve_workspace_task(self) -> None:
        self._approve_task_entry(self._selected_workspace_task())

    def _reject_task_entry(self, selected_task: dict[str, Any] | None) -> None:
        if selected_task is None or self._chat_thread is not None:
            return
        approval_id = str(selected_task.get("approval_id", "")).strip()
        review_gate = str(selected_task.get("review_gate", "")).strip()
        task_id = str(selected_task.get("id", "")).strip()
        intelligence = self._task_intelligence(selected_task)
        approval_summary = _dict(intelligence.get("approval_summary"))
        summary_text = str(approval_summary.get("summary", selected_task.get("latest_update", ""))).strip()
        reason, accepted_reason = QInputDialog.getItem(
            self,
            "Reject Reason",
            "Why are you rejecting this path?",
            [
                "Too risky",
                "Not aligned with goal",
                "Touches forbidden area",
                "Needs a clearer diff",
                "Other",
            ],
            0,
            False,
        )
        if not accepted_reason or not str(reason or "").strip():
            return
        note, accepted_note = QInputDialog.getMultiLineText(
            self,
            "Reject Notes",
            "Optional notes for ARIS task memory:",
        )
        if not accepted_note:
            return
        if review_gate == "operator_review" and task_id:
            confirmed = QMessageBox.question(
                self,
                "Reject Changes",
                (
                    f"Reject adoption for {selected_task.get('title', 'this task')}?\n\n"
                    f"{summary_text}\n\n"
                    f"Reason: {reason}\n\n"
                    "Rejecting records the outcome and keeps the self-improve path out of admission."
                ),
            )
            if confirmed != QMessageBox.StandardButton.Yes:
                return
            self.host.record_rejection_reason(
                task_id=task_id,
                title=str(selected_task.get("title", "Task")).strip(),
                reason=str(reason).strip(),
                note=str(note).strip(),
                intelligence=intelligence,
            )
            self.host.resolve_operator_review(task_id=task_id, approved=False)
            self._workspace_add_activity(
                "Self-improvement rejected",
                f"{selected_task.get('title', 'Task')} was rejected and recorded for future avoidance.",
                "blocked",
            )
            self.refresh_from_runtime(select_session_id=self.current_session_id)
            return
        if not approval_id:
            QMessageBox.information(
                self,
                self.host.profile.desktop_title,
                "The selected task is not waiting on an approval gate.",
            )
            return
        confirmed = QMessageBox.question(
            self,
            "Reject Changes",
            (
                f"Reject changes for {selected_task.get('title', 'this task')}?\n\n"
                f"Approval: {approval_id}\n"
                f"{summary_text}\n\n"
                f"Reason: {reason}\n\n"
                "Rejecting keeps the run contained and prevents progression."
            ),
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        self.host.record_rejection_reason(
            task_id=task_id or approval_id,
            title=str(selected_task.get("title", "Task")).strip(),
            reason=str(reason).strip(),
            note=str(note).strip(),
            intelligence=intelligence,
        )
        self._start_approval_resolution(approval_id=approval_id, approved=False)

    def _reject_workspace_task(self) -> None:
        self._reject_task_entry(self._selected_workspace_task())

    def _show_logs_for_task(self, selected_task: dict[str, Any] | None) -> None:
        if selected_task is None:
            return
        run_id = self._task_run_id(selected_task)
        if str(selected_task.get("task_type", "")).strip() == "agent_run" and run_id:
            payload = self.host.get_agent_run(run_id)
            events = self.host.list_agent_run_events(run_id, limit=30)
            self.workspace_worker_output.setPlainText(
                _pretty_json(
                    {
                        "run": payload,
                        "events": events,
                    }
                )
            )
            self._workspace_add_activity("Run logs opened", f"Governed event history for {run_id} is open.", "neutral")
            self._show_inspect_panel(tab="surfaces", surface_tab_index=3)
            return
        if str(selected_task.get("task_type", "")).strip() == "orchestrated":
            payload = {"task": selected_task}
            if run_id:
                payload["run"] = self.host.get_agent_run(run_id)
                payload["events"] = self.host.list_agent_run_events(run_id, limit=30)
            self.workspace_worker_output.setPlainText(_pretty_json(payload))
            self._workspace_add_activity(
                "Queued task inspected",
                f"Queue state for {str(selected_task.get('id', 'task')).strip()} is open.",
                "neutral",
            )
            self._show_inspect_panel(tab="surfaces", surface_tab_index=3)
            return

        if self.snapshot is not None:
            surface = self._workspace_surface(self.snapshot)
            self.workspace_worker_output.setPlainText(
                _pretty_json(
                    {
                        "task": selected_task,
                        "pending_approvals": surface.get("pending_approvals", []),
                        "approval_audit": surface.get("approval_audit", []),
                    }
                )
            )
            self._workspace_add_activity(
                "Task context opened",
                f"Workspace logs for {str(selected_task.get('id', 'task')).strip()} are visible in the worker lane.",
                "neutral",
            )
            self._show_inspect_panel(tab="surfaces", surface_tab_index=3)

    def _show_workspace_logs(self) -> None:
        self._show_logs_for_task(self._selected_workspace_task())

    def _cancel_task_entry(self, selected_task: dict[str, Any] | None) -> None:
        if selected_task is None or self._chat_thread is not None:
            return
        if str(selected_task.get("status", "")).strip() != "Running":
            QMessageBox.information(
                self,
                self.host.profile.desktop_title,
                "Only running tasks can be cancelled from the active lane.",
            )
            return
        run_id = self._task_run_id(selected_task)
        if not run_id:
            QMessageBox.information(
                self,
                self.host.profile.desktop_title,
                "This task does not have a live governed run to cancel.",
            )
            return
        confirmed = QMessageBox.question(
            self,
            "Cancel Run",
            (
                f"Cancel {selected_task.get('title', 'this task')}?\n\n"
                f"Run: {run_id}\n"
                f"Impact: {selected_task.get('latest_update', '')}\n\n"
                "Cancelling halts the current governed run and records the stopped state."
            ),
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        payload = self.host.cancel_agent_run(run_id)
        self.workspace_worker_output.setPlainText(_pretty_json(payload))
        if bool(payload.get("ok")):
            self._workspace_add_activity(
                "Run cancelled",
                f"{selected_task.get('title', 'Task')} was stopped before completion.",
                "warning",
            )
            self.refresh_from_runtime(select_session_id=self.current_session_id)
            self._show_inspect_panel(tab="surfaces", surface_tab_index=3)
            return
        QMessageBox.warning(
            self,
            self.host.profile.desktop_title,
            str(payload.get("error", "The run could not be cancelled.")),
        )

    def _ship_release(self) -> None:
        self.workspace_ship_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            payload = self.host.ship_release()
        except Exception as exc:
            payload = {
                "ok": False,
                "lane": "shipping",
                "error": str(exc),
                "missing_items": ["shipping_lane_exception"],
            }
        finally:
            QApplication.restoreOverrideCursor()
            self.workspace_ship_button.setEnabled(True)

        ok = bool(payload.get("ok"))
        artifact_paths = [str(item) for item in list(payload.get("generated_artifact_paths", []))]
        manifest_path = str(payload.get("manifest_path", "")).strip()
        missing_items = [str(item) for item in list(payload.get("missing_items", []))]
        self._workspace_worker_override = {
            "title": "Shipping Lane",
            "status": "Done" if ok else "Blocked",
            "lines": [
                "[shipping] precheck, verify, build copy, manifest, and zip pipeline finished.",
                f"[shipping] result: {'PASS' if ok else 'FAIL'}",
                f"[shipping] manifest: {manifest_path or 'not written'}",
                f"[shipping] artifacts: {len(artifact_paths)} generated path(s)",
                (
                    "[shipping] missing: none"
                    if not missing_items
                    else "[shipping] missing: " + ", ".join(missing_items[:5])
                ),
            ],
        }
        self._workspace_add_activity(
            "Shipping Lane passed" if ok else "Shipping Lane failed",
            (
                f"Manifest written to {manifest_path}."
                if manifest_path
                else "Shipping readout completed without a manifest."
            ),
            "connected" if ok else "blocked",
        )
        if self.snapshot is not None:
            self._update_operator(self.snapshot)
        self.workspace_worker_output.setPlainText(_pretty_json(payload))
        if ok:
            speak("Packaging complete. Artifacts verified.", "shipping_complete")
        else:
            speak("Action blocked. Law violation detected.", "blocked_action")
        if ok:
            QMessageBox.information(self, "Ship Release", _pretty_json(payload))
        else:
            QMessageBox.warning(self, "Ship Release", _pretty_json(payload))

    def _update_governance(self, snapshot: DesktopSnapshot) -> None:
        status = snapshot.status
        kill_switch = _dict(status.get("kill_switch"))
        self.kill_summary.setHtml(
            f"""
            <html><body style="background:#0f151b;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
            <div style="padding:8px 4px;">
              <div style="font-size:24px;font-weight:700;color:#f4dfbc;">Governance cockpit</div>
              <div style="margin-top:8px;color:#a9bdd0;line-height:1.5;">
                Staged governance, halls, kill switch, Shield of Truth, and repo logbook all remain visible here.
              </div>
              <div style="margin-top:14px;padding:14px 16px;border:1px solid #233340;border-radius:18px;background:#111a21;">
                <div><b>Mode:</b> {escape(str(kill_switch.get("mode", "unknown")))}</div>
                <div><b>Active:</b> {escape(str(kill_switch.get("active", False)))}</div>
                <div><b>Summary:</b> {escape(str(kill_switch.get("summary", "ARIS is nominal.")))}</div>
                <div><b>Shield of Truth:</b> {escape(str(_dict(status.get("shield_of_truth")).get("active", False)))}</div>
                <div><b>Repo Logbook:</b> {escape(str(_dict(status.get("repo_logbook")).get("active", False)))}</div>
              </div>
            </div></body></html>
            """
        )
        self.activity_text.setPlainText(_pretty_json(list(snapshot.activity)))
        self.discards_text.setPlainText(_pretty_json(list(snapshot.discards)))
        self.fame_text.setPlainText(_pretty_json(list(snapshot.fame)))
        self.shame_text.setPlainText(_pretty_json(list(snapshot.shame)))

    def _update_workspace(self, snapshot: DesktopSnapshot) -> None:
        self.workspace_session_label.setText(f"Current governed workspace session: {snapshot.session_id}")
        if snapshot.current_project_path:
            self.workspace_project_path.setText(snapshot.current_project_path)
            self.workspace_project_path.setCursorPosition(0)
            self.workspace_project_note.setText(
                "Current project was set explicitly through the native folder picker."
            )
        else:
            self.workspace_project_path.clear()
            self.workspace_project_path.setPlaceholderText("No project selected.")
            self.workspace_project_note.setText(
                "Load a project folder to set the current project for this desktop host."
            )

        selected_project_payload = {
            "path": snapshot.current_project_path,
            "source": "native_folder_picker",
            "selection_required": True,
        }
        if snapshot.workspace is None:
            if snapshot.current_project_path:
                self.workspace_summary.setPlainText(
                    _pretty_json(
                        {
                            "selected_project": selected_project_payload,
                            "status": "Project selected. No governed workspace has been materialized from this folder yet.",
                        }
                    )
                )
            else:
                self.workspace_summary.setPlainText("No project selected.")
            self.workspace_approvals.clear()
            self.workspace_repo_map.clear()
            self.workspace_files.clear()
            return

        workspace = _dict(snapshot.workspace)
        summary_payload = {
            "selected_project": selected_project_payload,
            "project": workspace.get("project", {}),
            "git": workspace.get("git", {}),
            "verification": workspace.get("verification", {}),
            "tasks": workspace.get("tasks", []),
            "imports": workspace.get("imports", []),
        }
        files_payload = {
            "files": workspace.get("files", []),
            "sandbox": workspace.get("sandbox", {}),
            "snapshots": workspace.get("snapshots", []),
            "applied_changes": workspace.get("applied_changes", []),
        }
        self.workspace_summary.setPlainText(_pretty_json(summary_payload))
        self.workspace_approvals.setPlainText(_pretty_json(workspace.get("pending_approvals", [])))
        self.workspace_repo_map.setPlainText(_pretty_json(workspace.get("repo_map", {})))
        self.workspace_files.setPlainText(_pretty_json(files_payload))

    def _load_project(self) -> None:
        current_index = self.tabs.currentIndex()
        project_path = self.host.select_current_project()
        if not project_path:
            self.refresh_from_runtime(select_session_id=self.current_session_id)
            self.tabs.setCurrentIndex(current_index)
            return
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.tabs.setCurrentIndex(current_index)

    def _update_mystic(self, snapshot: DesktopSnapshot) -> None:
        mystic = snapshot.mystic or {}
        reflection = _dict(_dict(mystic).get("reflection"))
        self.mystic_status.setHtml(
            f"""
            <html><body style="background:#0f151b;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
            <div style="padding:8px 4px;">
              <div style="font-size:24px;font-weight:700;color:#f4dfbc;">Mystic sustainment and reflection</div>
              <div style="margin-top:8px;color:#a9bdd0;line-height:1.5;">
                Human sustainment stays separate from the runtime core while still remaining visible and governed.
              </div>
              <div style="margin-top:14px;padding:14px 16px;border:1px solid #233340;border-radius:18px;background:#111a21;">
                <div><b>Alert level:</b> {escape(str(_dict(mystic).get("alert_level", 0)))}</div>
                <div><b>Session minutes:</b> {escape(str(_dict(mystic).get("session_minutes", 0)))}</div>
                <div><b>Muted:</b> {escape(str(_dict(mystic).get("muted", False)))}</div>
                <div><b>Reflection mode:</b> {escape(str(reflection.get("mode", "unknown")))}</div>
                <div><b>Merged with Jarvis:</b> {escape(str(reflection.get("merged_with_jarvis", False)))}</div>
              </div>
            </div></body></html>
            """
        )
        if not self.mystic_output.toPlainText().strip():
            self.mystic_output.setPlainText(_pretty_json(mystic))

    def _on_session_changed(self) -> None:
        item = self.session_list.currentItem()
        if item is None:
            return
        session_id = str(item.data(Qt.UserRole) or "").strip()
        if not session_id or session_id == self.current_session_id:
            return
        self._reset_workspace_runtime_state()
        self.current_session_id = session_id
        self.refresh_from_runtime(select_session_id=session_id)

    def _create_new_session(self) -> None:
        session_id = self.host.create_session(f"{self.host.profile.desktop_title} Session")
        self._reset_workspace_runtime_state()
        self.current_session_id = session_id
        self.refresh_from_runtime(select_session_id=session_id)
        self.tabs.setCurrentIndex(0)
        self.chat_input.setFocus()

    def _start_chat(self) -> None:
        message = self.chat_input.toPlainText().strip()
        if not message:
            return
        if self._chat_thread is not None:
            return
        if self.snapshot is None:
            self.refresh_from_runtime(select_session_id=self.current_session_id)
        if self.snapshot is None:
            return

        brain = self._current_brain_state_payload()
        chat_mode = self._chat_mode_for_brain(brain)
        fast_mode = self._fast_mode_for_brain(brain, chat_mode=chat_mode)
        selected_task = self._selected_workspace_task() if self._linked_task_enabled else None
        task_memory_context = []
        if isinstance(selected_task, dict):
            task_memory_context = self.host.task_prompt_context(str(selected_task.get("id", "")).strip())
        composed_message = message
        if task_memory_context:
            composed_message = (
                message
                + "\n\nTask memory:\n"
                + "\n".join(f"- {line}" for line in task_memory_context if str(line).strip())
            )
        self.chat_input.clear()
        self._workspace_transcript_override = []
        if chat_mode == "agent" and getattr(self.host, "_workers_started", False):
            queue_name = (
                "SELF_IMPROVE"
                if brain["mode"] in {"Build", "Evaluate"} and brain["target"] == "Operator Review"
                else "OPERATOR"
            )
            item = self.host.enqueue_operator_task(
                session_id=self.current_session_id,
                title=message.splitlines()[0][:96] or "Queued task",
                prompt=composed_message,
                priority=1 if queue_name == "SELF_IMPROVE" else 2,
                queue_name=queue_name,
                requires_approval=queue_name == "SELF_IMPROVE",
                source="task_input",
                metadata={"brain_state": brain},
            )
            self._workspace_add_activity(
                "Task queued",
                f"{item.get('title', 'Task')} entered the {queue_name.replace('_', ' ').title()} lane.",
                "connected" if queue_name == "OPERATOR" else "warning",
            )
            self.refresh_from_runtime(select_session_id=self.current_session_id)
            return
        self._start_runtime_chat(
            prompt=composed_message,
            chat_mode=chat_mode,
            fast_mode=fast_mode,
        )

    def _cleanup_chat_thread(self) -> None:
        if self._chat_worker is not None:
            self._chat_worker.deleteLater()
        if self._chat_thread is not None:
            self._chat_thread.deleteLater()
        self._chat_worker = None
        self._chat_thread = None
        self.send_button.setEnabled(True)
        self.send_button.setText(self._send_button_label())

    def _on_chat_event(self, event: DesktopChatEvent) -> None:
        if event.event == "meta":
            self._latest_chat_meta = event.payload
            self.workspace_worker_output.setPlainText(_pretty_json(event.payload))
            return
        if event.event == "token":
            self._streaming_reply += str(event.payload.get("content", ""))
            self.chat_output.setHtml(_render_transcript(self._stream_base_messages, self._streaming_reply))
            return
        if event.event == "agent_step":
            existing = self.workspace_worker_output.toPlainText().strip()
            prefix = f"{existing}\n\n" if existing else ""
            self.workspace_worker_output.setPlainText(prefix + _pretty_json(event.payload))
            self._append_live_task_stream_line(
                event.payload.get("summary")
                or event.payload.get("detail")
                or event.payload.get("message")
                or event.payload.get("content"),
                timestamp=event.payload.get("created_at") or event.payload.get("timestamp") or event.payload.get("time") or "Now",
            )
            return
        if event.event.startswith("exec_"):
            existing = self.workspace_worker_output.toPlainText().strip()
            prefix = f"{existing}\n\n" if existing else ""
            self.workspace_worker_output.setPlainText(prefix + f"{event.event}\n{_pretty_json(event.payload)}")
            self._append_live_task_stream_line(
                event.payload.get("message")
                or event.payload.get("detail")
                or event.payload.get("summary")
                or event.event,
                timestamp=event.payload.get("created_at") or event.payload.get("timestamp") or event.payload.get("time") or "Now",
            )

    def _on_chat_failed(self, message: str) -> None:
        if self._chat_thread is not None:
            self._chat_thread.quit()
        QMessageBox.critical(self, self.host.profile.desktop_title, message or "The chat stream failed.")

    def _on_chat_finished(self, session_id: str) -> None:
        self.current_session_id = session_id or self.current_session_id
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.tabs.setCurrentIndex(0)

    def _activate_soft_kill(self) -> None:
        reason = self.kill_reason.text().strip() or "Manual desktop containment request."
        payload = self.host.activate_soft_kill(reason=reason)
        self.kill_reason.clear()
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        QMessageBox.information(self, "Soft Kill", _pretty_json(payload))

    def _activate_hard_kill(self) -> None:
        confirmed = QMessageBox.question(
            self,
            "Confirm Hard Kill",
                "Trigger the hard kill switch for this ARIS V2 runtime?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        reason = self.kill_reason.text().strip() or "Manual desktop hard containment request."
        payload = self.host.activate_hard_kill(reason=reason)
        self.kill_reason.clear()
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        QMessageBox.information(self, "Hard Kill", _pretty_json(payload))

    def _reset_kill_switch(self) -> None:
        confirmed = QMessageBox.question(
            self,
            "Reset Kill Switch",
            "Reset the kill switch and reseal integrity from the desktop host?",
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        reason = self.kill_reason.text().strip() or "Manual desktop reset."
        payload = self.host.reset_kill_switch(reason=reason, reseal_integrity=True)
        self.kill_reason.clear()
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        QMessageBox.information(self, "Kill Switch Reset", _pretty_json(payload))

    def _mystic_tick(self) -> None:
        payload = self.host.mystic_tick(session_id=self.current_session_id)
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.mystic_output.setPlainText(_pretty_json(payload))

    def _mystic_break(self) -> None:
        payload = self.host.mystic_break(session_id=self.current_session_id)
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.mystic_output.setPlainText(_pretty_json(payload))

    def _mystic_acknowledge(self) -> None:
        payload = self.host.mystic_acknowledge(session_id=self.current_session_id)
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.mystic_output.setPlainText(_pretty_json(payload))

    def _mystic_mute(self) -> None:
        payload = self.host.mystic_mute(session_id=self.current_session_id, minutes=10)
        self.refresh_from_runtime(select_session_id=self.current_session_id)
        self.mystic_output.setPlainText(_pretty_json(payload))

    def _run_mystic_read(self) -> None:
        text = self.mystic_input.toPlainText().strip()
        if not text:
            return
        payload = self.host.mystic_read(session_id=self.current_session_id, input_text=text)
        self.mystic_output.setPlainText(_pretty_json(payload))
        self.refresh_from_runtime(select_session_id=self.current_session_id)


def launch_desktop_app(host: ArisRuntimeDesktopHost) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(host.profile.desktop_title)
    window = ArisRuntimeDesktopWindow(host)
    window.show()
    return int(app.exec())
