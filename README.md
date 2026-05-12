# claude-code-profiles

Lightweight CLI to manage named profiles for [Claude Code](https://claude.ai/code) — switch which MCP servers and plugins are active without touching your `settings.json` manually.

## How it works

Each profile declares which MCP servers and plugins to enable. When you run `ccp <name>`, it:

1. Reads your `~/.claude/settings.json` and `~/.claude.json` in memory — never writes to them
2. Builds a filtered MCP config containing only the servers your profile wants
3. Launches claude with `--mcp-config <tmpfile> --strict-mcp-config --settings <tmpfile>`
4. Cleans up the temp files when the session ends

**Plugins** are controlled via `--settings` (patches `enabledPlugins`).
**MCP servers** are controlled via `--mcp-config` + `--strict-mcp-config`, which tells Claude Code to use only the servers in the profile and ignore all others.

Your base settings are never modified.

### Where MCP definitions come from

`ccp` discovers MCP server definitions from three sources, in priority order:

1. **`~/.claude.json`** — user-scope registry (where `claude mcp add --scope user` writes)
2. **`~/.claude/settings.json` `mcpServers`** — directly defined servers
3. **`.mcp.json` files** — scanned walking up from the current directory to home, plus plugin cache and marketplace directories

> **Note:** If you add a new MCP after creating a profile, update the profile to include it — otherwise it will be excluded when the profile is applied.

## Requirements

- Python 3.9+
- Claude Code installed and configured (`~/.claude/settings.json` must exist)

## Installation

```bash
uv tool install claude-code-profiles
```

To update later:

```bash
uv tool upgrade claude-code-profiles
```

Make sure `~/.local/bin` is on your `$PATH`. If it isn't, add this to your shell config:

```bash
export PATH="$PATH:$HOME/.local/bin"
```

To uninstall:

```bash
uv tool uninstall claude-code-profiles
```

## Usage

```bash
ccp list              # list available profiles
ccp show <name>       # show profile contents
ccp create <name>     # create a new profile (opens VS Code or nano)
ccp remove <name>     # delete a profile
ccp <name> [args...]  # launch claude with profile applied
```

## Creating a profile

```bash
ccp create code
```

This opens an editor pre-populated with every MCP and plugin discovered from your setup. Remove the ones you don't want, save and close.

**Profile structure:**

```json
{
  "description": "Code mode — LSPs and GitHub only",
  "enabledMcpjsonServers": ["github", "postgres", "filesystem"],
  "enabledPlugins": [
    "some-plugin@claude-plugins-official"
  ]
}
```

Anything removed from the lists is disabled when the profile is applied.

## Profiles directory

Profiles are stored in `~/.claude/profiles/` by default. Override with:

```bash
export CCP_PROFILES_DIR=/path/to/profiles
```

## Example profiles

**code** — focused coding session:
```json
{
  "description": "Coding — GitHub, LSP, and docs",
  "enabledMcpjsonServers": ["github", "filesystem"],
  "enabledPlugins": [
    "context7@claude-plugins-official"
  ]
}
```

**infra** — infrastructure work:
```json
{
  "description": "Infra — Kubernetes, Terraform, PagerDuty",
  "enabledMcpjsonServers": ["kubernetes", "pagerduty", "github"],
  "enabledPlugins": []
}
```

**research** — docs and planning:
```json
{
  "description": "Research — notes and web",
  "enabledMcpjsonServers": ["obsidian", "brave-search"],
  "enabledPlugins": [
    "context7@claude-plugins-official"
  ]
}
```
