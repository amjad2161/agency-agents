# 🔌 Model Context Protocol (MCP) Integration Guide

> **Give every agent in The Agency real-world tools.** MCP is an open protocol
> for connecting AI agents to data sources, APIs, and services — filesystems,
> GitHub, browsers, databases, internal APIs, and more. This guide shows how to
> wire any agent in this catalog to MCP servers so they move from "smart text
> generators" to "agents that can actually do the work."

---

## 📖 What is MCP?

The **Model Context Protocol** (MCP) is an open standard originally published
by Anthropic and now adopted by Claude Code, OpenAI's agents stack, Cursor,
Continue, Goose, Zed, Cline, and many others. An MCP server exposes three
kinds of capabilities to an agent:

| Primitive | What it is | Example |
|-----------|-----------|---------|
| **Tools** | Functions the agent can call | `github.create_issue`, `fs.read_file` |
| **Resources** | Read-only context the agent can load | a DB schema, a wiki page |
| **Prompts** | Parameterized prompt templates | "Write a release note for commit X" |

Every agent in this repo is a *personality and playbook* written as a Markdown
system prompt. MCP is what lets that personality **touch the real world**.

---

## 🧩 Why this matters for The Agency

The agents in this catalog already describe *what* they do. By default, though,
they can only produce text. Hooking them up to MCP gives each division
concrete, reusable capabilities:

| Division | High-value MCP servers |
|----------|------------------------|
| **Engineering** | `filesystem`, `git`, `github`, language servers, `sqlite`/`postgres` |
| **Marketing** / **Paid Media** | `brave-search`, `firecrawl`, social APIs, analytics MCPs |
| **Sales** | `stripe`, `hubspot`, `salesforce`, CRM MCPs |
| **Support** | `zendesk`, `intercom`, ticketing MCPs, knowledge base RAG |
| **Product** / **Project Management** | `linear`, `jira`, `notion`, `asana` MCPs |
| **Testing** | `playwright`, `puppeteer`, HTTP MCPs |
| **Finance** | `stripe`, accounting MCPs, spreadsheet MCPs |
| **Design** / **Spatial Computing** | `figma`, asset-library MCPs |

---

## 🚀 Recommended MCP servers

These are production-grade, actively-maintained servers. Install what your
agents actually need — more tools is **not** better; agents pick tools by name
and description, so noise hurts selection accuracy.

### Core / foundational

- **Filesystem** — `@modelcontextprotocol/server-filesystem`
- **Git** — `@modelcontextprotocol/server-git`
- **GitHub** — [`github/github-mcp-server`](https://github.com/github/github-mcp-server) (first-party)
- **Fetch / HTTP** — `@modelcontextprotocol/server-fetch`
- **Shell / commands** — community `mcp-server-commands`

### Developer productivity

- **Playwright** — `@executeautomation/mcp-playwright` (browser automation)
- **Puppeteer** — `@modelcontextprotocol/server-puppeteer`
- **SQLite / Postgres** — `@modelcontextprotocol/server-sqlite`, `@modelcontextprotocol/server-postgres`
- **Sentry** — community Sentry MCP for incident triage
- **Cloudflare** — `@cloudflare/mcp-server-cloudflare`

### Research & knowledge

- **Brave Search** — `@brave/brave-search-mcp`
- **Firecrawl** — `firecrawl-mcp` (web crawling / scraping)
- **Memory** — `@modelcontextprotocol/server-memory` (agent long-term memory)

### SaaS / business

- **Stripe** — [`stripe/agent-toolkit`](https://github.com/stripe/agent-toolkit)
- **Supabase** — `supabase-community/supabase-mcp`
- **Notion**, **Linear**, **Slack**, **Google Drive** — see the official
  [`modelcontextprotocol/servers`](https://github.com/modelcontextprotocol/servers)
  repository and the community list at
  [`punkpeye/awesome-mcp-servers`](https://github.com/punkpeye/awesome-mcp-servers).

> ⚠️ **Always check the license** of a third-party MCP server before you ship
> it to customers. Many are MIT/Apache-2.0, but some community servers use
> copyleft licenses.

---

## 🛠️ Wiring an agent to MCP servers

The Agency's agents are transport-agnostic Markdown files, so the MCP wiring
happens in your **host tool's** config, not in the agent file. Below are the
most common hosts.

### Claude Code

Add servers to `~/.claude/mcp.json` (or a project-scoped `.mcp.json`):

```jsonc
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/me/projects"]
    },
    "github": {
      "command": "docker",
      "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
               "ghcr.io/github/github-mcp-server"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_PAT}" }
    }
  }
}
```

Then activate an agent as usual — it inherits the tool list automatically.

### GitHub Copilot (agents)

Place MCP server definitions in `~/.copilot/mcp.json` using the same schema.
The agents installed via `./scripts/install.sh --tool copilot` will see the
tools at runtime.

### Cursor

Cursor reads MCP config from `~/.cursor/mcp.json` (global) or
`.cursor/mcp.json` (per-project). Same schema as Claude Code.

### OpenCode / Goose / Zed / Cline / Continue

All of these consume the same `mcpServers` schema. Refer to each tool's docs
for the exact config path.

### Gemini CLI / Antigravity

These consume MCP via their extension/skill manifest — see the per-tool
configs already generated under
[`integrations/gemini-cli/`](./gemini-cli/) and
[`integrations/antigravity/`](./antigravity/).

---

## 🧪 Minimal recommended stack per role

If you just want a sensible default, start here:

```jsonc
{
  "mcpServers": {
    "filesystem": { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "."] },
    "git":        { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-git"] },
    "github":     { "command": "docker", "args": ["run", "-i", "--rm", "-e", "GITHUB_PERSONAL_ACCESS_TOKEN", "ghcr.io/github/github-mcp-server"] },
    "fetch":      { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-fetch"] },
    "memory":     { "command": "npx", "args": ["-y", "@modelcontextprotocol/server-memory"] }
  }
}
```

That single config covers 80% of what the Engineering, Product, Support, and
Strategy agents need.

---

## 🛡️ Security considerations

MCP turns a text-only agent into something with real side effects. Treat it
accordingly.

1. **Scope filesystem servers** to a single project directory, never `/` or
   `$HOME`.
2. **Use short-lived tokens** (GitHub PATs with minimal scopes, rotated
   regularly) instead of long-lived admin credentials.
3. **Review tool descriptions** — a compromised third-party MCP server can
   smuggle prompt injection into your agent via its tool descriptions. Pair
   this with the **Prompt Injection Defender** agent
   (`engineering/engineering-prompt-injection-defender.md`).
4. **Run untrusted MCP servers in containers** (Docker, Podman, or a devbox)
   so they can't reach the host filesystem or network beyond what you allow.
5. **Log every tool call** — Goose, Claude Code, and Cursor support trace
   logging. Keep it on in production.
6. **Red-team your MCP stack** regularly — see the
   **LLM Red-Teamer** agent (`engineering/engineering-llm-red-teamer.md`).

---

## 📚 Further reading

- Protocol spec — <https://modelcontextprotocol.io>
- Official servers — <https://github.com/modelcontextprotocol/servers>
- GitHub's MCP server — <https://github.com/github/github-mcp-server>
- Awesome list — <https://github.com/punkpeye/awesome-mcp-servers>
- Building your own server — see the **MCP Builder** agent
  (`specialized/specialized-mcp-builder.md`) in this repo.
