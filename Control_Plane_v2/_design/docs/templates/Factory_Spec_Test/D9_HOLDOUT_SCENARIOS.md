# D9: Holdout Scenarios — Dark Factory Orchestrator

**Component:** Dark Factory Orchestrator
**Spec Version:** 0.1.0
**Contracts:** D4 v0.1.0
**Status:** Draft
**Author:** Ray + Claude (spec author — NOT the builder agent)
**Last Run:** Not yet executed
**CRITICAL: This document is stored separately from the builder. The builder agent MUST NOT see these scenarios before completing their work.**

---

## Scenarios

### HS-001: Validate the real test/ spec and catch intentional gaps

```yaml
component: dark-factory-orchestrator
scenario: validate-real-spec
priority: P0
```

**Validates:** SC-001 (validate complete spec), SC-006 (missing doc)
**Contracts:** IN-001, OUT-001
**Type:** Happy path + Error path

**Setup:**
```bash
# Use the actual test/ directory as a known-good spec
SPEC_DIR="_design/docs/templates/test"
# Create a copy with a deliberate gap for the error test
cp -r "$SPEC_DIR" /tmp/factory_holdout_incomplete
rm /tmp/factory_holdout_incomplete/D5_RESEARCH.md
```

**Execute:**
```bash
# Test 1: Validate the real spec (should PASS)
python3 -m factory validate --spec-dir "$SPEC_DIR" > /tmp/holdout_hs001_pass.json 2>&1
echo "EXIT_PASS=$?" > /tmp/holdout_hs001_codes.txt

# Test 2: Validate the incomplete spec (should FAIL)
python3 -m factory validate --spec-dir /tmp/factory_holdout_incomplete > /tmp/holdout_hs001_fail.json 2>&1
echo "EXIT_FAIL=$?" >> /tmp/holdout_hs001_codes.txt
```

**Verify:**

| Check | What to Examine | PASS Condition | FAIL Condition |
|-------|----------------|----------------|----------------|
| 1 | Exit code for test 1 | EXIT_PASS=0 | Non-zero |
| 2 | JSON output status for test 1 | `"status": "PASS"` | Any other status |
| 3 | Exit code for test 2 | EXIT_FAIL=1 (non-zero) | EXIT_FAIL=0 |
| 4 | JSON output for test 2 | Contains "Missing required document: D5_RESEARCH.md" | Does not name missing doc |

**Cleanup:**
```bash
rm -rf /tmp/factory_holdout_incomplete /tmp/holdout_hs001_*
```

### HS-002: Generated handoffs contain no D9 holdout content

```yaml
component: dark-factory-orchestrator
scenario: holdout-isolation
priority: P0
```

**Validates:** SC-002 (generate handoffs), D1 Article 2 (holdout isolation)
**Contracts:** OUT-002
**Type:** Side-effect verification

**Setup:**
```bash
SPEC_DIR="_design/docs/templates/test"
OUTPUT_DIR="/tmp/factory_holdout_hs002"
mkdir -p "$OUTPUT_DIR"
```

**Execute:**
```bash
python3 -m factory validate --spec-dir "$SPEC_DIR" && \
python3 -m factory generate --spec-dir "$SPEC_DIR" --output-dir "$OUTPUT_DIR"
```

**Verify:**

| Check | What to Examine | PASS Condition | FAIL Condition |
|-------|----------------|----------------|----------------|
| 1 | Handoff files exist | At least 1 .md file in $OUTPUT_DIR/H-FACTORY-*/ | No handoff files |
| 2 | Grep all handoffs for "HS-001" | Zero matches | Any match (holdout ID leaked) |
| 3 | Grep all handoffs for "HS-002" | Zero matches | Any match |
| 4 | Grep all handoffs for "Holdout" (case-insensitive) | Zero matches | Any match (holdout concept leaked) |
| 5 | Grep all handoffs for "Malformed JSON from LLM" | Zero matches | Any match (HS-001 title from test/ D9) |

```bash
LEAKED=$(grep -ri "HS-\|holdout\|Malformed JSON from LLM" "$OUTPUT_DIR"/H-FACTORY-*/*.md | wc -l)
test "$LEAKED" -eq 0
```

**Cleanup:**
```bash
rm -rf "$OUTPUT_DIR"
```

### HS-003: Handoff traceability is complete

```yaml
component: dark-factory-orchestrator
scenario: traceability-complete
priority: P0
```

**Validates:** SC-002 (generate handoffs), D1 Article 4 (every handoff is traceable)
**Contracts:** OUT-002
**Type:** Integration

**Setup:**
```bash
SPEC_DIR="_design/docs/templates/test"
OUTPUT_DIR="/tmp/factory_holdout_hs003"
mkdir -p "$OUTPUT_DIR"
python3 -m factory generate --spec-dir "$SPEC_DIR" --output-dir "$OUTPUT_DIR"
```

**Execute:**
```bash
# Extract all D2 scenario IDs from the spec
python3 -c "
import json
with open('$OUTPUT_DIR/handoff_index.json') as f:
    index = json.load(f)
scenarios_covered = set()
for handoff in index['handoffs']:
    scenarios_covered.update(handoff['scenarios'])
print(json.dumps(sorted(list(scenarios_covered))))
" > /tmp/holdout_hs003_covered.json

# Extract all D2 scenario IDs from the spec directly
python3 -c "
import re
with open('$SPEC_DIR/D2_SPECIFICATION.md') as f:
    content = f.read()
scenarios = re.findall(r'#### (SC-\d+):', content)
print(json.dumps(sorted(scenarios)))
" > /tmp/holdout_hs003_expected.json
```

**Verify:**

| Check | What to Examine | PASS Condition | FAIL Condition |
|-------|----------------|----------------|----------------|
| 1 | handoff_index.json exists | File exists and is valid JSON | Missing or malformed |
| 2 | Coverage | Every scenario in expected appears in covered | Any scenario missing |
| 3 | Handoff sections | Each handoff .md has all 10 required sections | Missing section |

```bash
diff /tmp/holdout_hs003_expected.json /tmp/holdout_hs003_covered.json
```

**Cleanup:**
```bash
rm -rf "$OUTPUT_DIR" /tmp/holdout_hs003_*
```

### HS-004: D8 dependency cycle detection

```yaml
component: dark-factory-orchestrator
scenario: cycle-detection
priority: P0
```

**Validates:** SC-010 (dependency cycle)
**Contracts:** IN-001, OUT-001, ERR-001
**Type:** Error path

**Setup:**
```bash
# Create a spec with a dependency cycle in D8
SPEC_DIR="/tmp/factory_holdout_hs004"
cp -r "_design/docs/templates/test" "$SPEC_DIR"

# Modify D8 to introduce a cycle: T-002 depends on T-005, T-005 depends on T-002
python3 -c "
with open('$SPEC_DIR/D8_TASKS.md', 'r') as f:
    content = f.read()
content = content.replace(
    '**Dependency:** T-001 (ContractLoader available)',
    '**Dependency:** T-005'
)
with open('$SPEC_DIR/D8_TASKS.md', 'w') as f:
    f.write(content)
"
```

**Execute:**
```bash
python3 -m factory validate --spec-dir "$SPEC_DIR" > /tmp/holdout_hs004_result.json 2>&1
EXIT_CODE=$?
```

**Verify:**

| Check | What to Examine | PASS Condition | FAIL Condition |
|-------|----------------|----------------|----------------|
| 1 | Exit code | Non-zero | Zero (should have detected cycle) |
| 2 | Output | Contains "cycle" (case-insensitive) | No mention of cycle |
| 3 | Output | Names at least 2 task IDs in the cycle | No task IDs |

```bash
test "$EXIT_CODE" -ne 0 && grep -i "cycle" /tmp/holdout_hs004_result.json && grep "T-00" /tmp/holdout_hs004_result.json
```

**Cleanup:**
```bash
rm -rf "$SPEC_DIR" /tmp/holdout_hs004_*
```

### HS-005: Builder failure propagates correctly through dependency graph

```yaml
component: dark-factory-orchestrator
scenario: failure-propagation
priority: P1
```

**Validates:** SC-008 (builder fails a task), SC-005 (full pipeline)
**Contracts:** SIDE-001, ERR-003
**Type:** Integration

**Setup:**
```bash
SPEC_DIR="_design/docs/templates/test"
OUTPUT_DIR="/tmp/factory_holdout_hs005"
mkdir -p "$OUTPUT_DIR"

# Pre-generate handoffs and prompts
python3 -m factory generate --spec-dir "$SPEC_DIR" --output-dir "$OUTPUT_DIR"
python3 -m factory prompts --handoffs-dir "$OUTPUT_DIR" --spec-dir "$SPEC_DIR"

# Create a mock Claude Code that fails T-003 but succeeds T-004
# (both are Phase 2 peers in the test/ D8)
cat > /tmp/mock_claude.sh << 'MOCK'
#!/bin/bash
# Read the prompt, check which task, return appropriate result
if echo "$@" | grep -q "T-003\|TraceWriter"; then
  echo "Status: FAIL" > "$FACTORY_RESULTS_PATH"
  exit 0
else
  echo "Status: PASS" > "$FACTORY_RESULTS_PATH"
  exit 0
fi
MOCK
chmod +x /tmp/mock_claude.sh
```

**Execute:**
```bash
FACTORY_CLAUDE_PATH=/tmp/mock_claude.sh \
python3 -m factory run --spec-dir "$SPEC_DIR" --output-dir "$OUTPUT_DIR" > /tmp/holdout_hs005_report.json 2>&1
```

**Verify:**

| Check | What to Examine | PASS Condition | FAIL Condition |
|-------|----------------|----------------|----------------|
| 1 | T-003 status | FAILED | Any other status |
| 2 | T-005 status (depends on T-003) | BLOCKED | COMPLETED or DISPATCHED |
| 3 | T-004 status (parallel peer, no dep on T-003) | COMPLETED | BLOCKED (incorrectly blocked) |
| 4 | Dispatch ledger | Contains entries for T-003, T-004 | Missing entries |

**Cleanup:**
```bash
rm -rf "$OUTPUT_DIR" /tmp/factory_holdout_hs005_* /tmp/mock_claude.sh
```

### HS-006: Generated prompts have exactly 13 questions

```yaml
component: dark-factory-orchestrator
scenario: prompt-question-count
priority: P1
```

**Validates:** SC-003 (generate prompts)
**Contracts:** OUT-003
**Type:** Side-effect verification

**Setup:**
```bash
SPEC_DIR="_design/docs/templates/test"
OUTPUT_DIR="/tmp/factory_holdout_hs006"
mkdir -p "$OUTPUT_DIR"
python3 -m factory generate --spec-dir "$SPEC_DIR" --output-dir "$OUTPUT_DIR"
python3 -m factory prompts --handoffs-dir "$OUTPUT_DIR" --spec-dir "$SPEC_DIR"
```

**Execute:**
```bash
# Count numbered questions in each prompt file
for prompt in "$OUTPUT_DIR"/H-FACTORY-*/*_AGENT_PROMPT.md; do
  COUNT=$(grep -cE '^\d+\.' "$prompt")
  HANDOFF=$(basename "$(dirname "$prompt")")
  echo "$HANDOFF: $COUNT questions"
done > /tmp/holdout_hs006_counts.txt
```

**Verify:**

| Check | What to Examine | PASS Condition | FAIL Condition |
|-------|----------------|----------------|----------------|
| 1 | Question count per prompt | Every prompt has exactly 13 | Any prompt with != 13 |
| 2 | Expected answers files exist | One *_EXPECTED_ANSWERS.md per prompt | Missing expected answers |
| 3 | Expected answers NOT in prompt | Prompt file does not contain "Expected Answer" | Answers leaked into prompt |

```bash
# All prompts must have 13 questions
! grep -v "13 questions" /tmp/holdout_hs006_counts.txt
```

**Cleanup:**
```bash
rm -rf "$OUTPUT_DIR" /tmp/holdout_hs006_*
```

---

## Scenario Coverage Matrix

| D2 Scenario | Priority | Holdout Coverage | Notes |
|-------------|----------|-----------------|-------|
| SC-001 | P1 | HS-001 | Validate pass + fail |
| SC-002 | P1 | HS-002, HS-003 | Isolation + traceability |
| SC-003 | P1 | HS-006 | Prompt structure |
| SC-004 | P1 | — | Holdout runner tested by HS-001 verify steps themselves |
| SC-005 | P2 | HS-005 | Full pipeline with failure propagation |
| SC-006 | P1 | HS-001 | Missing doc detection |
| SC-007 | P1 | — | Covered by validator unit tests |
| SC-008 | P1 | HS-005 | Builder failure + dependency blocking |
| SC-009 | P1 | — | Holdout failure tracing tested by HS-005 |
| SC-010 | P1 | HS-004 | Cycle detection |

---

## Run Protocol

**When to run:** After builder delivers the orchestrator and all handoff-level tests pass.
**Run environment:** Local machine with Python 3.10+, test/ spec directory available, factory CLI installed.
**Run order:** P0 scenarios first (HS-001, HS-002, HS-003, HS-004). If any P0 fails, stop. Then P1 (HS-005, HS-006).
**Pass threshold:** All P0 pass (4/4). All P1 pass (2/2). No partial credit.
**On failure:** File against the D8 task that should have satisfied the failing scenario. Include: which D2 scenario failed, which D4 contract was violated, actual vs. expected output.
