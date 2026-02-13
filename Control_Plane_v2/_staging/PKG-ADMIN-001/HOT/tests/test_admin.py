"""Tests for ADMIN config and entrypoint.

DTT: tests written before implementation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_staging = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(_staging / "PKG-ADMIN-001" / "HOT" / "admin"))

from main import build_session_host, load_admin_config, run_cli  # noqa: E402


def _write_admin_files(tmp_path: Path):
    cfg_dir = tmp_path / "HOT" / "config"
    tpl_dir = tmp_path / "HOT" / "attention_templates"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    tpl_dir.mkdir(parents=True, exist_ok=True)

    cfg = {
        "agent_id": "admin-001",
        "agent_class": "ADMIN",
        "framework_id": "FMWK-005",
        "tier": "hot",
        "system_prompt": "You are ADMIN",
        "attention": {
            "template_id": "ATT-ADMIN-001",
            "prompt_contract": {
                "contract_id": "PRC-ADMIN-001",
                "prompt_pack_id": "PRM-ADMIN-001",
                "boundary": {"max_tokens": 4096, "temperature": 0.0},
            },
        },
        "tools": [
            {
                "tool_id": "list_packages",
                "description": "List packages",
                "handler": "tools.list_packages",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
        "budget": {"session_token_limit": 1000, "turn_limit": 5, "timeout_seconds": 300},
        "permissions": {"read": ["HOT/*"], "write": ["HO2/*"], "forbidden": ["HOT/kernel/*"]},
    }
    tpl = {
        "template_id": "ATT-ADMIN-001",
        "version": "1.0.0",
        "description": "Admin template",
        "applies_to": {"agent_class": ["ADMIN"], "framework_id": ["FMWK-005"]},
        "pipeline": [{"stage": "tier_select", "type": "tier_select", "config": {"tiers": ["hot"]}}],
        "budget": {"max_context_tokens": 1000, "max_queries": 10, "timeout_ms": 5000},
        "fallback": {"on_timeout": "return_partial", "on_empty": "proceed_empty"},
    }

    cfg_path = cfg_dir / "admin_config.json"
    tpl_path = tpl_dir / "ATT-ADMIN-001.json"
    cfg_path.write_text(json.dumps(cfg))
    tpl_path.write_text(json.dumps(tpl))
    return cfg_path, tpl_path


class TestAdminConfig:
    def test_admin_config_valid_json(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        loaded = load_admin_config(cfg_path)
        assert loaded["agent_id"] == "admin-001"

    def test_admin_config_has_required_fields(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        loaded = load_admin_config(cfg_path)
        for key in ["agent_id", "agent_class", "tools", "system_prompt", "attention"]:
            assert key in loaded

    def test_admin_attention_template_valid(self, tmp_path: Path):
        _, tpl_path = _write_admin_files(tmp_path)
        tpl = json.loads(tpl_path.read_text())
        assert tpl["template_id"] == "ATT-ADMIN-001"
        assert isinstance(tpl["pipeline"], list)

    def test_admin_tools_have_schemas(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        loaded = load_admin_config(cfg_path)
        for tool in loaded["tools"]:
            assert "parameters" in tool
            assert tool["parameters"]["type"] == "object"


class TestAdminEntrypoint:
    def test_build_session_host(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        root = tmp_path
        host = build_session_host(root=root, config_path=cfg_path, dev_mode=True)
        assert host is not None

    def test_run_cli_creates_session(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        outputs = []
        prompts = iter(["exit"])

        code = run_cli(
            root=tmp_path,
            config_path=cfg_path,
            dev_mode=True,
            input_fn=lambda _p: next(prompts),
            output_fn=lambda s: outputs.append(s),
        )

        assert code == 0
        assert any("session" in line.lower() for line in outputs)

    def test_run_cli_processes_turn(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        prompts = iter(["hello", "exit"])
        outputs = []

        run_cli(
            root=tmp_path,
            config_path=cfg_path,
            dev_mode=True,
            input_fn=lambda _p: next(prompts),
            output_fn=lambda s: outputs.append(s),
        )

        assert any("assistant" in line.lower() for line in outputs)

    def test_run_cli_clean_shutdown(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        outputs = []

        code = run_cli(
            root=tmp_path,
            config_path=cfg_path,
            dev_mode=True,
            input_fn=lambda _p: "quit",
            output_fn=lambda s: outputs.append(s),
        )

        assert code == 0
        assert any("ended" in line.lower() for line in outputs)

    def test_missing_config_fails_fast(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_admin_config(tmp_path / "HOT" / "config" / "missing.json")

    def test_invalid_config_rejected(self, tmp_path: Path):
        p = tmp_path / "HOT" / "config"
        p.mkdir(parents=True, exist_ok=True)
        bad = p / "admin_config.json"
        bad.write_text("{}")
        with pytest.raises(ValueError, match="required"):
            load_admin_config(bad)
