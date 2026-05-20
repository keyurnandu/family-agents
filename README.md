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

**Switch model mid-session** — no need to restart:
```
/model haiku    # switch to faster/cheaper for simple questions
/model opus     # switch to most powerful for deep analysis
/model sonnet   # back to default
/model          # show what's currently active
```

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
| `/model [alias]` | Show current model or switch — `haiku` · `sonnet` · `opus` |
| `/load <path>` | Load an existing codebase for review or editing |
| `/unload` | Unload the current codebase |
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

Each document is written by the most relevant agent (BSA for requirements, Lead for architecture, PM for sprint plans, etc.), saved as `docs/<type>-<date>.md`, and a confirmation is shown with the path and suggested next steps:

```
✓ Document created: projects/my-app/docs/requirements-doc-2026-05-20.md  42 lines · 3,210 chars
  Read it: show requirements-doc-2026-05-20.md
  Next:    start sprint planning or implementation
```

### Guided workflow — Aria always suggests what's next

After every team response, Aria closes with a **What would you like to do next?** section offering 2–3 concrete options based on where the project is:

```
What would you like to do next?
• Start implementation — Sam and Jordan can begin coding the core mechanics
• Refine the requirements — add more detail to any epic before building
• Generate a sprint plan — break the work into sprints and assign stories
```

This keeps the conversation moving without you having to guess what's possible.

### Picking up where you left off

After a document is exported, two things happen automatically:

1. **Compact summary saved to memory** — key epics, stories, decisions extracted as bullet points and saved to project memory. Persists across sessions.
2. **Full doc loaded into agent context** — on every subsequent session, the 3 most recent docs are injected directly into each agent's system prompt.

This means in a new session the team already knows your requirements, epics, and sprint plan — they won't re-analyse or ask again. They pick up and keep working:

```
New session, project: my-app
You: implement the login epic from the requirements

→ Sam already has the full requirements doc
→ Knows: Epic 1 = Authentication (login, register, password reset)
→ Goes straight to implementation, no re-discovery
```

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

`/load` works anywhere — before or after opening a project. If no project is open, the folder name is automatically used as the project name so each codebase gets its own isolated memory, history, and docs.

```bash
/load C:\projects\my-app
/load /home/user/my-api
/load C:\Users\you\OneDrive\Desktop\my-backend    ← OneDrive paths work fine
```

There is **no filesystem sandbox** — Python has full read/write access to any path on your machine. `/load` simply tells the team *where to look*. Once loaded, the path is saved and **auto-reloaded every session** so you never have to run `/load` again for the same project.

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
│  Agents can read any file. Suggest changes? One prompt.  │
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

### Reading files instantly

Simple file-read requests are served directly from disk — **zero LLM calls**, instant response.

**Exact filename** (any file with an extension):
```
You: show config.py
You: read sprint.md
You: display src/auth/middleware.ts
You: show full requirements.txt      ← no truncation, complete file
```

**Fuzzy doc name** (keywords matched against your exported docs folder — no extension needed):
```
You: read the sprint details          → matches sprint-plan-2026-05-20.md
You: show epics and stories           → matches epics-and-user-stories-*.md
You: can you read the requirements    → matches requirements-doc-*.md
```

Works with intent words: `read`, `show`, `display`, `view`, `open`, `print`, `cat`, `get`, `fetch`, `see`. The file is shown with syntax highlighting and line numbers.

- Default cap: **20,000 chars**. Anything larger shows a truncation note.
- Add `full` / `entire` / `complete` to remove the cap entirely.

For agents doing work (e.g. "work on Epic 1"), they read files mid-task via `READ_FILE:<path>`. Reads are capped at `max_read_file_chars` (default 20,000). Review, audit, and analysis tasks automatically get the full file with no cap — the agent needs everything to give useful feedback.

The team sees your folder structure to **depth 3** (e.g. `app/services/runner/`) so they can reference deep files by their actual path. If a path is slightly off, a filename fuzzy search finds the right file automatically.

### Applying changes

When an agent suggests file changes, you see a compact summary with diff stats and a single prompt:

```
Sam wants to write 3 files to C:\projects\my-app:
  ✨  playwright_runner.py    NEW   +142   from app.core.config import…
  ✏   app/core/config.py     +12 -4       from pydantic_settings import…
  ✏   requirements.txt       +3 -1        fastapi==0.111.0…

  d = show diff · y = apply · N = skip

  Apply all changes? [d/y/N]
```

- **y** — applies everything at once
- **n** — discards all
- **d** — shows the full colour-coded diff (green = added, red = removed) before you decide. Type `d` again to re-read, then `y` or `n`

New files show `✨ NEW` with a line count. Modified files show `+added -removed` counts so you know exactly what changed before approving.

### Memory across sessions

When you load a codebase, the path is saved to project memory. Next time you open the same project you get a prompt:

```
Last session had /path/to/my-app loaded — reload it? [y/N]
```

- **y** — the team rescans the codebase and picks up exactly where you left off  ← **press this**
- **n** (default) — skipped; use `/load` again anytime
- If the path no longer exists (moved or deleted), the reference is silently cleared

The codebase is **reloaded automatically** every time you open the project — no prompt, no keypress needed. If the path no longer exists (moved or deleted) the reference is silently cleared.

Any decisions, notes, or architectural discussions from previous sessions are already in project memory — the team picks up exactly where you left off.

### Unload

```
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

Tech stack is inferred from your description. Scaffolding runs exactly once — on the first message of a new project. Skipped for general chat and for any project opened via `/load` (the codebase already exists).

### Memory

Two layers of memory persist across sessions:

**Role memory** (`memory/roles/*.md`)
Each agent's identity, responsibilities, and working style. Edit any `.md` file to tune how that agent thinks and communicates. Changes take effect on the next run — no code changes needed.

**Project memory** (`memory/dynamic/<project>/memory.md`)
Facts, decisions, and constraints captured during your conversations. Auto-saved when:
- You say *"remember that…"* or *"note that…"*
- An agent outputs `REMEMBER: …` in its response
- Aria identifies a key decision or constraint worth persisting
- You kick off an epic or story — a plan summary (which epic, what steps, which files) is automatically extracted and saved under category `epic-plan` so the team can pick up exactly where they left off in future sessions

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

## Token Usage & Optimization

### Live feedback

Every message now shows a compact token summary after the team responds:

```
~1,400 tokens this message  ·  session ~9,800  ·  12% of safe context
```

Turns yellow at 50% and shows a warning at 75%:

```
~3,200 tokens this message  ·  session ~65,000  ·  81% of safe context  ⚠ context large — consider /clear
```

Use `/status` for a full breakdown with a visual bar.

### Optimization tips

| Action | Impact |
|---|---|
| `/model haiku` for simple questions | ~10× cheaper than Sonnet, plenty fast for Q&A |
| `/model opus` only for deep analysis | Save it for architecture decisions or complex reviews |
| `/clear` when context bar goes yellow | Resets the context window — memory and history stay |
| Keep `max_history_messages` low | Each resumed message costs tokens on every call |
| `/unload` codebase when not needed | Codebase tree + key files go into every agent prompt |
| Lower `max_memory_entries` | Controls how many memory entries agents see per call |

### What consumes the most tokens

1. **Codebase loaded** — the folder tree and key files are injected into every agent's system prompt on every message. Unload when you're done reviewing.
2. **Multi-agent phases** — a 4-agent response = 4 full system prompts + 1 routing call + 1 synthesis call. Single-agent @mentions are far cheaper.
3. **Project memory growth** — by default agents only see the last 40 memory entries (full history stays on disk). Tune with `max_memory_entries` in `config/settings.yaml`.
4. **Long conversation history** — tune `max_history_messages` in `config/settings.yaml` (default: 10).

### Zero-cost operations

These bypass the LLM pipeline entirely:

| Request | Cost |
|---|---|
| `show config.py` / `read sprint.md` | 0 LLM calls — served direct from disk |
| `show full requirements.txt` | 0 LLM calls — full file, no truncation |
| `/memory`, `/history`, `/status`, `/team` | 0 LLM calls — local data only |
| `show the team` / `show memory` / `project status` | 0 LLM calls — natural-language shortcuts |
| `teach sam React Native` | 0 routing + synthesis — handled then exits |
| `/export <type>` | 1 LLM call (the doc writer), no routing or synthesis |

### Routing speed

Aria's routing decision runs on `routing_model` (default: `haiku`) — a separate, faster model from the one agents use. This makes the "Aria is routing…" step noticeably quicker without sacrificing response quality.

Two config knobs control routing overhead:

| Setting | Default | Effect |
|---|---|---|
| `routing_model` | `haiku` | Model for Aria's routing call — haiku is ~3× faster than sonnet |
| `max_routing_memory` | `8` | Memory entries sent to routing — lower = smaller prompt = faster |

Routing also uses a stripped-down system prompt: no full document content (just titles), no role definitions, no codebase tree — only what Aria needs to decide *who* to ask.

---

## Configuration

**`config/settings.yaml`**

```yaml
model: sonnet            # alias: haiku / sonnet / opus
routing_model: haiku     # model used for Aria's routing decision — haiku is faster and sufficient
max_history_messages: 10 # conversation turns loaded when resuming a project
max_memory_entries: 15   # memory entries injected into agent prompts (full history kept on disk)
max_routing_memory: 8    # memory entries passed to routing (smaller = faster routing calls)
max_project_docs: 1      # docs injected into agent prompts (most recent only; full docs on disk)
max_doc_chars: 1500      # chars per injected doc (say 'show full <doc>.md' to see complete file)
max_read_file_chars: 20000  # chars per READ_FILE request; review/audit tasks always get the full file

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
