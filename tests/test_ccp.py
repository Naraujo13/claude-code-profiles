import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

import ccp


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def base_settings():
    return {
        "mcpServers": {
            "obsidian": {"type": "sse", "url": "http://localhost:27123"},
        },
        "enabledPlugins": {
            "context7@claude-plugins-official": True,
            "gopls-lsp@claude-plugins-official": False,
        },
        "enabledMcpjsonServers": ["obsidian"],
    }


@pytest.fixture
def settings_file(tmp_path, base_settings):
    f = tmp_path / "settings.json"
    f.write_text(json.dumps(base_settings))
    return f


@pytest.fixture
def profiles_dir(tmp_path, monkeypatch):
    d = tmp_path / "profiles"
    d.mkdir()
    monkeypatch.setattr(ccp, "PROFILES_DIR", d)
    return d


def write_profile(profiles_dir, name, data):
    (profiles_dir / f"{name}.json").write_text(json.dumps(data))


# ── patch_settings ─────────────────────────────────────────────────────────────

class TestPatchSettings:
    def test_patches_mcp_servers(self, base_settings):
        result = ccp.patch_settings(base_settings, {"enabledMcpjsonServers": ["github"]})
        assert result["enabledMcpjsonServers"] == ["github"]

    def test_patches_plugins_enabled(self, base_settings):
        result = ccp.patch_settings(base_settings, {"enabledPlugins": ["context7@claude-plugins-official"]})
        assert result["enabledPlugins"]["context7@claude-plugins-official"] is True
        assert result["enabledPlugins"]["gopls-lsp@claude-plugins-official"] is False

    def test_patches_plugins_none_enabled(self, base_settings):
        result = ccp.patch_settings(base_settings, {"enabledPlugins": []})
        assert all(v is False for v in result["enabledPlugins"].values())

    def test_no_mcp_key_leaves_unchanged(self, base_settings):
        original = base_settings["enabledMcpjsonServers"][:]
        ccp.patch_settings(base_settings, {})
        assert base_settings["enabledMcpjsonServers"] == original

    def test_no_plugins_key_leaves_unchanged(self, base_settings):
        original = dict(base_settings["enabledPlugins"])
        ccp.patch_settings(base_settings, {})
        assert base_settings["enabledPlugins"] == original

    def test_settings_without_plugins_key(self):
        result = ccp.patch_settings({}, {"enabledPlugins": ["foo"]})
        assert result == {}


# ── _parse_mcp_file ────────────────────────────────────────────────────────────

class TestParseMcpFile:
    def test_standard_format(self, tmp_path):
        f = tmp_path / ".mcp.json"
        f.write_text(json.dumps({"mcpServers": {"github": {"type": "sse", "url": "http://x"}}}))
        assert ccp._parse_mcp_file(f) == {"github": {"type": "sse", "url": "http://x"}}

    def test_flat_format(self, tmp_path):
        f = tmp_path / ".mcp.json"
        f.write_text(json.dumps({"github": {"type": "sse", "url": "http://x"}}))
        assert ccp._parse_mcp_file(f) == {"github": {"type": "sse", "url": "http://x"}}

    def test_flat_format_command_key(self, tmp_path):
        f = tmp_path / ".mcp.json"
        f.write_text(json.dumps({"mytool": {"command": "npx", "args": []}}))
        assert ccp._parse_mcp_file(f) == {"mytool": {"command": "npx", "args": []}}

    def test_invalid_json_returns_empty(self, tmp_path):
        f = tmp_path / ".mcp.json"
        f.write_text("not json{{")
        assert ccp._parse_mcp_file(f) == {}

    def test_missing_file_returns_empty(self, tmp_path):
        assert ccp._parse_mcp_file(tmp_path / "nonexistent.json") == {}

    def test_empty_object_returns_empty(self, tmp_path):
        f = tmp_path / ".mcp.json"
        f.write_text("{}")
        assert ccp._parse_mcp_file(f) == {}

    def test_non_mcp_values_returns_empty(self, tmp_path):
        f = tmp_path / ".mcp.json"
        f.write_text(json.dumps({"key": "string_value"}))
        assert ccp._parse_mcp_file(f) == {}


# ── _load_user_mcp_registry ────────────────────────────────────────────────────

class TestLoadUserMcpRegistry:
    def test_reads_mcp_servers(self, tmp_path, monkeypatch):
        claude_json = tmp_path / ".claude.json"
        claude_json.write_text(json.dumps({"mcpServers": {"github": {"type": "sse"}}}))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert ccp._load_user_mcp_registry() == {"github": {"type": "sse"}}

    def test_missing_file_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert ccp._load_user_mcp_registry() == {}

    def test_invalid_json_returns_empty(self, tmp_path, monkeypatch):
        (tmp_path / ".claude.json").write_text("bad json")
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert ccp._load_user_mcp_registry() == {}

    def test_no_mcp_servers_key_returns_empty(self, tmp_path, monkeypatch):
        (tmp_path / ".claude.json").write_text(json.dumps({"other": "data"}))
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        assert ccp._load_user_mcp_registry() == {}


# ── load_settings ──────────────────────────────────────────────────────────────

class TestLoadSettings:
    def test_loads_file(self, settings_file, base_settings, monkeypatch):
        monkeypatch.setattr(ccp, "SETTINGS_PATH", settings_file)
        assert ccp.load_settings() == base_settings

    def test_missing_file_exits(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ccp, "SETTINGS_PATH", tmp_path / "nope.json")
        with pytest.raises(SystemExit):
            ccp.load_settings()


# ── load_profile ───────────────────────────────────────────────────────────────

class TestLoadProfile:
    def test_loads_existing(self, profiles_dir):
        data = {"description": "test", "enabledMcpjsonServers": ["github"]}
        write_profile(profiles_dir, "code", data)
        assert ccp.load_profile("code") == data

    def test_missing_exits(self, profiles_dir):
        with pytest.raises(SystemExit):
            ccp.load_profile("nonexistent")


# ── collect_mcp_definitions ────────────────────────────────────────────────────

class TestCollectMcpDefinitions:
    def test_from_settings(self, monkeypatch):
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        settings = {"mcpServers": {"obsidian": {"type": "sse", "url": "http://x"}}}
        result = ccp.collect_mcp_definitions(settings, ["obsidian"])
        assert result == {"mcpServers": {"obsidian": {"type": "sse", "url": "http://x"}}}

    def test_from_user_registry(self, monkeypatch):
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {"github": {"type": "sse"}})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        result = ccp.collect_mcp_definitions({}, ["github"])
        assert result == {"mcpServers": {"github": {"type": "sse"}}}

    def test_from_mcp_file(self, tmp_path, monkeypatch):
        mcp_file = tmp_path / ".mcp.json"
        mcp_file.write_text(json.dumps({"mcpServers": {"local": {"command": "npx"}}}))
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [mcp_file])
        result = ccp.collect_mcp_definitions({}, ["local"])
        assert result["mcpServers"]["local"] == {"command": "npx"}

    def test_registry_takes_priority_over_settings(self, monkeypatch):
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {"shared": {"url": "from-registry"}})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        settings = {"mcpServers": {"shared": {"url": "from-settings"}}}
        result = ccp.collect_mcp_definitions(settings, ["shared"])
        assert result["mcpServers"]["shared"]["url"] == "from-registry"

    def test_skips_non_enabled(self, monkeypatch):
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {"github": {}, "slack": {}})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        result = ccp.collect_mcp_definitions({}, ["github"])
        assert "slack" not in result["mcpServers"]

    def test_empty_enabled_list(self, monkeypatch):
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {"github": {}})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        result = ccp.collect_mcp_definitions({}, [])
        assert result == {"mcpServers": {}}


# ── discover_available ─────────────────────────────────────────────────────────

class TestDiscoverAvailable:
    def test_combines_all_sources(self, tmp_path, monkeypatch):
        mcp_file = tmp_path / ".mcp.json"
        mcp_file.write_text(json.dumps({"mcpServers": {"file-mcp": {"type": "sse"}}}))
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {"registry-mcp": {}})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [mcp_file])
        settings = {
            "mcpServers": {"settings-mcp": {}},
            "enabledPlugins": {"plugin-a": True},
        }
        mcps, plugins = ccp.discover_available(settings)
        assert "registry-mcp" in mcps
        assert "settings-mcp" in mcps
        assert "file-mcp" in mcps
        assert plugins == ["plugin-a"]

    def test_returns_sorted(self, monkeypatch):
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {"z-mcp": {}, "a-mcp": {}})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        mcps, _ = ccp.discover_available({})
        assert mcps == sorted(mcps)


# ── _collect_all_mcp_files ─────────────────────────────────────────────────────

class TestCollectAllMcpFiles:
    def test_finds_mcp_json_in_cwd(self, tmp_path, monkeypatch):
        mcp = tmp_path / ".mcp.json"
        mcp.write_text("{}")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = ccp._collect_all_mcp_files()
        assert mcp in result

    def test_finds_files_in_plugin_cache(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        cache = tmp_path / ".claude" / "plugins" / "cache" / "org" / "plugin" / "1.0"
        cache.mkdir(parents=True)
        mcp = cache / ".mcp.json"
        mcp.write_text("{}")
        result = ccp._collect_all_mcp_files()
        assert mcp in result

    def test_no_files_returns_empty(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(Path, "home", lambda: tmp_path)
        result = ccp._collect_all_mcp_files()
        assert result == []


# ── cmd_list ───────────────────────────────────────────────────────────────────

class TestCmdList:
    def test_empty_dir(self, profiles_dir, capsys):
        ccp.cmd_list()
        assert "No profiles" in capsys.readouterr().out

    def test_lists_profiles_with_meta(self, profiles_dir, capsys):
        write_profile(profiles_dir, "code", {
            "description": "Coding",
            "enabledMcpjsonServers": ["github"],
            "enabledPlugins": ["context7@claude-plugins-official"],
        })
        ccp.cmd_list()
        out = capsys.readouterr().out
        assert "code" in out
        assert "Coding" in out
        assert "1 MCPs" in out

    def test_broken_profile_does_not_crash(self, profiles_dir, capsys):
        (profiles_dir / "broken.json").write_text("not json")
        ccp.cmd_list()
        assert "broken" in capsys.readouterr().out


# ── cmd_show ───────────────────────────────────────────────────────────────────

class TestCmdShow:
    def test_shows_mcps_and_plugins(self, profiles_dir, capsys):
        write_profile(profiles_dir, "code", {
            "description": "Coding",
            "enabledMcpjsonServers": ["github"],
            "enabledPlugins": ["context7@claude-plugins-official"],
        })
        ccp.cmd_show("code")
        out = capsys.readouterr().out
        assert "github" in out
        assert "context7" in out
        assert "Coding" in out

    def test_empty_mcps_and_plugins(self, profiles_dir, capsys):
        write_profile(profiles_dir, "bare", {"enabledMcpjsonServers": [], "enabledPlugins": []})
        ccp.cmd_show("bare")
        out = capsys.readouterr().out
        assert "(none)" in out

    def test_no_description(self, profiles_dir, capsys):
        write_profile(profiles_dir, "nodesc", {"enabledMcpjsonServers": []})
        ccp.cmd_show("nodesc")
        assert "Desc" not in capsys.readouterr().out


# ── cmd_remove ─────────────────────────────────────────────────────────────────

class TestCmdRemove:
    def test_removes_profile(self, profiles_dir):
        write_profile(profiles_dir, "code", {})
        ccp.cmd_remove("code")
        assert not (profiles_dir / "code.json").exists()

    def test_missing_exits(self, profiles_dir):
        with pytest.raises(SystemExit):
            ccp.cmd_remove("nonexistent")


# ── cmd_create ─────────────────────────────────────────────────────────────────

class TestCmdCreate:
    def test_creates_profile(self, profiles_dir, settings_file, monkeypatch):
        monkeypatch.setattr(ccp, "SETTINGS_PATH", settings_file)
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        monkeypatch.setattr(ccp, "_open_editor", lambda path, name: None)
        ccp.cmd_create("newprofile")
        assert (profiles_dir / "newprofile.json").exists()

    def test_existing_profile_exits(self, profiles_dir, monkeypatch):
        write_profile(profiles_dir, "exists", {})
        with pytest.raises(SystemExit):
            ccp.cmd_create("exists")


# ── cmd_edit ───────────────────────────────────────────────────────────────────

class TestCmdEdit:
    def test_opens_editor(self, profiles_dir, monkeypatch):
        write_profile(profiles_dir, "code", {})
        opened = []
        monkeypatch.setattr(ccp, "_open_editor", lambda path, name: opened.append(name))
        ccp.cmd_edit("code")
        assert opened == ["code"]

    def test_missing_exits(self, profiles_dir):
        with pytest.raises(SystemExit):
            ccp.cmd_edit("nonexistent")


# ── _open_editor ───────────────────────────────────────────────────────────────

class TestOpenEditor:
    def test_uses_vscode_when_available(self, tmp_path, monkeypatch):
        f = tmp_path / "profile.json"
        f.write_text("{}")
        calls = []
        monkeypatch.setattr(ccp.shutil, "which", lambda cmd: "/usr/bin/code" if cmd == "code" else None)
        monkeypatch.setattr(ccp.subprocess, "run", lambda args, **kw: calls.append(args))
        ccp._open_editor(f, "test")
        assert calls[0][0] == "code"

    def test_falls_back_to_nano(self, tmp_path, monkeypatch):
        f = tmp_path / "profile.json"
        f.write_text("{}")
        calls = []
        monkeypatch.setattr(ccp.shutil, "which", lambda cmd: None if cmd == "code" else "/bin/nano")
        monkeypatch.setattr(ccp.subprocess, "run", lambda args, **kw: calls.append(args))
        ccp._open_editor(f, "test")
        assert "nano" in calls[0][0]

    def test_warns_on_invalid_json_after_edit(self, tmp_path, monkeypatch, capsys):
        f = tmp_path / "profile.json"
        f.write_text("valid json initially")
        monkeypatch.setattr(ccp.shutil, "which", lambda cmd: None)
        monkeypatch.setattr(ccp.subprocess, "run", lambda args, **kw: f.write_text("broken{"))
        ccp._open_editor(f, "test")
        assert "Warning" in capsys.readouterr().out


# ── main ───────────────────────────────────────────────────────────────────────

class TestMain:
    def test_no_args_exits_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ccp"])
        with pytest.raises(SystemExit) as exc:
            ccp.main()
        assert exc.value.code == 0

    def test_help_flag_exits_zero(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ccp", "--help"])
        with pytest.raises(SystemExit) as exc:
            ccp.main()
        assert exc.value.code == 0

    def test_list_routes(self, profiles_dir, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ccp", "list"])
        ccp.main()

    def test_show_missing_arg_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ccp", "show"])
        with pytest.raises(SystemExit):
            ccp.main()

    def test_create_missing_arg_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ccp", "create"])
        with pytest.raises(SystemExit):
            ccp.main()

    def test_edit_missing_arg_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ccp", "edit"])
        with pytest.raises(SystemExit):
            ccp.main()

    def test_remove_missing_arg_exits(self, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["ccp", "remove"])
        with pytest.raises(SystemExit):
            ccp.main()

    def test_launch_profile(self, profiles_dir, settings_file, monkeypatch):
        monkeypatch.setattr(ccp, "SETTINGS_PATH", settings_file)
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        monkeypatch.setattr(ccp.shutil, "which", lambda cmd: "/usr/bin/claude")
        write_profile(profiles_dir, "code", {"enabledMcpjsonServers": ["obsidian"], "enabledPlugins": []})
        runs = []
        monkeypatch.setattr(ccp.subprocess, "run", lambda args, **kw: runs.append(args))
        monkeypatch.setattr(sys, "argv", ["ccp", "code"])
        ccp.main()
        assert any("--mcp-config" in str(r) for r in runs)

    def test_launch_no_claude_binary_exits(self, profiles_dir, settings_file, monkeypatch):
        monkeypatch.setattr(ccp, "SETTINGS_PATH", settings_file)
        monkeypatch.setattr(ccp, "_load_user_mcp_registry", lambda: {})
        monkeypatch.setattr(ccp, "_collect_all_mcp_files", lambda: [])
        monkeypatch.setattr(ccp.shutil, "which", lambda cmd: None)
        write_profile(profiles_dir, "code", {"enabledMcpjsonServers": [], "enabledPlugins": []})
        monkeypatch.setattr(sys, "argv", ["ccp", "code"])
        with pytest.raises(SystemExit):
            ccp.main()
