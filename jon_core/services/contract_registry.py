"""ContractRegistry - Module contract registration and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import threading
import json


@dataclass
class ModuleContract:
    """Module contract definition."""
    module_name: str
    version: str
    input_schema: Dict[str, Any]
    output_schema: Dict[str, Any]
    governance_schema: Dict[str, Any]
    failure_schema: Dict[str, Any]
    registered_at: float = field(default_factory=lambda: __import__('time').time())
    amended_at: Optional[float] = None
    amendment_count: int = 0


class ContractRegistry:
    """Module contract registration with validation and versioning."""
    
    def __init__(self):
        self._contracts: Dict[str, ModuleContract] = {}
        self._lock = threading.RLock()

    def register(self, contract: ModuleContract) -> bool:
        """Register module contract."""
        with self._lock:
            if contract.module_name in self._contracts:
                return False
            self._contracts[contract.module_name] = contract
            return True

    def get(self, module_name: str) -> Optional[ModuleContract]:
        with self._lock:
            return self._contracts.get(module_name)

    def validate_input(self, module_name: str, input_data: Dict[str, Any]) -> bool:
        """Validate input against contract schema."""
        contract = self.get(module_name)
        if not contract:
            return False
        return self._validate_against_schema(input_data, contract.input_schema)

    def validate_output(self, module_name: str, output_data: Dict[str, Any]) -> bool:
        """Validate output against contract schema."""
        contract = self.get(module_name)
        if not contract:
            return False
        return self._validate_against_schema(output_data, contract.output_schema)

    def validate_governance(self, module_name: str, governance_data: Dict[str, Any]) -> bool:
        """Validate governance data against contract schema."""
        contract = self.get(module_name)
        if not contract:
            return False
        return self._validate_against_schema(governance_data, contract.governance_schema)

    def validate_failure(self, module_name: str, failure_data: Dict[str, Any]) -> bool:
        """Validate failure data against contract schema."""
        contract = self.get(module_name)
        if not contract:
            return False
        return self._validate_against_schema(failure_data, contract.failure_schema)

    def _validate_against_schema(self, data: Dict[str, Any], schema: Dict[str, Any]) -> bool:
        """Simple schema validation (placeholder for JSON Schema)."""
        # In production, use jsonschema library
        required = schema.get("required", [])
        for field in required:
            if field not in data:
                return False
        return True

    def amend(self, module_name: str, amendments: Dict[str, Any]) -> bool:
        """Amend contract (versioned)."""
        with self._lock:
            contract = self._contracts.get(module_name)
            if not contract:
                return False
            
            # Apply amendments
            for key, value in amendments.items():
                if hasattr(contract, key):
                    setattr(contract, key, value)
            
            import time
            contract.amended_at = time.time()
            contract.amendment_count += 1
            return True

    def list_contracts(self) -> List[ModuleContract]:
        with self._lock:
            return list(self._contracts.values())

    def query_for_governance_surface(self, module_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Query contracts for Governance Surface."""
        with self._lock:
            if module_name:
                contract = self._contracts.get(module_name)
                return [contract.__dict__] if contract else []
            return [c.__dict__ for c in self._contracts.values()]