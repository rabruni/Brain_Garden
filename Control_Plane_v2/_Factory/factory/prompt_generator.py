"""Agent prompt generator (T-004)."""
from __future__ import annotations

from pathlib import Path

from factory.models import AgentPrompt, GenerationError, Handoff, ProductSpec


_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "prompt_template.md"
_CONTRACT_VERSION = "1.1.0"

_MANDATORY_RULES = [
    "ALL work goes in `Control_Plane_v2/_staging/`. NEVER write to the conflated repo tree.",
    "DTT: Design → Test → Then implement. Per-behavior TDD cycles.",
    "Archive creation: Use `packages.py:pack()` for ALL archives. NEVER use shell `tar`.",
    "Hash format: All SHA256 hashes in manifest.json MUST use `sha256:<64hex>` format (71 chars). Use `hashing.py:compute_sha256()`.",
    "Clean-room verification: Extract CP_BOOTSTRAP.tar.gz → run install.sh → install YOUR package → ALL gates must pass.",
    "Full regression: Run ALL staged package tests (not just yours). Report total count, pass/fail.",
    "Results file: Write RESULTS.md following the FULL template in BUILDER_HANDOFF_STANDARD.md.",
    "Registry updates: If your package introduces new frameworks or specs, update registry CSVs.",
    "CP_BOOTSTRAP rebuild: If added to bootstrap, rebuild and report SHA256.",
    "Built-in tools: Use `hashing.py:compute_sha256()` and `packages.py:pack()`. NEVER use raw hashlib or shell tar.",
]

_ADVERSARIAL_QUESTIONS = [
    "11. The Failure Mode: Which specific file/hash in your scope is the most likely culprit if a gate check fails?",
    "12. The Shortcut Check: Is there a Kernel tool you are tempted to skip in favor of a standard shell command? If yes, explain why you will NOT do that.",
    "13. The Semantic Audit: Identify one word in your current plan that is ambiguous according to the Lexicon of Precision and redefine it now.",
]


def _load_template() -> str:
    if not _TEMPLATE_PATH.exists():
        raise GenerationError(f"Prompt template not found: {_TEMPLATE_PATH}")
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


def _generate_verification_questions(
    handoff: Handoff, spec: ProductSpec
) -> list[str]:
    """Generate 10 verification questions from D2 scenarios and D4 contracts."""
    questions: list[str] = []

    # Q1-3: Scope
    questions.append(
        f"1. What is the scope of {handoff.task_id}? List the D2 scenarios you must satisfy: {', '.join(handoff.scenarios)}."
    )
    questions.append(
        f"2. What is this task NOT responsible for? Name at least one capability explicitly excluded."
    )
    questions.append(
        f"3. What D4 contracts does {handoff.task_id} implement? List them: {', '.join(handoff.contracts)}."
    )

    # Q4-6: Technical
    sc_map = {s.id: s for s in spec.specification.scenarios}
    tech_scenarios = [sc_map[sid] for sid in handoff.scenarios if sid in sc_map]
    if tech_scenarios:
        sc = tech_scenarios[0]
        questions.append(
            f"4. For scenario {sc.id}, what is the expected input format and output format?"
        )
    else:
        questions.append("4. What is the primary input and output format for this task?")

    questions.append(
        "5. What data model entities (D3) does this task create, modify, or consume?"
    )
    questions.append(
        "6. What error conditions must this task handle? List the relevant ERR contracts."
    )

    # Q7-8: Packaging
    questions.append(
        "7. What package ID will contain this task's output? What layer does it target?"
    )
    questions.append(
        "8. What dependencies does this package declare? List package IDs."
    )

    # Q9: Tests
    questions.append(
        f"9. How many test methods will you write for this task? (Minimum based on scope: "
        f"{len(handoff.scenarios)} scenarios × 2 = {len(handoff.scenarios) * 2}+)"
    )

    # Q10: Integration
    questions.append(
        "10. How does this task integrate with the rest of the pipeline? What component consumes its output?"
    )

    return questions


def _generate_expected_answers(
    handoff: Handoff, spec: ProductSpec, questions: list[str]
) -> list[str]:
    """Generate expected answers for the reviewer."""
    answers: list[str] = []
    sc_map = {s.id: s for s in spec.specification.scenarios}

    answers.append(f"A1: Scenarios: {', '.join(handoff.scenarios)}")
    answers.append(f"A2: Should exclude anything not in task {handoff.task_id}'s D8 scope.")
    answers.append(f"A3: Contracts: {', '.join(handoff.contracts)}")

    if handoff.scenarios:
        sc = sc_map.get(handoff.scenarios[0])
        if sc:
            answers.append(f"A4: Input per {sc.id}: {sc.given[:100]}. Output: {sc.then[:100]}")
        else:
            answers.append("A4: See D2 scenarios.")
    else:
        answers.append("A4: See D2 scenarios.")

    answers.append("A5: See D3 entities referenced by this task's scenarios.")
    answers.append(
        f"A6: Error contracts: "
        + ", ".join(c for c in handoff.contracts if c.startswith("ERR"))
    )
    answers.append(f"A7: Package: {spec.package_id}")
    answers.append("A8: See D7 dependency declarations.")
    answers.append(f"A9: Minimum {len(handoff.scenarios) * 2}+ tests.")
    answers.append("A10: See D8 dependency graph for downstream consumers.")

    # Adversarial expected answers
    answers.append("A11: The most fragile artifact is [agent identifies specific file/hash].")
    answers.append("A12: Agent should identify any temptation and explain why they will use kernel tools.")
    answers.append("A13: Agent identifies and redefines one ambiguous term.")

    return answers


def generate_prompts(
    handoffs: list[Handoff],
    spec: ProductSpec,
    output_dir: str | Path,
) -> list[AgentPrompt]:
    """Generate agent prompts from handoffs.

    One prompt per handoff following BUILDER_PROMPT_CONTRACT.md template.
    Writes prompt file + expected answers file (separate).
    """
    out_path = Path(output_dir)
    template = _load_template()
    prompts: list[AgentPrompt] = []

    for handoff in sorted(handoffs, key=lambda h: h.handoff_id):
        handoff_dir = out_path / handoff.handoff_id
        handoff_dir.mkdir(parents=True, exist_ok=True)

        questions = _generate_verification_questions(handoff, spec)
        expected = _generate_expected_answers(handoff, spec, questions)

        # Render template
        rendered = template.format_map({
            "handoff_id": handoff.handoff_id,
            "mission_oneliner": handoff.mission,
            "contract_version": _CONTRACT_VERSION,
            "handoff_path": handoff.output_path,
            "mandatory_rules": "\n".join(
                f"{i+1}. {rule}" for i, rule in enumerate(_MANDATORY_RULES)
            ),
            "verification_questions": "\n".join(questions),
            "adversarial_questions": "\n".join(_ADVERSARIAL_QUESTIONS),
        })

        # Write prompt file (agent-visible)
        prompt_path = handoff_dir / f"{handoff.handoff_id}_AGENT_PROMPT.md"
        prompt_path.write_text(rendered, encoding="utf-8")

        # Write expected answers (reviewer-only, separate file)
        answers_path = handoff_dir / f"{handoff.handoff_id}_EXPECTED_ANSWERS.md"
        answers_text = f"# Expected Answers: {handoff.handoff_id}\n\n"
        answers_text += "\n".join(expected)
        answers_path.write_text(answers_text, encoding="utf-8")

        prompt = AgentPrompt(
            handoff_id=handoff.handoff_id,
            contract_version=_CONTRACT_VERSION,
            mission_oneliner=handoff.mission,
            mandatory_rules=list(_MANDATORY_RULES),
            verification_questions=questions,
            adversarial_questions=list(_ADVERSARIAL_QUESTIONS),
            expected_answers=expected,
            prompt_text=rendered,
        )
        prompts.append(prompt)

    return prompts
