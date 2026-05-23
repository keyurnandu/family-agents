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

### Verify the installation

```bash
pytest
```

195 tests should pass in under 7 seconds. Tests cover all internal optimizations (caching, dedup, threading, regex compilation, path normalization, auto-approve, destructive command detection, always-on auto-pilot, loop safety guards) without requiring an LLM connection.

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

You (sonnet): _
```

The prompt always shows which model is active. It updates live when you `/model` switch.

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
You (sonnet): build a login page with HTML, CSS, and JS
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
You (sonnet): what's the difference between REST and GraphQL?
You (sonnet): how should I structure a Node.js monorepo?
You (sonnet): @sam what are your capabilities?
```
Saved as **💬 General chat** so nothing is lost. Use `/new <name>` or `/switch` to move into a project anytime.

**Switch model mid-session** — no need to restart. The prompt updates immediately:
```
/model haiku    → You (haiku): _
/model opus     → You (opus): _
/model sonnet   → You (sonnet): _
/model          # show what's currently active
```

**Ctrl+C** — interrupt any running agent and return to the prompt immediately. Then use `/redo` to edit and re-send your last message without retyping it.

**Paste mode** — paste multi-line content (pytest output, error logs, long prompts) as a single message instead of line-by-line:

```
You (sonnet): /paste
Paste mode opened — paste your content below, then type /end to send.
  ···: FAILED tests/test_api.py::test_login - AssertionError
  ···: FAILED tests/test_api.py::test_logout - ImportError
  ···: 2 failed, 23 passed in 4.1s
  ···: /end

  Submitting 3 lines as one message…
```

`"""` also works as an opener/closer if your terminal handles it. Use `/paste` + `/end` for reliability.

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
| `/auto on\|off\|status` | Auto-approve file writes + safe bash (auto-pilot is always on) |
| `/tdd on\|off\|status` | Toggle TDD mode — Casey writes tests first, Sam implements, health check runs after every write |
| `/tdd health <cmd>` | Set the health check command (e.g. `python -c "from app.main import app"`) |
| `/switch [name\|number]` | Switch to another project — case-insensitive, shows picker if no arg |
| `/switch _general` | Switch to the general chat workspace |
| `/new <name>` | Create and switch to a brand new project |
| `/clear` | Reset context window — keeps all memory and history |
| `/redo` | Re-send or edit your last message — pre-filled prompt, press Enter to re-send or type a correction |
| `/paste` | Open paste mode — type or paste multi-line content, then `/end` to send as one message |
| `/end` | Close paste mode and send everything as a single message |
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
You (sonnet): generate a requirements doc
You (sonnet): export the architecture decisions
You (sonnet): create a sprint plan from what we've discussed
You (sonnet): write a technical spec
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
You (sonnet): implement the login epic from the requirements

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

## Auto-Approve (`/auto`) & Always-On Auto-Pilot

### Auto-approve: reduce approval friction

`/auto` controls whether file writes and safe bash commands are auto-approved. Auto-pilot (Aria deciding next steps) is always active regardless of this setting.

```
/auto on      # auto-approve file writes + safe bash
/auto off     # require manual approval for all actions
/auto status  # show current setting
```

| Action | `/auto on` | `/auto off` (default) |
|---|---|---|
| File writes (EXEC:file) | ⚡ Auto-approved | Prompt (d/y/N) |
| Safe bash (npm install, pytest, etc.) | ⚡ Auto-approved | Prompt (Allow?) |
| **Destructive bash** (rm -rf, DROP TABLE, git push --force, etc.) | **Always prompts** | Prompt (Allow?) |
| **Path escape** (commands/files referencing paths outside the project) | **Blocked** | **Blocked** |

### Always-on auto-pilot

Aria automatically decides the next logical step after every turn that produces actionable work (multi-phase routing or file writes/bash execution). No toggle needed — this is always active.

For simple Q&A or informational responses, Aria stops and waits for your input.

```
You (sonnet): build the auth system with JWT

🤖 Auto-pilot  iteration 1/5  Now implement the login endpoint…
🤖 Auto-pilot  iteration 2/5  Write tests for the auth middleware…
🤖 Auto-pilot  iteration 3/5  Implement the registration flow…

⚠ Auto-pilot reached 5 iterations — pausing for your input.
  💡 Work may be incomplete. Type continue to resume auto-pilot.

You: continue
🤖 Auto-pilot resuming  original: build the auth system with JWT
🤖 Auto-pilot  iteration 1/5  Add rate limiting to login endpoint…
```

Press **Ctrl+C** at any time to interrupt the auto-pilot loop. Type **continue**, **resume**, or **go** to pick up where it left off.

### Safety guards

Auto-pilot has three built-in guards that prevent getting stuck:

| Guard | What it does |
|---|---|
| **Failure exit** | If the last iteration had `BASH FAILED` or `HEALTH_CHECK: FAILED`, auto-pilot stops — unless the response also shows progress (`FILE WRITTEN`, `BASH OK`, or `HEALTH_CHECK: PASSED`), meaning the agent is actively fixing things |
| **Duplicate detection** | Tracks all previous auto-pilot messages. If the next step is >80% similar to any previous one, stops — it's a loop |
| **Hard cap** | After 5 iterations, always pauses for your input regardless of what Aria decides |
| **Resume on incomplete** | When auto-pilot stops prematurely (cap, failure, or duplicate loop), it saves context and prompts you to type `continue` to resume where it left off |

---

## Test-Driven Development (TDD) Mode

Enable TDD mode for a project and the team enforces the red-green loop automatically — no manual prompting needed.

```
/tdd on       # enable (prompts for a health check command)
/tdd off      # disable
/tdd status   # show current state
/tdd health python -c "from app.main import app"   # update health check only
```

### What happens when TDD is on

**Routing changes:** For every implementation task, Aria automatically creates two sequential phases:

```
Phase 1 — Write Tests    Casey writes failing tests for the feature
               │  test files fed as context ↓
Phase 2 — Implement      Sam implements until the tests pass
```

**After every approved file write**, the health check runs automatically:
```
🧪 TDD health check running…  python -c "from app.main import app"
  ✓ Health check passed

# or if it fails:
  ✗ Health check FAILED
  ImportError: cannot import name 'StepRunStatus' from 'app.models.test_case'
```

If the check fails, the output is shown immediately so Sam can fix the broken import before moving on — breaking imports never accumulate.

### Health check command

Set it to whatever verifies your project is in a clean state:

| Project type | Suggested command |
|---|---|
| Python / FastAPI | `venv\Scripts\python.exe -c "from app.main import app"` |
| Python / any | `venv\Scripts\python.exe -m pytest --collect-only -q` |
| Node.js | `npm test -- --passWithNoTests` |
| Generic import | `python -c "import mymodule"` |

The command is saved to project memory and **persists across sessions** — set it once, it runs forever until you change it.

### TDD is per-project

Each project has its own TDD mode and health check command. Switching projects restores that project's TDD settings automatically.

### `/tdd status` output

```
TDD Mode: ON
Health check: venv\Scripts\python.exe -c "from app.main import app"
Workflow: Casey writes tests first → Sam implements → health check runs after every file write
```

The `/status` command also shows TDD mode in the project snapshot.

---

## Agents See Command Output

When an agent runs a shell command via `EXEC:bash`, the full output is captured and fed back into their context — so they can read test results, errors, and logs and respond accordingly in the same turn.

```
Sam wants to run:  venv\Scripts\python.exe -m pytest tests/ -v
  Allow? [y/N]: y

  Running…

========================= test session starts ==========================
collected 25 items

tests/test_selectors.py .....  [ 20%]
tests/test_models.py ..........[ 60%]
tests/test_api.py ..........   [100%]

========================= 25 passed in 3.42s ===========================

  ✓ Done  (exit 0)
```

Sam's next response will say "All 25 tests passed — implementation is complete" because he actually read the output, not just "the command ran".

If a test fails, Sam sees the full traceback and fixes the issue immediately. **Never ask an agent to "run pytest and tell me the results"** — use `EXEC:bash` so the agent sees the output directly.

---

## Agent Self-Learning — The Feedback Loop

Every agent improves automatically over time. Lessons from failures, corrections, and reflections are saved to their skill files and loaded in every future session.

### Three ways agents learn

**1. Automatically from failures**

Every time a bash command fails or a TDD health check fails after a file write, the responsible agent immediately extracts a lesson and saves it:

```
✗ Exited 1  ('uv' is not recognized…)
  📚 💻 Sam learned: Never use uv on this machine — use venv\Scripts\python.exe instead.
```

No user action needed. The lesson is **active immediately** — the agent's prompt cache is evicted and the lesson is injected into the conversation history so the very next response reflects it.

**2. From your corrections**

When you correct an agent's approach, the lesson is automatically detected and saved:

```
You (sonnet): stop using uv — it's not installed, use venv\Scripts\python.exe

  📚 💻 Sam learned: Never use uv on this machine — always use venv\Scripts\python.exe directly.
```

Correction patterns detected: "stop doing", "never use", "don't", "wrong because", "you should have", "next time", "always use instead".

**3. `/retrospective` — deliberate reflection**

At the end of a session, ask every agent to reflect on their own performance and save a lesson:

```
/retrospective

💻 Sam reflecting…
  → Never attempt to run pytest without first verifying the import chain is clean
  ✓ Saved to Sam's skills — active immediately

⚡ Jordan reflecting…
  → Always check all callers of a module before renaming or removing a symbol
  ✓ Saved to Jordan's skills — active immediately

✅ Casey reflecting…
  → Before writing tests, confirm the test runner can collect them with --collect-only
  ✓ Saved to Casey's skills — active immediately
```

Lessons are injected into the conversation history and the agent's prompt cache is evicted — the very next response reflects the new knowledge. No restart needed.

**`/feedback <agent> <lesson>`** — inject a lesson directly:

```
/feedback @sam never use uv on Windows — it's not installed
/feedback jordan always audit all imports from a file before modifying it
/feedback casey check venv exists before writing pytest commands
```

Feedback also applies immediately — the agent corrects course in the same session without needing a restart.

### Where lessons are stored

All auto-learned lessons accumulate in `memory/skills/<role>/auto-learned.md` — one file per agent, timestamped entries. Loaded automatically into every agent's system prompt alongside manually-added skills.

```
# Auto-Learned Lessons — developer

### [2026-05-21 14:32] via bash-failure
Never use uv on this machine — 'uv' is not recognized. Use venv\Scripts\python.exe.

### [2026-05-21 15:01] via health-check-failure
Before writing files that import from a model, verify all referenced symbols exist in that model.

### [2026-05-21 15:45] via retrospective
Always scan all files importing from a module before modifying it — fix all callers in one pass.
```

### The compound effect

Each session the team is a little better than the last. Over weeks of use, agents accumulate a detailed, project-specific knowledge base of what works and what doesn't on your machine, in your codebase, with your workflow.

---

## Teaching the Team New Skills

Any agent can be taught new skills that persist across all projects and sessions. Skills are stored as markdown files in `memory/skills/<role>/` and are automatically included in the agent's system prompt.

### Natural language — just tell the team:
```
You (sonnet): teach sam React Native
You (sonnet): the dev team needs to learn AWS
You (sonnet): morgan should know event storming
You (sonnet): add GraphQL expertise to jordan
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
You (sonnet): review the architecture and flag any concerns
You (sonnet): @jordan what would you change about this API design?
You (sonnet): @casey what test coverage is missing?
You (sonnet): how does the authentication flow work?
```

If an agent needs to go deeper into a specific file, it requests it automatically with `READ_FILE:<path>` — no action needed from you.

### Reading files instantly

Simple file-read requests are served directly from disk — **zero LLM calls**, instant response.

**Exact filename** (any file with an extension):
```
You (sonnet): show config.py
You (sonnet): read sprint.md
You (sonnet): display src/auth/middleware.ts
You (sonnet): show full requirements.txt      ← no truncation, complete file
```

**Fuzzy doc name** (keywords matched against your exported docs folder — no extension needed):
```
You (sonnet): read the sprint details          → matches sprint-plan-2026-05-20.md
You (sonnet): show epics and stories           → matches epics-and-user-stories-*.md
You (sonnet): can you read the requirements    → matches requirements-doc-*.md
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
| `venv/` *(Python only)* | Virtual environment — created automatically via `python -m venv venv && pip install -r requirements.txt` as the final scaffold step |

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
│   ├── db_manager.py         # SQLite conversation history (persistent connection)
│   ├── memory_manager.py     # Project memory read/write (hash-based dedup)
│   └── display.py            # Rich terminal UI
├── tests/                    # 195 tests — all TDD, run with `pytest`
│   ├── conftest.py           # Shared fixtures (base_dir, config, db_path)
│   ├── test_smoke.py         # Smoke test for fixture integrity
│   ├── test_claude_client.py # CLI check caching
│   ├── test_regexes.py       # Module-level regex validation
│   ├── test_imports.py       # No inline imports, synthesis trimming
│   ├── test_db_manager.py    # Persistent connection, CRUD operations
│   ├── test_prompt_cache.py  # Cache eviction at cap
│   ├── test_config_pass.py   # Config pass-through to Orchestrator
│   ├── test_synthesis.py     # Per-agent response capping
│   ├── test_memory_dedup.py  # Hash-based dedup, no false positives
│   ├── test_build_tree.py    # Single-pass file counting
│   ├── test_state_lock.py    # Threading lock on state updates
│   ├── test_role_trim.py     # Shared EXEC instructions, role file limits
│   ├── test_peer_consult.py  # Bench agent consultation via ASK_COLLEAGUE
│   ├── test_path_length.py   # Windows path normalization (WinError 206, multi-dir)
│   └── test_export_doc.py    # Doc export: update existing, no truncation
├── config/
│   └── settings.yaml         # Model, team roster, agent personas
├── pytest.ini                # Test configuration
└── requirements.txt          # click, rich, pyyaml, pytest — no anthropic SDK
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

### Built-in token optimizations

Several optimizations run automatically to keep token usage low:

| Optimization | What it does |
|---|---|
| **Per-turn cache** | Docs, memory, TDD config, and project state loaded once per message — shared across all routing, agent, and synthesis calls |
| **Routing prompt cache** | Aria's routing prompt rebuilt only when the team roster, memory, TDD state, or project state actually changes — not on every message |
| **Role-filtered memory** | Each agent only receives memory categories relevant to their domain (PM/BSA skip technical entries; Developer/Lead skip requirement noise) |
| **Synthesis output trimming** | Large pytest/bash output blocks condensed to a 3-line summary before Aria's synthesis call — saves 500–2000 tokens on code-heavy turns |
| **Synthesis per-agent cap** | Each agent's response is capped at ~400 tokens (1600 chars) before being fed into synthesis — prevents a single verbose agent from dominating Aria's context |
| **Batched lesson extraction** | Multiple failures in one turn produce a single haiku call for all lessons instead of one call per failure |
| **Codebase content hash** | Agent system prompt cache invalidates correctly when files change on disk, not just when the path changes |
| **Prompt cache eviction** | `Agent._prompt_cache` capped at 20 entries with LRU eviction — prevents unbounded memory growth across projects |
| **Persistent DB connection** | Single SQLite connection reused for the session instead of opening/closing per query — eliminates repeated connection overhead |
| **CLI check cache** | `claude` CLI existence verified once per process, not on every LLM call |
| **Module-level regexes** | All frequently-used regexes compiled once at module load — not recompiled inside hot methods |
| **Config pass-through** | `settings.yaml` parsed once at startup and passed to Orchestrator — no redundant YAML re-reads |
| **Shared EXEC instructions** | The "Executing Actions" prompt section is defined once in code and injected only for implementation roles (developer, lead, qa, devops) — eliminated ~60 lines of duplication across role files |
| **Single-pass file count** | `build_tree` counts files during its directory walk instead of a separate `rglob("*")` traversal |
| **Thread-safe state updates** | Background `_update_project_state` protected by a threading lock — prevents concurrent writes from stomping on each other |
| **Hash-based memory dedup** | Memory dedup compares full normalized content against parsed entries instead of a fragile 60-char substring check — no false positives on entries sharing a common prefix |
| **Bench agent consultation** | Any instantiated agent (including bench agents not on the active roster) can be consulted via `ASK_COLLEAGUE` — only truly non-existent roles are rejected |
| **Bash path normalization** | `normalize_bash_command()` case-insensitively strips absolute paths from EXEC:bash commands before execution — handles write_dir, project_dir, and base_dir simultaneously (longest first) to prevent WinError 206 on long Windows/OneDrive paths, even when a codebase is `/load`ed at a different path |

### How Aria routes smarter

Six intelligence layers run automatically every turn:

| Feature | How it works |
|---|---|
| **Project state document** | After every exchange Aria updates `state.md` in the background — what's built, decisions made, what's next. Injected into routing so Aria never re-derives context from scratch |
| **Clarification gate** | For large/vague new-build requests with little existing context, Aria asks one focused question before routing — prevents a wasted phase on the wrong interpretation |
| **Dynamic bench agents** | Aria can pull in `researcher`, `qa`, or `devops` for a phase even if they're not on the active team — no `/add` needed when the task clearly requires their specialty |
| **Confidence escalation** | If Haiku produces a thin plan for a complex message (single agent, vague task), routing automatically re-runs with Sonnet |
| **Intent verification** | After agents respond, a heuristic check detects if the user asked for code but only got prose — surfaces a clear warning |
| **State-aware next steps** | Aria's synthesis reads `state.md` to suggest concrete next actions (e.g. "auth is done → write tests") instead of generic options |
| **Auto-retry after lesson** | When a bash command or health check fails, the agent learns a lesson AND immediately retries to fix the problem in the same turn — no manual re-send needed. If the retry succeeds, auto-pilot continues instead of stopping on the stale failure |

### Routing speed

Aria's routing decision runs on `routing_model` (default: `haiku`) — a separate, faster model from the one agents use. This makes the "Aria is routing…" step noticeably quicker without sacrificing response quality.

| Setting | Default | Effect |
|---|---|---|
| `routing_model` | `haiku` | Model for Aria's routing call — haiku is ~3× faster than sonnet |
| `max_routing_memory` | `8` | Memory entries sent to routing — lower = smaller prompt = faster |

Routing also uses a stripped-down system prompt: no full document content (just titles), no role definitions, no codebase tree — only what Aria needs to decide *who* to ask.

#### New `/state` command

```
/state
```

Shows the current `state.md` — a live structured snapshot of the project:

```
# Project State

## What exists
- auth/login.py (complete)
- api/routes.py (complete)

## In progress
- Payment integration (started, not complete)

## Open decisions
- DB: chose PostgreSQL (2026-05-10)

## Next logical steps
- Add integration tests for the auth flow
- Wire up payment webhooks
- Deploy to staging
```

Updated automatically after every exchange. Also visible in `/status`.

---

## Configuration

**`config/settings.yaml`**

```yaml
model: sonnet            # alias: haiku / sonnet / opus
routing_model: haiku     # model used for Aria's routing decision — haiku is faster and sufficient
safe_context_tokens: 200000  # token threshold for the context bar — set to your model's context window
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
