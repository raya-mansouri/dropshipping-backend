# GitHub Starred Repositories — Claude Code Integration Guide

*Updated: 2026-03-22 | Source: github.com/raya-mansouri*

---

## ✅ Already Installed

| Plugin | Source | What it does |
|--------|--------|--------------|
| `minimax-skills` | MiniMax-AI/skills | PDF, PPTX, Excel, DOCX, frontend, fullstack, Android, iOS, shader |
| `ui-ux-pro-max` | nextlevelbuilder/ui-ux-pro-max-skill | UI/UX design intelligence — 50+ styles, 161 reasoning rules |
| `commit-commands` | claude-plugins-official | git commit, push, PR commands |
| `security-guidance` | claude-plugins-official | Security best practices |
| `sentry` | claude-plugins-official | Sentry issue tracking |
| `greptile` | claude-plugins-official | Code search/understanding |
| `pyright-lsp` | claude-plugins-official | Python type checking |
| `github` | claude-plugins-official | GitHub integration |
| `frontend-design` | claude-plugins-official | Frontend design intelligence |
| `feature-dev` | claude-plugins-official | Feature development workflow |
| `serena` | claude-plugins-official | Semantic code editing |
| `agent-sdk-dev` | claude-plugins-official | Claude Agent SDK development |
| `pr-review-toolkit` | claude-plugins-official | PR review with specialized agents |
| `playwright` | claude-plugins-official | E2E testing |
| `ralph-wiggum` | claude-plugins-official | Autonomous agent loop |
| `hookify` | claude-plugins-official | Hook creation/management |
| `vercel` | claude-plugins-official | Vercel deployment |
| `plugin-dev` | claude-plugins-official | Plugin development |
| `everything-claude-code` | everything-claude-code | Coding standards, TDD, security, E2E, backend/frontend patterns |

---

## ✅ Installed This Session (from your starred repos)

### Skills (47 files → `~/.claude/skills/`)
Installed from **keon/antigravity-awesome-skills** (1,225 total skills):

| Category | Skills Installed |
|----------|-----------------|
| **FastAPI / Python** | `fastapi-pro`, `fastapi-router-py`, `fastapi-templates`, `python-pro`, `python-fastapi-development`, `python-development-python-scaffold`, `python-patterns`, `python-performance-optimization`, `python-testing-patterns`, `python-packaging`, `async-python-patterns` |
| **Backend** | `backend-architect`, `backend-development-feature-development`, `backend-dev-guidelines`, `backend-security-coder`, `docker-expert` |
| **Database / PostgreSQL** | `postgres-best-practices`, `postgresql`, `postgresql-optimization`, `database`, `database-admin` |
| **API Design** | `api-design-principles`, `api-documentation`, `api-patterns`, `api-security-best-practices`, `api-security-testing` |
| **Context Engineering** | `context-driven-development`, `context-fundamentals`, `context-manager`, `context-optimization`, `context-window-management`, `context-compression` |
| **Code Review** | `code-reviewer`, `code-review-checklist`, `code-review-excellence`, `requesting-code-review`, `receiving-code-review` |
| **Git** | `git-advanced-workflows`, `git-pr-workflows-git-workflow`, `git-pr-workflows-pr-enhance`, `git-pushing` |
| **Security** | `security-scanning-security-sast`, `security-scanning-security-hardening`, `security-scanning-security-dependencies` |
| **Planning / Agents** | `planning-with-files`, `agents-md`, `agent-orchestration-multi-agent-optimize` |

### Plugins (installed via `claude plugin install`)

| Plugin | Source Repo | What it does |
|--------|------------|--------------|
| `claude-mem` | thedotmack/claude-mem | Auto-captures sessions → compresses with AI → injects into future sessions |
| `claude-hud` | jarrodwatts/claude-hud | Real-time HUD: context bar, tools, agent status, todo progress |
| `planning-with-files` | OthmanAdi/planning-with-files | Manus-style persistent markdown planning (task_plan.md, findings.md, progress.md) |
| `visual-explainer` | nicobailon/visual-explainer | Terminal output → styled HTML pages & slides with Mermaid diagrams |
| `pg` (pg-aiguide) | timescale/pg-aiguide | PostgreSQL docs search + best-practice skills (4× more constraints) |
| `understand-anything` | Lum1104/Understand-Anything | Multi-agent codebase analysis with interactive knowledge graph |
| `superpowers` | obra/superpowers | Brainstorming, planning, TDD, debugging, code review, worktree skills |
| `python-development` | wshobson/agents | Python pro, django-pro, fastapi-pro agents |
| `backend-development` | wshobson/agents | Backend architect + agents |
| `database-design` | wshobson/agents | Database architect agents |
| `security-scanning` | wshobson/agents | Security auditor agents |
| `comprehensive-review` | wshobson/agents | Architect-review, code-reviewer, security-auditor agents |
| `tdd-workflows` | wshobson/agents | TDD workflow agents |
| `productivity` | anthropics/knowledge-work-plugins | Official Anthropic productivity plugin |
| `data` | anthropics/knowledge-work-plugins | Official Anthropic data plugin |
| `product-management` | anthropics/knowledge-work-plugins | Official Anthropic PM plugin |

---

## 📋 Complete Starred Repo Catalog (100+ repos)

### Tier 1: Direct Claude Code Integration

| Repo | Claude Code Role | Install |
|------|-----------------|---------|
| keon/antigravity-awesome-skills | 1,225+ skills → `~/.claude/skills/` | `npx antigravity-awesome-skills --claude` |
| anthropics/knowledge-work-plugins | Official Anthropic plugins (11 available) | `claude plugin marketplace add anthropics/knowledge-work-plugins` |
| obra/superpowers | Skills: brainstorming, TDD, debugging, PR workflows | `claude plugin install superpowers@superpowers-marketplace` |
| wshobson/agents | 72 plugins × 112 agents × 146 skills | `claude plugin marketplace add wshobson/agents` |
| thedotmack/claude-mem | Cross-session memory | `claude plugin marketplace add thedotmack/claude-mem` |
| jarrodwatts/claude-hud | Real-time session HUD | `claude plugin marketplace add jarrodwatts/claude-hud` |
| OthmanAdi/planning-with-files | Manus-style file planning | `claude plugin marketplace add OthmanAdi/planning-with-files` |
| nicobailon/visual-explainer | HTML diagrams from terminal output | `claude plugin marketplace add nicobailon/visual-explainer` |
| timescale/pg-aiguide | PostgreSQL knowledge + MCP | `claude plugin marketplace add timescale/pg-aiguide` |
| Lum1104/Understand-Anything | Codebase knowledge graph | `claude plugin marketplace add Lum1104/Understand-Anything` |
| MiniMax-AI/skills | PDF, PPTX, Excel, DOCX, frontend/fullstack | `/plugin marketplace add https://github.com/MiniMax-AI/skills` |
| nextlevelbuilder/ui-ux-pro-max-skill | UI/UX design (50+ styles) | `/plugin marketplace add nextlevelbuilder/ui-ux-pro-max-skill` |
| disler/claude-code-hooks-mastery | Hook examples (13 lifecycle events) | Clone → copy hooks to `.claude/hooks/` |
| phuryn/pm-skills | 100+ PM skills | Clone → copy to `.claude/skills/` |
| openai/skills | OpenAI agent skills | Clone → copy to `.claude/skills/` |
| huggingface/skills | HuggingFace ecosystem skills | Clone → copy to `.claude/skills/` |
| microsoft/skills | Microsoft skills for SDKs | Clone → copy to `.claude/skills/` |
| muratcankoylan/Agent-Skills-for-Context-Engineering | Context engineering skills | Clone → copy to `.claude/skills/` |
| anthropics/skills | Official Anthropic skills (DOCX, PDF, etc.) | `claude plugin marketplace add anthropics/skills` |
| ComposioHQ/awesome-claude-skills | Curated Claude skills | Reference |
| keon/awesome-agent-skills | Curated skills collection | Reference |
| keon/awesome-claude-skills-1 | Curated Claude skills | Reference |

### Tier 2: Agent/AI Frameworks (standalone tools)

| Repo | Type | Use |
|------|------|-----|
| affaan-m/claude-swarm | CLI (pip install) | Multi-agent task decomposition with Opus+Haiku |
| affaan-m/everything-claude-code | Agent harness | Performance optimization system |
| Yeachan-Heo/oh-my-claudecode | Claude Code harness | Teams-first multi-agent orchestration |
| mikeyobrien/ralph-orchestrator | Claude Code plugin | Improved Ralph Wiggum / autonomous loops |
| CloudAI-X/claude-workflow-v2 | Claude Code plugin | Universal workflow (agents, commands, skills, hooks) |
| NousResearch/hermes-agent | Framework | Agent that grows with you |
| promptfoo/promptfoo | CLI tool | Prompt testing, red-teaming, RAG evaluation |
| pydantic/pydantic-ai | Python framework | GenAI agent framework (Pydantic-style) |
| openai/openai-agents-python | Python framework | Lightweight multi-agent workflows |
| QwenLM/Qwen-Agent | Python framework | Agent framework on Qwen 3.0 |
| langchain-ai/langchain | Framework | Agent engineering platform |
| BerriAI/litellm | Gateway | 100+ LLM APIs via unified interface |

### Tier 3: MCP Servers (add to `.mcp.json`)

| Repo | MCP Server | What it gives Claude |
|------|-----------|---------------------|
| modelcontextprotocol/servers | Official MCP servers | Filesystem, GitHub, Slack, etc. |
| modelcontextprotocol/registry | MCP registry | Discover community MCP servers |
| timescale/pg-aiguide | MCP at `mcp.tigerdata.com/docs` | PostgreSQL docs semantic search |
| getzep/graphiti | Local MCP | Real-time knowledge graphs for agents |
| topoteretes/cognee | Local MCP | Knowledge engine — 6-line agent memory |
| excalidraw/excalidraw-mcp | MCP | Diagramming inside Claude |
| supermemoryai/supermemory | MCP | Fast scalable memory engine |
| vectorize-io/hindsight | MCP | Agent memory that learns |
| getsentry/sentry-mcp | MCP | Sentry issue management |
| MicrosoftDocs/mcp | MCP | Microsoft Learn docs |
| IBM/mcp | MCP | IBM services collection |
| timescale/pg-aiguide | MCP | PostgreSQL best practices |

### Tier 4: CLAUDE.md / Rules / Prompts

| Repo | Content | How to use |
|------|---------|-----------|
| danielmiessler/Fabric | 200+ prompt patterns | Copy patterns as skills or rules |
| danielmiessler/Telos | Deep context framework | Reference for CLAUDE.md structure |
| agentsmd/agents.md | AGENTS.md format spec | ✅ Created AGENTS.md this session |
| shanraisshan/claude-code-best-practice | Claude Code best practices | Reference for CLAUDE.md |
| FlorianBruniaux/claude-code-ultimate-guide | Comprehensive Claude Code guide | Reference |
| x1xhlol/system-prompts-and-models-of-ai-tools | System prompt leaks | Reference |
| asgeirtj/system_prompts_leaks | System prompt collection | Reference |
| smkalami/prompt-decorators | Prompt decorators (+++Reason) | Add to system prompt |

### Tier 5: Learning & Context Engineering

| Repo | Learn |
|------|-------|
| shareAI-lab/learn-claude-code | 12-session agent harness engineering course |
| keon/Awesome-Context-Engineering | Context engineering survey |
| keon/awesome-agentic-patterns | Agentic AI pattern catalogue |
| keon/awesome-claude | Everything Claude (MCP, skills, extensions) |
| keon/awesome-claude-code | Awesome Claude Code tools list |
| keon/awesome-claude-code-1 | Curated Claude Code resources |
| keon/500-AI-Agents-Projects | 500 AI agent project examples |
| keon/awesome-ai-agent-frameworks | AI agent frameworks list |
| keon/Awesome-Self-Evolving-Agents | Self-evolving agents survey |
| microsoft/generative-ai-for-beginners | 21-lesson GenAI course |

### Tier 6: Project-Specific (Basalam)

| Repo | Use |
|------|-----|
| basalam/python-sdk | Basalam SDK — used by this project's Basalam integration |
| tirth8205/code-review-graph | Local knowledge graph for Claude Code — store domain relationships |
| fastapi/full-stack-fastapi-template | Reference for FastAPI project structure |
| fastapi/fastapi-vscode | FastAPI VS Code extension |

---

## 🔧 Quick Install Reference

### Reinstall all skills from antigravity
```bash
npx antigravity-awesome-skills --claude
```

### Install claude-workflow-v2 (full plugin)
```bash
npx install-claude-workflow-v2@latest
```

### Add more wshobson workflow plugins
```bash
claude plugin install full-stack-orchestration@claude-code-workflows
claude plugin install agent-teams@claude-code-workflows
claude plugin install observability@claude-code-workflows
claude plugin install deployment@claude-code-workflows
claude plugin install llm-applications@claude-code-workflows
claude plugin install agent-orchestration@claude-code-workflows
claude plugin install context-management@claude-code-workflows
```

### Add more Anthropic knowledge-work plugins
```bash
claude plugin install sales@knowledge-work-plugins
claude plugin install customer-support@knowledge-work-plugins
claude plugin install marketing@knowledge-work-plugins
claude plugin install legal@knowledge-work-plugins
claude plugin install finance@knowledge-work-plugins
claude plugin install enterprise-search@knowledge-work-plugins
```

### Install standalone tools
```bash
pip install claude-swarm          # Multi-agent swarm CLI
npm install -g uipro-cli          # UI/UX Pro CLI (offline skill install)
```

### Add MCP servers (edit ~/.config/claude/mcp.json)
```json
{
  "mcpServers": {
    "postgres-docs": {
      "url": "https://mcp.tigerdata.com/docs",
      "transport": "http"
    }
  }
}
```

---

## 📁 Project Files Created

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Project context for Claude (architecture, patterns, commands) |
| `AGENTS.md` | Agent instructions (dev env, architecture rules, test requirements, PR format) |

---

## 📚 Learn More

- [shareAI-lab/learn-claude-code](https://github.com/shareAI-lab/learn-claude-code) — 12-session hands-on course
- [keon/Awesome-Context-Engineering](https://github.com/keon/Awesome-Context-Engineering) — Context engineering survey
- [antigravity.codes/agent-skills](https://antigravity.codes/agent-skills) — Browse 500+ skills online
- [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) — Official Anthropic plugins

## Available Claude Code Skills

Skills installed from starred repositories, providing specialized capabilities for development:

### FastAPI / Python
- `fastapi-pro`
- `fastapi-router-py`
- `fastapi-templates`
- `python-pro`
- `python-fastapi-development`
- `python-development-python-scaffold`
- `python-patterns`
- `python-performance-optimization`
- `python-testing-patterns`
- `python-packaging`
- `async-python-patterns`

### Backend
- `backend-architect`
- `backend-development-feature-development`
- `backend-dev-guidelines`
- `backend-security-coder`
- `docker-expert`

### Database / PostgreSQL
- `postgres-best-practices`
- `postgresql`
- `postgresql-optimization`
- `database`
- `database-admin`

### API Design
- `api-design-principles`
- `api-documentation`
- `api-patterns`
- `api-security-best-practices`
- `api-security-testing`

### Context Engineering
- `context-driven-development`
- `context-fundamentals`
- `context-manager`
- `context-optimization`
- `context-window-management`
- `context-compression`

### Code Review
- `code-reviewer`
- `code-review-checklist`
- `code-review-excellence`
- `requesting-code-review`
- `receiving-code-review`

### Git
- `git-advanced-workflows`
- `git-pr-workflows-git-workflow`
- `git-pr-workflows-pr-enhance`
- `git-pushing`

### Security
- `security-scanning-security-sast`
- `security-scanning-security-hardening`
- `security-scanning-security-dependencies`

### Planning / Agents
- `planning-with-files`
- `agents-md`
- `agent-orchestration-multi-agent-optimize`

Additional skills from other sources: PDF, PPTX, Excel, DOCX, frontend, fullstack, Android, iOS, shader, UI/UX design intelligence (50+ styles, 161 reasoning rules), git commit/push/PR commands, security best practices, Sentry issue tracking, code search/understanding, Python type checking, GitHub integration, frontend design intelligence, feature development workflow, semantic code editing, Claude Agent SDK development, PR review with specialized agents, E2E testing, autonomous agent loop, hook creation/management, Vercel deployment, plugin development, coding standards, TDD, security, E2E, backend/frontend patterns.

## Installed Plugins

Plugins providing extended functionality for Claude Code:

| Plugin | Source | Description |
|--------|--------|-------------|
| `minimax-skills` | MiniMax-AI/skills | PDF, PPTX, Excel, DOCX, frontend, fullstack, Android, iOS, shader |
| `ui-ux-pro-max` | nextlevelbuilder/ui-ux-pro-max-skill | UI/UX design intelligence — 50+ styles, 161 reasoning rules |
| `commit-commands` | claude-plugins-official | git commit, push, PR commands |
| `security-guidance` | claude-plugins-official | Security best practices |
| `sentry` | claude-plugins-official | Sentry issue tracking |
| `greptile` | claude-plugins-official | Code search/understanding |
| `pyright-lsp` | claude-plugins-official | Python type checking |
| `github` | claude-plugins-official | GitHub integration |
| `frontend-design` | claude-plugins-official | Frontend design intelligence |
| `feature-dev` | claude-plugins-official | Feature development workflow |
| `serena` | claude-plugins-official | Semantic code editing |
| `agent-sdk-dev` | claude-plugins-official | Claude Agent SDK development |
| `pr-review-toolkit` | claude-plugins-official | PR review with specialized agents |
| `playwright` | claude-plugins-official | E2E testing |
| `ralph-wiggum` | claude-plugins-official | Autonomous agent loop |
| `hookify` | claude-plugins-official | Hook creation/management |
| `vercel` | claude-plugins-official | Vercel deployment |
| `plugin-dev` | claude-plugins-official | Plugin development |
| `everything-claude-code` | everything-claude-code | Coding standards, TDD, security, E2E, backend/frontend patterns |
| `claude-mem` | thedotmack/claude-mem | Auto-captures sessions → compresses with AI → injects into future sessions |
| `claude-hud` | jarrodwatts/claude-hud | Real-time HUD: context bar, tools, agent status, todo progress |
| `planning-with-files` | OthmanAdi/planning-with-files | Manus-style persistent markdown planning (task_plan.md, findings.md, progress.md) |
| `visual-explainer` | nicobailon/visual-explainer | Terminal output → styled HTML pages & slides with Mermaid diagrams |
| `pg` (pg-aiguide) | timescale/pg-aiguide | PostgreSQL docs search + best-practice skills (4× more constraints) |
| `understand-anything` | Lum1104/Understand-Anything | Multi-agent codebase analysis with interactive knowledge graph |
| `superpowers` | obra/superpowers | Brainstorming, planning, TDD, debugging, code review, worktree skills |
| `python-development` | wshobson/agents | Python pro, django-pro, fastapi-pro agents |
| `backend-development` | wshobson/agents | Backend architect + agents |
| `database-design` | wshobson/agents | Database architect agents |
| `security-scanning` | wshobson/agents | Security auditor agents |
| `comprehensive-review` | wshobson/agents | Architect-review, code-reviewer, security-auditor agents |
| `tdd-workflows` | wshobson/agents | TDD workflow agents |
| `productivity` | anthropics/knowledge-work-plugins | Official Anthropic productivity plugin |
| `data` | anthropics/knowledge-work-plugins | Official Anthropic data plugin |
| `product-management` | anthropics/knowledge-work-plugins | Official Anthropic PM plugin |

## MCP Servers

Model Context Protocol (MCP) servers providing external data and tools:

| Server | Repo | Description |
|--------|------|-------------|
| Official MCP servers | modelcontextprotocol/servers | Filesystem, GitHub, Slack, etc. |
| MCP registry | modelcontextprotocol/registry | Discover community MCP servers |
| PostgreSQL guide | timescale/pg-aiguide | PostgreSQL docs semantic search |
| Graphiti | getzep/graphiti | Real-time knowledge graphs for agents |
| Cognee | topoteretes/cognee | Knowledge engine — 6-line agent memory |
| Excalidraw MCP | excalidraw/excalidraw-mcp | Diagramming inside Claude |
| Supermemory | supermemoryai/supermemory | Fast scalable memory engine |
| Hindsight | vectorize-io/hindsight | Agent memory that learns |
| Sentry MCP | getsentry/sentry-mcp | Sentry issue management |
| Microsoft Docs MCP | MicrosoftDocs/mcp | Microsoft Learn docs |
| IBM MCP | IBM/mcp | IBM services collection |
| PostgreSQL best practices | timescale/pg-aiguide | PostgreSQL best practices |

## Prompt Patterns and Rules

Prompt patterns and rules from starred repositories for enhanced AI interactions:

| Resource | Repo | Description |
|----------|------|-------------|
| Fabric | danielmiessler/Fabric | 200+ prompt patterns — copy as skills or rules |
| Telos | danielmiessler/Telos | Deep context framework — reference for CLAUDE.md structure |
| AGENTS.md | agentsmd/agents.md | AGENTS.md format spec — created AGENTS.md this session |
| Claude Code best practices | shanraisshan/claude-code-best-practice | Reference for CLAUDE.md |
| Ultimate guide | FlorianBruniaux/claude-code-ultimate-guide | Comprehensive Claude Code guide |
| System prompts | x1xhlol/system-prompts-and-models-of-ai-tools | System prompt leaks — reference |
| System prompts collection | asgeirtj/system_prompts_leaks | System prompt collection — reference |
| Prompt decorators | smkalami/prompt-decorators | Prompt decorators (+++Reason) — add to system prompt |
