# claude-code-profiles

Claude Code loads every MCP server and plugin you have configured. As your setup grows, that can become context clutter with irrelevant toolings for different situations.

`ccp` lets you define named profiles and launch Claude with only what that context needs. Run multiple sessions in parallel, each with a different profile, without touching your `settings.json`.


```bash
ccp infra      # terminal 1: claude with k8s, pagerduty, terraform
ccp code       # terminal 2: claude with github, lsp, docs
ccp research   # terminal 3: claude with search and notes only
```

Each runs independently with its own isolated tool set, allowing for different setups in parallel sessions.

## Install

```bash
uv tool install claude-code-profiles
```

Requires Python 3.9+ and [Claude Code](https://claude.ai/code).

## Quickstart

```bash
ccp create <profile>   # opens editor pre-filled with all your MCPs and plugins
                       # remove what you don't want, save and close
ccp <profile>          # launch claude with that profile
```

## Commands

```bash
ccp list              # list profiles
ccp show <name>       # inspect a profile
ccp create <name>     # create a new profile
ccp edit <name>       # edit an existing profile
ccp remove <name>     # delete a profile
ccp <name> [args...]  # launch claude with profile applied
```

## Profile format

```json
{
  "description": "Coding — GitHub and docs only",
  "enabledMcpjsonServers": ["github", "filesystem"],
  "enabledPlugins": ["context7@claude-plugins-official"]
}
```

Profiles live in `~/.claude/profiles/` by default. Override with `$CCP_PROFILES_DIR`.

## How it works

When you run `ccp <name>`, it builds a filtered MCP config from your profile and launches Claude with `--mcp-config --strict-mcp-config --settings`, using temp files that are cleaned up after the session. Nothing is written to your settings.

MCP definitions are discovered from `~/.claude.json`, `~/.claude/settings.json`, and `.mcp.json` files walked up from your current directory.
