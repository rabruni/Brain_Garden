# Requirements

## Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-1 | System MUST reject completions without prompt_pack_id |
| FR-2 | System MUST verify prompt hash matches registry |
| FR-3 | System MUST log prompt_pack_id in evidence |
| FR-4 | System MUST NOT log raw prompt content |
| FR-5 | System MUST support template variable substitution |
| FR-6 | System MUST track prompt versions |

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | Prompt loading MUST complete in < 100ms |
| NFR-2 | Hash verification MUST use SHA256 |
| NFR-3 | Registry MUST be human-readable (CSV) |
| NFR-4 | Prompts MUST be version-controlled |

## Security Requirements

| ID | Requirement |
|----|-------------|
| SR-1 | Prompts MUST NOT contain raw secrets |
| SR-2 | Template variables MUST be validated |
| SR-3 | Prompt changes MUST be approved |
| SR-4 | Hash mismatches MUST cause HARD FAIL |

## Acceptance Criteria

1. All existing LLM calls use governed prompts
2. Ungoverned prompt attempts are rejected
3. Evidence logs show prompt_pack_id (not content)
4. Hash verification catches tampered prompts
