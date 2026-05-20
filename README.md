# Tech Organization Agent System

A multi-agent CLI that simulates a full software development team. You play the **customer** — describe your project, ask questions, and your AI team handles requirements, architecture, planning, research, and more.

No API key required. Runs entirely through your locally installed **Claude Code** CLI.

---

## The Team

| | Agent | Name | @mention | Speciality |
|---|---|---|---|---|
| 🎯 | Orchestrator | **Aria** | — | Routes work between specialists, synthesizes responses, manages project memory |
| 📋 | PM | **Alex** | `@alex` | Scope, timelines, risk management, stakeholder priorities |
| 🔍 | BSA | **Morgan** | `@morgan` | Requirements, user stories, acceptance criteria, process mapping |
| 💻 | Developer | **Sam** | `@sam` | Implementation, APIs, database design, code architecture |
| ⚡ | Tech Lead | **Jordan** | `@jordan` | System design, technology selection, code review, non-functional requirements |
| 🔬 | Researcher | **Riley** | `@riley` | Technology evaluation, best practices, comparative analysis |
| ✅ | QA | **Casey** | `@casey` | Testing strategy, quality gates, test cases, edge cases |
| 🚀 | DevOps | **Taylor** | `@taylor` | CI/CD pipelines, cloud infrastructure, deployments, monitoring |

**Default active team:** PM · BSA · Developer · Lead

Researcher, QA, and DevOps join automatically when the project needs them, or you can add them manually with `/add <role>`.

---

## Prerequisites

- Python 3.10+
- [Claude Code](https://claude.ai/code) installed and logged in

That's it — no API keys, no environment variables.

---

## Setup

```bash
git clone https://github.com/keyurnandu/family-agents.git
cd family-agents
pip install -r requirements.txt
```

---

## Usage

```bash
# Start — one You: prompt handles everything
python cli.py

# Skip straight into a specific project
python cli.py --project my-app

# List all saved projects (non-interactive)
python cli.py --list

# Use a faster/cheaper model
python cli.py --model haiku

# Use a more powerful model
python cli.py --model opus
```

### Startup

On launch you get a single `You:` prompt. The screen shows your saved projects (if any) and a one-line hint above it:

```
──────────────── Your Projects ────────────────
  1  restaurant-saas    3 msgs · today
  2  my-portfolio       12 msgs · Mon
  💬 General chat  ·  5 msgs · today
────────────────────────────────────────────────

Type a number to resume, a name to start new, just start talking for adhoc questions, or /help.

You: _
```

| Input | What happens |
|---|---|
| `1` | Resume project #1 |
| `my-app` | Create / open project named my-app |
| `what is REST?` | Auto-routes to general chat (no project needed) |
| `/help` | Show help panel |
| `/team` | Show team roster |
| `/quit` | Exit |

---

## Talking to the Team

**Normal message** — Aria routes automatically to the right agents, who work in parallel within each phase:
```
You: build a login page with HTML, CSS, and JS
→ Sam (Developer) and Jordan (Lead) work simultaneously
→ Aria synthesizes their responses
```

**@mention** — talk directly to one agent by name, skipping routing entirely:
```
@sam add unit tests for the calculator
@jordan what architecture would you recommend?
@morgan write user stories for the checkout flow
@riley compare Redis vs Memcached for our use case
@casey what edge cases should we test?
@taylor set up a CI/CD pipeline
```

Both the friendly name (`@sam`) and the role key (`@developer`) are accepted.

**General chat** — no project needed. Just start talking and the team answers:
```
You: what's the difference between REST and GraphQL?
You: how should I structure a Node.js monorepo?
You: @sam what are your capabilities?
```
Saved as **💬 General chat** so nothing is lost. Use `/new <name>` or `/switch` to move into a project anytime.

**Ctrl+C** — interrupt any running agent and return to the prompt immediately.

---

## In-Session Commands

| Command | Description |
|---|---|
| `/team` | Show active team roster with @mention shortcuts |
| `/add <role>` | Add an agent (e.g. `/add qa`) |
| `/remove <role>` | Remove an agent (e.g. `/remove devops`) |
| `/memory` | View everything saved to project memory |
| `/history` | Show recent conversation turns |
| `/project` | Show project stats (messages, memory items, model) |
| `/status` | Project snapshot — memory, files, token usage, docs |
| `/export <type>` | Generate a doc (requirements, architecture, sprint-plan…) |
| `/switch [name\|number]` | Switch to another project — shows picker if no arg |
| `/switch _general` | Switch to the general chat workspace |
| `/new <name>` | Create and switch to a brand new project |
| `/clear` | Reset context window — keeps all memory and history |
| `/load <path>` | Load an existing codebase for review or editing |
| `/unload` | Unload the current codebase |
| `/edit-mode on\|off` | Enable or disable writes to the loaded codebase |
| `/help` | Show full help |
| `/quit` | Exit |

**Available roles:** `pm` · `bsa` · `developer` · `lead` · `researcher` · `qa` · `devops`

---

## Export & Reports

After a project conversation, generate clean documents directly from what's been discussed and decided. Saved to `projects/<name>/docs/`.

**Natural language:**
```
You: generate a requirements doc
You: export the architecture decisions
You: create a sprint plan from what we've discussed
You: write a technical spec
```

**Command:**
```
/export requirements
/export architecture
/export technical-spec
/export sprint-plan
/export api-docs
/export test-plan
/export deployment-plan
```

Each document is written by the most relevant agent (BSA for requirements, Lead for architecture, PM for sprint plans, etc.), saved as `docs/<type>-<date>.md`, and a preview is shown in the terminal.

---

## Project Status

`/status` gives a live snapshot of where a project stands:

```
╭─ Status: restaurant-saas ──────────────────────────╮
│  Messages:  47  ·  Last active: today               │
│  Team:      pm · bsa · developer · lead             │
│  Skills:    3 total across team                     │
│                                                     │
│  Memory (12 items)                                  │
│    decision 5   requirement 4   technical 3         │
│                                                     │
│  Files (8 created · 2 docs)                         │
│    index.js  app.js  package.json  …                │
│                                                     │
│  Session  14 calls · ~8,400 tokens estimated        │
│  ████████████░░░░░░░  60% of safe context           │
╰─────────────────────────────────────────────────────╯
```

The token bar turns yellow at 50% and red at 80% — a signal to consider `/clear` before the context window fills up.

---

## Teaching the Team New Skills

Any agent can be taught new skills that persist across all projects and sessions. Skills are stored as markdown files in `memory/skills/<role>/` and are automatically included in the agent's system prompt.

### Natural language — just tell the team:
```
You: teach sam React Native
You: the dev team needs to learn AWS
You: morgan should know event storming
You: add GraphQL expertise to jordan
```

### Command:
```
/skill add developer          → prompted for skill name and description
/skill add developer aws      → prompted for description only
/skill list                   → show all skills for all roles
/skill list developer         → show Sam's skills
/skill remove developer aws   → remove a skill
```

Skills show up in `/team` as a count next to each agent so you always know what the team has learned. Skill content is AI-generated from your description — a few focused bullet points are added to the agent's system prompt.

---

## Codebase Review & Editing

Point the team at any existing project on your machine — they'll scan it, understand the structure, and help you review, extend, or refactor it.

### Load a codebase

```bash
/load C:\projects\my-app
/load /home/user/my-api
```

On load, the team automatically:
- Builds a depth-2 folder tree of the project
- Reads key files (`README`, entry points, config files, `package.json` / `requirements.txt`, etc.)
- Detects the tech stack
- Saves a summary to project memory

A panel confirms what was found:

```
╭─ Codebase Loaded ───────────────────────────────────────╮
│  ✓ Codebase loaded                                       │
│                                                          │
│  Path:       C:\projects\my-app                          │
│  Tech stack: TypeScript, React, Node.js                  │
│  Files:      84 total · 6 key files read                 │
│                                                          │
│  Structure:                                              │
│    my-app/                                               │
│    ├── src/                                              │
│    │   ├── components/                                   │
│    │   └── api/                                          │
│    └── package.json                                      │
│                                                          │
│  Mode: READ-ONLY — use /edit-mode on to enable writes    │
╰─────────────────────────────────────────────────────────╯
```

### Talk to the team about the codebase

Once loaded, just chat normally — agents know the full structure and key file contents:

```
You: review the architecture and flag any concerns
You: @jordan what would you change about this API design?
You: @casey what test coverage is missing?
You: how does the authentication flow work?
```

If an agent needs to go deeper into a specific file, it requests it automatically with `READ_FILE:<path>` — no action needed from you.

### Deep dives on specific files

You can also ask directly:

```
You: @sam walk me through src/auth/middleware.ts
You: explain what the database migration scripts do
```

The agent will read the file on demand and explain it in context.

### Edit mode

By default the codebase is **read-only** — agents can analyse and suggest, but nothing is written. When you're ready to apply changes:

```bash
/edit-mode on    # allow agents to write to the loaded codebase
/edit-mode off   # back to read-only
```

With edit mode on, agents write files using the same permission-prompted flow as normal project files — you approve each write before it happens.

### Memory across sessions

When you load a codebase, the path is saved to project memory. Next time you open the same project you get a prompt:

```
Last session had /path/to/my-app loaded — reload it? [y/N]
```

- **y** — the team rescans the codebase and picks up exactly where you left off
- **n** — skipped; use `/load` again anytime
- If the path no longer exists (moved or deleted), the reference is silently cleared

Any decisions, notes, or architectural discussions from previous sessions are already in project memory — even after a reload, the team has full context.

### Unload

```bash
/unload    # removes the codebase from the team's context and clears the saved path
```

---

## How It Works

### Orchestration

Every message goes to **Aria**, who decides which specialists to involve and what to ask each of them. After collecting their responses, Aria synthesizes a clear unified reply. Agents can also consult each other mid-task.

```
You
 └─▶ Aria (routing)
       ├─▶ Alex (PM)    ──▶ responds
       └─▶ Morgan (BSA) ──▶ consults Sam (Developer) ──▶ responds
             │
             ▼
       Aria (synthesis)
             │
             ▼
            You
```

### Phase-Aware Workflow

For complex tasks Aria automatically organises work into **sequential phases**, so each team hands off to the next only when their work is done. Agents **within a phase run in parallel**.

```
Phase 1 — Requirements    PM + BSA work in parallel
               │  output fed as context ↓
Phase 2 — Implementation  Developer + Lead work in parallel
               │  output fed as context ↓
Phase 3 — QA              Casey tests the implementation
               │  output fed as context ↓
Phase 4 — DevOps          Taylor deploys after QA passes
```

Simple questions or discussions are handled in a single phase — everyone answers in parallel immediately. Aria decides the right shape for every message.

### Auto-Scaffolding

When you describe a new project for the first time, Developer and Lead automatically scaffold the full folder and file structure to developer standards — before any feature work begins. Every file is permission-prompted before it is written.

| File / Folder | Description |
|---|---|
| `README.md` | Project overview, tech stack, setup steps |
| `.gitignore` | Stack-appropriate ignores |
| `.env.example` | Placeholder environment variables |
| `package.json` / `requirements.txt` / etc. | Dependency file for the chosen stack |
| `src/` / `lib/` / `app/` | Source folders with `.gitkeep` |
| Entry point | `src/index.js`, `src/main.py`, `src/App.tsx`, etc. with starter boilerplate |
| Config files | `tsconfig.json`, `.eslintrc`, `pytest.ini`, `Makefile`, etc. as appropriate |

Tech stack is inferred from your description. Scaffolding runs exactly once — on the first message of a new project. Skipped for general chat.

### Memory

Two layers of memory persist across sessions:

**Role memory** (`memory/roles/*.md`)
Each agent's identity, responsibilities, and working style. Edit any `.md` file to tune how that agent thinks and communicates. Changes take effect on the next run — no code changes needed.

**Project memory** (`memory/dynamic/<project>/memory.md`)
Facts, decisions, and constraints captured during your conversations. Auto-saved when:
- You say *"remember that…"* or *"note that…"*
- An agent outputs `REMEMBER: …` in its response
- Aria identifies a key decision or constraint worth persisting

Use `/memory` at any time to review what's been captured.

### Conversation History

Full conversation history is stored in `db/conversations.db` (SQLite). When you resume a project, the last session's context loads automatically.

---

## Project Structure

```
family-agents/
├── cli.py                    # Entry point and REPL
├── orchestrator.py           # Aria — central coordinator and router
├── agents/
│   └── agent.py              # Generic specialist agent (all roles use this)
├── memory/
│   └── roles/                # Predefined role definitions (plain markdown)
│       ├── orchestrator.md
│       ├── pm.md
│       ├── bsa.md
│       ├── developer.md
│       ├── lead.md
│       ├── researcher.md
│       ├── qa.md
│       └── devops.md
├── projects/                 # Agent-created files land here (one folder per project)
│   └── <project-name>/
│       ├── src/
│       └── ...
├── utils/
│   ├── action_executor.py    # Permission-prompted file/command execution
│   ├── claude_client.py      # Subprocess wrapper for `claude --print`
│   ├── db_manager.py         # SQLite conversation history
│   ├── memory_manager.py     # Project memory read/write
│   └── display.py            # Rich terminal UI
├── config/
│   └── settings.yaml         # Model, team roster, agent personas
└── requirements.txt          # click, rich, pyyaml — no anthropic SDK
```

> `db/`, `memory/dynamic/`, and `projects/*/` are excluded from git — they contain your local project data. The `projects/` folder itself is tracked so it exists on a fresh clone.

---

## Where Project Files Go

When an agent creates a file or runs a command, a permission prompt appears in your terminal before anything executes:

```
💻 Sam wants to write  src/app.py
╭─ Create  src/app.py ─────────────────────╮
│  1  def main():                           │
│  2      print("Hello!")                   │
╰──────────────────────────────────────────╯
  Allow? [y/N]:
```

All approved files are written to:
```
family-agents/projects/<project-name>/
```

Each project gets its own subfolder — your source code is never touched.

---

## Customizing Agents

Every agent's behavior is driven by its role file in `memory/roles/`. Open any `.md` file and edit:
- The agent's identity and working style
- Their responsibilities and focus areas
- What clarifying questions they ask
- When they consult colleagues

To add a brand new role:
1. Create `memory/roles/<role>.md` with the agent's identity and instructions
2. Add the role to `config/settings.yaml` under `agent_personas` and `team.available_agents`

---

## Configuration

**`config/settings.yaml`**

```yaml
model: sonnet            # alias: haiku / sonnet / opus
max_history_messages: 10 # conversation turns loaded when resuming a project

team:
  default_roster: [pm, bsa, developer, lead]
  available_agents: [researcher, qa, devops]

agent_personas:
  pm:
    name: "Alex"
    emoji: "📋"
    color: "green"
  # ... one entry per role
```

**Model aliases** (passed to `claude --model`):
| Alias | Model | Best for |
|---|---|---|
| `haiku` | Claude Haiku | Fast responses, lower cost |
| `sonnet` | Claude Sonnet | Balanced — default |
| `opus` | Claude Opus | Complex architecture, deep analysis |

---

## How It Uses Claude Code

Every agent call is a `claude --print` subprocess — the same Claude you're already running. No SDK, no API key, no extra cost beyond your existing Claude subscription.

```
python cli.py
  └─▶ orchestrator.py: call_claude_json(routing_prompt)
        └─▶ claude --print --model sonnet --system-prompt "..." "..."
  └─▶ agents/agent.py: call_claude(task_prompt)
        └─▶ claude --print --model sonnet --system-prompt "..." "..."
```
