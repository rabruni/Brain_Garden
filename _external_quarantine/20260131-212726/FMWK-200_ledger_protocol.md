# FMWK-200: Ledger Protocol Standard

## Purpose
Define a portable ledger protocol for governed systems, ensuring tamper-evident append-only logging with pluggable backends and Merkle/chain integrity.

## Scope
- Applies to any Control Plane or external framework needing governed ledger semantics.
- Covers write semantics, integrity fields, and verification expectations.
- Excludes transport-specific concerns (left to adapters).

## Requirements
1. **Entry schema**: `previous_hash`, `entry_hash`, deterministic serialization, UTC timestamp, UUID-based id.
2. **Tamper evidence**: chained hashes plus optional segment Merkle roots and root-of-roots.
3. **Portability**: Provide a `LedgerProtocol` interface for alternative backends (file, SQLite, remote).
4. **Rotation**: Segmented ledgers must preserve chain continuity.
5. **Verification**: Implement full-chain and segment-parallel verification paths.

## Conformance
- Reference implementation: `lib/ledger_client.py` (LIB-001).
- Governing specs: `SPEC-024` (governance logging), `SPEC-025` (Merkle chaining).

## Status
- Version: 1.0.0
- State: draft
- Owner: claude
- Created: 2026-01-30
- Source Spec: SPEC-025
