# FMWK-107: Package Management Standard

**Status:** Draft  
**Altitude:** L3 (Design)  
**Purpose:** Define required metadata, provenance, and validation rules for governed packages managed by the Control Plane registries. No execution or installer logic is included—this framework governs metadata only.

---

## 1. Scope
- Applies to all entries with `entity_type=package` in the Control Plane registries.
- Governs creation, update, and validation of package metadata; does not perform installation.
- Enforces reproducibility, provenance, and dependency correctness for downstream tooling.

## 2. Required Fields
- `id` (`PKG-###`): unique package identifier.
- `name`: human-readable package name.
- `version`: semver (`MAJOR.MINOR.PATCH`), tag or commit pinned.
- `source`: immutable locator (e.g., git URL + commit/tag, OCI ref, HTTPS tarball).
- `source_type`: one of `git|pypi|tar|oci|local`.
- `digest`: SHA256 (hex). Required for all non-local sources.
- `signature` (optional): detached signature or signature reference.
- `platform`: OS list (e.g., `linux`, `darwin`); `any` allowed.
- `arch`: CPU arch list (e.g., `x86_64`, `arm64`); `any` allowed.
- `deps`: comma list of `PKG-###[@constraint]` where constraint is semver range (`^`, `~`, exact, `>=`).
- `conflicts`: comma list of package IDs/ranges that must not co‑install.
- `license`: SPDX identifier.
- `status`: `proposed|draft|validated|active|superseded|deprecated|retired|archived|yanked`.
- `selected`: `yes|no`.
- `priority`: `P0|P1|P2|P3`.
- `owner`: accountable party.
- `created_at`: ISO 8601 date.
- `content_hash`: SHA256 of the row contents (deterministic canonicalization).

## 3. Rules
- **Pinning:** `source` must be immutable (commit SHA, tagged digest, or versioned tarball). Mutable branches are disallowed.
- **Digest Required:** `digest` is mandatory unless `source_type=local`; local must still carry a `content_hash`.
- **Dependency Integrity:** All `deps` must exist, satisfy semver constraints, and be acyclic. `conflicts` must be disjoint from `deps`.
- **Platform Fit:** If `platform`/`arch` not `any`, they must be validated against a controlled enum.
- **Provenance:** `owner` + `created_at` required; `source_spec_id` in the registry row must point to the spec authoring the change.
- **Lifecycle:** `yanked` marks removal from resolution; `deprecated` allows install with warning; `retired` marks historical and not installable.

## 4. Validation Requirements
- Schema validation per `types_registry.csv` (`entity_type=package`).
- Semver parse for `version` and dep constraints.
- Digest present and hex; signature optional but, if present, non-empty.
- Dependency graph: no missing nodes, no cycles, no conflicts.
- Platform/arch enums validated.
- `content_hash` recomputed during validation; mismatches fail.

## 5. Testing Requirements (per FMWK-103)
- Unit tests covering: schema, semver/constraints, dep resolution (happy, missing, cycle, conflict), digest enforcement, platform filtering.
- Coverage: include new validator modules and tests in coverage config.

## 6. Governance Links
- Complies with FMWK-100 (DoD), FMWK-103 (testing), FMWK-104 (policy lifecycle).
- Spec packs implementing packages must declare `complies_with` including FMWK-107.

## 7. Artifacts
- Registry: `registries/packages_registry.csv`
- Validator: `scripts/validate_packages.py`
- Compiler: `scripts/package_sync.py` (optional compiled JSON)
- Spec: `specs/SPEC-026_package_registry/*`

## 8. Non-Goals
- No install or execution logic.
- No runtime package fetching; metadata only.

---

## Appendix: Canonical Terminology Glossary

The following terms have precise meanings in the Control Plane system. They must not be conflated.

| Term | Definition |
|------|------------|
| **Control Plane** | The whole governed system boundary. It is the authority that enforces policy, manages artifacts, and maintains integrity. The Control Plane *contains* registries, ledgers, libraries, and scripts. |
| **Registry** | A declarative dataset (CSV or compiled JSON) inside the Control Plane that lists governed artifacts and their metadata. Registries are *subcomponents* of the Control Plane—they record what exists but do not themselves govern. |
| **Ledger** | An append-only evidence store with hash-chained entries. The ledger records decisions and events for audit purposes. |
| **Gate** | An enforcement decision point where the Control Plane validates, authorizes, and logs transitions. |

**Key Distinction:**
- The **Control Plane** governs.
- The **Registry** records.
- These are not synonyms. "Registry" must never be used to mean "the governing system."

