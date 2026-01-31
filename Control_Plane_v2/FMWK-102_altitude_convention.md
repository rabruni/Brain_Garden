# FMWK-102: Altitude Convention Standard

**Version:** 1.0.0
**Status:** DRAFT
**Purpose:** Standardize altitude numbering and provide inspection criteria

---

## 1. The Altitude Convention

### Standard: Higher Number = Higher Abstraction

```
L4 ──────────────────────────────────────────── HIGHEST (most abstract)
│   IDENTITY: Why we exist, values, north stars
│   Think: "30,000 foot view"
│
L3 ────────────────────────────────────────────
│   STRATEGY: What matters, priorities, goals
│   Think: "Flight plan"
│
L2 ────────────────────────────────────────────
│   OPERATIONS: This week, tasks, execution plan
│   Think: "Runway operations"
│
L1 ──────────────────────────────────────────── LOWEST (most concrete)
    MOMENT: Right now, this action, this line of code
    Think: "Wheels on the ground"
```

### Mnemonic: "L4 = Look Far, L1 = Look Here"

| Level | Mnemonic | Question Answered | Time Horizon |
|-------|----------|-------------------|--------------|
| L4 | Look Far | WHY does this exist? | Years |
| L3 | Look Forward | WHAT should we build? | Months |
| L2 | Look Around | HOW do we build it? | Weeks |
| L1 | Look Here | WHAT do I do NOW? | Hours/Minutes |

### Alternative Mental Model: Zoom Levels

```
L4: Satellite view    🛰️  (see the whole continent)
L3: Airplane view     ✈️  (see the city layout)
L2: Drone view        🚁  (see the buildings)
L1: Street view       🚶  (see the door handles)
```

---

## 2. Why This Convention?

### Consistency with Existing Code

The `altitude.py` module already uses this convention:
```python
class Level(Enum):
    L4 = 4  # Identity (highest)
    L3 = 3  # Strategy
    L2 = 2  # Operations
    L1 = 1  # Moment (lowest)
```

### Intuitive for Abstraction

- Higher altitude = more abstract = bigger picture
- Lower altitude = more concrete = more detail
- "Ascending" = zooming out
- "Descending" = zooming in

### Conflict with Other Models

Note: This is OPPOSITE of C4 Model (where Level 1 = Context, Level 4 = Code).
We chose higher=abstract because:
- Matches physical altitude metaphor (higher up = see more)
- Already implemented in altitude.py
- Matches DoPeJar HRM conventions

---

## 3. Altitude Inspection Matrix

### How to Know When Altitude Quality is Achieved

Each cell defines: WHAT to check, HOW to check it, PASS/FAIL criteria.

---

### L4 (Identity/Vision) Inspection

| Check | How to Inspect | Pass Criteria | Fail Criteria |
|-------|----------------|---------------|---------------|
| Vision present | Search 00_overview for "vision", "purpose", "why" | 2+ sentences describing future state | Missing or <2 sentences |
| Problem narrative | Check 01_problem word count | 100+ words in problem description | <100 words or bullet-only |
| Non-goals explicit | Search 01_problem for "non-goal" section | 1+ explicit non-goal | Missing non-goals section |
| No implementation | Search 04_design for file paths | Zero file paths mentioned | Any `.py`, `.js`, etc. paths |
| No test code | Search 05_testing for code blocks | Zero code blocks | Any ``` code blocks |
| Stakeholders defined | Search 00_overview for "stakeholder" | At least 1 stakeholder | Missing stakeholders |
| Success measurable | Check 00_overview success criteria | Criteria are measurable | Vague criteria ("make it better") |

**L4 Pass Score:** 6/7 checks pass (allow 1 exception with justification)

---

### L3 (Strategy/Design) Inspection

| Check | How to Inspect | Pass Criteria | Fail Criteria |
|-------|----------------|---------------|---------------|
| Components defined | Search 04_design for component list | 2+ named components | <2 or unnamed |
| Interfaces described | Search 04_design for "interface", "input", "output" | Each component has I/O | Components without I/O |
| Requirements exist | Search 03_requirements for "FR-" pattern | 1+ FR-XXX requirement | Zero requirements |
| Acceptance criteria | Check each FR-XXX has criteria | All FRs have criteria | Any FR missing criteria |
| Test command exists | Search 05_testing for "$ " | Single $ command line | Zero or multiple $ lines |
| File structure shown | Search 04_design for directory tree | Directory structure present | No structure |
| No implementation code | Search for function bodies | Zero function implementations | Any actual code |

**L3 Pass Score:** 6/7 checks pass

---

### L2 (Operations/Build) Inspection

| Check | How to Inspect | Pass Criteria | Fail Criteria |
|-------|----------------|---------------|---------------|
| File paths exact | Search 04_design for paths | Full paths with extensions | Partial or missing paths |
| Function signatures | Search for `def ` or `function ` | Signatures documented | Missing signatures |
| Test files exist | Check referenced test files | Files exist on disk | Referenced files missing |
| Commands executable | Try running 06_rollout commands | Commands execute | Commands fail |
| L3 reference | Check for link to L3 spec | Reference present | No reference |
| Error handling | Search for "error", "exception", "fail" | Error cases documented | No error handling |

**L2 Pass Score:** 5/6 checks pass

---

## 4. Automated Inspection Script

### Proposed: validate_altitude_depth.py

```python
#!/usr/bin/env python3
"""
Validate spec pack content depth matches declared altitude.

Usage:
    python3 scripts/validate_altitude_depth.py --target SPEC-XXX

Exit codes:
    0 = Pass (altitude quality achieved)
    1 = Fail (content doesn't match altitude)
    2 = Target not found
"""

import re
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class InspectionResult:
    check_name: str
    passed: bool
    reason: str
    evidence: str = ""

def inspect_l4(spec_root: Path) -> List[InspectionResult]:
    """Inspect L4 (Vision) altitude requirements."""
    results = []

    # Check 1: Vision present
    overview = (spec_root / "00_overview.md").read_text()
    vision_patterns = ["vision", "purpose", "why we", "exists to"]
    has_vision = any(p in overview.lower() for p in vision_patterns)
    results.append(InspectionResult(
        "vision_present",
        has_vision,
        "Vision statement found" if has_vision else "No vision statement"
    ))

    # Check 2: Problem narrative (100+ words)
    problem = (spec_root / "01_problem.md").read_text()
    word_count = len(problem.split())
    results.append(InspectionResult(
        "problem_narrative",
        word_count >= 100,
        f"Problem has {word_count} words",
        f"Threshold: 100 words"
    ))

    # Check 3: Non-goals explicit
    has_nongoals = "non-goal" in problem.lower() or "non goal" in problem.lower()
    results.append(InspectionResult(
        "nongoals_explicit",
        has_nongoals,
        "Non-goals section found" if has_nongoals else "No non-goals section"
    ))

    # Check 4: No implementation details
    design = (spec_root / "04_design.md").read_text()
    file_patterns = r'\.(py|js|ts|go|rs|java|cpp|c|h|md)\b'
    has_files = bool(re.search(file_patterns, design))
    results.append(InspectionResult(
        "no_implementation",
        not has_files,
        "No file paths found" if not has_files else "File paths found (too detailed for L4)"
    ))

    # Check 5: No test code
    testing = (spec_root / "05_testing.md").read_text()
    has_code = "```" in testing and ("def " in testing or "function " in testing)
    results.append(InspectionResult(
        "no_test_code",
        not has_code,
        "No test code found" if not has_code else "Test code found (too detailed for L4)"
    ))

    return results

def inspect_l3(spec_root: Path) -> List[InspectionResult]:
    """Inspect L3 (Strategy/Design) altitude requirements."""
    results = []

    # Check 1: Components defined
    design = (spec_root / "04_design.md").read_text()
    component_patterns = ["component", "module", "service", "## "]
    component_count = sum(design.lower().count(p) for p in component_patterns[:3])
    results.append(InspectionResult(
        "components_defined",
        component_count >= 2,
        f"Found {component_count} component references"
    ))

    # Check 2: Requirements exist
    requirements = (spec_root / "03_requirements.md").read_text()
    fr_count = len(re.findall(r'FR-\d+', requirements))
    results.append(InspectionResult(
        "requirements_exist",
        fr_count >= 1,
        f"Found {fr_count} functional requirements"
    ))

    # Check 3: Test command exists
    testing = (spec_root / "05_testing.md").read_text()
    dollar_lines = [l for l in testing.split('\n') if l.strip().startswith('$')]
    results.append(InspectionResult(
        "test_command_exists",
        len(dollar_lines) == 1,
        f"Found {len(dollar_lines)} test command(s)" + (" (should be 1)" if len(dollar_lines) != 1 else "")
    ))

    # Check 4: No implementation code (full function bodies)
    has_impl = bool(re.search(r'def \w+\([^)]*\):\s*\n\s+[^#"\']', design))
    results.append(InspectionResult(
        "no_implementation_code",
        not has_impl,
        "No function implementations" if not has_impl else "Function implementations found (too detailed for L3)"
    ))

    return results

def inspect_l2(spec_root: Path) -> List[InspectionResult]:
    """Inspect L2 (Operations/Build) altitude requirements."""
    results = []

    # Check 1: File paths exact
    design = (spec_root / "04_design.md").read_text()
    path_pattern = r'[/\\][\w/\\]+\.\w+'
    paths = re.findall(path_pattern, design)
    results.append(InspectionResult(
        "file_paths_exact",
        len(paths) >= 1,
        f"Found {len(paths)} file paths"
    ))

    # Check 2: Function signatures
    has_signatures = "def " in design or "function " in design or "fn " in design
    results.append(InspectionResult(
        "function_signatures",
        has_signatures,
        "Function signatures found" if has_signatures else "No function signatures"
    ))

    # Check 3: Commands executable (check format only)
    rollout = (spec_root / "06_rollout.md").read_text()
    has_commands = "$" in rollout or "```bash" in rollout or "```shell" in rollout
    results.append(InspectionResult(
        "commands_present",
        has_commands,
        "Executable commands found" if has_commands else "No executable commands"
    ))

    return results

def calculate_score(results: List[InspectionResult]) -> Tuple[int, int, bool]:
    """Calculate pass score."""
    passed = sum(1 for r in results if r.passed)
    total = len(results)
    threshold = total - 1  # Allow 1 failure
    return passed, total, passed >= threshold
```

---

## 5. Inspection Report Format

When running altitude validation, output should be:

```
ALTITUDE INSPECTION: SPEC-XXX
Declared Altitude: L3 (Strategy/Design)
================================================================================

CHECK                     STATUS    REASON
─────────────────────────────────────────────────────────────────────────────────
components_defined        [PASS]    Found 4 component references
requirements_exist        [PASS]    Found 3 functional requirements
test_command_exists       [PASS]    Found 1 test command(s)
no_implementation_code    [PASS]    No function implementations
interfaces_described      [FAIL]    Component "Shaper" missing I/O description
file_structure_shown      [PASS]    Directory structure present
acceptance_criteria       [PASS]    All FRs have criteria

================================================================================
SCORE: 6/7 (threshold: 6/7)
RESULT: PASS

Note: 1 check failed but within tolerance.
Action: Consider adding I/O description for Shaper component.
```

---

## 6. Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ALTITUDE QUICK REFERENCE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  L4 (VISION)     "Look Far"     🛰️  Satellite                              │
│  ─────────────────────────────────────────────────────────────────────────  │
│  MUST HAVE: Vision, Problem narrative, Non-goals, Stakeholders             │
│  MUST NOT:  File paths, Code blocks, Implementation details                │
│  INSPECT:   Word count > 100, No .py/.js paths, No ``` code                │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  L3 (DESIGN)     "Look Forward" ✈️  Airplane                                │
│  ─────────────────────────────────────────────────────────────────────────  │
│  MUST HAVE: Components, FR-XXX requirements, Test command, Interfaces      │
│  MUST NOT:  Function implementations, Actual test code                     │
│  INSPECT:   2+ components, 1+ FR-XXX, Single $ command, No def bodies      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  L2 (BUILD)      "Look Around"  🚁  Drone                                   │
│  ─────────────────────────────────────────────────────────────────────────  │
│  MUST HAVE: Exact paths, Function signatures, Test files, Commands         │
│  MUST NOT:  (No restrictions - this is implementation level)               │
│  INSPECT:   Paths exist, Signatures present, Commands runnable             │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  L1 (EXECUTE)    "Look Here"    🚶  Street                                  │
│  ─────────────────────────────────────────────────────────────────────────  │
│  This is runtime - no spec pack needed, just execution and logs            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 7. Integration with Gates

### Gate G1.5: Altitude Depth Validation

```
Phase: After G1 (structure), Before G2 (syntax)

Input: spec_id, declared_altitude (from 08_commit.md)

Process:
  1. Load spec pack files
  2. Run inspect_l{altitude}() function
  3. Calculate score
  4. Compare to threshold

Output:
  PASS: Score meets threshold
  FAIL: category=SPEC_DEFECT, route to Phase1

Evidence: Inspection report saved to artifacts/{phase}/altitude_inspection.json
```

---

## Metadata

```yaml
framework_id: FMWK-102
name: Altitude Convention Standard
version: 1.0.0
status: draft
created: 2026-01-27
category: Governance
dependencies: [FMWK-101]
provides: [altitude_convention, inspection_criteria, validation_script]
ci_gate: required
```
