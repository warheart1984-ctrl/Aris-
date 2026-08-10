from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
import json
import uuid


class BlueprintFormat(Enum):
    """Supported blueprint file formats."""
    JSON = "json"
    ARISBP = "arisbp"


@dataclass(slots=True)
class BlueprintMetadata:
    """Blueprint metadata."""
    id: str
    name: str
    description: str
    version: str = "1.0.0"
    author: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    tags: list[str] = field(default_factory=list)
    category: str = "feature"  # feature, bugfix, refactor, refactor, infra, docs, etc.
    compatibility: list[str] = field(default_factory=lambda: ["v2"])


@dataclass(slots=True)
class BlueprintStep:
    """A single step in a blueprint."""
    id: str
    name: str
    description: str
    action_type: str  # patch_create, file_write, command_execute, etc.
    parameters: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)  # step IDs this depends on
    risk_level: str = "low"  # low, medium, high, critical
    rollback: Optional[str] = None  # rollback action description
    validation: Optional[str] = None  # how to validate this step


@dataclass(slots=True)
class Blueprint:
    """Blueprint definition - a reusable workflow template."""
    metadata: BlueprintMetadata
    steps: list[BlueprintStep] = field(default_factory=list)
    variables: dict[str, Any] = field(default_factory=dict)  # template variables
    requirements: list[str] = field(default_factory=list)  # prerequisites
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata": asdict(self.metadata),
            "steps": [asdict(step) for step in self.steps],
            "variables": self.variables,
            "requirements": self.requirements,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Blueprint":
        metadata = BlueprintMetadata(**data.get("metadata", {}))
        steps = [BlueprintStep(**step) for step in data.get("steps", [])]
        variables = data.get("variables", {})
        requirements = data.get("requirements", [])
        return cls(metadata=metadata, steps=steps, variables=variables, requirements=requirements)
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Blueprint":
        return cls.from_dict(json.loads(json_str))
    
    def save(self, path: Path, format: BlueprintFormat = BlueprintFormat.JSON) -> None:
        """Save blueprint to file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        if format == BlueprintFormat.JSON:
            path.write_text(self.to_json(), encoding="utf-8")
        elif format == BlueprintFormat.ARISBP:
            # Custom binary format could go here
            path.write_text(self.to_json(), encoding="utf-8")
    
    @classmethod
    def load(cls, path: Path, format: BlueprintFormat = BlueprintFormat.JSON) -> "Blueprint":
        """Load blueprint from file."""
        if format == BlueprintFormat.JSON or format == BlueprintFormat.ARISBP:
            return cls.from_json(path.read_text(encoding="utf-8"))
        raise ValueError(f"Unsupported format: {format}")


# Built-in blueprint templates
BLUEPRINT_TEMPLATES: dict[str, Blueprint] = {}


def _make_template(
    id: str,
    name: str,
    description: str,
    category: str,
    steps: list[BlueprintStep],
    variables: dict[str, Any] | None = None,
    requirements: list[str] | None = None,
    tags: list[str] | None = None,
) -> Blueprint:
    """Create a blueprint template."""
    return Blueprint(
        metadata=BlueprintMetadata(
            id=id,
            name=name,
            description=description,
            category=category,
            tags=tags or [],
        ),
        steps=steps,
        variables=variables or {},
        requirements=requirements or [],
    )


# Core templates
BLUEPRINT_TEMPLATES["auth-module"] = _make_template(
    id="auth-module",
    name="Authentication Module",
    description="Add authentication module with JWT validation, login/logout, and session management",
    category="feature",
    steps=[
        BlueprintStep(
            id="auth-1",
            name="Create auth module structure",
            description="Create auth module directory and base files",
            action_type="file_write",
            parameters={
                "path": "src/auth/__init__.py",
                "content": "# Authentication module\n",
            },
        ),
        BlueprintStep(
            id="auth-2",
            name="Implement JWT validation",
            description="Add JWT token validation with RS256",
            action_type="file_write",
            parameters={
                "path": "src/auth/jwt.py",
                "content": "def validate_jwt(token: str) -> dict: ...",
            },
            dependencies=["auth-1"],
        ),
        BlueprintStep(
            id="auth-3",
            name="Add login/logout endpoints",
            description="Create authentication endpoints",
            action_type="file_write",
            parameters={
                "path": "src/auth/endpoints.py",
                "content": "def login(): ...\ndef logout(): ...",
            },
            dependencies=["auth-1"],
        ),
        BlueprintStep(
            id="auth-4",
            name="Add session management",
            description="Implement session creation and validation",
            action_type="file_write",
            parameters={
                "path": "src/auth/session.py",
                "content": "class SessionManager: ...",
            },
            dependencies=["auth-2", "auth-3"],
        ),
        BlueprintStep(
            id="auth-5",
            name="Add auth tests",
            description="Create unit tests for authentication module",
            action_type="file_write",
            parameters={
                "path": "tests/test_auth.py",
                "content": "def test_jwt_validation(): ...\ndef test_login(): ...",
            },
            dependencies=["auth-2", "auth-3", "auth-4"],
        ),
    ],
    variables={
        "module_name": "auth",
        "jwt_algorithm": "RS256",
        "token_expiry": "1h",
    },
    requirements=["Python 3.11+", "PyJWT", "cryptography"],
    tags=["auth", "security", "jwt", "backend"],
)


BLUEPRINT_TEMPLATES["feature-branch"] = _make_template(
    id="feature-branch",
    name="Feature Branch Workflow",
    description="Create a feature branch with proper setup, CI checks, and PR template",
    category="workflow",
    steps=[
        BlueprintStep(
            id="fb-1",
            name="Create feature branch",
            description="Create and checkout new feature branch",
            action_type="command_execute",
            parameters={"command": "git checkout -b feature/{{feature_name}}"},
        ),
        BlueprintStep(
            id="fb-2",
            name="Add feature flag",
            description="Add feature flag for gradual rollout",
            action_type="file_write",
            parameters={
                "path": "src/config/flags.py",
                "content": "FEATURE_{{FEATURE_NAME}} = False",
            },
        ),
        BlueprintStep(
            id="fb-3",
            name="Add tests",
            description="Write tests for the new feature",
            action_type="file_write",
            parameters={
                "path": "tests/test_{{feature_name}}.py",
                "content": "def test_{{feature_name}}(): ...",
            },
        ),
        BlueprintStep(
            id="fb-4",
            name="Update CHANGELOG",
            description="Add entry to CHANGELOG.md",
            action_type="file_write",
            parameters={
                "path": "CHANGELOG.md",
                "content": "## [Unreleased]\n### Added\n- {{feature_name}}: {{description}}",
            },
        ),
    ],
    variables={
        "feature_name": "new-feature",
        "description": "Description of the feature",
    },
    tags=["workflow", "git", "ci"],
)


BLUEPRINT_TEMPLATES["bugfix-hotfix"] = _make_template(
    id="bugfix-hotfix",
    name="Bugfix Hotfix",
    description="Quick bugfix workflow with test, fix, and verification",
    category="bugfix",
    steps=[
        BlueprintStep(
            id="bf-1",
            name="Reproduce bug",
            description="Create minimal reproduction test",
            action_type="file_write",
            parameters={
                "path": "tests/repro_{{bug_id}}.py",
                "content": "def test_repro_{{bug_id}}(): ...",
            },
        ),
        BlueprintStep(
            id="bf-2",
            name="Implement fix",
            description="Apply minimal fix for the bug",
            action_type="patch_create",
            parameters={
                "target": "{{affected_file}}",
                "patch": "{{fix_patch}}",
            },
        ),
        BlueprintStep(
            id="bf-3",
            name="Verify fix",
            description="Run reproduction test to verify fix",
            action_type="command_execute",
            parameters={"command": "pytest tests/repro_{{bug_id}}.py -v"},
        ),
        BlueprintStep(
            id="bf-4",
            name="Run regression suite",
            description="Ensure no regressions",
            action_type="command_execute",
            parameters={"command": "pytest -x -q"},
        ),
    ],
    variables={
        "bug_id": "BUG-123",
        "affected_file": "src/module.py",
        "fix_patch": "@@ -1,3 +1,4 @@\n+fix",
    },
    tags=["bugfix", "hotfix", "testing"],
)


BLUEPRINT_TEMPLATES["refactor-module"] = _make_template(
    id="refactor-module",
    name="Module Refactor",
    description="Safe module refactoring with tests and validation",
    category="refactor",
    steps=[
        BlueprintStep(
            id="rf-1",
            name="Extract interface",
            description="Extract public interface from module",
            action_type="patch_create",
            parameters={"target": "{{module_path}}", "patch": "{{interface_patch}}"},
        ),
        BlueprintStep(
            id="rf-2",
            name="Add characterization tests",
            description="Write tests that capture current behavior",
            action_type="file_write",
            parameters={
                "path": "tests/characterization_{{module_name}}.py",
                "content": "def test_current_behavior(): ...",
            },
        ),
        BlueprintStep(
            id="rf-3",
            name="Refactor implementation",
            description="Refactor internals while keeping tests green",
            action_type="patch_create",
            parameters={"target": "{{module_path}}", "patch": "{{refactor_patch}}"},
        ),
        BlueprintStep(
            id="rf-4",
            name="Run characterization tests",
            description="Verify behavior preserved",
            action_type="command_execute",
            parameters={"command": "pytest tests/characterization_{{module_name}}.py -v"},
        ),
        BlueprintStep(
            id="rf-5",
            name="Run full test suite",
            description="Ensure no regressions",
            action_type="command_execute",
            parameters={"command": "pytest -x -q"},
        ),
    ],
    variables={
        "module_name": "legacy_module",
        "module_path": "src/legacy_module.py",
    },
    tags=["refactor", "testing", "safe"],
)


BLUEPRINT_TEMPLATES["api-endpoint"] = _make_template(
    id="api-endpoint",
    name="REST API Endpoint",
    description="Create a new REST API endpoint with validation, docs, and tests",
    category="feature",
    steps=[
        BlueprintStep(
            id="api-1",
            name="Define OpenAPI spec",
            description="Add endpoint to OpenAPI specification",
            action_type="file_write",
            parameters={
                "path": "docs/api/{{endpoint_name}}.yaml",
                "content": "path: /api/v1/{{endpoint_name}}\nget:\n  summary: {{description}}",
            },
        ),
        BlueprintStep(
            id="api-2",
            name="Create request/response models",
            description="Add Pydantic models for request/response",
            action_type="file_write",
            parameters={
                "path": "src/api/models/{{endpoint_name}}.py",
                "content": "from pydantic import BaseModel\n\nclass {{ModelName}}Request(BaseModel): ...\nclass {{ModelName}}Response(BaseModel): ...",
            },
        ),
        BlueprintStep(
            id="api-3",
            name="Implement endpoint handler",
            description="Create FastAPI endpoint handler",
            action_type="file_write",
            parameters={
                "path": "src/api/endpoints/{{endpoint_name}}.py",
                "content": "@router.get('/{{endpoint_name}}')\nasync def {{endpoint_name}}(): ...",
            },
        ),
        BlueprintStep(
            id="api-4",
            name="Add validation",
            description="Add input validation and error handling",
            action_type="patch_create",
            parameters={
                "target": "src/api/endpoints/{{endpoint_name}}.py",
                "patch": "{{validation_patch}}",
            },
        ),
        BlueprintStep(
            id="api-5",
            name="Add tests",
            description="Add integration tests for endpoint",
            action_type="file_write",
            parameters={
                "path": "tests/api/test_{{endpoint_name}}.py",
                "content": "def test_{{endpoint_name}}(): ...",
            },
        ),
        BlueprintStep(
            id="api-6",
            name="Update API docs",
            description="Regenerate API documentation",
            action_type="command_execute",
            parameters={"command": "python -m scripts.generate_docs"},
        ),
    ],
    variables={
        "endpoint_name": "users",
        "description": "Get user by ID",
        "ModelName": "User",
    },
    tags=["api", "rest", "fastapi", "backend"],
)


def get_template(id: str) -> Optional[Blueprint]:
    """Get a blueprint template by ID."""
    return BLUEPRINT_TEMPLATES.get(id)


def list_templates(category: Optional[str] = None) -> list[Blueprint]:
    """List available blueprint templates."""
    templates = list(BLUEPRINT_TEMPLATES.values())
    if category:
        templates = [t for t in templates if t.metadata.category == category]
    return templates