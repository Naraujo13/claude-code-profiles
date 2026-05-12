#!/usr/bin/env python3
"""
ccp - Claude Code Profiles

Manage named profiles for Claude Code MCP servers and plugins.
Profiles are stored in ~/.claude/profiles/ (or $CCP_PROFILES_DIR).

Usage:
  ccp list              List available profiles
  ccp show <name>       Show profile contents
  ccp create <name>     Create a new profile (opens editor)
  ccp edit <name>       Edit an existing profile (opens editor)
  ccp remove <name>     Delete a profile
  ccp <name> [args...]  Launch claude with profile applied (never writes to settings.json)
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
PROFILES_DIR = Path(os.environ.get("CCP_PROFILES_DIR", Path.home() / ".claude" / "profiles"))

# ── settings ──────────────────────────────────────────────────────────────────

def load_settings() -> dict:
    if not SETTINGS_PATH.exists():
        die(f"Claude Code settings not found at {SETTINGS_PATH}")
    with open(SETTINGS_PATH) as f:
        return json.load(f)


# ── profiles ──────────────────────────────────────────────────────────────────

def profile_path(name: str) -> Path:
    return PROFILES_DIR / f"{name}.json"


def load_profile(name: str) -> dict:
    path = profile_path(name)
    if not path.exists():
        die(f"Profile '{name}' not found. Run: ccp list")
    with open(path) as f:
        return json.load(f)


def patch_settings(settings: dict, profile: dict) -> dict:
    if "enabledMcpjsonServers" in profile:
        settings["enabledMcpjsonServers"] = profile["enabledMcpjsonServers"]

    if "enabledPlugins" in profile:
        enabled = set(profile["enabledPlugins"])
        current_plugins = settings.get("enabledPlugins", {})
        for plugin in current_plugins:
            current_plugins[plugin] = plugin in enabled

    return settings



def _parse_mcp_file(path: Path) -> dict:
    """Parse a .mcp.json file, normalising both {mcpServers:{}} and flat {} formats."""
    try:
        data = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    # Standard format: {"mcpServers": {"name": {...}}}
    if "mcpServers" in data:
        return data["mcpServers"]
    # Compact format: {"name": {"type": ..., "url": ...}}
    # Heuristic: values are dicts with at least one of these keys
    mcp_keys = {"type", "command", "url"}
    if all(isinstance(v, dict) and mcp_keys & v.keys() for v in data.values()):
        return data
    return {}


def _collect_all_mcp_files() -> list[Path]:
    """Return all .mcp.json paths from: cwd→home walk, plugin cache, plugin marketplaces."""
    paths = []
    home = Path.home()

    # Walk up from cwd to home (project-level files)
    current = Path.cwd()
    while True:
        candidate = current / ".mcp.json"
        if candidate.exists():
            paths.append(candidate)
        if current == home or current.parent == current:
            break
        current = current.parent

    # Plugin cache: ~/.claude/plugins/cache/*/<plugin>/<version>/.mcp.json
    cache_root = home / ".claude" / "plugins" / "cache"
    if cache_root.exists():
        paths.extend(cache_root.rglob(".mcp.json"))

    # Plugin marketplaces: ~/.claude/plugins/marketplaces/*/external_plugins/*/.mcp.json
    market_root = home / ".claude" / "plugins" / "marketplaces"
    if market_root.exists():
        paths.extend(market_root.rglob(".mcp.json"))

    return paths


def discover_available(settings: dict) -> tuple[list[str], list[str]]:
    mcps = set(_load_user_mcp_registry().keys())
    mcps.update(settings.get("mcpServers", {}).keys())
    for path in _collect_all_mcp_files():
        mcps.update(_parse_mcp_file(path).keys())
    plugins = list(settings.get("enabledPlugins", {}).keys())
    return sorted(mcps), sorted(plugins)


def _load_user_mcp_registry() -> dict:
    """Read ~/.claude.json — where 'claude mcp add --scope user' writes server definitions."""
    path = Path.home() / ".claude.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text()).get("mcpServers", {})
    except (json.JSONDecodeError, OSError):
        return {}


def collect_mcp_definitions(settings: dict, enabled: list[str]) -> dict:
    """Build a --mcp-config compatible dict with full definitions for enabled servers only."""
    wanted = set(enabled)
    servers = {}

    # Source 1: user-scope registry (~/.claude.json) — has all plugin-registered MCPs
    for name, cfg in _load_user_mcp_registry().items():
        if name in wanted:
            servers[name] = cfg

    # Source 2: settings.json mcpServers (project-scope, e.g. obsidian)
    for name, cfg in settings.get("mcpServers", {}).items():
        if name in wanted and name not in servers:
            servers[name] = cfg

    # Source 3: .mcp.json files from cwd walk + plugin cache/marketplaces
    for path in _collect_all_mcp_files():
        for name, cfg in _parse_mcp_file(path).items():
            if name in wanted and name not in servers:
                servers[name] = cfg

    return {"mcpServers": servers}


# ── commands ──────────────────────────────────────────────────────────────────

def cmd_list() -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profiles = sorted(p.stem for p in PROFILES_DIR.glob("*.json"))

    if not profiles:
        print("No profiles found. Create one with: ccp create <name>")
        return

    for name in profiles:
        try:
            data = json.loads(profile_path(name).read_text())
            desc = f" — {data['description']}" if data.get("description") else ""
            mcp_count = len(data.get("enabledMcpjsonServers", []))
            plugin_count = len(data.get("enabledPlugins", []))
            meta = f" ({mcp_count} MCPs, {plugin_count} plugins)"
        except Exception:
            desc, meta = "", ""
        print(f"  {name}{desc}{meta}")


def cmd_show(name: str) -> None:
    profile = load_profile(name)

    print(f"Profile : {name}")
    if profile.get("description"):
        print(f"Desc    : {profile['description']}")

    mcps = profile.get("enabledMcpjsonServers", [])
    print(f"\nMCPs ({len(mcps)}):")
    for m in mcps:
        print(f"  {m}")
    if not mcps:
        print("  (none)")

    plugins = profile.get("enabledPlugins", [])
    print(f"\nPlugins ({len(plugins)}):")
    for p in plugins:
        print(f"  {p}")
    if not plugins:
        print("  (none)")




def cmd_create(name: str) -> None:
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = profile_path(name)

    if path.exists():
        die(f"Profile '{name}' already exists. Edit it directly:\n  $EDITOR {path}")

    settings = load_settings()
    available_mcps, available_plugins = discover_available(settings)

    template = {
        "description": "",
        "enabledMcpjsonServers": available_mcps,
        "enabledPlugins": available_plugins,
    }

    path.write_text(json.dumps(template, indent=2))
    _open_editor(path, name)


def cmd_edit(name: str) -> None:
    path = profile_path(name)
    if not path.exists():
        die(f"Profile '{name}' not found. Run: ccp list")
    _open_editor(path, name)


def _open_editor(path: Path, name: str) -> None:
    print(f"Opening '{name}' — close the file in your editor to continue.")
    if shutil.which("code"):
        subprocess.run(["code", "--wait", str(path)])
    else:
        subprocess.run([shutil.which("nano") or "nano", str(path)])

    try:
        json.loads(path.read_text())
        print(f"Profile '{name}' saved to {path}")
    except json.JSONDecodeError:
        print(f"Warning: saved but has JSON errors — fix before using:\n  $EDITOR {path}")


def cmd_remove(name: str) -> None:
    path = profile_path(name)
    if not path.exists():
        die(f"Profile '{name}' not found. Run: ccp list")
    path.unlink()
    print(f"Profile '{name}' removed.")


# ── main ──────────────────────────────────────────────────────────────────────

def die(msg: str) -> None:
    print(f"Error: {msg}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    args = sys.argv[1:]

    if not args or args[0] in ("-h", "--help"):
        print((__doc__ or "").strip())
        sys.exit(0)

    cmd = args[0]

    if cmd == "list":
        cmd_list()
    elif cmd == "show":
        if len(args) < 2:
            die("Usage: ccp show <name>")
        cmd_show(args[1])
    elif cmd == "create":
        if len(args) < 2:
            die("Usage: ccp create <name>")
        cmd_create(args[1])
    elif cmd == "edit":
        if len(args) < 2:
            die("Usage: ccp edit <name>")
        cmd_edit(args[1])
    elif cmd == "remove":
        if len(args) < 2:
            die("Usage: ccp remove <name>")
        cmd_remove(args[1])
    else:
        # Session-scoped: never writes to ~/.claude/settings.json
        settings = load_settings()
        profile = load_profile(cmd)
        patched = patch_settings(settings, profile)

        enabled_mcps = patched.get("enabledMcpjsonServers", [])
        mcp_config = collect_mcp_definitions(settings, enabled_mcps)

        # --settings handles plugins; --mcp-config + --strict-mcp-config handles MCPs
        plugin_overlay = {"enabledPlugins": patched.get("enabledPlugins", {})}

        claude_bin = shutil.which("claude")
        if not claude_bin:
            die("'claude' not found in PATH. Is Claude Code installed?")

        tmp_files = []
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(plugin_overlay, f, indent=2)
                tmp_files.append(f.name)
                settings_tmp = f.name

            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
                json.dump(mcp_config, f, indent=2)
                tmp_files.append(f.name)
                mcp_tmp = f.name

            subprocess.run([
                claude_bin,
                "--settings", settings_tmp,
                "--mcp-config", mcp_tmp,
                "--strict-mcp-config",
            ] + args[1:])
        finally:
            for f in tmp_files:
                os.unlink(f)


if __name__ == "__main__":
    main()
