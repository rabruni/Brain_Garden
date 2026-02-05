# LLM Agent Patterns for Control Plane
**Version**: 1.0
**Locked**: 2026-02-04

---

## Core Problem: Drift

Traditional LLM agents drift because:
- Context window compresses/summarizes → loses fidelity
- Model attention drifts → prioritizes wrong things
- Hallucination fills gaps → invents false memories

**Result**: Unreliable, inconsistent, unverifiable.

---

## Solution: Externalized Memory

```
Traditional:  Agent.memory["key"] = value    ← mutable, drifts
Control Plane: ledger.read("L-EXEC", turn=1) ← immutable, verified
```

Agents don't REMEMBER, they READ.

---

## Memory Tiers (HO Model)

### HO1: Fast Memory / Execution
```python
# Agent has NO memory of what it did
# Same inputs → same outputs (deterministic)
# Cannot drift because cannot remember
# Ledger is FOR OTHERS to read

def execute_ho1(query, context):
    result = process(query, context)
    ledger.write_exec(query, result)  # For others
    return result  # Forget immediately
```

### HO2: Slow Memory / Session
```python
# Agent READS session ledger for context
# Memory is EXTERNAL and VERIFIABLE

def execute_ho2(query, session_id):
    # Read previous context from ledger
    history = ledger.read_session(session_id)

    # Execute with context
    result = process(query, history)

    # Write to session ledger
    ledger.write_session(session_id, query, result)
    return result
```

### HO3: Higher Order / Learning
```python
# Patterns extracted from many sessions
# Wisdom accumulates in governed artifacts

def learn_ho3():
    all_sessions = ledger.read_all_sessions()
    patterns = extract_patterns(all_sessions)

    # Write insights for future use
    ledger.write_insights(patterns)
```

---

## One-Shot Pattern (KERNEL.semantic)

All KERNEL.semantic agents use this pattern:

```python
def kernel_semantic_call(prompt_id, input_data):
    # 1. Load registered prompt
    prompt = load_governed_prompt(prompt_id)

    # 2. Validate input against schema
    validate_json_schema(input_data, prompt.input_schema)

    # 3. Call LLM with strict controls
    response = llm.complete(
        prompt=prompt.template,
        input=json.dumps(input_data),
        output_format="json",
        max_tokens=prompt.max_tokens,
        temperature=0,  # Deterministic
    )

    # 4. Validate output against schema
    output = json.loads(response)
    validate_json_schema(output, prompt.output_schema)

    # 5. Log everything
    ledger.write({
        "prompt_id": prompt_id,
        "input_hash": hash_json(input_data),
        "output_hash": hash_json(output),
        "timestamp": now(),
    })

    # 6. Return (no state kept)
    return output
```

### Key Constraints

| Constraint | Why |
|------------|-----|
| One-shot only | No multi-turn = no drift accumulation |
| Strict JSON | Parseable, verifiable, schema-bound |
| Registered prompts | Governance over content |
| Logged I/O | Full audit trail |
| No human interaction | No prompt injection |
| Stateless | Memory in ledgers only |
| Temperature 0 | Deterministic outputs |

---

## ADMIN Agent Pattern

ADMIN agents are human-facing, so they use LLM more freely but still controlled:

```python
class AdminAgent:
    def __init__(self, root):
        self.root = root
        self.tools = AdminTools(root, capabilities)

    def handle_query(self, query, session):
        # 1. Log query to session ledger
        session.write_query(query)

        # 2. Load governed prompt
        prompt = load_governed_prompt("PRM-ADMIN-GENERAL-001")

        # 3. Build context from ledger reads
        context = self.gather_context(session)

        # 4. Call LLM with tool access
        response = self.llm_with_tools(query, context, prompt)

        # 5. Log response
        session.write_response(response)

        # 6. Log observations (breadcrumbs)
        for file_read in self.tools.files_accessed:
            self.log_observe(file_read)

        return response

    def llm_with_tools(self, query, context, prompt):
        # Tool loop with logging
        messages = [{"role": "user", "content": query}]

        for turn in range(MAX_TURNS):
            response = llm.complete(
                system=prompt.template.format(**context),
                messages=messages,
                tools=TOOL_DEFINITIONS,
            )

            if response.stop_reason == "end_turn":
                return response.text

            # Execute tools, log each
            for tool_use in response.tool_uses:
                result = self.tools.execute(tool_use)
                self.log_tool_use(tool_use, result)
                messages.append(tool_result(result))
```

---

## Resident Agent Pattern

Residents are most restricted:

```python
class ResidentAgent:
    def __init__(self, work_order):
        self.work_order = work_order
        self.scope = work_order.scope  # What we can access

    def execute(self, task):
        # 1. Verify task is in scope
        if not self.scope.allows(task):
            raise ScopeViolation(task)

        # 2. Declare inputs upfront
        inputs = self.declare_inputs(task)
        for inp in inputs:
            if not self.scope.allows_read(inp):
                raise ScopeViolation(inp)

        # 3. Execute (no memory of previous tasks)
        result = self.process(task, inputs)

        # 4. Log to L-EXEC
        ledger.write_exec({
            "work_order_id": self.work_order.id,
            "task": task,
            "inputs": [hash(i) for i in inputs],
            "output": hash(result),
        })

        # 5. Forget everything
        return result
```

---

## Turn Isolation

### Pre-Declaration (Residents)

```yaml
# Prompt header declares inputs BEFORE turn
declared_inputs:
  - file: requirements.md
    hash: sha256:abc123...
  - ledger_entry: L-EXEC#42
```

Violation if agent reads undeclared file.

### Post-Declaration (ADMIN)

```yaml
# ADMIN logs reads DURING/AFTER turn
observed_reads:
  - file: ledger/governance.jsonl
    hash: sha256:...
    timestamp: ...
```

Violation if read is not logged.

---

## Prompt Governance

All LLM prompts must be registered:

```json
{
  "prompt_id": "PRM-ROUTER-001",
  "title": "Query Router",
  "hash": "sha256:abc...",
  "input_schema": "schemas/router_input.json",
  "output_schema": "schemas/router_output.json",
  "max_tokens": 256,
  "temperature": 0,
  "registered_at": "2026-02-04T00:00:00Z"
}
```

Gate G-PROMPT validates:
- Prompt exists in registry
- Hash matches current content
- Schema is valid
- Token limits are reasonable

---

## Anti-Drift Checklist

| Check | How |
|-------|-----|
| No persistent memory | State in ledgers only |
| Same inputs = same outputs | Temperature 0, stateless |
| Audit trail | All I/O logged with hashes |
| Verifiable | Can replay any turn |
| Bounded | Max tokens, max turns |
| Schema-validated | Strict JSON in/out |
| Registered prompts | No ad-hoc prompts |

---

## Error Handling

```python
def safe_llm_call(prompt_id, input_data):
    try:
        return kernel_semantic_call(prompt_id, input_data)
    except SchemaValidationError as e:
        ledger.write_error(prompt_id, "schema_error", str(e))
        raise
    except LLMError as e:
        ledger.write_error(prompt_id, "llm_error", str(e))
        raise
    except Exception as e:
        ledger.write_error(prompt_id, "unknown_error", str(e))
        raise
```

All errors logged. No silent failures.

---

## Performance Benefits

| Aspect | Traditional | HO Model |
|--------|-------------|----------|
| Reliability | Degrades | Constant |
| Consistency | Contradicts self | Cannot contradict |
| Verifiability | Trust me | Check ledger |
| Recoverability | Start over | Replay from ledger |
| Correctability | Maybe sticks | Persists in ledger |
| Auditability | Black box | Full trace |

---

## Summary

1. **Externalize memory** to ledgers (don't trust context)
2. **One-shot** for KERNEL.semantic (no multi-turn)
3. **Strict JSON** for all LLM I/O
4. **Register prompts** with hashes
5. **Log everything** with hashes
6. **Temperature 0** for determinism
7. **Pre/post-declare** all reads
8. **Stateless execution** at HO1

This is how you get reliable LLM agents without drift.
