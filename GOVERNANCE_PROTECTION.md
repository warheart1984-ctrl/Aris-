# ARIS Governance Protection & Voice Activation

## Overview

This document describes the governance protection mechanisms that prevent unauthorized changes to the ARIS runtime, constitutional laws, and Voss Binding binary. It also covers the voice activation system for operator interaction.

---

## Governance Protection (Immutable)

### 1. Foundation Store - Immutable Constitutional Anchors
**Location**: `jon_core/services/foundation_store.py`

Protected entries that **cannot be modified once locked**:
- `UL_ROOT_LAW_LOCKED` - Universal Law root axiom
- `ARIS_HANDBOOK_LOCKED` - ARIS operator handbook
- `ARIS_DOC_CHANNEL_LOCKED` - Document channel protocol

```python
store = FoundationStore()
store.set("UL_ROOT_LAW_LOCKED", law_content)  # Only works before lock
store.lock("UL_ROOT_LAW_LOCKED")  # Irreversible
# store.set("UL_ROOT_LAW_LOCKED", new_content)  # FAILS - returns False
```

### 2. Identity Registry - Protected Identities
**Location**: `jon_core/services/identity_registry.py`

Identities that **cannot be copied or assumed**:
- `ARIS` - Primary runtime identity (copy_protected=true, lineage_required=true)
- `AAIS` - Governance identity (copy_protected=true, lineage_required=true)

Required host capabilities: `governance`, `runtime`, `audit`

```python
registry = IdentityRegistry()
registry.is_protected("ARIS")  # True
registry.requires_lineage("ARIS")  # True
registry.is_copy_protected("ARIS")  # True
```

### 3. Supremacy Validator - No Override Backdoor
**Location**: `jon_core/laws/supremacy_validator.py`

**No admin backdoor. No debug bypass. No emergency override.**
All config/deployment changes validated against Λ.1-Λ.7 before application.

```python
validator = SupremacyValidator()
validator.assert_valid(change, context)  # Raises OverrideLockout if rejected
# validator.lockout_active  # Always True - cannot be disabled
```

### 4. Hall Router - Fingerprint-Based Re-Entry Blocking
**Location**: `jon_core/services/hall_router.py`

Mutations routed to immutable halls with **fingerprint-based blocking**:
- **Discard** - Failed verification, no re-entry
- **Shame** - Policy violation, blocked from re-entry
- **Fame** - Successful, lineage tracked

```python
router = HallRouter()
blocker = router.find_reentry_blocker(fingerprint)  # Returns entry if blocked
router.is_blocked(action)  # True if fingerprint in any hall
```

### 5. Shield of Truth - Immutable 7 Laws
**Location**: `jon_core/services/shield_of_truth.py`

Adjudication against **immutable law set** (cannot be modified at runtime):
1. Safety over Speed
2. Truth over Speed
3. Operator Intent over Autonomy
4. No Hidden Actions
5. Verifiable Evidence
6. Reversible Changes
7. Identity Preservation

### 6. Law Spine - Immutable Manifest
**Location**: `jon_core/runtime/__init__.py`

Root law manifest with **SHA256 verification** - fails closed on hash mismatch:
```python
spine = LawSpine(manifest)
snapshot = spine.snapshot()
snapshot.ok  # True only if manifest_hash == expected_hash
```

### 7. Law Ledger - Tamper-Evident Chain
**Location**: `jon_core/services/law_ledger.py`

Append-only JSONL with **hash chain integrity**:
```python
ledger = LawLedger()
ledger.record(LawLedgerEventType.MUTATION_GATE, payload)
valid, errors = ledger.verify_chain_integrity()  # Verifies from genesis
```

### 8. Forbidden Caller Fields
**Location**: `jon_core/adapters/__init__.py` → `LawContextBuilder`

Runtime **rejects any caller attempting to inject**:
- `identity`, `scope`, `speech`, `host`, `verification`, `lineage`

---

## Voss Binding Binary Protection

The Voss Binding binary (`evolving_ai/voss_binding/`) is **law-bound** through:

1. **Governance metadata** (`governance.json`) loaded at startup via `FoundationStore`
2. **MutationGate admission** required for any binary modification
3. **HallRouter fingerprinting** prevents re-entry of rejected patches
4. **OverrideReckoning** tracks escalating cost for bypass attempts
5. **ShieldOfTruth adjudication** evaluates against 7 immutable laws
6. **LawLedger** records all mutation attempts with hash chain

```python
# Any modification to Voss Binding must pass:
mutation_gate.review(context, action)  # → MutationAdmission with recovery actions
hall_router.discard(action, lineage)   # Blocked if fingerprint exists
override_reckoning.record(...)         # Escalating cost/severity
shield.adjudicate(context, action)     # 7-law adjudication
law_ledger.record(...)                 # Immutable audit trail
```

---

## Voice Activation for Operators

### Components (Already Implemented)

| Component | File | Purpose |
|-----------|------|---------|
| Voice Identity | `voice_identity.py` | Speaker verification, enrollment, privileges |
| Voice Commands | `voice_commands.py` | Speech recognition, command pipeline |
| Voice Auth | `voice_auth.py` | Authorization management |
| Command Types | `command_types.py` | Command/request structures |
| Constitutional Gate | `constitutional_gate.py` | Governance validation for voice commands |

### Enable Voice Activation

Set environment variables:
```bash
# Enable voice commands (default: true)
ARIS_VOICE_COMMANDS_ENABLED=true

# Voice auth (default: true)
ARIS_VOICE_AUTH_ENABLED=true

# Speaker verification threshold (default: 0.85)
ARIS_VOICE_THRESHOLD=0.85

# Method: resemblyzer, speechbrain, custom, disabled
ARIS_VOICE_METHOD=resemblyzer

# Timeout settings
ARIS_VOICE_COMMAND_TIMEOUT=5.0
ARIS_VOICE_COMMAND_PHRASE_TIMEOUT=3.0
ARIS_VOICE_COMMAND_ENERGY_THRESHOLD=300
```

### Speaker Enrollment (Operator Setup)

```python
from evolving_ai.aris_runtime.voice_identity import create_voice_identity_provider
from pathlib import Path

provider = create_voice_identity_provider(Path("data_root"))

# Start enrollment (3 samples required by default)
provider.start_enrollment("operator_1", "Primary Operator", privileges=["operator", "admin"])

# Add audio samples (bytes)
provider.add_enrollment_sample(audio_bytes)  # Returns (count, required)

# Complete enrollment
profile = provider.complete_enrollment()  # SpeakerProfile with embeddings
```

### Voice Command Pipeline

```
Audio Input → Speech Recognition → Command Normalizer → Constitutional Gate → Evidence Recorder → Execution
                     ↓
            Voice Auth Manager (Speaker Verification)
                     ↓
            Privilege Check (operator/admin privileges)
                     ↓
            Constitutional Gate (Λ.1-Λ.7, SpeechChain, CISIV)
```

### Operator Privileges

Verified speakers receive privileges based on enrollment:
- `operator` - Standard operator commands
- `admin` - Administrative functions (kill switch, manifest, etc.)
- `governance` - Governance operations (mutation gate, hall router, etc.)

```python
# Check privileges
provider.is_authorized(speaker_id)  # True/False
provider.get_speaker_privileges(speaker_id)  # ["operator", "admin"]
```

---

## Enforcement Summary

| Protection | Mechanism | Bypass Possible? |
|------------|-----------|------------------|
| Constitutional Laws (Λ.1-Λ.7) | SupremacyValidator + OverrideLockout | **No** |
| Foundation Entries | FoundationStore.lock() | **No** (irreversible) |
| Protected Identities | IdentityRegistry (copy_protected, lineage_required) | **No** |
| Voss Binary | MutationGate → HallRouter → ShieldOfTruth | **No** (full pipeline) |
| Audit Trail | LawLedger (hash chain) | **No** (tamper-evident) |
| Voice Auth | SpeakerVerification + Privileges | **No** (cryptographic) |

---

## For Contributors

**You may NOT:**
- Modify `UL_ROOT_LAW_LOCKED`, `ARIS_HANDBOOK_LOCKED`, `ARIS_DOC_CHANNEL_LOCKED`
- Change `ARIS` or `AAIS` identity configuration
- Disable `SupremacyValidator.lockout_active`
- Remove HallRouter fingerprint entries
- Modify ShieldOfTruth law set
- Alter LawSpine manifest without hash update
- Inject forbidden caller fields (identity, scope, speech, host, verification, lineage)

**You MAY:**
- Add new voice operators via enrollment
- Configure voice timeout/threshold settings
- Extend voice command vocabulary
- Add non-governance features
- Improve performance/UX within constitutional boundaries

All changes must pass the full governance pipeline: **MutationGate → HallRouter → OverrideReckoning → ShieldOfTruth → LawLedger → FoundationStore**.