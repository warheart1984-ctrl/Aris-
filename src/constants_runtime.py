from __future__ import annotations

UL_ROOT_LAW_ID = "UL_ROOT_LAW_LOCKED"
ARIS_HANDBOOK_ID = "ARIS_HANDBOOK_LOCKED"
UL_IDENTITY_SOURCE = "UL"

LAW_CLASS_ROOT = "UL_ROOT_LAW"
LAW_CLASS_FOUNDATIONAL = "FOUNDATIONAL_MEMORY"

DISPOSITION_VALID = "valid"
DISPOSITION_DEGRADED = "degraded"
DISPOSITION_REJECTED = "rejected"

SPEECH_STATE = "0001"
SPEECH_CODE = "1000"
SPEECH_VERIFICATION = "1001"
SPEECH_CHAIN = (SPEECH_STATE, SPEECH_CODE, SPEECH_VERIFICATION)

ROOT_LAW_SCOPE = "GLOBAL"
ROOT_LAW_PRIORITY = "MAX"
ROOT_LAW_EXECUTION_PHASE = "ALWAYS_PRE"
ROOT_LAW_MUTABILITY = "NONE"

CISIV_STAGE_SEQUENCE = ("state", "lineage", "legitimacy", "review", "verification")

LEDGER_FILENAME = "law_ledger.jsonl"
FOUNDATION_STORE_FILENAME = "foundation_store.json"
LAW_MANIFEST_FILENAME = "law_manifest.json"

HOST_LEGITIMACY_SECRET_ENV = "ARIS_HOST_LEGITIMACY_SECRET"

PROTECTED_IDENTITIES = frozenset({"ARIS", "AAIS"})
FOUNDATIONAL_MEMORY_IDS = frozenset({UL_ROOT_LAW_ID, ARIS_HANDBOOK_ID})

MUTATION_ACTION_TYPES = frozenset(
    {
        "file_write",
        "file_replace",
        "text_patch_apply",
        "patch_apply",
        "patch_hunk_apply",
        "patch_line_apply",
        "symbol_edit",
        "task_approval",
        "approval_resolution",
        "workspace_import_upload",
        "workspace_repo_clone",
        "change_rollback",
        "mutation_apply",
        "foundation_mutation",
    }
)

SENSITIVE_ACTION_TYPES = frozenset(
    MUTATION_ACTION_TYPES
    | {
        "python_execute",
        "command_execute",
        "identity_claim",
        "runtime_admin",
        "kill_switch",
        "verification_override",
    }
)

SCOPE_BY_ACTION_TYPE = {
    "python_execute": "execution",
    "command_execute": "execution",
    "file_write": "workspace_mutation",
    "file_replace": "workspace_mutation",
    "text_patch_apply": "workspace_mutation",
    "patch_apply": "workspace_mutation",
    "patch_hunk_apply": "workspace_mutation",
    "patch_line_apply": "workspace_mutation",
    "symbol_edit": "workspace_mutation",
    "task_approval": "approval",
    "approval_resolution": "approval",
    "workspace_import_upload": "workspace_mutation",
    "workspace_repo_clone": "workspace_mutation",
    "change_rollback": "workspace_mutation",
    "mutation_apply": "workspace_mutation",
    "foundation_mutation": "foundational",
    "identity_claim": "identity",
    "runtime_admin": "admin",
}

KNOWN_INTERNAL_HOSTS = frozenset(
    {
        "aris-runtime",
        "aris-demo-runtime",
        "aris-api",
        "aris-demo-api",
        "aais-runtime",
        "aais-api",
    }
)

IDENTITY_PRESERVING_CAPABILITIES = frozenset(
    {
        "governance",
        "verification",
        "lineage",
        "identity_preservation",
    }
)

FORBIDDEN_CALLER_FIELDS = frozenset(
    {
        "allowed_scopes",
        "verification_present",
        "1001_pass",
        "verified",
        "law_verified",
        "mutation_gate_token",
        "host_legitimate",
        "host_attested",
        "lineage_verified",
        "override_authority",
        "bypass_requested",
        "authority_expansion",
    }
)

POST_VERIFICATION_COOLDOWN_SECONDS = 2.0
