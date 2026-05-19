# Tech Organization Agent System

A multi-agent CLI that simulates a full software development team. You play the **customer** — describe your project, answer questions, and the team handles requirements, architecture, planning, and more.

---

## The Team

| Agent | Name | Role |
|---|---|---|
| 🎯 Orchestrator | **Aria** | Routes work, synthesizes responses, manages memory |
| 📋 PM | **Alex** | Scope, timelines, risk, priorities |
| 🔍 BSA | **Morgan** | Requirements, user stories, acceptance criteria |
| 💻 Developer | **Sam** | Implementation, APIs, database, code architecture |
| ⚡ Tech Lead | **Jordan** | System design, technology selection, code review |
| 🔬 Researcher | **Riley** | Technology evaluation, best practices, comparisons |
| ✅ QA | **Casey** | Testing strategy, quality gates, edge cases |
| 🚀 DevOps | **Taylor** | CI/CD pipelines, cloud infrastructure, deployments |

Default active team: **PM · BSA · Developer · Lead**. Researcher, QA, and DevOps can be added on demand — either manually or automatically by Aria when the project needs them.

---

## Setup

**Prerequisites:** Python 3.10+, an [Anthropic API key](https://console.anthropic.com/)

```bash
git clone https://github.com/keyurnandu/family-agents.git
cd family-agents
pip install -r requirements.txt
```

Set your API key:

```bash
# Windows
set ANTHROPIC_API_KEY=sk-ant-...

# macOS / Linux
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Usage

```bash
# Start a new project (prompts for a name)
python cli.py

# Resume an existing project
python cli.py --project my-app

# List all saved projects
python cli.py --list

# Use a specific model
python cli.py --model claude-opus-4-7
```

---

## In-Session Commands

| Command | Description |
|---|---|
| `/team` | Show the active team roster |
| `/add <role>` | Add an agent (e.g. `/add qa`) |
| `/remove <role>` | Remove an agent (e.g. `/remove devops`) |
| `/memory` | View saved project memory |
| `/history` | Show recent conversation |
| `/project` | Show project stats |
| `/clear` | Reset context window (keeps memory) |
| `/help` | Full help |
| `/quit` | Exit |

---

## How It Works

### Orchestration
Every message you send goes to **Aria**, who decides which specialists to consult. Aria collects their responses and synthesizes a unified reply. Agents can also call each other — for example, Sam (Developer) can consult Riley (Researcher) for a technology recommendation mid-task.

```
You → Aria → Alex (PM) + Morgan (BSA)
                  ↓
             Morgan → Sam (Developer) [peer consult]
                  ↓
             Aria synthesizes → You
```

### Memory
Two layers of memory persist across sessions:

- **Role memory** (`memory/roles/*.md`) — each agent's predefined identity, responsibilities, and working style. Edit these to tune agent behavior.
- **Project memory** (`memory/dynamic/<project>/memory.md`) — decisions, requirements, and constraints captured during your conversations. Auto-saved when:
  - You say *"remember that…"* or *"note that…"*
  - An agent outputs `REMEMBER: …`
  - Aria detects a key decision or constraint

### Conversation History
Full conversation history is stored in `db/conversations.db` (SQLite). Projects resume seamlessly — the last session's context is loaded automatically.

---

## Project Structure

```
family-agents/
├── cli.py                  # Entry point
├── orchestrator.py         # Central coordinator (Aria)
├── agents/
│   └── agent.py            # Generic specialist agent
├── memory/
│   └── roles/              # Predefined role definitions (markdown)
│       ├── orchestrator.md
│       ├── pm.md
│       ├── bsa.md
│       ├── developer.md
│       ├── lead.md
│       ├── researcher.md
│       ├── qa.md
│       └── devops.md
├── utils/
│   ├── db_manager.py       # SQLite conversation history
│   ├── memory_manager.py   # Project memory read/write
│   └── display.py          # Rich terminal UI
├── config/
│   └── settings.yaml       # Model, team roster, agent personas
└── requirements.txt
```

> `db/` and `memory/dynamic/` are excluded from git — they contain your local project data.

---

## Customizing Agents

Each agent's behavior is defined by its role memory file in `memory/roles/`. Open any `.md` file to adjust the agent's identity, responsibilities, communication style, or routing preferences. Changes take effect immediately on the next run — no code changes needed.

To add a completely new role:
1. Create `memory/roles/<role>.md`
2. Add the role to `config/settings.yaml` under `agent_personas` and `team.available_agents`

---

## Configuration (`config/settings.yaml`)

```yaml
model: claude-sonnet-4-6       # default model
max_tokens: 4096
max_tool_iterations: 12        # max agent calls per user message
max_history_messages: 10       # conversation turns loaded on resume

team:
  default_roster: [pm, bsa, developer, lead]
  available_agents: [researcher, qa, devops]
```
