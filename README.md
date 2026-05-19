# Tech Organization Agent System

A multi-agent CLI that simulates a full software development team. You play the **customer** — describe your project, ask questions, and your AI team handles requirements, architecture, planning, research, and more.

No API key required. Runs entirely through your locally installed **Claude Code** CLI.

---

## The Team

| | Agent | Name | Speciality |
|---|---|---|---|
| 🎯 | Orchestrator | **Aria** | Routes work between specialists, synthesizes responses, manages project memory |
| 📋 | PM | **Alex** | Scope, timelines, risk management, stakeholder priorities |
| 🔍 | BSA | **Morgan** | Requirements, user stories, acceptance criteria, process mapping |
| 💻 | Developer | **Sam** | Implementation, APIs, database design, code architecture |
| ⚡ | Tech Lead | **Jordan** | System design, technology selection, code review, non-functional requirements |
| 🔬 | Researcher | **Riley** | Technology evaluation, best practices, comparative analysis |
| ✅ | QA | **Casey** | Testing strategy, quality gates, test cases, edge cases |
| 🚀 | DevOps | **Taylor** | CI/CD pipelines, cloud infrastructure, deployments, monitoring |

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
# Start — shows project picker if you have saved projects, or asks for a name on first run
python cli.py

# Skip the picker and jump straight into a project
python cli.py --project my-app

# List all saved projects (non-interactive)
python cli.py --list

# Use a faster/cheaper model
python cli.py --model haiku

# Use a more powerful model
python cli.py --model opus
```

### Startup picker

On first run you'll be asked for a project name. On every subsequent run a numbered list of your projects appears — type a number to resume or type a new name to create:

```
──────────────── Your Projects ────────────────
  1  restaurant-saas    3 msgs · today
  2  my-portfolio       12 msgs · Mon
────────────────────────────────────────────────

Resume [1-2], new name, or /help :
```

`/help`, `/list`, and `/quit` all work at this prompt too.

Once inside a project, just describe your work naturally.

### General chat (no project needed)

Not everything needs a project. Just start typing a question or sentence and the team answers immediately — no project name required:

```
You: what's the difference between REST and GraphQL?
You: how should I structure a Node.js monorepo?
You: @sam what are your capabilities?
```

The conversation is saved as **💬 General chat** so nothing is ever lost. Use `/new <name>` or `/switch` to move into a real project whenever you're ready.

```
You: I want to build a SaaS app for restaurant reservations
```

Aria routes your message to the right team members, they collaborate, and you get a unified response.

---

## Talking to the Team

**Normal message** — Aria routes automatically to the right agents, who work in parallel:
```
You: build a login page with HTML, CSS, and JS
→ Sam (Developer) and Jordan (Lead) work simultaneously
→ Aria synthesizes their responses
```

**@mention** — talk directly to one specific agent, skipping routing:
```
@sam add unit tests for the calculator
@jordan what architecture would you recommend?
@morgan write user stories for the checkout flow
@riley compare Redis vs Memcached for our use case
```

**Ctrl+C** — interrupt any running agent and return to the prompt immediately.

---

## In-Session Commands

| Command | Description |
|---|---|
| `/team` | Show the active team roster |
| `/add <role>` | Add an agent (e.g. `/add qa`) |
| `/remove <role>` | Remove an agent (e.g. `/remove devops`) |
| `/memory` | View everything saved to project memory |
| `/history` | Show recent conversation turns |
| `/project` | Show project stats (messages, memory items, model) |
| `/switch [name]` | Switch to another project (shows picker if no name given) |
| `/new <name>` | Create and switch to a brand new project |
| `/clear` | Reset context window — keeps all memory and history |
| `/help` | Show full help |
| `/quit` | Exit |

**Available roles:** `pm` · `bsa` · `developer` · `lead` · `researcher` · `qa` · `devops`

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
Phase 1 — Requirements  (PM + BSA work in parallel)
          │  output fed as context →
Phase 2 — Implementation  (Developer + Lead work in parallel)
          │  output fed as context →
Phase 3 — QA  (Casey tests the implementation)
          │  output fed as context →
Phase 4 — DevOps  (Taylor deploys after QA passes)
```

Simple questions or discussions that don't need sequencing are handled in a single phase (everyone works in parallel immediately). Aria decides the right shape for every message.

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

Full conversation history is stored in `db/conversations.db` (SQLite). When you resume a project with `--project <name>`, the last session's context loads automatically.

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
│       ├── index.html
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

The `projects/` folder is created automatically when you start a session. Each project gets its own subfolder — source code is never touched.

---

## How It Uses Claude Code

Every agent call is a `claude --print` subprocess — the same Claude you're already running. No SDK, no API key, no extra cost beyond your existing Claude subscription. The system passes each agent's role definition as a `--system-prompt` and the task as the prompt argument.

```
python cli.py
  └─▶ orchestrator.py: call_claude_json(routing_prompt)
        └─▶ claude --print --model sonnet --system-prompt "..." "..."
  └─▶ agents/agent.py: call_claude(task_prompt)
        └─▶ claude --print --model sonnet --system-prompt "..." "..."
```
