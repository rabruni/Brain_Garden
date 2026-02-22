"""Heading-based D1-D10 markdown parser (T-001)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from factory.models import (
    AgentContextDoc,
    Article,
    BoundaryDefinitions,
    ConstitutionDoc,
    Contract,
    ContractsDoc,
    DataModelDoc,
    Entity,
    EntityField,
    Gap,
    GapAnalysisDoc,
    HoldoutDoc,
    HoldoutScenario,
    ParseError,
    PlanDoc,
    ProductSpec,
    ResearchDoc,
    ResearchQuestion,
    Scenario,
    SpecDoc,
    Task,
    TasksDoc,
)

# ---------------------------------------------------------------------------
# Document file mapping
# ---------------------------------------------------------------------------

REQUIRED_DOCS: dict[str, str] = {
    "D1": "D1_CONSTITUTION.md",
    "D2": "D2_SPECIFICATION.md",
    "D3": "D3_DATA_MODEL.md",
    "D4": "D4_CONTRACTS.md",
    "D5": "D5_RESEARCH.md",
    "D6": "D6_GAP_ANALYSIS.md",
    "D7": "D7_PLAN.md",
    "D8": "D8_TASKS.md",
    "D9": "D9_HOLDOUT_SCENARIOS.md",
    "D10": "D10_AGENT_CONTEXT.md",
}


# ---------------------------------------------------------------------------
# Heading splitter
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


def _split_sections(text: str) -> list[tuple[int, str, str]]:
    """Split markdown into (level, heading_text, body) tuples."""
    matches = list(_HEADING_RE.finditer(text))
    sections: list[tuple[int, str, str]] = []
    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        sections.append((level, heading, body))
    return sections


# ---------------------------------------------------------------------------
# Field extractors
# ---------------------------------------------------------------------------

_BOLD_FIELD_RE = re.compile(r"\*\*(\w[\w\s/]*):\*\*\s*(.+)")
_METADATA_RE = re.compile(r"^\*\*(.+?):\*\*\s*(.+)$", re.MULTILINE)


def _extract_bold_fields(text: str) -> dict[str, str]:
    """Extract **Key:** Value fields from text."""
    fields: dict[str, str] = {}
    for m in _BOLD_FIELD_RE.finditer(text):
        fields[m.group(1).strip()] = m.group(2).strip()
    return fields


def _extract_metadata(text: str) -> dict[str, str]:
    """Extract top-level **Key:** Value metadata lines."""
    meta: dict[str, str] = {}
    for m in _METADATA_RE.finditer(text):
        meta[m.group(1).strip()] = m.group(2).strip()
    return meta


def _extract_list_items(text: str) -> list[str]:
    """Extract bullet/numbered list items from text."""
    items: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        m = re.match(r"^[-*+]\s+(.+)$", stripped)
        if m:
            items.append(m.group(1).strip())
            continue
        m = re.match(r"^\d+\.\s+(.+)$", stripped)
        if m:
            items.append(m.group(1).strip())
    return items


def _extract_ids(text: str, pattern: str) -> list[str]:
    """Extract IDs matching a regex pattern from text."""
    return sorted(set(re.findall(pattern, text)))


def _extract_code_block(text: str, lang: str = "") -> str:
    """Extract the first fenced code block from text, optionally matching language."""
    if lang:
        pat = re.compile(rf"```{re.escape(lang)}\s*\n(.*?)```", re.DOTALL)
    else:
        pat = re.compile(r"```\w*\s*\n(.*?)```", re.DOTALL)
    m = pat.search(text)
    return m.group(1).strip() if m else ""


def _find_section(sections: list[tuple[int, str, str]], heading_fragment: str,
                  level: int | None = None) -> str:
    """Find first section whose heading contains fragment (case-insensitive)."""
    frag = heading_fragment.lower()
    for lvl, heading, body in sections:
        if level is not None and lvl != level:
            continue
        if frag in heading.lower():
            return body
    return ""


def _find_all_sections(sections: list[tuple[int, str, str]], heading_fragment: str,
                       level: int | None = None) -> list[tuple[str, str]]:
    """Find all sections whose heading contains fragment. Returns (heading, body) pairs."""
    frag = heading_fragment.lower()
    results: list[tuple[str, str]] = []
    for lvl, heading, body in sections:
        if level is not None and lvl != level:
            continue
        if frag in heading.lower():
            results.append((heading, body))
    return results


# ---------------------------------------------------------------------------
# Per-document parsers
# ---------------------------------------------------------------------------

def _parse_d1(text: str) -> ConstitutionDoc:
    """Parse D1 Constitution."""
    meta = _extract_metadata(text)
    version = meta.get("Version", "")
    sections = _split_sections(text)

    # Articles
    articles: list[Article] = []
    for lvl, heading, body in sections:
        if lvl == 3 and heading.lower().startswith("article"):
            name = heading
            fields = _extract_bold_fields(body)
            articles.append(Article(
                name=name,
                rule=fields.get("Rule", ""),
                why=fields.get("Why", ""),
                test=fields.get("Test", ""),
                violations=fields.get("Violations", ""),
            ))

    # Boundaries
    always_body = _find_section(sections, "always")
    ask_body = _find_section(sections, "ask first")
    never_body = _find_section(sections, "never")
    boundaries = BoundaryDefinitions(
        always=_extract_list_items(always_body),
        ask_first=_extract_list_items(ask_body),
        never=_extract_list_items(never_body),
    )

    return ConstitutionDoc(version=version, articles=articles, boundaries=boundaries)


def _parse_d2(text: str) -> SpecDoc:
    """Parse D2 Specification."""
    sections = _split_sections(text)

    purpose = _find_section(sections, "component purpose")
    not_this = _find_section(sections, "what this component is not")

    # Scenarios: #### SC-NNN: Title
    scenarios: list[Scenario] = []
    sc_re = re.compile(r"(SC-\d+):\s*(.+)")
    for lvl, heading, body in sections:
        if lvl == 4:
            m = sc_re.search(heading)
            if m:
                sc_id = m.group(1)
                sc_title = m.group(2).strip()
                fields = _extract_bold_fields(body)
                # Extract GIVEN/WHEN/THEN
                given = ""
                when = ""
                then = ""
                for line in body.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("**GIVEN**"):
                        given = stripped.replace("**GIVEN**", "").strip()
                    elif stripped.startswith("**WHEN**"):
                        when = stripped.replace("**WHEN**", "").strip()
                    elif stripped.startswith("**THEN**"):
                        then = stripped.replace("**THEN**", "").strip()
                    elif stripped.startswith("**AND**") and then:
                        then += " " + stripped.replace("**AND**", "").strip()

                scenarios.append(Scenario(
                    id=sc_id,
                    title=sc_title,
                    priority=fields.get("Priority", ""),
                    source=fields.get("Source", ""),
                    given=given,
                    when=when,
                    then=then,
                    testing_approach=fields.get("Testing Approach", ""),
                ))

    # Deferred capabilities
    deferred: list[str] = []
    for lvl, heading, body in sections:
        if lvl == 4 and heading.startswith("DEF-"):
            deferred.append(heading)

    # Success criteria
    sc_body = _find_section(sections, "success criteria")
    success = _extract_list_items(sc_body)

    return SpecDoc(
        component_purpose=purpose,
        not_this=not_this,
        scenarios=scenarios,
        deferred=deferred,
        success_criteria=success,
    )


def _parse_d3(text: str) -> DataModelDoc:
    """Parse D3 Data Model."""
    sections = _split_sections(text)
    entities: list[Entity] = []

    entity_re = re.compile(r"(E-\d+):\s*(\w+)")
    for lvl, heading, body in sections:
        if lvl == 3:
            m = entity_re.search(heading)
            if m:
                eid = m.group(1)
                ename = m.group(2)
                fields_list = _extract_bold_fields(body)
                scope = fields_list.get("Scope", "")
                desc = fields_list.get("Description", "")

                # Extract table fields
                efields: list[EntityField] = []
                in_table = False
                for line in body.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("| Field"):
                        in_table = True
                        continue
                    if in_table and stripped.startswith("|---"):
                        continue
                    if in_table and stripped.startswith("|"):
                        cols = [c.strip() for c in stripped.split("|")[1:-1]]
                        if len(cols) >= 4:
                            efields.append(EntityField(
                                name=cols[0],
                                type=cols[1],
                                required=cols[2].lower() == "yes",
                                description=cols[3] if len(cols) > 3 else "",
                                constraints=cols[4] if len(cols) > 4 else "",
                            ))
                    elif in_table and not stripped.startswith("|"):
                        in_table = False

                entities.append(Entity(
                    id=eid, name=ename, scope=scope,
                    description=desc, fields=efields,
                ))

    return DataModelDoc(entities=entities)


def _parse_d4(text: str) -> ContractsDoc:
    """Parse D4 Contracts."""
    sections = _split_sections(text)

    def _parse_contract_group(kind: str, prefix: str) -> list[Contract]:
        contracts: list[Contract] = []
        pat = re.compile(rf"({prefix}-\d+):\s*(.+)")
        for lvl, heading, body in sections:
            if lvl == 4:
                m = pat.search(heading)
                if m:
                    cid = m.group(1)
                    cname = m.group(2).strip()
                    fields = _extract_bold_fields(body)
                    sc_text = fields.get("Scenarios", "")
                    sc_ids = _extract_ids(sc_text, r"SC-\d+")
                    contracts.append(Contract(
                        id=cid, name=cname, kind=kind,
                        scenarios=sc_ids, description=body[:200],
                    ))
        return contracts

    inbound = _parse_contract_group("inbound", "IN")
    outbound = _parse_contract_group("outbound", "OUT")
    side_effects = _parse_contract_group("side_effect", "SIDE")
    errors = _parse_contract_group("error", "ERR")

    return ContractsDoc(
        inbound=inbound, outbound=outbound,
        side_effects=side_effects, errors=errors,
    )


def _parse_d5(text: str) -> ResearchDoc:
    """Parse D5 Research."""
    sections = _split_sections(text)
    questions: list[ResearchQuestion] = []

    rq_re = re.compile(r"(RQ-\d+):\s*(.+)")
    for lvl, heading, body in sections:
        if lvl == 4:
            m = rq_re.search(heading)
            if m:
                qid = m.group(1)
                qtitle = m.group(2).strip()
                fields = _extract_bold_fields(body)
                questions.append(ResearchQuestion(
                    id=qid,
                    question=qtitle,
                    decision=fields.get("Decision", ""),
                    rationale=fields.get("Rationale", ""),
                ))

    return ResearchDoc(questions=questions)


def _parse_d6(text: str) -> GapAnalysisDoc:
    """Parse D6 Gap Analysis."""
    sections = _split_sections(text)
    gaps: list[Gap] = []
    clarifications: list[Gap] = []

    gap_re = re.compile(r"(GAP-\d+):\s*(.+)")
    clr_re = re.compile(r"(CLR-\d+):\s*(.+)")

    for lvl, heading, body in sections:
        if lvl == 4:
            m = gap_re.search(heading)
            if m:
                fields = _extract_bold_fields(body)
                # Status might be in heading or body
                status = ""
                status_match = re.search(r"\((\w+)\)", heading)
                if status_match:
                    status = status_match.group(1)
                if not status:
                    status = fields.get("Status", "RESOLVED")
                gaps.append(Gap(
                    id=m.group(1),
                    title=m.group(2).strip(),
                    status=status.upper(),
                    category=fields.get("Category", ""),
                    description=body[:300],
                ))

            m = clr_re.search(heading)
            if m:
                fields = _extract_bold_fields(body)
                status_raw = fields.get("Status", "")
                # Extract leading status word: "RESOLVED(..." -> "RESOLVED"
                status = re.match(r"(\w+)", status_raw).group(1).upper() if status_raw else "OPEN"
                clarifications.append(Gap(
                    id=m.group(1),
                    title=m.group(2).strip(),
                    status=status,
                    category=fields.get("Category", ""),
                    description=body[:300],
                ))

    return GapAnalysisDoc(gaps=gaps, clarifications=clarifications)


def _parse_d7(text: str) -> PlanDoc:
    """Parse D7 Plan."""
    sections = _split_sections(text)

    summary = _find_section(sections, "summary")
    arch_body = _find_section(sections, "architecture overview")
    if not arch_body:
        arch_body = _find_section(sections, "architecture")
    file_order = _find_section(sections, "file creation order")
    testing = _find_section(sections, "testing strategy")

    return PlanDoc(
        summary=summary,
        architecture=arch_body,
        file_creation_order=file_order,
        testing_strategy=testing,
        raw_text=text,
    )


def _parse_d8(text: str) -> TasksDoc:
    """Parse D8 Tasks."""
    sections = _split_sections(text)
    tasks: list[Task] = []

    task_re = re.compile(r"(T-\d+):\s*(.+)")
    for lvl, heading, body in sections:
        if lvl == 4:
            m = task_re.search(heading)
            if m:
                tid = m.group(1)
                ttitle = m.group(2).strip()
                fields = _extract_bold_fields(body)

                # Phase
                phase_str = fields.get("Phase", "0")
                phase_match = re.search(r"(\d+)", phase_str)
                phase = int(phase_match.group(1)) if phase_match else 0

                # Dependencies
                dep_raw = fields.get("Dependency", fields.get("Dependencies", ""))
                depends_on = _extract_ids(dep_raw, r"T-\d+") if dep_raw and dep_raw.lower() != "none" else []

                # Scenarios
                sc_raw = fields.get("Scenarios Satisfied", fields.get("Scenarios", ""))
                scenarios_satisfied = _extract_ids(sc_raw, r"SC-\d+")

                # Contracts
                ct_raw = fields.get("Contracts Implemented", fields.get("Contracts", ""))
                contracts_impl = _extract_ids(ct_raw, r"(?:IN|OUT|SIDE|ERR)-\d+")

                # Scope
                scope = fields.get("Scope", "")

                # Acceptance criteria: text after "**Acceptance Criteria:**"
                ac_match = re.search(r"\*\*Acceptance Criteria:\*\*\s*(.*?)(?=\n####|\Z)",
                                     body, re.DOTALL)
                acceptance = ac_match.group(1).strip() if ac_match else ""

                tasks.append(Task(
                    id=tid, title=ttitle, phase=phase,
                    depends_on=depends_on, scope=scope,
                    scenarios_satisfied=scenarios_satisfied,
                    contracts_implemented=contracts_impl,
                    acceptance_criteria=acceptance,
                    description=body,
                ))

    return TasksDoc(tasks=tasks)


def _parse_d9(text: str) -> HoldoutDoc:
    """Parse D9 Holdout Scenarios."""
    sections = _split_sections(text)
    scenarios: list[HoldoutScenario] = []

    hs_re = re.compile(r"(HS-\d+):\s*(.+)")
    for lvl, heading, body in sections:
        if lvl == 3:
            m = hs_re.search(heading)
            if m:
                hsid = m.group(1)
                hstitle = m.group(2).strip()
                fields = _extract_bold_fields(body)

                # Priority from YAML block
                priority = ""
                yaml_block = _extract_code_block(body, "yaml")
                if yaml_block:
                    pm = re.search(r"priority:\s*(\w+)", yaml_block)
                    if pm:
                        priority = pm.group(1)

                # Validates / Contracts
                validates_raw = fields.get("Validates", "")
                validates = _extract_ids(validates_raw, r"SC-\d+")
                contracts_raw = fields.get("Contracts", "")
                contracts = _extract_ids(contracts_raw, r"(?:IN|OUT|SIDE|ERR)-\d+")

                # Setup / Execute / Verify / Cleanup blocks
                setup = ""
                execute = ""
                verify = ""
                cleanup = ""
                sub_sections = _split_sections(body)

                # Also look for bold section markers **Setup:** etc.
                for sname in ["Setup", "Execute", "Verify", "Cleanup"]:
                    code = ""
                    # Check sub-headings
                    for _lvl, sh, sb in sub_sections:
                        if sname.lower() in sh.lower():
                            code = _extract_code_block(sb, "bash")
                            if not code:
                                code = sb
                            break
                    # If not found in sub-headings, look in body after bold marker
                    if not code:
                        marker_re = re.compile(
                            rf"\*\*{sname}:\*\*\s*\n(.*?)(?=\*\*(?:Setup|Execute|Verify|Cleanup):\*\*|\Z)",
                            re.DOTALL)
                        mm = marker_re.search(body)
                        if mm:
                            code = _extract_code_block(mm.group(1), "bash")
                            if not code:
                                code = mm.group(1).strip()

                    if sname == "Setup":
                        setup = code
                    elif sname == "Execute":
                        execute = code
                    elif sname == "Verify":
                        verify = code
                    elif sname == "Cleanup":
                        cleanup = code

                scenarios.append(HoldoutScenario(
                    id=hsid, title=hstitle, priority=priority,
                    validates=validates, contracts=contracts,
                    setup=setup, execute=execute,
                    verify=verify, cleanup=cleanup,
                ))

    return HoldoutDoc(scenarios=scenarios)


def _parse_d10(text: str) -> AgentContextDoc:
    """Parse D10 Agent Context."""
    sections = _split_sections(text)

    commands = _find_section(sections, "commands")
    if not commands:
        commands = _find_section(sections, "command")
    tool_rules = _find_section(sections, "tool rules")
    conventions = _find_section(sections, "coding conventions")
    if not conventions:
        conventions = _find_section(sections, "conventions")

    return AgentContextDoc(
        commands=commands,
        tool_rules=tool_rules,
        coding_conventions=conventions,
        raw_text=text,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(spec_dir: str | Path) -> ProductSpec:
    """Parse a directory of D1-D10 markdown files into a ProductSpec.

    Raises ParseError if required documents are missing or unparseable.
    """
    spec_path = Path(spec_dir)
    if not spec_path.is_dir():
        raise ParseError(f"Spec directory does not exist: {spec_dir}")

    # Discover files
    files: dict[str, Path] = {}
    missing: list[str] = []
    for key, filename in REQUIRED_DOCS.items():
        fpath = spec_path / filename
        if fpath.exists():
            files[key] = fpath
        else:
            missing.append(filename)

    if missing:
        raise ParseError(f"Missing required document(s): {', '.join(missing)}")

    # Read all files
    texts: dict[str, str] = {}
    for key, fpath in files.items():
        texts[key] = fpath.read_text(encoding="utf-8")

    # Extract metadata from D2
    d2_meta = _extract_metadata(texts["D2"])
    component_name = d2_meta.get("Component", "")
    package_id = d2_meta.get("Package ID", "")

    # Parse each document
    constitution = _parse_d1(texts["D1"])
    specification = _parse_d2(texts["D2"])
    data_model = _parse_d3(texts["D3"])
    contracts = _parse_d4(texts["D4"])
    research = _parse_d5(texts["D5"])
    gap_analysis = _parse_d6(texts["D6"])
    plan = _parse_d7(texts["D7"])
    tasks = _parse_d8(texts["D8"])
    holdouts = _parse_d9(texts["D9"])
    agent_context = _parse_d10(texts["D10"])

    return ProductSpec(
        spec_dir=str(spec_path),
        component_name=component_name,
        package_id=package_id,
        constitution=constitution,
        specification=specification,
        data_model=data_model,
        contracts=contracts,
        research=research,
        gap_analysis=gap_analysis,
        plan=plan,
        tasks=tasks,
        holdouts=holdouts,
        agent_context=agent_context,
    )
