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

from .desktop_support import ArisDemoDesktopHost, DesktopChatEvent, DesktopSnapshot
from .voice import speak
from .workspace_demo_logic import (
    BRAIN_MODE_OPTIONS,
    BRAIN_PERMISSION_OPTIONS,
    BRAIN_RESPONSE_STYLE_OPTIONS,
    BRAIN_SCOPE_OPTIONS,
    BRAIN_TARGET_OPTIONS,
    DEFAULT_BRAIN_STATE,
    build_workspace_demo_decision,
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
    defaults = dict(DEFAULT_BRAIN_STATE)
    if profile_id == "v1":
        defaults.update(
            {
                "mode": "Build",
                "scope": "Selected Repo",
                "target": "Forge",
                "permission": "Approval Required",
                "response_style": "Operator",
            }
        )
    elif profile_id == "v2":
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
    if profile_id == "v1":
        return "ARIS Studio V1"
    if profile_id == "v2":
        return "ARIS Studio V2"
    return "ARIS Studio"


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
        host: ArisDemoDesktopHost,
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


class ArisDemoDesktopWindow(QMainWindow):
    def __init__(self, host: ArisDemoDesktopHost) -> None:
        super().__init__()
        self.host = host
        self.snapshot: DesktopSnapshot | None = None
        self.current_session_id: str | None = None
        self._transcript_cache: list[dict[str, Any]] = []
        self._stream_base_messages: list[dict[str, Any]] = []
        self._streaming_reply = ""
        self._latest_chat_meta: dict[str, Any] = {}
        self._chat_thread: QThread | None = None
        self._chat_worker: ChatWorker | None = None
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
        speak("ARIS is ready.", "system_ready")

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
        subtitle = QLabel("UL runtime host\ncross-platform desktop shell")
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
        self.new_session_button = QPushButton("New Session")
        self.refresh_button = QPushButton("Refresh")
        self.new_session_button.clicked.connect(self._create_new_session)
        self.refresh_button.clicked.connect(lambda: self.refresh_from_runtime(select_session_id=self.current_session_id))
        action_row.addWidget(self.new_session_button)
        action_row.addWidget(self.refresh_button)

        session_label = QLabel("Sessions")
        session_label.setObjectName("railHeading")
        self.session_list = QListWidget()
        self.session_list.itemSelectionChanged.connect(self._on_session_changed)

        self.rail_info = QLabel("")
        self.rail_info.setWordWrap(True)
        self.rail_info.setObjectName("railInfo")

        rail_layout.addWidget(brand)
        rail_layout.addWidget(subtitle)
        rail_layout.addLayout(badge_row)
        rail_layout.addLayout(action_row)
        rail_layout.addSpacing(10)
        rail_layout.addWidget(session_label)
        rail_layout.addWidget(self.session_list, 1)
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

        self.status_brain_value = add_status_field("Brain")
        self.status_tier_value = add_status_field("Tier")
        self.status_workspace_value = add_status_field("Workspace")
        self.status_upgrade_value = add_status_field("Upgrade")
        self.status_memory_value = add_status_field("Memory")
        self.status_voice_value = add_status_field("Voice")
        status_layout.addStretch(1)
        self.operator_session_label = QLabel("")
        self.operator_session_label.setObjectName("microDetail")
        status_layout.addWidget(self.operator_session_label)

        studio_splitter = QSplitter(Qt.Vertical)
        body_splitter = QSplitter(Qt.Horizontal)

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
        center_layout.setSpacing(10)
        center_layout.addWidget(QLabel("System Surface"))
        self.studio_surface_tabs = QTabWidget()
        self.studio_surface_tabs.addTab(self._build_studio_governance_surface(), "Governance")
        self.studio_surface_tabs.addTab(self._build_studio_memory_surface(), "Memory")
        self.studio_surface_tabs.addTab(self._build_studio_upgrades_surface(), "Upgrades")
        self.studio_surface_tabs.addTab(self._build_studio_runtime_surface(), "Runtime")
        self.studio_surface_tabs.addTab(self._build_studio_file_viewer_surface(), "File Viewer")
        center_layout.addWidget(self.studio_surface_tabs, 1)

        chat_panel = QFrame()
        chat_panel.setObjectName("composerPanel")
        chat_panel.setMinimumWidth(380)
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.setContentsMargins(18, 18, 18, 18)
        chat_layout.setSpacing(10)
        chat_header = QHBoxLayout()
        chat_header.setSpacing(10)
        chat_header.addWidget(QLabel("ARIS Operator"))
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

        chip_row = QHBoxLayout()
        chip_row.setSpacing(8)
        self.repo_context_button = QPushButton("Detach Workspace Context")
        self.repo_context_button.clicked.connect(self._toggle_repo_context)
        self.link_task_button = QPushButton("Unlink Task")
        self.link_task_button.clicked.connect(self._toggle_link_task)
        self.approval_mode_button = QPushButton("Approval Mode: Guarded")
        self.approval_mode_button.clicked.connect(self._toggle_approval_mode)
        chip_row.addWidget(self.repo_context_button)
        chip_row.addWidget(self.link_task_button)
        chip_row.addWidget(self.approval_mode_button)
        chip_row.addStretch(1)
        chat_layout.addLayout(chip_row)

        feedback_row = QHBoxLayout()
        feedback_row.setSpacing(8)
        self.feedback_bug_button = QPushButton("Report Bug")
        self.feedback_bug_button.clicked.connect(lambda: self._collect_feedback("bug"))
        self.feedback_general_button = QPushButton("Give Feedback")
        self.feedback_general_button.clicked.connect(lambda: self._collect_feedback("confusing"))
        self.feedback_feature_button = QPushButton("Request Feature")
        self.feedback_feature_button.clicked.connect(lambda: self._collect_feedback("feature_request"))
        self.feedback_form_button = QPushButton("Open Form")
        self.feedback_form_button.clicked.connect(self._open_feedback_form)
        feedback_row.addWidget(self.feedback_bug_button)
        feedback_row.addWidget(self.feedback_general_button)
        feedback_row.addWidget(self.feedback_feature_button)
        feedback_row.addWidget(self.feedback_form_button)
        chat_layout.addLayout(feedback_row)

        self.workspace_route_summary = QLabel("")
        self.workspace_route_summary.setWordWrap(True)
        self.workspace_route_summary.setObjectName("microDetail")
        self.workspace_prompt_context = QLabel("")
        self.workspace_prompt_context.setWordWrap(True)
        self.workspace_prompt_context.setObjectName("microDetail")
        chat_layout.addWidget(self.workspace_brain_pills)
        chat_layout.addWidget(self.workspace_route_summary)
        chat_layout.addWidget(self.workspace_prompt_context)

        self.chat_output = QTextBrowser()
        self.chat_output.setOpenExternalLinks(False)
        chat_layout.addWidget(self.chat_output, 1)

        composer = QFrame()
        composer.setObjectName("composerPanel")
        composer_layout = QVBoxLayout(composer)
        composer_layout.setContentsMargins(12, 12, 12, 12)
        composer_layout.setSpacing(8)
        composer_layout.addWidget(QLabel("Ask ARIS"))
        self.chat_input = QPlainTextEdit()
        if self.host.profile.id == "v1":
            self.chat_input.setPlaceholderText(
                "Ask ARIS to inspect the active workspace, route the task through Forge, or prepare a governed execution packet."
            )
        elif self.host.profile.id == "v2":
            self.chat_input.setPlaceholderText(
                "Ask ARIS to route governed repo work through Forge while keeping UL runtime admission visible."
            )
        else:
            self.chat_input.setPlaceholderText(
                "Ask ARIS to inspect the active workspace, route a task, or prepare a governed execution packet."
            )
        self.chat_input.setFixedHeight(110)
        self.send_button = QPushButton("Ask ARIS")
        self.send_button.clicked.connect(self._start_chat)
        composer_layout.addWidget(self.chat_input)
        composer_layout.addWidget(self.send_button, 0, Qt.AlignRight)
        chat_layout.addWidget(composer)

        body_splitter.addWidget(explorer_panel)
        body_splitter.addWidget(center_panel)
        body_splitter.addWidget(chat_panel)
        body_splitter.setStretchFactor(0, 3)
        body_splitter.setStretchFactor(1, 6)
        body_splitter.setStretchFactor(2, 4)

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

        studio_splitter.addWidget(body_splitter)
        studio_splitter.addWidget(event_panel)
        studio_splitter.setStretchFactor(0, 8)
        studio_splitter.setStretchFactor(1, 3)

        layout.addWidget(status_strip)
        layout.addWidget(studio_splitter, 1)
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
        task_header.addWidget(QLabel("Task Board"))
        task_header.addStretch(1)
        self.workspace_task_search = QLineEdit()
        self.workspace_task_search.setPlaceholderText("Filter tasks")
        self.workspace_task_search.textChanged.connect(self._on_workspace_task_search_changed)
        task_header.addWidget(self.workspace_task_search, 1)
        task_layout.addLayout(task_header)
        task_tab_row = QHBoxLayout()
        task_tab_row.setSpacing(8)
        self.task_tab_buttons = {}
        for label in ("All", "Running", "Review", "Done"):
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
        self.workspace_logs_button = QPushButton("Logs")
        self.workspace_logs_button.clicked.connect(self._show_workspace_logs)
        self.workspace_ship_button = QPushButton("Ship Release")
        self.workspace_ship_button.clicked.connect(self._ship_release)
        action_row.addWidget(self.workspace_run_button)
        action_row.addWidget(self.workspace_approve_button)
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
        self.studio_memory_view = QPlainTextEdit()
        self.studio_memory_view.setReadOnly(True)
        layout.addWidget(self.workspace_brain_state)
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
        if self._chat_thread is None:
            self.refresh_from_runtime(select_session_id=self.current_session_id)

    def refresh_from_runtime(self, *, select_session_id: str | None = None) -> None:
        snapshot = self.host.snapshot(select_session_id or self.current_session_id)
        if snapshot.session_id is None:
            session_id = self.host.ensure_session()
            snapshot = self.host.snapshot(session_id)
        self.snapshot = snapshot
        self.current_session_id = snapshot.session_id
        self._transcript_cache = list(snapshot.transcript)
        self._populate_session_list(snapshot)
        self._update_header(snapshot)
        self._update_operator(snapshot)

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
        self.rail_info.setText(
            f"{len(snapshot.features)} live surfaces\n"
            f"{len(snapshot.sessions)} sessions\n"
            f"Native targets: {', '.join(item.label for item in snapshot.packaging_targets)}"
        )

    def _update_header(self, snapshot: DesktopSnapshot) -> None:
        status = snapshot.status
        kill_switch = _dict(status.get("kill_switch"))
        demo_mode = _dict(status.get("demo_mode"))
        model_router = _dict(status.get("model_router"))
        router_mode = str(model_router.get("mode", "auto")).strip().upper() or "AUTO"
        pinned_system = str(model_router.get("pinned_system", "")).strip().replace("_", " ")
        repo_target = str(status.get("repo_target", "")).strip()
        system_name = str(status.get("system_name", self.host.profile.system_name)).strip() or self.host.profile.system_name
        self.setWindowTitle(self.host.profile.desktop_title)
        self.hero_title.setText(self._studio_name)
        self.hero_subtitle.setText(
            f"{system_name} | {status.get('law_mode', 'unknown')} | "
            f"{status.get('service_name', 'Advanced Repo Intelligence Service Demo')} | "
            f"{repo_target} | Router {router_mode}"
            + (f" ({pinned_system.title()})" if pinned_system else "")
        )
        self.route_label.setText("Route: " + " -> ".join(str(item) for item in demo_mode.get("route", [])))

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
        demo_mode = _dict(status.get("demo_mode"))
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
            This window is a declared host over the existing ARIS Demo service. UL remains the identity source,
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
            <div><b>Demo route:</b> {escape(" -> ".join(str(item) for item in demo_mode.get("route", [])))}</div>
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
            "workspaces": [dict(item) for item in list(base.get("workspaces", [])) if isinstance(item, dict)],
            "active_workspace": dict(_dict(base.get("active_workspace"))),
            "file_explorer": dict(_dict(base.get("file_explorer"))),
            "event_stream": [dict(item) for item in list(base.get("event_stream", [])) if isinstance(item, dict)],
            "feedback": dict(_dict(base.get("feedback"))),
            "upgrades": upgrades,
        }
        self._ensure_workspace_selection(surface)
        return surface

    def _workspace_messages(self, snapshot: DesktopSnapshot) -> list[dict[str, Any]]:
        if self._workspace_transcript_override:
            return [dict(item) for item in self._workspace_transcript_override]
        return seed_workspace_messages()

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
                f"{task.get('id', 'task')}  {task.get('status', 'Review')}  {task.get('priority', 'Medium')}\n"
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
        counts = {"All": len(tasks), "Running": 0, "Review": 0, "Done": 0}
        for task in tasks:
            status = str(task.get("status", "")).strip()
            if status in counts:
                counts[status] += 1
        return counts

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
        self.status_voice_value.setText(
            "On" if str(os.getenv("ARIS_VOICE_ENABLED", "true")).strip().lower() != "false" else "Off"
        )
        self.event_stream_status.setText(
            f"{len(recent_events)} recent event(s) tracked in the local runtime lane."
        )

    def _update_memory_surface(self, snapshot: DesktopSnapshot, surface: dict[str, Any]) -> None:
        active_workspace = _dict(surface.get("active_workspace"))
        file_explorer = _dict(surface.get("file_explorer"))
        selected_file = _dict(file_explorer.get("selected_file"))
        memory_payload = {
            "session_id": snapshot.session_id,
            "runtime_profile": snapshot.status.get("runtime_profile"),
            "active_workspace": active_workspace,
            "selected_file": selected_file,
            "recent_events": list(surface.get("event_stream", []))[:8],
            "mystic": snapshot.mystic or {},
        }
        self.studio_memory_view.setPlainText(_pretty_json(memory_payload))

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
                f"{task.get('id', 'task')} · {repo_name} · {task.get('status', 'Review')} · {task.get('priority', 'Medium')}\n"
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
                    "Approval Gated" if brain["permission"] in {"Approval Required", "Suggest Only", "Read Only"} else "Safe Demo Actions",
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

        if isinstance(selected_task, dict):
            task_html = f"""
            <html><body style="background:#10171e;color:#edf2f7;font-family:'Trebuchet MS','Avenir Next','Segoe UI',sans-serif;">
            <div style="padding:4px 2px;">
              <div style="font-size:18px;font-weight:700;color:#f4dfbc;">{escape(str(selected_task.get("title", "Task")))}</div>
              <div style="margin-top:6px;color:#8ea4bb;">{escape(str(selected_task.get('id', 'task')))}</div>
              <div style="margin-top:12px;"><b>Status:</b> {escape(str(selected_task.get('status', 'Review')))}</div>
              <div><b>Priority:</b> {escape(str(selected_task.get('priority', 'Medium')))}</div>
              <div style="margin-top:10px;line-height:1.5;">{escape(str(selected_task.get('summary', '')))}</div>
              <div style="margin-top:10px;color:#c5d2df;">{escape(str(selected_task.get('latest_update', '')))}</div>
            </div></body></html>
            """
        else:
            task_html = "<html><body style='color:#edf2f7;'>No task selected.</body></html>"
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
        self.workspace_run_button.setEnabled(buttons_enabled)
        self.workspace_approve_button.setEnabled(buttons_enabled)
        self.workspace_logs_button.setEnabled(buttons_enabled)
        self.workspace_ship_button.setEnabled(True)
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
        self._update_file_viewer(surface)

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

    def _reset_workspace_demo_state(self) -> None:
        self._workspace_transcript_override = []
        self._workspace_task_overrides.clear()
        self._workspace_activity_overrides.clear()
        self._workspace_worker_override = None
        self._selected_workspace_repo_id = None
        self._selected_workspace_task_id = None
        self._latest_chat_meta = {}

    def _transition_workspace_task_to_review(self, task_id: str) -> None:
        if not task_id:
            return
        self._workspace_task_overrides[task_id] = {
            "status": "Review",
            "priority": "High",
            "latest_update": "Execution finished. Diff and validation output are waiting behind approval.",
        }
        self._workspace_worker_override = {
            "title": "Validation And Diff",
            "status": "Review",
            "lines": [
                f"[forge-worker] {task_id} finished under ARIS orchestration.",
                "[diff] workspace patch is staged behind approval.",
                "[tests] validation passed and is ready for operator review.",
            ],
        }
        self._workspace_add_activity("Task ready for review", f"{task_id} moved into Review after validation completed.", "warning")
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _run_workspace_task(self) -> None:
        task_id = str(self._selected_workspace_task_id or "").strip()
        if not task_id:
            return
        self._workspace_task_overrides[task_id] = {
            "status": "Running",
            "priority": "High",
            "latest_update": "Worker lane accepted the plan and is generating logs, patch output, and validation.",
        }
        self._workspace_worker_override = {
            "title": "Execution Lane",
            "status": "Running",
            "lines": [
                f"[forge-worker] {task_id} is running behind the ARIS operator surface.",
                "[plan] repo context is attached and approval gates remain active.",
                "[next] validation will surface here before any apply step.",
            ],
        }
        self._workspace_add_activity("Run started", f"{task_id} entered the worker lane from the ARIS workspace.", "connected")
        if self.snapshot is not None:
            self._update_operator(self.snapshot)
        QTimer.singleShot(1200, lambda: self._transition_workspace_task_to_review(task_id))

    def _approve_workspace_task(self) -> None:
        task_id = str(self._selected_workspace_task_id or "").strip()
        if not task_id:
            return
        self._workspace_task_overrides[task_id] = {
            "status": "Done",
            "priority": "Medium",
            "latest_update": "Approval granted. Patch applied and verification returned clean.",
        }
        self._workspace_worker_override = {
            "title": "Apply Result",
            "status": "Done",
            "lines": [
                f"[forge-worker] {task_id} applied after operator approval.",
                "[apply] guarded patch landed cleanly.",
                "[verification] branch remains clean and synced.",
            ],
        }
        self._workspace_add_activity("Approved and applied", f"{task_id} was approved by the operator and applied cleanly.", "connected")
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _show_workspace_logs(self) -> None:
        task_id = str(self._selected_workspace_task_id or "").strip()
        if not task_id:
            return
        self._workspace_worker_override = {
            "title": "Worker Logs",
            "status": "Ready",
            "lines": [
                f"[forge-worker] {task_id} log tail opened from the workspace inspector.",
                "[trace] repo map, approval seams, and verification output are available.",
                "[note] Forge remains a worker lane; ARIS keeps the conversation here.",
            ],
        }
        self._workspace_add_activity("Logs opened", f"Worker output for {task_id} was opened from the context panel.", "neutral")
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

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
        self._reset_workspace_demo_state()
        self.current_session_id = session_id
        self.refresh_from_runtime(select_session_id=session_id)

    def _create_new_session(self) -> None:
        session_id = self.host.create_session(f"{self.host.profile.desktop_title} Session")
        self._reset_workspace_demo_state()
        self.current_session_id = session_id
        self.refresh_from_runtime(select_session_id=session_id)
        self.tabs.setCurrentIndex(0)
        self.chat_input.setFocus()

    def _start_chat(self) -> None:
        message = self.chat_input.toPlainText().strip()
        if not message:
            return
        if self.snapshot is None:
            self.refresh_from_runtime(select_session_id=self.current_session_id)
        if self.snapshot is None:
            return

        surface = self._workspace_surface(self.snapshot)
        selected_repo, selected_task = self._workspace_selected_context(surface)
        brain = self._current_brain_state_payload()
        decision = build_workspace_demo_decision(
            prompt=message,
            brain_state=brain,
            repo=selected_repo,
            task=selected_task,
        )

        transcript = self._workspace_messages(self.snapshot)
        transcript.append({"role": "user", "content": message, "created_at": ""})
        transcript.append({"role": "assistant", "content": str(decision.get("content", "")).strip(), "created_at": ""})
        self._workspace_transcript_override = transcript[-16:]

        task_id = str(self._selected_workspace_task_id or "").strip()
        if task_id and (decision.get("task_status") or decision.get("task_update")):
            existing = dict(self._workspace_task_overrides.get(task_id, {}))
            if decision.get("task_status"):
                existing["status"] = str(decision.get("task_status"))
            if decision.get("task_update"):
                existing["latest_update"] = str(decision.get("task_update"))
            if str(decision.get("worker_status", "")).strip().lower() == "review":
                existing["priority"] = "High"
            self._workspace_task_overrides[task_id] = existing

        self._workspace_worker_override = {
            "title": str(decision.get("worker_title", "ARIS Control Lane")),
            "status": str(decision.get("worker_status", "Ready")),
            "lines": [str(item) for item in list(decision.get("worker_lines", []))],
        }
        self._workspace_add_activity(
            str(decision.get("activity_title", "ARIS route updated")),
            str(decision.get("activity_detail", "ARIS updated the workspace route.")),
            "warning" if bool(decision.get("blocked")) else "connected",
        )
        self.chat_input.clear()
        self.chat_output.setHtml(_render_transcript(self._workspace_transcript_override))
        if decision.get("blocked"):
            speak("Action blocked. Law violation detected.", "blocked_action")

        if task_id and str(decision.get("worker_status", "")).strip().lower() == "running":
            QTimer.singleShot(1200, lambda: self._transition_workspace_task_to_review(task_id))
        if self.snapshot is not None:
            self._update_operator(self.snapshot)

    def _cleanup_chat_thread(self) -> None:
        if self._chat_worker is not None:
            self._chat_worker.deleteLater()
        if self._chat_thread is not None:
            self._chat_thread.deleteLater()
        self._chat_worker = None
        self._chat_thread = None
        self.send_button.setEnabled(True)
        self.send_button.setText("Ask ARIS")

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
            return
        if event.event.startswith("exec_"):
            existing = self.workspace_worker_output.toPlainText().strip()
            prefix = f"{existing}\n\n" if existing else ""
            self.workspace_worker_output.setPlainText(prefix + f"{event.event}\n{_pretty_json(event.payload)}")

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
            "Trigger the hard kill switch for this ARIS Demo runtime?",
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


def launch_desktop_app(host: ArisDemoDesktopHost) -> int:
    app = QApplication.instance() or QApplication([])
    app.setApplicationName(host.profile.desktop_title)
    window = ArisDemoDesktopWindow(host)
    window.show()
    return int(app.exec())