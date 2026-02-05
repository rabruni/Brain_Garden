# Testing Strategy

## Unit Tests

### test_prompt_loader.py

| Test | Description |
|------|-------------|
| test_load_prompt_success | Load valid prompt |
| test_load_prompt_not_found | Missing prompt raises error |
| test_load_prompt_hash_mismatch | Tampered prompt raises error |
| test_load_prompt_invalid_id | Invalid ID format raises error |
| test_verify_hash_valid | Valid hash returns True |
| test_verify_hash_invalid | Invalid hash returns False |
| test_list_prompts_active | List active prompts only |
| test_list_prompts_all | List all prompts |

### test_stdlib_llm_governed.py

| Test | Description |
|------|-------------|
| test_complete_with_governed_prompt | Completion with valid prompt |
| test_complete_evidence_has_prompt_id | Evidence includes prompt_pack_id |
| test_complete_evidence_no_raw_content | Evidence excludes raw content |

## Integration Tests

| Test | Description |
|------|-------------|
| test_admin_llm_assisted_uses_governed | Admin agent uses governed prompts |
| test_router_llm_path_uses_governed | Router LLM path uses governed prompts |

## Security Tests

| Test | Description |
|------|-------------|
| test_no_secrets_in_prompts | Scan prompts for secrets |
| test_hash_verification_prevents_tampering | Modified prompts fail |
| test_ungoverned_prompt_rejected | Direct prompts rejected |

## Verification Commands

```bash
# Run all prompt tests
pytest tests/test_prompt_loader.py -v

# Verify no secrets in prompts
grep -r "API_KEY\|SECRET\|PASSWORD" governed_prompts/

# Check all prompts are registered
python3 -c "from lib.prompt_loader import verify_registry; verify_registry()"
```
