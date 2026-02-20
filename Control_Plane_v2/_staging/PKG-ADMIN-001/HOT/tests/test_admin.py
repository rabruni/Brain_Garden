"""Tests for ADMIN config and entrypoint.

DTT: tests written before implementation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Dual-context path detection: installed root vs staging packages
# Probe: kernel/ledger_client.py exists ONLY in installed root (merged from PKG-KERNEL-001).
# It does NOT exist in PKG-ADMIN-001's own HOT, so this probe is unambiguous.
# NOTE: Do NOT use admin/main.py as probe — it exists in BOTH contexts (ambiguous).
_HERE = Path(__file__).resolve().parent
_HOT = _HERE.parent

if (_HOT / "kernel" / "ledger_client.py").exists():
    # Installed layout — all packages merged under HOT/
    _ROOT = _HOT.parent  # install root (parent of HOT/)
    sys.path.insert(0, str(_HOT / "admin"))
    for p in [_HOT / "kernel", _HOT / "scripts", _HOT,
              _ROOT / "HO1" / "kernel", _ROOT / "HO2" / "kernel"]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
else:
    # Staging layout — admin code in sibling package
    _STAGING_ROOT = _HERE.parents[2]
    sys.path.insert(0, str(_STAGING_ROOT / "PKG-ADMIN-001" / "HOT" / "admin"))
    for p in [
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT" / "kernel",
        _STAGING_ROOT / "PKG-KERNEL-001" / "HOT",
        _STAGING_ROOT / "PKG-BOOT-MATERIALIZE-001" / "HOT" / "scripts",
        _STAGING_ROOT / "PKG-HO1-EXECUTOR-001" / "HO1" / "kernel",
        _STAGING_ROOT / "PKG-HO2-SUPERVISOR-001" / "HO2" / "kernel",
    ]:
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

import main as admin_main  # noqa: E402
from main import build_session_host_v2, load_admin_config, run_cli  # noqa: E402


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


def _write_layout_json(tmp_path: Path) -> Path:
    # Reuse the same dual-context detection as the module-level path setup.
    # _HOT is already resolved at module level via kernel/ledger_client.py probe.
    if (_HOT / "config" / "layout.json").exists():
        layout_src = _HOT / "config" / "layout.json"
    else:
        layout_src = _HERE.parents[2] / "PKG-LAYOUT-002" / "HOT" / "config" / "layout.json"
    cfg_dir = tmp_path / "HOT" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    dst = cfg_dir / "layout.json"
    dst.write_text(layout_src.read_text())
    return dst


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
    def test_build_session_host_v2(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        root = tmp_path
        shell = build_session_host_v2(root=root, config_path=cfg_path, dev_mode=True)
        assert shell is not None

    def test_run_cli_creates_session(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        outputs = []
        prompts = iter(["/exit"])

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
        prompts = iter(["hello", "/exit"])
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
            input_fn=lambda _p: "/exit",
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


class TestBootMaterializeDevBypass:
    def test_boot_materialize_runs_under_pristine_bypass(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        _write_layout_json(tmp_path)
        outputs = []

        code = run_cli(
            root=tmp_path,
            config_path=cfg_path,
            dev_mode=True,
            input_fn=lambda _p: "/exit",
            output_fn=lambda s: outputs.append(s),
        )

        assert code == 0
        assert (tmp_path / "HO2" / "ledger").exists()

    def test_boot_materialize_called_before_session_host_v2(self, tmp_path: Path, monkeypatch):
        _write_admin_files(tmp_path)
        _write_layout_json(tmp_path)
        order = []

        class DummyShell:
            def run(self):
                order.append("run")

        import boot_materialize as boot_materialize_mod

        def fake_boot(root):
            assert root == tmp_path
            order.append("boot")
            return 0

        def fake_build(root, config_path, dev_mode=False, input_fn=input, output_fn=print):
            order.append("build")
            return DummyShell()

        monkeypatch.setattr(boot_materialize_mod, "boot_materialize", fake_boot)
        monkeypatch.setattr(admin_main, "build_session_host_v2", fake_build)

        code = run_cli(
            root=tmp_path,
            config_path=tmp_path / "HOT" / "config" / "admin_config.json",
            dev_mode=True,
            input_fn=lambda _p: "/exit",
            output_fn=lambda _s: None,
        )

        assert code == 0
        assert order == ["boot", "build", "run"]

    def test_pristine_patch_stopped_on_exit(self, tmp_path: Path, monkeypatch):
        _write_admin_files(tmp_path)
        _write_layout_json(tmp_path)
        observations = {}

        import boot_materialize as boot_materialize_mod
        import kernel.pristine as pristine_mod

        original = pristine_mod.assert_append_only

        class DummyShell:
            def run(self):
                pass

        def fake_boot(_root):
            observations["during_boot_is_patched"] = pristine_mod.assert_append_only is not original
            return 0

        def fake_build(root, config_path, dev_mode=False, input_fn=input, output_fn=print):
            return DummyShell()

        monkeypatch.setattr(boot_materialize_mod, "boot_materialize", fake_boot)
        monkeypatch.setattr(admin_main, "build_session_host_v2", fake_build)

        code = run_cli(
            root=tmp_path,
            config_path=tmp_path / "HOT" / "config" / "admin_config.json",
            dev_mode=True,
            input_fn=lambda _p: "/exit",
            output_fn=lambda _s: None,
        )

        assert code == 0
        assert observations["during_boot_is_patched"] is True
        assert pristine_mod.assert_append_only is original


# Tool-Use Wiring Test (1) — HANDOFF-21
class TestToolUseWiring:
    def test_ho2_config_receives_tool_ids(self, tmp_path: Path):
        """build_session_host_v2() passes tool IDs from admin_config.json to HO2Config."""
        cfg_path, _ = _write_admin_files(tmp_path)
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        # Access HO2 supervisor through the shell chain: shell._host -> session_host._ho2
        ho2 = shell._host._ho2
        assert "list_packages" in ho2._config.tools_allowed


class TestQueryLedgerEnrichment:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _seed_governance_entry(self, tmp_path: Path, reason: str):
        from ledger_client import LedgerClient, LedgerEntry

        ledger_path = tmp_path / "HOT" / "ledger" / "governance.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = LedgerClient(ledger_path=ledger_path)
        with patch("kernel.pristine.assert_append_only", return_value=None):
            ledger.write(
                LedgerEntry(
                    event_type="TURN_RECORDED",
                    submission_id="SES-TEST0001",
                    decision="RECORDED",
                    reason=reason,
                    metadata={"alpha": 1, "beta": 2},
                )
            )

    def _query(self, tmp_path: Path):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        return dispatcher.tools["query_ledger"]({"max_entries": 10})

    def test_query_ledger_returns_event_type(self, tmp_path: Path):
        self._seed_governance_entry(tmp_path, "ok")
        result = self._query(tmp_path)
        assert result["entries"][0]["event_type"] == "TURN_RECORDED"

    def test_query_ledger_returns_timestamp(self, tmp_path: Path):
        self._seed_governance_entry(tmp_path, "ok")
        result = self._query(tmp_path)
        assert isinstance(result["entries"][0]["timestamp"], str)
        assert "T" in result["entries"][0]["timestamp"]

    def test_query_ledger_returns_submission_id(self, tmp_path: Path):
        self._seed_governance_entry(tmp_path, "ok")
        result = self._query(tmp_path)
        assert result["entries"][0]["submission_id"] == "SES-TEST0001"

    def test_query_ledger_returns_metadata_keys(self, tmp_path: Path):
        self._seed_governance_entry(tmp_path, "ok")
        result = self._query(tmp_path)
        assert result["entries"][0]["metadata_keys"] == ["alpha", "beta"]

    def test_query_ledger_reason_not_truncated(self, tmp_path: Path):
        self._seed_governance_entry(tmp_path, "x" * 300)
        result = self._query(tmp_path)
        assert len(result["entries"][0]["reason"]) == 300

    def test_query_ledger_returns_metadata_values(self, tmp_path: Path):
        self._seed_governance_entry(tmp_path, "ok")
        result = self._query(tmp_path)
        assert result["entries"][0]["metadata"] == {"alpha": 1, "beta": 2}


class TestQueryLedgerSelection:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _seed_entry(self, tmp_path: Path, rel_ledger_path: str, event_type: str):
        from ledger_client import LedgerClient, LedgerEntry

        ledger_path = tmp_path / rel_ledger_path
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = LedgerClient(ledger_path=ledger_path)
        with patch("kernel.pristine.assert_append_only", return_value=None):
            ledger.write(
                LedgerEntry(
                    event_type=event_type,
                    submission_id="SES-LEDGER001",
                    decision="RECORDED",
                    reason=f"{event_type} event",
                    metadata={"source": rel_ledger_path},
                )
            )

    def _query(self, tmp_path: Path, **args):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        return dispatcher.tools["query_ledger"](args)

    def test_query_ledger_default_governance(self, tmp_path: Path):
        self._seed_entry(tmp_path, "HOT/ledger/governance.jsonl", "HOT_EVENT")
        result = self._query(tmp_path, max_entries=10)
        assert result["status"] == "ok"
        assert result["source"] == "governance"
        assert result["entries"][0]["event_type"] == "HOT_EVENT"

    def test_query_ledger_ho2m(self, tmp_path: Path):
        self._seed_entry(tmp_path, "HO2/ledger/ho2m.jsonl", "TURN_RECORDED")
        result = self._query(tmp_path, ledger="ho2m", event_type="TURN_RECORDED", max_entries=10)
        assert result["status"] == "ok"
        assert result["source"] == "ho2m"
        assert result["entries"][0]["event_type"] == "TURN_RECORDED"

    def test_query_ledger_ho1m(self, tmp_path: Path):
        self._seed_entry(tmp_path, "HO1/ledger/ho1m.jsonl", "LLM_CALL")
        result = self._query(tmp_path, ledger="ho1m", event_type="LLM_CALL", max_entries=10)
        assert result["status"] == "ok"
        assert result["source"] == "ho1m"
        assert result["entries"][0]["event_type"] == "LLM_CALL"

    def test_query_ledger_invalid_source(self, tmp_path: Path):
        result = self._query(tmp_path, ledger="bogus")
        assert result["status"] == "error"
        assert "Unknown ledger" in result["error"]

    def test_query_ledger_returns_source_field(self, tmp_path: Path):
        self._seed_entry(tmp_path, "HOT/ledger/governance.jsonl", "ANY")
        result = self._query(tmp_path, max_entries=10)
        assert result["source"] == "governance"


class TestListFilesTool:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _list_files(self, tmp_path: Path, **args):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        return dispatcher.tools["list_files"](args)

    def test_list_files_returns_directory_contents(self, tmp_path: Path):
        (tmp_path / "HOT" / "kernel").mkdir(parents=True, exist_ok=True)
        (tmp_path / "HOT" / "kernel" / "a.py").write_text("print('a')\n")
        (tmp_path / "HOT" / "kernel" / "b.json").write_text("{}\n")
        result = self._list_files(tmp_path, path="HOT/kernel", max_depth=3, glob="*")
        assert result["status"] == "ok"
        paths = [f["path"] for f in result["files"]]
        assert "HOT/kernel/a.py" in paths
        assert "HOT/kernel/b.json" in paths

    def test_list_files_respects_max_depth(self, tmp_path: Path):
        (tmp_path / "HOT" / "kernel" / "nested").mkdir(parents=True, exist_ok=True)
        (tmp_path / "HOT" / "kernel" / "root.py").write_text("print('root')\n")
        (tmp_path / "HOT" / "kernel" / "nested" / "child.py").write_text("print('child')\n")
        result = self._list_files(tmp_path, path="HOT/kernel", max_depth=1, glob="*.py")
        assert result["status"] == "ok"
        paths = [f["path"] for f in result["files"]]
        assert "HOT/kernel/root.py" in paths
        assert "HOT/kernel/nested/child.py" not in paths

    def test_list_files_glob_filter(self, tmp_path: Path):
        (tmp_path / "HOT" / "kernel").mkdir(parents=True, exist_ok=True)
        (tmp_path / "HOT" / "kernel" / "one.py").write_text("print('1')\n")
        (tmp_path / "HOT" / "kernel" / "two.json").write_text("{}\n")
        result = self._list_files(tmp_path, path="HOT/kernel", max_depth=3, glob="*.py")
        assert result["status"] == "ok"
        paths = [f["path"] for f in result["files"] if f["type"] == "file"]
        assert "HOT/kernel/one.py" in paths
        assert "HOT/kernel/two.json" not in paths

    def test_list_files_escapes_root_blocked(self, tmp_path: Path):
        result = self._list_files(tmp_path, path="../../", max_depth=3, glob="*")
        assert result["status"] == "error"
        assert "escapes root" in result["error"]

    def test_list_files_nonexistent_dir(self, tmp_path: Path):
        result = self._list_files(tmp_path, path="HOT/missing", max_depth=3, glob="*")
        assert result["status"] == "error"
        assert "directory not found" in result["error"]

    def test_list_files_handles_symlink_root(self, tmp_path: Path):
        real_root = tmp_path / "real_root"
        link_root = tmp_path / "link_root"
        (real_root / "HOT" / "kernel").mkdir(parents=True, exist_ok=True)
        (real_root / "HOT" / "kernel" / "x.py").write_text("print('x')\n")
        link_root.symlink_to(real_root, target_is_directory=True)

        result = self._list_files(link_root, path="HOT/kernel", max_depth=3, glob="*.py")
        assert result["status"] == "ok"
        paths = [f["path"] for f in result["files"] if f["type"] == "file"]
        assert "HOT/kernel/x.py" in paths

    def test_list_files_in_admin_config(self):
        cfg_path = Path(admin_main.__file__).resolve().parents[1] / "config" / "admin_config.json"
        cfg = json.loads(cfg_path.read_text())
        tool_ids = [t.get("tool_id") for t in cfg.get("tools", [])]
        assert "list_files" in tool_ids


class TestBudgetWiring26A:
    def _write_budget_fields(self, cfg_path: Path):
        cfg = json.loads(cfg_path.read_text())
        cfg["budget"].update({
            "classify_budget": 3333,
            "synthesize_budget": 88888,
            "followup_min_remaining": 777,
            "budget_mode": "warn",
        })
        cfg_path.write_text(json.dumps(cfg))

    def test_budget_config_fields_passed_to_ho2(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        self._write_budget_fields(cfg_path)

        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2_cfg = shell._host._ho2._config

        assert ho2_cfg.classify_budget == 3333
        assert ho2_cfg.synthesize_budget == 88888
        assert ho2_cfg.followup_min_remaining == 777
        assert ho2_cfg.budget_mode == "warn"

    def test_budget_mode_passed_to_gateway(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        self._write_budget_fields(cfg_path)

        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        assert shell._host._gateway._budget_mode == "warn"

    def test_budget_mode_passed_to_ho1(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        self._write_budget_fields(cfg_path)

        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        assert shell._host._ho2._ho1.config["budget_mode"] == "warn"
        assert shell._host._ho2._ho1.config["followup_min_remaining"] == 777


class TestListSessions:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _seed_ho2m(self, tmp_path: Path, event_type: str, session_id: str, metadata: dict):
        from ledger_client import LedgerClient, LedgerEntry

        ledger_path = tmp_path / "HO2" / "ledger" / "ho2m.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = LedgerClient(ledger_path=ledger_path)
        with patch("kernel.pristine.assert_append_only", return_value=None):
            ledger.write(
                LedgerEntry(
                    event_type=event_type,
                    submission_id=session_id,
                    decision=event_type,
                    reason=f"{event_type} for {session_id}",
                    metadata=metadata,
                )
            )

    def _list_sessions(self, tmp_path: Path, **args):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        return dispatcher.tools["list_sessions"](args)

    def test_list_sessions_returns_sessions(self, tmp_path: Path):
        self._seed_ho2m(tmp_path, "SESSION_START", "SES-A0000001", {"provenance": {"session_id": "SES-A0000001"}})
        self._seed_ho2m(tmp_path, "TURN_RECORDED", "SES-A0000001", {"turn_number": 1, "user_message": "hello", "response": "hi"})
        self._seed_ho2m(tmp_path, "SESSION_END", "SES-A0000001", {"turn_count": 1})

        self._seed_ho2m(tmp_path, "SESSION_START", "SES-A0000002", {"provenance": {"session_id": "SES-A0000002"}})
        self._seed_ho2m(tmp_path, "TURN_RECORDED", "SES-A0000002", {"turn_number": 1, "user_message": "status?", "response": "ok"})
        self._seed_ho2m(tmp_path, "SESSION_END", "SES-A0000002", {"turn_count": 1})

        result = self._list_sessions(tmp_path, limit=20, offset=0)
        assert result["status"] == "ok"
        assert result["count"] == 2
        ids = {s["session_id"] for s in result["sessions"]}
        assert ids == {"SES-A0000001", "SES-A0000002"}

    def test_list_sessions_includes_turn_count(self, tmp_path: Path):
        sid = "SES-TURN0001"
        self._seed_ho2m(tmp_path, "SESSION_START", sid, {"provenance": {"session_id": sid}})
        self._seed_ho2m(tmp_path, "TURN_RECORDED", sid, {"turn_number": 1, "user_message": "a", "response": "b"})
        self._seed_ho2m(tmp_path, "TURN_RECORDED", sid, {"turn_number": 2, "user_message": "c", "response": "d"})
        self._seed_ho2m(tmp_path, "TURN_RECORDED", sid, {"turn_number": 3, "user_message": "e", "response": "f"})
        self._seed_ho2m(tmp_path, "SESSION_END", sid, {"turn_count": 3})

        result = self._list_sessions(tmp_path)
        assert result["sessions"][0]["turn_count"] == 3

    def test_list_sessions_status_completed(self, tmp_path: Path):
        sid = "SES-COMPLETE1"
        self._seed_ho2m(tmp_path, "SESSION_START", sid, {"provenance": {"session_id": sid}})
        self._seed_ho2m(tmp_path, "SESSION_END", sid, {"turn_count": 0})
        result = self._list_sessions(tmp_path)
        assert result["sessions"][0]["status"] == "completed"

    def test_list_sessions_status_active(self, tmp_path: Path):
        sid = "SES-ACTIVE01"
        self._seed_ho2m(tmp_path, "SESSION_START", sid, {"provenance": {"session_id": sid}})
        result = self._list_sessions(tmp_path)
        assert result["sessions"][0]["status"] == "active"

    def test_list_sessions_pagination(self, tmp_path: Path):
        for i in range(5):
            sid = f"SES-PAGE{i:04d}"
            self._seed_ho2m(tmp_path, "SESSION_START", sid, {"provenance": {"session_id": sid}})
            self._seed_ho2m(tmp_path, "SESSION_END", sid, {"turn_count": 0})
        result = self._list_sessions(tmp_path, limit=2, offset=2)
        assert result["count"] == 5
        assert len(result["sessions"]) == 2

    def test_list_sessions_first_message_preview(self, tmp_path: Path):
        sid = "SES-PREVIEW1"
        self._seed_ho2m(tmp_path, "SESSION_START", sid, {"provenance": {"session_id": sid}})
        self._seed_ho2m(tmp_path, "TURN_RECORDED", sid, {"turn_number": 1, "user_message": "hello world", "response": "hi"})
        self._seed_ho2m(tmp_path, "SESSION_END", sid, {"turn_count": 1})
        result = self._list_sessions(tmp_path)
        assert result["sessions"][0]["first_user_message"] == "hello world"


class TestSessionOverview:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _seed(self, tmp_path: Path, ledger_rel: str, event_type: str, submission_id: str, metadata: dict, reason: str = ""):
        from ledger_client import LedgerClient, LedgerEntry

        ledger_path = tmp_path / ledger_rel
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = LedgerClient(ledger_path=ledger_path)
        with patch("kernel.pristine.assert_append_only", return_value=None):
            ledger.write(
                LedgerEntry(
                    event_type=event_type,
                    submission_id=submission_id,
                    decision=event_type,
                    reason=reason or f"{event_type} reason",
                    metadata=metadata,
                )
            )

    def _overview(self, tmp_path: Path, session_id: str, **extra):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        args = {"session_id": session_id}
        args.update(extra)
        return dispatcher.tools["session_overview"](args)

    def _seed_session_common(self, tmp_path: Path, sid: str):
        self._seed(
            tmp_path, "HO2/ledger/ho2m.jsonl", "SESSION_START", sid,
            {"provenance": {"session_id": sid}},
        )
        self._seed(
            tmp_path, "HO2/ledger/ho2m.jsonl", "TURN_RECORDED", sid,
            {"provenance": {"session_id": sid}, "turn_number": 1, "user_message": "what frameworks are installed?", "response": "checking"},
        )
        self._seed(
            tmp_path, "HO2/ledger/ho2m.jsonl", "TURN_RECORDED", sid,
            {"provenance": {"session_id": sid}, "turn_number": 2, "user_message": "show ledger events", "response": "done"},
        )
        self._seed(
            tmp_path, "HO2/ledger/ho2m.jsonl", "SESSION_END", sid,
            {"provenance": {"session_id": sid}, "turn_count": 2},
        )
        self._seed(
            tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", f"WO-{sid}-001",
            {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-001"}, "wo_type": "classify"},
        )
        self._seed(
            tmp_path, "HO2/ledger/ho2m.jsonl", "WO_PLANNED", f"WO-{sid}-002",
            {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-002"}, "wo_type": "synthesize"},
        )
        self._seed(
            tmp_path, "HO1/ledger/ho1m.jsonl", "LLM_CALL", f"WO-{sid}-001",
            {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-001"}, "input_tokens": 10, "output_tokens": 5},
        )
        self._seed(
            tmp_path, "HO1/ledger/ho1m.jsonl", "TOOL_CALL", f"WO-{sid}-002",
            {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-002"}, "tool_id": "list_packages", "status": "ok"},
        )
        self._seed(
            tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-SYNTHESIZE-001",
            {"session_id": sid, "work_order_id": f"WO-{sid}-002", "input_tokens": 7, "output_tokens": 3, "prompt": "p", "response": "r"},
        )

    def test_overview_human_summary(self, tmp_path: Path):
        sid = "SES-OVERVIEW1"
        self._seed_session_common(tmp_path, sid)
        result = self._overview(tmp_path, sid)
        assert result["status"] == "ok"
        assert isinstance(result["summary"]["about"], str)
        assert "frameworks" in result["summary"]["about"].lower()

    def test_overview_about_field_deterministic(self, tmp_path: Path):
        sid = "SES-OVERVIEW2"
        self._seed_session_common(tmp_path, sid)
        r1 = self._overview(tmp_path, sid)
        r2 = self._overview(tmp_path, sid)
        assert r1["summary"]["about"] == r2["summary"]["about"]

    def test_overview_includes_errors(self, tmp_path: Path):
        sid = "SES-OVERVIEW3"
        self._seed_session_common(tmp_path, sid)
        self._seed(
            tmp_path, "HO1/ledger/ho1m.jsonl", "WO_FAILED", f"WO-{sid}-009",
            {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-009"}},
            reason="budget_exhausted: Token budget exhausted",
        )
        result = self._overview(tmp_path, sid)
        assert len(result["summary"]["errors"]) >= 1

    def test_overview_token_totals(self, tmp_path: Path):
        sid = "SES-OVERVIEW4"
        self._seed_session_common(tmp_path, sid)
        result = self._overview(tmp_path, sid)
        assert result["diagnostics"]["tokens"]["grand_total"] == 25

    def test_overview_tool_counts(self, tmp_path: Path):
        sid = "SES-OVERVIEW5"
        self._seed_session_common(tmp_path, sid)
        self._seed(
            tmp_path, "HO1/ledger/ho1m.jsonl", "TOOL_CALL", f"WO-{sid}-003",
            {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-003"}, "tool_id": "list_packages", "status": "ok"},
        )
        result = self._overview(tmp_path, sid)
        assert result["diagnostics"]["tools"]["total_calls"] >= 2
        assert result["diagnostics"]["tools"]["by_tool"]["list_packages"]["called"] >= 2

    def test_overview_wo_by_state(self, tmp_path: Path):
        sid = "SES-OVERVIEW6"
        self._seed_session_common(tmp_path, sid)
        self._seed(
            tmp_path, "HO1/ledger/ho1m.jsonl", "WO_COMPLETED", f"WO-{sid}-010",
            {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-010"}},
        )
        self._seed(
            tmp_path, "HO1/ledger/ho1m.jsonl", "WO_FAILED", f"WO-{sid}-011",
            {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-011"}},
            reason="failed",
        )
        result = self._overview(tmp_path, sid)
        assert result["diagnostics"]["work_orders"]["by_state"]["completed"] >= 1
        assert result["diagnostics"]["work_orders"]["by_state"]["failed"] >= 1

    def test_overview_unknown_session(self, tmp_path: Path):
        result = self._overview(tmp_path, "SES-NOPE000")
        assert result["status"] == "error"


class TestReconstructSession:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _seed(self, tmp_path: Path, ledger_rel: str, event_type: str, submission_id: str, metadata: dict, timestamp: str):
        from ledger_client import LedgerClient, LedgerEntry

        ledger_path = tmp_path / ledger_rel
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = LedgerClient(ledger_path=ledger_path)
        with patch("kernel.pristine.assert_append_only", return_value=None):
            ledger.write(
                LedgerEntry(
                    event_type=event_type,
                    submission_id=submission_id,
                    decision=event_type,
                    reason=f"{event_type} reason",
                    metadata=metadata,
                    timestamp=timestamp,
                )
            )

    def _reconstruct(self, tmp_path: Path, session_id: str, **extra):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        args = {"session_id": session_id}
        args.update(extra)
        return dispatcher.tools["reconstruct_session"](args)

    def test_reconstruct_chronological_order(self, tmp_path: Path):
        sid = "SES-RC000001"
        self._seed(tmp_path, "HO2/ledger/ho2m.jsonl", "TURN_RECORDED", sid, {"provenance": {"session_id": sid}}, "2026-02-17T10:00:02+00:00")
        self._seed(tmp_path, "HO1/ledger/ho1m.jsonl", "TOOL_CALL", f"WO-{sid}-001", {"provenance": {"session_id": sid, "work_order_id": f"WO-{sid}-001"}}, "2026-02-17T10:00:03+00:00")
        self._seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-SYNTH", {"session_id": sid, "work_order_id": f"WO-{sid}-001"}, "2026-02-17T10:00:01+00:00")
        result = self._reconstruct(tmp_path, sid, verbosity="compact")
        stamps = [e["timestamp"] for e in result["timeline"]]
        assert stamps == sorted(stamps)

    def test_reconstruct_includes_source(self, tmp_path: Path):
        sid = "SES-RC000002"
        self._seed(tmp_path, "HO2/ledger/ho2m.jsonl", "SESSION_START", sid, {"provenance": {"session_id": sid}}, "2026-02-17T10:00:00+00:00")
        result = self._reconstruct(tmp_path, sid)
        assert result["timeline"][0]["source"] in {"ho2m", "ho1m", "governance"}

    def test_reconstruct_compact_mode(self, tmp_path: Path):
        sid = "SES-RC000003"
        self._seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-SYNTH", {"session_id": sid, "prompt": "PROMPT", "response": "RESPONSE"}, "2026-02-17T10:00:00+00:00")
        result = self._reconstruct(tmp_path, sid, verbosity="compact")
        payload = result["timeline"][0]["payload"]
        assert "prompt" not in payload
        assert "response" not in payload

    def test_reconstruct_full_mode(self, tmp_path: Path):
        sid = "SES-RC000004"
        self._seed(tmp_path, "HOT/ledger/governance.jsonl", "EXCHANGE", "PRC-SYNTH", {"session_id": sid, "prompt": "PROMPT", "response": "RESPONSE"}, "2026-02-17T10:00:00+00:00")
        result = self._reconstruct(tmp_path, sid, verbosity="full", include_prompts=True)
        payload = result["timeline"][0]["payload"]
        assert payload["prompt"] == "PROMPT"
        assert payload["response"] == "RESPONSE"

    def test_reconstruct_pagination(self, tmp_path: Path):
        sid = "SES-RC000005"
        for i in range(50):
            self._seed(
                tmp_path,
                "HO2/ledger/ho2m.jsonl",
                "TURN_RECORDED",
                sid,
                {"provenance": {"session_id": sid}, "turn_number": i + 1, "user_message": f"m{i}", "response": f"r{i}"},
                f"2026-02-17T10:00:{i:02d}+00:00",
            )
        result = self._reconstruct(tmp_path, sid, limit=10, offset=5)
        assert result["event_count"] == 50
        assert result["returned"] == 10

    def test_reconstruct_max_bytes_cap(self, tmp_path: Path):
        sid = "SES-RC000006"
        for i in range(20):
            self._seed(
                tmp_path,
                "HO2/ledger/ho2m.jsonl",
                "TURN_RECORDED",
                sid,
                {"provenance": {"session_id": sid}, "turn_number": i + 1, "user_message": "x" * 200, "response": "y" * 200},
                f"2026-02-17T10:01:{i:02d}+00:00",
            )
        result = self._reconstruct(tmp_path, sid, verbosity="full", include_prompts=True, max_bytes=600)
        assert result["truncated"] is True
        assert result["returned"] < result["event_count"]


class TestQueryLedgerFull:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _seed(self, tmp_path: Path, event_type: str, metadata: dict):
        from ledger_client import LedgerClient, LedgerEntry

        ledger_path = tmp_path / "HOT" / "ledger" / "governance.jsonl"
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = LedgerClient(ledger_path=ledger_path)
        with patch("kernel.pristine.assert_append_only", return_value=None):
            ledger.write(
                LedgerEntry(
                    event_type=event_type,
                    submission_id="SUB-001",
                    decision=event_type,
                    reason=f"{event_type} reason",
                    metadata=metadata,
                )
            )

    def _query(self, tmp_path: Path, **args):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        return dispatcher.tools["query_ledger_full"](args)

    def test_full_returns_metadata(self, tmp_path: Path):
        self._seed(tmp_path, "EXCHANGE", {"alpha": 1, "beta": {"nested": True}})
        result = self._query(tmp_path, ledger="governance", event_type="EXCHANGE", limit=5, offset=0)
        assert result["status"] == "ok"
        assert result["entries"][0]["metadata"] == {"alpha": 1, "beta": {"nested": True}}

    def test_full_pagination(self, tmp_path: Path):
        for i in range(20):
            self._seed(tmp_path, "EXCHANGE", {"idx": i})
        result = self._query(tmp_path, ledger="governance", event_type="EXCHANGE", limit=3, offset=5)
        assert result["count"] == 20
        assert len(result["entries"]) == 3

    def test_full_default_governance(self, tmp_path: Path):
        self._seed(tmp_path, "TURN_RECORDED", {"x": 1})
        result = self._query(tmp_path, event_type="TURN_RECORDED", limit=5, offset=0)
        assert result["source"] == "governance"


class TestGrepJsonl:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _seed(self, tmp_path: Path, ledger_rel: str, reason: str):
        from ledger_client import LedgerClient, LedgerEntry

        ledger_path = tmp_path / ledger_rel
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        ledger = LedgerClient(ledger_path=ledger_path)
        with patch("kernel.pristine.assert_append_only", return_value=None):
            ledger.write(
                LedgerEntry(
                    event_type="WO_FAILED",
                    submission_id="SUB-001",
                    decision="FAILED",
                    reason=reason,
                    metadata={"info": "x"},
                )
            )

    def _grep(self, tmp_path: Path, **args):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        return dispatcher.tools["grep_jsonl"](args)

    def test_grep_finds_matching_lines(self, tmp_path: Path):
        self._seed(tmp_path, "HO2/ledger/ho2m.jsonl", "budget_exhausted: only 10 tokens")
        self._seed(tmp_path, "HO2/ledger/ho2m.jsonl", "ok")
        self._seed(tmp_path, "HO2/ledger/ho2m.jsonl", "budget_exhausted: follow-up denied")
        result = self._grep(tmp_path, ledger="ho2m", pattern="budget_exhausted", limit=20, offset=0)
        assert result["status"] == "ok"
        assert result["count"] == 2
        assert len(result["entries"]) == 2
        assert result["entries"][0]["line_number"] >= 1

    def test_grep_returns_raw_json(self, tmp_path: Path):
        self._seed(tmp_path, "HOT/ledger/governance.jsonl", "budget_exhausted")
        result = self._grep(tmp_path, ledger="governance", pattern="budget_exhausted", limit=10, offset=0)
        assert result["entries"][0]["raw"].startswith("{")
        assert "budget_exhausted" in result["entries"][0]["raw"]

    def test_grep_invalid_ledger(self, tmp_path: Path):
        result = self._grep(tmp_path, ledger="bogus", pattern="x", limit=10, offset=0)
        assert result["status"] == "error"

    def test_grep_no_matches(self, tmp_path: Path):
        self._seed(tmp_path, "HO1/ledger/ho1m.jsonl", "all good")
        result = self._grep(tmp_path, ledger="ho1m", pattern="budget_exhausted", limit=10, offset=0)
        assert result["status"] == "ok"
        assert result["count"] == 0
        assert result["entries"] == []


class TestForensicToolsInConfig:
    def test_all_forensic_tools_in_config(self):
        cfg_path = Path(admin_main.__file__).resolve().parents[1] / "config" / "admin_config.json"
        cfg = json.loads(cfg_path.read_text())
        tool_ids = {t.get("tool_id") for t in cfg.get("tools", [])}
        expected = {
            "list_sessions",
            "session_overview",
            "reconstruct_session",
            "query_ledger_full",
            "grep_jsonl",
            "trace_prompt_journey",
        }
        assert expected.issubset(tool_ids)

    def test_trace_prompt_journey_registered(self, tmp_path: Path):
        class _CaptureDispatcher:
            def __init__(self):
                self.tools = {}

            def register_tool(self, name, handler):
                self.tools[name] = handler

        dispatcher = _CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)
        assert "trace_prompt_journey" in dispatcher.tools


# ====================================================================
# HANDOFF-27: Dev Tool Suite Tests
# ====================================================================

import os  # noqa: E402


def _write_admin_files_with_profile(tmp_path: Path, tool_profile: str | None = None):
    """Create admin config files, optionally with tool_profile."""
    cfg_path, tpl_path = _write_admin_files(tmp_path)
    if tool_profile is not None:
        cfg = json.loads(cfg_path.read_text())
        cfg["tool_profile"] = tool_profile
        cfg_path.write_text(json.dumps(cfg))
    return cfg_path, tpl_path


def _setup_dev_tools(tmp_path: Path, forbidden=None):
    """Register dev tools against a capture dispatcher and return handler dict."""
    from main import _register_dev_tools

    class _Dispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler, schema=None):
            self.tools[name] = handler

    d = _Dispatcher()
    permissions = {"forbidden": forbidden or ["HOT/kernel/*", "HOT/scripts/*"]}
    _register_dev_tools(d, root=tmp_path, permissions=permissions)
    return d.tools


class TestDualGate:
    """Tests for the dual gate mechanism (tool_profile + env var)."""

    def test_dev_tools_registered_when_both_gates_pass(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("CP_ADMIN_ENABLE_RISKY_TOOLS", "1")
        cfg_path, _ = _write_admin_files_with_profile(tmp_path, "development")
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        for tool_id in ["write_file_dev", "edit_file_dev", "grep_dev", "run_shell_dev"]:
            assert tool_id in ho2._config.tools_allowed

    def test_dev_tools_not_registered_without_env_var(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("CP_ADMIN_ENABLE_RISKY_TOOLS", raising=False)
        cfg_path, _ = _write_admin_files_with_profile(tmp_path, "development")
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        for tool_id in ["write_file_dev", "edit_file_dev", "grep_dev", "run_shell_dev"]:
            assert tool_id not in ho2._config.tools_allowed

    def test_dev_tools_not_registered_without_config(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("CP_ADMIN_ENABLE_RISKY_TOOLS", "1")
        cfg_path, _ = _write_admin_files_with_profile(tmp_path, "production")
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        for tool_id in ["write_file_dev", "edit_file_dev", "grep_dev", "run_shell_dev"]:
            assert tool_id not in ho2._config.tools_allowed

    def test_dev_tools_not_registered_default_profile(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("CP_ADMIN_ENABLE_RISKY_TOOLS", "1")
        cfg_path, _ = _write_admin_files(tmp_path)  # no tool_profile field
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        for tool_id in ["write_file_dev", "edit_file_dev", "grep_dev", "run_shell_dev"]:
            assert tool_id not in ho2._config.tools_allowed

    def test_existing_tools_always_registered(self, tmp_path: Path, monkeypatch):
        monkeypatch.delenv("CP_ADMIN_ENABLE_RISKY_TOOLS", raising=False)
        cfg_path, _ = _write_admin_files(tmp_path)
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        assert "list_packages" in ho2._config.tools_allowed

    def test_dev_tools_coexist_with_core_tools(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("CP_ADMIN_ENABLE_RISKY_TOOLS", "1")
        cfg_path, _ = _write_admin_files_with_profile(tmp_path, "development")
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        # 1 core tool from _write_admin_files + 4 dev tools = 5 total
        assert "list_packages" in ho2._config.tools_allowed
        assert "write_file_dev" in ho2._config.tools_allowed
        assert len(ho2._config.tools_allowed) == 5


class TestWriteFileDev:
    def _get_handler(self, tmp_path):
        return _setup_dev_tools(tmp_path)["write_file_dev"]

    def test_write_file_creates_new(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"path": "test.txt", "content": "hello"})
        assert result["status"] == "ok"
        assert (tmp_path / "test.txt").read_text() == "hello"
        assert result["bytes_written"] == 5

    def test_write_file_overwrites(self, tmp_path: Path):
        (tmp_path / "existing.txt").write_text("old content")
        handler = self._get_handler(tmp_path)
        result = handler({"path": "existing.txt", "content": "new"})
        assert result["status"] == "ok"
        assert (tmp_path / "existing.txt").read_text() == "new"
        assert result["bytes_written"] == 3

    def test_write_file_creates_dirs(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"path": "deep/nested/file.txt", "content": "hello", "create_dirs": True})
        assert result["status"] == "ok"
        assert result["created_dirs"] is True
        assert (tmp_path / "deep" / "nested" / "file.txt").read_text() == "hello"

    def test_write_file_blocks_traversal(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"path": "../../etc/passwd", "content": "hack"})
        assert result["status"] == "error"
        assert "escapes root" in result["error"]

    def test_write_file_blocks_forbidden(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"path": "HOT/kernel/test.py", "content": "hack"})
        assert result["status"] == "error"
        assert "forbidden" in result["error"]

    def test_write_file_rejects_oversized(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"path": "big.txt", "content": "x" * 1_000_001})
        assert result["status"] == "error"
        assert "1MB" in result["error"]


class TestEditFileDev:
    def _get_handler(self, tmp_path):
        return _setup_dev_tools(tmp_path)["edit_file_dev"]

    def test_edit_file_replaces_unique(self, tmp_path: Path):
        (tmp_path / "target.py").write_text("def old_name():\n    pass\n")
        handler = self._get_handler(tmp_path)
        result = handler({"path": "target.py", "old_string": "old_name", "new_string": "new_name"})
        assert result["status"] == "ok"
        assert result["replacements"] == 1
        assert "new_name" in (tmp_path / "target.py").read_text()

    def test_edit_file_replaces_all(self, tmp_path: Path):
        (tmp_path / "target.py").write_text("foo\nfoo\nfoo\n")
        handler = self._get_handler(tmp_path)
        result = handler({"path": "target.py", "old_string": "foo", "new_string": "bar", "replace_all": True})
        assert result["status"] == "ok"
        assert result["replacements"] == 3
        assert (tmp_path / "target.py").read_text() == "bar\nbar\nbar\n"

    def test_edit_file_not_found(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"path": "missing.py", "old_string": "x", "new_string": "y"})
        assert result["status"] == "error"
        assert "file not found" in result["error"]

    def test_edit_file_old_string_missing(self, tmp_path: Path):
        (tmp_path / "target.py").write_text("hello world\n")
        handler = self._get_handler(tmp_path)
        result = handler({"path": "target.py", "old_string": "NONEXISTENT", "new_string": "y"})
        assert result["status"] == "error"
        assert "not found in file" in result["error"]

    def test_edit_file_ambiguous_without_replace_all(self, tmp_path: Path):
        (tmp_path / "target.py").write_text("aa\naa\n")
        handler = self._get_handler(tmp_path)
        result = handler({"path": "target.py", "old_string": "aa", "new_string": "bb"})
        assert result["status"] == "error"
        assert "found 2 times" in result["error"]


class TestGrepDev:
    def _get_handler(self, tmp_path):
        return _setup_dev_tools(tmp_path)["grep_dev"]

    def test_grep_finds_matches(self, tmp_path: Path):
        (tmp_path / "a.py").write_text("def handle_turn():\n    pass\n")
        (tmp_path / "b.py").write_text("def handle_turn():\n    pass\n")
        handler = self._get_handler(tmp_path)
        result = handler({"pattern": "def handle_turn"})
        assert result["status"] == "ok"
        assert result["match_count"] >= 2

    def test_grep_with_context(self, tmp_path: Path):
        (tmp_path / "c.py").write_text("line1\ndef target():\nline3\n")
        handler = self._get_handler(tmp_path)
        result = handler({"pattern": "def target", "path": "c.py", "context_lines": 1})
        assert result["status"] == "ok"
        assert len(result["results"]) == 1
        assert len(result["results"][0]["context_before"]) > 0

    def test_grep_respects_glob(self, tmp_path: Path):
        (tmp_path / "code.py").write_text("match_here\n")
        (tmp_path / "data.txt").write_text("match_here\n")
        handler = self._get_handler(tmp_path)
        result = handler({"pattern": "match_here", "glob": "*.py"})
        assert result["status"] == "ok"
        files = [r["file"] for r in result["results"]]
        assert any("code.py" in f for f in files)
        assert not any("data.txt" in f for f in files)

    def test_grep_invalid_regex(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"pattern": "[invalid"})
        assert result["status"] == "error"
        assert "invalid regex" in result["error"]

    def test_grep_blocks_traversal(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"pattern": "test", "path": "../../"})
        assert result["status"] == "error"
        assert "escapes root" in result["error"]


class TestRunShellDev:
    def _get_handler(self, tmp_path):
        return _setup_dev_tools(tmp_path)["run_shell_dev"]

    def test_run_shell_success(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"command": "echo hello"})
        assert result["status"] == "ok"
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]
        assert result["timed_out"] is False

    def test_run_shell_captures_stderr(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"command": "echo error >&2"})
        assert result["status"] == "ok"
        assert "error" in result["stderr"]

    def test_run_shell_timeout(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"command": "sleep 999", "timeout": 1})
        assert result["status"] == "ok"
        assert result["timed_out"] is True
        assert result["exit_code"] == -1

    def test_run_shell_cwd(self, tmp_path: Path):
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        handler = self._get_handler(tmp_path)
        result = handler({"command": "pwd", "cwd": "subdir"})
        assert result["status"] == "ok"
        assert "subdir" in result["stdout"]

    def test_run_shell_cwd_traversal(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"command": "echo hi", "cwd": "../../"})
        assert result["status"] == "error"
        assert "escapes root" in result["error"]

    def test_run_shell_truncates_output(self, tmp_path: Path):
        handler = self._get_handler(tmp_path)
        result = handler({"command": "python3 -c \"print('x' * 60000)\""})
        assert result["status"] == "ok"
        assert "TRUNCATED" in result["stdout"]


class TestAdminReliability29P:
    class _CaptureDispatcher:
        def __init__(self):
            self.tools = {}

        def register_tool(self, name, handler):
            self.tools[name] = handler

    def _write_router_fields(self, cfg_path: Path):
        cfg = json.loads(cfg_path.read_text())
        cfg["router"] = {
            "llm_timeout_ms": 45000,
            "llm_max_retries": 2,
            "llm_retry_backoff_ms": 125,
        }
        cfg["tools"].extend([
            {
                "tool_id": "show_runtime_config",
                "description": "Show effective runtime config",
                "handler": "tools.show_runtime_config",
                "parameters": {"type": "object", "properties": {}},
            },
            {
                "tool_id": "list_tuning_files",
                "description": "List tuning files",
                "handler": "tools.list_tuning_files",
                "parameters": {"type": "object", "properties": {}},
            },
        ])
        cfg_path.write_text(json.dumps(cfg))

    def test_show_runtime_config_tool_returns_effective_values(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        self._write_router_fields(cfg_path)

        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(
            dispatcher,
            root=tmp_path,
            runtime_config={
                "provider_id": "anthropic",
                "model_id": "claude-sonnet-4-5-20250929",
                "llm_timeout_ms": 45000,
                "llm_max_retries": 2,
                "llm_retry_backoff_ms": 125,
                "budget_mode": "warn",
                "session_token_limit": 1000,
                "classify_budget": 2000,
                "synthesize_budget": 16000,
                "tool_profile": "production",
                "enabled_tool_ids": ["show_runtime_config", "list_tuning_files"],
            },
        )

        result = dispatcher.tools["show_runtime_config"]({})
        assert result["status"] == "ok"
        assert result["runtime"]["llm_timeout_ms"] == 45000
        assert result["runtime"]["llm_max_retries"] == 2
        assert result["runtime"]["llm_retry_backoff_ms"] == 125

    def test_list_tuning_files_tool_returns_expected_paths(self, tmp_path: Path):
        dispatcher = self._CaptureDispatcher()
        admin_main._register_admin_tools(dispatcher, root=tmp_path)

        result = dispatcher.tools["list_tuning_files"]({})
        assert result["status"] == "ok"
        paths = set(result["files"])
        assert "HOT/config/admin_config.json" in paths
        assert "HO1/contracts/synthesize.json" in paths
        assert "HO1/prompt_packs/PRM-SYNTHESIZE-001.txt" in paths

    def test_tools_present_in_admin_config_and_tools_allowed(self):
        cfg_path = Path(admin_main.__file__).resolve().parents[1] / "config" / "admin_config.json"
        cfg = json.loads(cfg_path.read_text())
        tool_ids = {t.get("tool_id") for t in cfg.get("tools", [])}
        assert "show_runtime_config" in tool_ids
        assert "list_tuning_files" in tool_ids

    def test_router_config_wired_from_admin_config(self, tmp_path: Path, monkeypatch):
        cfg_path, _ = _write_admin_files(tmp_path)
        self._write_router_fields(cfg_path)

        anthropic_path = (
            Path(admin_main.__file__).resolve().parents[3]
            / "PKG-ANTHROPIC-PROVIDER-001"
            / "HOT"
            / "kernel"
        )
        provider_path = (
            Path(admin_main.__file__).resolve().parents[3]
            / "PKG-LLM-GATEWAY-001"
            / "HOT"
            / "kernel"
        )
        if str(anthropic_path) not in sys.path:
            sys.path.insert(0, str(anthropic_path))
        if str(provider_path) not in sys.path:
            sys.path.insert(0, str(provider_path))
        import anthropic_provider

        class DummyAnthropicProvider:
            provider_id = "anthropic"

            def send(self, **kwargs):
                from provider import ProviderResponse
                return ProviderResponse(
                    content="ok",
                    model=kwargs.get("model_id", "dummy"),
                    input_tokens=1,
                    output_tokens=1,
                    request_id="req-dummy",
                    provider_id="anthropic",
                )

        monkeypatch.setattr(anthropic_provider, "AnthropicProvider", DummyAnthropicProvider)

        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        gateway_cfg = shell._host._gateway._config
        assert gateway_cfg.default_timeout_ms == 45000
        assert gateway_cfg.max_retries == 2
        assert gateway_cfg.retry_backoff_ms == 125


def test_synthesize_prompt_contains_grounding_rules():
    here = Path(__file__).resolve()
    candidates = [
        # Staging layout
        here.parents[3] / "PKG-HO1-EXECUTOR-001" / "HO1" / "prompt_packs" / "PRM-SYNTHESIZE-001.txt",
        # Installed clean-room layout
        here.parents[2] / "HO1" / "prompt_packs" / "PRM-SYNTHESIZE-001.txt",
    ]
    prompt_path = next((p for p in candidates if p.exists()), candidates[0])
    text = prompt_path.read_text()
    assert "Do not claim to have read ledgers, files, or code" in text
    assert "If evidence is missing" in text


# ====================================================================
# HANDOFF-31A1: HO3Memory Wiring Tests
# ====================================================================


def _write_admin_files_with_ho3(tmp_path: Path, ho3_enabled=True):
    """Like _write_admin_files but with ho3 config section."""
    cfg_path, tpl_path = _write_admin_files(tmp_path)
    cfg = json.loads(cfg_path.read_text())
    cfg["ho3"] = {
        "enabled": ho3_enabled,
        "memory_dir": "HOT/memory",
        "gate_count_threshold": 5,
        "gate_session_threshold": 3,
        "gate_window_hours": 168,
    }
    cfg["budget"]["consolidation_budget"] = 4000
    cfg["budget"]["ho3_bias_budget"] = 2000
    cfg_path.write_text(json.dumps(cfg))
    return cfg_path, tpl_path


class TestHO3Wiring:
    def test_ho3_memory_created_when_enabled(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files_with_ho3(tmp_path, ho3_enabled=True)
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        assert ho2._ho3_memory is not None

    def test_ho3_memory_none_when_disabled(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files_with_ho3(tmp_path, ho3_enabled=False)
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        assert ho2._ho3_memory is None

    def test_ho3_memory_none_when_section_missing(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files(tmp_path)
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2 = shell._host._ho2
        assert ho2._ho3_memory is None

    def test_ho3_config_values_mapped_to_ho2config(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files_with_ho3(tmp_path, ho3_enabled=True)
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2_cfg = shell._host._ho2._config
        assert ho2_cfg.ho3_enabled is True
        assert ho2_cfg.ho3_gate_count_threshold == 5
        assert ho2_cfg.ho3_gate_session_threshold == 3
        assert ho2_cfg.ho3_gate_window_hours == 168

    def test_consolidation_budget_from_config(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files_with_ho3(tmp_path, ho3_enabled=True)
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2_cfg = shell._host._ho2._config
        assert ho2_cfg.consolidation_budget == 4000

    def test_consolidation_budget_not_default_when_config_differs(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files_with_ho3(tmp_path, ho3_enabled=True)
        cfg = json.loads(cfg_path.read_text())
        cfg["budget"]["consolidation_budget"] = 8000
        cfg_path.write_text(json.dumps(cfg))
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho2_cfg = shell._host._ho2._config
        assert ho2_cfg.consolidation_budget == 8000

    def test_ho3_bias_budget_in_config(self):
        cfg_path = Path(admin_main.__file__).resolve().parents[1] / "config" / "admin_config.json"
        cfg = json.loads(cfg_path.read_text())
        assert cfg["budget"]["ho3_bias_budget"] == 2000

    def test_ho3_memory_dir_resolved_against_root(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files_with_ho3(tmp_path, ho3_enabled=True)
        shell = build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        ho3_mem = shell._host._ho2._ho3_memory
        assert ho3_mem is not None
        expected = tmp_path / "HOT" / "memory"
        assert ho3_mem.config.memory_dir == expected

    def test_ho3_memory_dir_created(self, tmp_path: Path):
        cfg_path, _ = _write_admin_files_with_ho3(tmp_path, ho3_enabled=True)
        memory_dir = tmp_path / "HOT" / "memory"
        assert not memory_dir.exists()
        build_session_host_v2(root=tmp_path, config_path=cfg_path, dev_mode=True)
        assert memory_dir.is_dir()

    def test_ho3_import_path_in_staging_mode(self):
        """Verify _ensure_import_paths includes PKG-HO3-MEMORY-001 path in staging mode."""
        staging = admin_main._staging_root()
        expected = str(staging / "PKG-HO3-MEMORY-001" / "HOT" / "kernel")
        # Call _ensure_import_paths (staging mode, no root)
        admin_main._ensure_import_paths(root=None)
        assert expected in sys.path
