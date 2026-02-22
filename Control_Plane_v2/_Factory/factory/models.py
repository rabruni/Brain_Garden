"""Data models for the Dark Factory Orchestrator (D3 entities)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ParseError(Exception):
    """Raised when a D-document cannot be parsed."""


class ValidationError(Exception):
    """Raised when spec validation fails structurally."""


class GenerationError(Exception):
    """Raised when handoff or prompt generation fails."""


class DispatchError(Exception):
    """Raised when agent dispatch fails at the infrastructure level."""


# ---------------------------------------------------------------------------
# Per-document parsed representations
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Article:
    """A single D1 article."""
    name: str
    rule: str
    why: str = ""
    test: str = ""
    violations: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "rule": self.rule, "why": self.why,
                "test": self.test, "violations": self.violations}


@dataclass(frozen=True)
class BoundaryDefinitions:
    """D1 boundary definitions: ALWAYS / ASK FIRST / NEVER."""
    always: list[str] = field(default_factory=list)
    ask_first: list[str] = field(default_factory=list)
    never: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"always": list(self.always), "ask_first": list(self.ask_first),
                "never": list(self.never)}


@dataclass(frozen=True)
class ConstitutionDoc:
    """Parsed D1 constitution."""
    version: str
    articles: list[Article] = field(default_factory=list)
    boundaries: BoundaryDefinitions = field(default_factory=BoundaryDefinitions)

    def to_dict(self) -> dict[str, Any]:
        return {"version": self.version,
                "articles": [a.to_dict() for a in self.articles],
                "boundaries": self.boundaries.to_dict()}


@dataclass(frozen=True)
class Scenario:
    """A single D2 user scenario."""
    id: str
    title: str
    priority: str = ""
    source: str = ""
    given: str = ""
    when: str = ""
    then: str = ""
    testing_approach: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "priority": self.priority,
                "source": self.source, "given": self.given, "when": self.when,
                "then": self.then, "testing_approach": self.testing_approach}


@dataclass(frozen=True)
class SpecDoc:
    """Parsed D2 specification."""
    component_purpose: str = ""
    not_this: str = ""
    scenarios: list[Scenario] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"component_purpose": self.component_purpose,
                "not_this": self.not_this,
                "scenarios": [s.to_dict() for s in self.scenarios],
                "deferred": list(self.deferred),
                "success_criteria": list(self.success_criteria)}


@dataclass(frozen=True)
class EntityField:
    """A single field in a D3 entity."""
    name: str
    type: str
    required: bool = False
    description: str = ""
    constraints: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "type": self.type, "required": self.required,
                "description": self.description, "constraints": self.constraints}


@dataclass(frozen=True)
class Entity:
    """A single D3 entity."""
    id: str
    name: str
    scope: str = ""
    description: str = ""
    fields: list[EntityField] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "scope": self.scope,
                "description": self.description,
                "fields": [f.to_dict() for f in self.fields]}


@dataclass(frozen=True)
class DataModelDoc:
    """Parsed D3 data model."""
    entities: list[Entity] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"entities": [e.to_dict() for e in self.entities]}


@dataclass(frozen=True)
class Contract:
    """A single D4 contract (inbound, outbound, side-effect, or error)."""
    id: str
    name: str
    kind: str  # "inbound", "outbound", "side_effect", "error"
    scenarios: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "kind": self.kind,
                "scenarios": list(self.scenarios),
                "description": self.description}


@dataclass(frozen=True)
class ContractsDoc:
    """Parsed D4 contracts."""
    inbound: list[Contract] = field(default_factory=list)
    outbound: list[Contract] = field(default_factory=list)
    side_effects: list[Contract] = field(default_factory=list)
    errors: list[Contract] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"inbound": [c.to_dict() for c in self.inbound],
                "outbound": [c.to_dict() for c in self.outbound],
                "side_effects": [c.to_dict() for c in self.side_effects],
                "errors": [c.to_dict() for c in self.errors]}

    def all_ids(self) -> list[str]:
        """Return sorted list of all contract IDs."""
        ids: list[str] = []
        for contracts in (self.inbound, self.outbound, self.side_effects, self.errors):
            ids.extend(c.id for c in contracts)
        return sorted(ids)


@dataclass(frozen=True)
class ResearchQuestion:
    """A single D5 research question."""
    id: str
    question: str
    decision: str = ""
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "question": self.question,
                "decision": self.decision, "rationale": self.rationale}


@dataclass(frozen=True)
class ResearchDoc:
    """Parsed D5 research."""
    questions: list[ResearchQuestion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"questions": [q.to_dict() for q in self.questions]}


@dataclass(frozen=True)
class Gap:
    """A single D6 gap or clarification."""
    id: str
    title: str
    status: str  # OPEN, RESOLVED, ASSUMED
    category: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "status": self.status,
                "category": self.category, "description": self.description}


@dataclass(frozen=True)
class GapAnalysisDoc:
    """Parsed D6 gap analysis."""
    gaps: list[Gap] = field(default_factory=list)
    clarifications: list[Gap] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"gaps": [g.to_dict() for g in self.gaps],
                "clarifications": [c.to_dict() for c in self.clarifications]}


@dataclass(frozen=True)
class PlanDoc:
    """Parsed D7 plan."""
    summary: str = ""
    architecture: str = ""
    file_creation_order: str = ""
    testing_strategy: str = ""
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"summary": self.summary, "architecture": self.architecture,
                "file_creation_order": self.file_creation_order,
                "testing_strategy": self.testing_strategy}


@dataclass(frozen=True)
class Task:
    """A single D8 task."""
    id: str
    title: str
    phase: int = 0
    depends_on: list[str] = field(default_factory=list)
    scope: str = ""
    scenarios_satisfied: list[str] = field(default_factory=list)
    contracts_implemented: list[str] = field(default_factory=list)
    acceptance_criteria: str = ""
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "phase": self.phase,
                "depends_on": list(self.depends_on), "scope": self.scope,
                "scenarios_satisfied": list(self.scenarios_satisfied),
                "contracts_implemented": list(self.contracts_implemented),
                "acceptance_criteria": self.acceptance_criteria,
                "description": self.description}


@dataclass(frozen=True)
class TasksDoc:
    """Parsed D8 tasks."""
    tasks: list[Task] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"tasks": [t.to_dict() for t in self.tasks]}


@dataclass(frozen=True)
class HoldoutScenario:
    """A single D9 holdout scenario."""
    id: str
    title: str
    priority: str = ""
    validates: list[str] = field(default_factory=list)
    contracts: list[str] = field(default_factory=list)
    setup: str = ""
    execute: str = ""
    verify: str = ""
    cleanup: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "title": self.title, "priority": self.priority,
                "validates": list(self.validates),
                "contracts": list(self.contracts),
                "setup": self.setup, "execute": self.execute,
                "verify": self.verify, "cleanup": self.cleanup}


@dataclass(frozen=True)
class HoldoutDoc:
    """Parsed D9 holdout scenarios."""
    scenarios: list[HoldoutScenario] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"scenarios": [s.to_dict() for s in self.scenarios]}


@dataclass(frozen=True)
class AgentContextDoc:
    """Parsed D10 agent context."""
    commands: str = ""
    tool_rules: str = ""
    coding_conventions: str = ""
    raw_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"commands": self.commands, "tool_rules": self.tool_rules,
                "coding_conventions": self.coding_conventions}


# ---------------------------------------------------------------------------
# D3 Entity: E-001 ProductSpec
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProductSpec:
    """E-001: Parsed representation of a complete D1-D10 product spec."""
    spec_dir: str
    component_name: str
    package_id: str
    constitution: ConstitutionDoc
    specification: SpecDoc
    data_model: DataModelDoc
    contracts: ContractsDoc
    research: ResearchDoc
    gap_analysis: GapAnalysisDoc
    plan: PlanDoc
    tasks: TasksDoc
    holdouts: HoldoutDoc
    agent_context: AgentContextDoc

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_dir": self.spec_dir,
            "component_name": self.component_name,
            "package_id": self.package_id,
            "constitution": self.constitution.to_dict(),
            "specification": self.specification.to_dict(),
            "data_model": self.data_model.to_dict(),
            "contracts": self.contracts.to_dict(),
            "research": self.research.to_dict(),
            "gap_analysis": self.gap_analysis.to_dict(),
            "plan": self.plan.to_dict(),
            "tasks": self.tasks.to_dict(),
            "holdouts": self.holdouts.to_dict(),
            "agent_context": self.agent_context.to_dict(),
        }


# ---------------------------------------------------------------------------
# D3 Entity: E-002 ValidationResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CheckResult:
    """Individual validation check result."""
    check_name: str
    status: str  # PASS or FAIL
    message: str
    details: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"check_name": self.check_name, "status": self.status,
                             "message": self.message}
        if self.details:
            d["details"] = list(self.details)
        return d


@dataclass(frozen=True)
class ValidationResult:
    """E-002: Result of validating a product spec."""
    status: str  # PASS or FAIL
    spec_dir: str
    checks: list[CheckResult] = field(default_factory=list)
    component_name: str = ""
    summary: dict[str, int] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "status": self.status,
            "spec_dir": self.spec_dir,
            "checks": [c.to_dict() for c in self.checks],
        }
        if self.component_name:
            d["component_name"] = self.component_name
        d["summary"] = dict(self.summary) if self.summary else None
        return d


# ---------------------------------------------------------------------------
# D3 Entity: E-003 Handoff
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Handoff:
    """E-003: A generated handoff document."""
    handoff_id: str
    task_id: str
    mission: str
    scenarios: list[str]
    contracts: list[str]
    critical_constraints: list[str]
    architecture: str
    implementation_steps: list[str]
    package_plan: str
    test_plan: list[str]
    existing_code_refs: list[str]
    verification_commands: list[str]
    files_summary: str
    design_principles: list[str]
    output_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "task_id": self.task_id,
            "mission": self.mission,
            "scenarios": list(self.scenarios),
            "contracts": list(self.contracts),
            "critical_constraints": list(self.critical_constraints),
            "architecture": self.architecture,
            "implementation_steps": list(self.implementation_steps),
            "package_plan": self.package_plan,
            "test_plan": list(self.test_plan),
            "existing_code_refs": list(self.existing_code_refs),
            "verification_commands": list(self.verification_commands),
            "files_summary": self.files_summary,
            "design_principles": list(self.design_principles),
            "output_path": self.output_path,
        }


# ---------------------------------------------------------------------------
# D3 Entity: E-004 AgentPrompt
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AgentPrompt:
    """E-004: A generated agent prompt."""
    handoff_id: str
    contract_version: str
    mission_oneliner: str
    mandatory_rules: list[str]
    verification_questions: list[str]
    adversarial_questions: list[str]
    expected_answers: list[str]
    prompt_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "handoff_id": self.handoff_id,
            "contract_version": self.contract_version,
            "mission_oneliner": self.mission_oneliner,
            "mandatory_rules": list(self.mandatory_rules),
            "verification_questions": list(self.verification_questions),
            "adversarial_questions": list(self.adversarial_questions),
            "expected_answers": list(self.expected_answers),
            "prompt_text": self.prompt_text,
        }


# ---------------------------------------------------------------------------
# D3 Entity: E-005 DispatchRecord
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DispatchRecord:
    """E-005: Record of one handoff dispatch."""
    dispatch_id: str
    handoff_id: str
    task_id: str
    timestamp_dispatched: str
    status: str  # DISPATCHED, COMPLETED, FAILED, BLOCKED
    timestamp_completed: str = ""
    results_path: str = ""
    error: str = ""
    tokens_used: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "dispatch_id": self.dispatch_id,
            "handoff_id": self.handoff_id,
            "task_id": self.task_id,
            "timestamp_dispatched": self.timestamp_dispatched,
            "status": self.status,
        }
        if self.timestamp_completed:
            d["timestamp_completed"] = self.timestamp_completed
        if self.results_path:
            d["results_path"] = self.results_path
        if self.error:
            d["error"] = self.error
        if self.tokens_used is not None:
            d["tokens_used"] = self.tokens_used
        return d


# ---------------------------------------------------------------------------
# D3 Entity: E-006 HoldoutResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HoldoutResult:
    """E-006: Result of running one holdout scenario."""
    holdout_id: str
    priority: str
    status: str  # PASS, FAIL, ERROR
    validates_scenarios: list[str]
    validates_contracts: list[str]
    responsible_task: str
    actual_output: str = ""
    expected_output: str = ""
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "holdout_id": self.holdout_id,
            "priority": self.priority,
            "status": self.status,
            "validates_scenarios": list(self.validates_scenarios),
            "validates_contracts": list(self.validates_contracts),
            "responsible_task": self.responsible_task,
        }
        if self.actual_output:
            d["actual_output"] = self.actual_output
        if self.expected_output:
            d["expected_output"] = self.expected_output
        if self.error_message:
            d["error_message"] = self.error_message
        return d


# ---------------------------------------------------------------------------
# D3 Entity: E-007 FactoryReport
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FactoryReport:
    """E-007: Complete report of a factory run."""
    spec_dir: str
    component_name: str
    validation: ValidationResult
    dispatches: list[DispatchRecord]
    holdouts: list[HoldoutResult]
    verdict: str  # ACCEPT, REJECT, PARTIAL
    verdict_reason: str
    total_tokens: int
    total_duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "spec_dir": self.spec_dir,
            "component_name": self.component_name,
            "validation": self.validation.to_dict(),
            "dispatches": [d.to_dict() for d in self.dispatches],
            "holdouts": [h.to_dict() for h in self.holdouts],
            "verdict": self.verdict,
            "verdict_reason": self.verdict_reason,
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
