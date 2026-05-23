# family-agents — Architecture Flow Diagram

High-level technical flow covering every major subsystem: CLI → Orchestrator → Agents → Action Executor → Learning Loop → Memory.

---

```mermaid
flowchart TD
    USER((👤 User)) -->|types in terminal| CLI_IN


    %% ─────────────────────────────────────────────
    subgraph CLI["🖥️  cli.py  —  Entry Point"]
        CLI_IN[Input Parser]
        CLI_IN -->|slash command| CMD{Command\nrouter}
        CMD -->|/team /add /remove| ROSTER[Team roster management]
        CMD -->|/memory /history /status| VIEW[View commands]
        CMD -->|/redo| REDO[Re-send or edit\nlast message]
        CMD -->|/paste · """| PASTE[Paste mode\naccumulate multi-line\nthen /end to send]
        CMD -->|/skill add/list/remove| SKILLS_CMD[Skill management]
        CMD -->|/export type| EXPORT[Export doc\nrequirements · architecture\nsprint-plan · api-docs]
        CMD -->|/auto on/off| AUTO_CMD[Auto-approve config\nfile + bash approval only]
        CMD -->|/tdd on/off/health| TDD_CMD[TDD mode config]
        CMD -->|/load path| CODEBASE[Load codebase\ninto context]
        CMD -->|/model alias| MODEL_SW[Switch model\nhaiku · sonnet · opus]
        CMD -->|/retrospective| RETRO_CMD[Per-agent reflection]
        CMD -->|/feedback agent text| FB_CMD[Inject lesson directly]
        CMD -->|/new · /switch| PROJ_SW[Project management\nSQLite]
        CLI_IN -->|plain message| PROCESS
    end

    %% ─────────────────────────────────────────────
    subgraph ORCH["🎯  orchestrator.py  —  Aria"]
        PROCESS[process\nuser_input]

        PROCESS --> TC[1 · Load per-turn caches\n📄 docs  🧠 memory  🧪 TDD state\nloaded ONCE — reused by all agents]

        TC --> ROUTE[2 · Aria routes via Haiku\ncall_claude_json → JSON phase plan\ncached by roster + mem_count + TDD]

        ROUTE --> PH{3 · Phase loop\nsequential}

        PH --> PAR[Run agents in parallel\nThreadPoolExecutor\none task per agent]

        PAR --> AOUT[Collect raw responses]

        AOUT --> AEXEC[4 · ActionExecutor\nparse EXEC: blocks]

        AEXEC --> OCM[Outcomes list\nFILE WRITTEN · BASH OK/FAILED\nHEALTH_CHECK PASSED/FAILED]

        OCM --> LCHK[5 · Check for lessons\nbatch all failures →\nsingle Haiku call]

        OCM --> PSUM[Phase summary\nnarrative ≤800c\n+ ACTIONS TAKEN ≤1500c]

        PSUM -->|context for next phase| PH

        PH -->|all phases done| SYNTH[6 · Synthesis\n_trim_for_synthesis\nstrips EXEC + condenses OUTPUT\nper-agent cap 1600 chars\nAria writes final summary]

        SYNTH --> DISP[Display to user\n+ token bar\n% of safe_context_tokens\ndefault 200k]

        DISP --> AUTO_CHK{Actionable work?\n_has_actionable_work}
        AUTO_CHK -->|yes| APILOT[_auto_pilot_decide\nHaiku JSON call\ncontinue? next_message?\nretry-aware: self-healed failures\ndon't trigger failure exit]
        APILOT -->|continue + next_msg| PROCESS
        APILOT -->|done or max 5| STOP((🛑))
        AUTO_CHK -->|no| STOP
    end

    %% ─────────────────────────────────────────────
    subgraph AGENT_SYS["💻  agents/agent.py  —  Specialist Agents"]
        AG_CALL[agent.call task]

        AG_CALL --> PCACHE{Prompt cache hit?\nkey = role · project\n· mem_count · skills_mtime\n· codebase_hash}

        PCACHE -->|miss| BUILD_SP[Build system prompt\n① role guide  memory/roles/role.md\n② role-filtered memory\n   PM/BSA → requirements+decisions\n   Dev/Lead → technical+decisions\n③ EXEC instructions for impl roles\n④ skills files  auto-learned.md\n⑤ codebase context if loaded\n⑥ per-turn docs injected]

        PCACHE -->|hit| CLAUDE_CALL

        BUILD_SP --> STORE_CACHE[Store in Agent._prompt_cache\nclass-level dict · LRU cap=20]
        STORE_CACHE --> CLAUDE_CALL

        CLAUDE_CALL[claude --print subprocess\nprompt via stdin\nno API key needed]

        CLAUDE_CALL --> AG_RESP[Agent response text\nwith optional EXEC: blocks]
    end

    %% ─────────────────────────────────────────────
    subgraph AE["⚙️  action_executor.py  —  Action Executor"]
        AE_PARSE[Parse EXEC: blocks\nvia regex split]

        AE_PARSE --> FILE_PATH[EXEC:file:path\nShow diff stats table\nNEW +added  EDIT +added -removed\nd=show full diff  y=apply  N=skip\nOne collective prompt for batch]

        AE_PARSE --> BASH_PATH[EXEC:bash\nIndividual confirm prompt\nnormalize_bash_command strips abs paths\nsubprocess capture_output=True\nprint to terminal AND inject to outcomes\ncapped at 3000 chars]

        FILE_PATH -->|approved| FILE_WRITE[Write files to disk\nproject_dir / path]

        FILE_WRITE --> TDD_HC[TDD health check\nauto-runs health cmd after every write\ne.g. pytest --collect-only\nor python -m py_compile]

        TDD_HC -->|FAILED| LCHK

        BASH_PATH -->|done| BASH_OUT[BASH OK/FAILED + OUTPUT\n→ outcomes list]
    end

    %% ─────────────────────────────────────────────
    subgraph LEARN["📚  Learning Loop  —  _apply_lesson"]
        LCHK --> APPLY

        RETRO_CMD --> RETRO_REFL[Each agent\n1 Haiku call per role\nreflect on session]
        RETRO_REFL --> APPLY

        FB_CMD --> APPLY

        APPLY[_apply_lesson\nrole · lesson]

        APPLY -->|① persist| SKILL_FILE[Save to\nmemory/skills/role/auto-learned.md\ntimestamped · survives restarts]

        APPLY -->|② invalidate cache| EVICT[Evict Agent._prompt_cache\nfor this role\nnext call rebuilds prompt\nwith lesson included]

        APPLY -->|③ inject to history| MSG_INJ[Append to self.messages\nLESSON LEARNED by Name\nvisible in conversation immediately\nno restart needed]

        MSG_INJ --> RETRY[_retry_after_lesson\nre-invoke agent with lesson in context\nproduce corrected EXEC: blocks\ncapped at 1 retry per role per phase]

        RETRY -->|success| RETRY_OK[RETRY OUTCOMES:\nBASH OK / FILE WRITTEN\nauto-pilot sees self-heal → continues]
        RETRY -->|failed again| RETRY_FAIL[RETRY OUTCOMES:\nBASH FAILED\nauto-pilot stops\npremature flag saved]
        RETRY_FAIL -->|user types continue| RESUME[_run_autopilot_loop\nresume from saved context\nfresh iteration counter]
    end

    %% ─────────────────────────────────────────────
    subgraph ARIA_INTEL["🧠  Aria Intelligence Layer"]
        CG[Clarification gate\npre-filter: large build + vague + early?\n→ 1 Haiku call → ask one question\nbefore routing if needed]

        CE[Confidence escalation\nHaiku routing thin for complex msg?\n→ re-run with Sonnet automatically]

        BA[Bench agent inclusion\nAria can pull in researcher·qa·devops\nfor any phase without /add command]

        IV[Intent verification\nheuristic: asked for code → got prose?\n→ surface warning to user]

        PS_UPDATE[_update_project_state\nbackground daemon thread + _state_lock\nHaiku writes state.md after every turn\n— what exists · in progress · decisions · next steps]

        PS_READ[_load_project_state\nread state.md → _turn_state\ninjected into routing prompt + synthesis\nso next turn Aria reasons from facts not inference]
    end

    %% ─────────────────────────────────────────────
    subgraph MEM["🗄️  Memory Layer"]
        DB[(SQLite\ndb_manager.py\npersistent connection\nprojects · messages\ntimestamps)]

        MD_MEM[(memory/dynamic/project/\nmemory.md\ndecisions · requirements\ntechnical · notes · epic-plans)]

        MD_SKILLS[(memory/skills/role/\nauto-learned.md\ncustom skill files .md)]

        MD_ROLES[(memory/roles/role.md\nrole identity · responsibilities\nbehaviours · output format)]

        STATE_FILE[(projects/name/state.md\nstructured project snapshot\nupdated every turn in background)]
    end

    %% ─────────────────────────────────────────────
    %% Cross-subgraph connections
    PAR --> AG_CALL
    AEXEC --> AE_PARSE
    LCHK --> APPLY
    TC --> MD_MEM
    TC --> MD_SKILLS
    TC --> PS_READ
    BUILD_SP --> MD_MEM
    BUILD_SP --> MD_SKILLS
    BUILD_SP --> MD_ROLES
    PROCESS --> DB
    PROCESS --> CG
    CG -->|needs clarification| USER
    CG -->|clear enough| ROUTE
    ROUTE --> CE
    CE --> PHASE
    PAR --> BA
    BA -->|bench pulled in| AGENT_SYS
    SYNTH --> IV
    IV -->|mismatch| USER
    DISP --> USER
    REDO --> PROCESS
    PASTE --> PROCESS
    EXPORT --> PROCESS
    RETRO_CMD -.->|triggers| PROCESS
    SYNTH --> PS_UPDATE
    PS_UPDATE --> STATE_FILE
    PS_READ --> STATE_FILE

    %% ─────────────────────────────────────────────
    %% Styling
    classDef userNode fill:#1a1a2e,stroke:#e94560,color:#fff,rx:50
    classDef cliBox fill:#16213e,stroke:#0f3460,color:#e0e0e0
    classDef orchBox fill:#0f3460,stroke:#533483,color:#e0e0e0
    classDef agentBox fill:#533483,stroke:#e94560,color:#fff
    classDef execBox fill:#1b4332,stroke:#40916c,color:#e0e0e0
    classDef learnBox fill:#3d1a00,stroke:#f4a261,color:#fff
    classDef memBox fill:#1c1c1c,stroke:#555,color:#ccc

    class USER userNode
```

---

## Key Design Decisions

| Concern | Approach |
|---|---|
| **No SDK / API key** | All LLM calls go through `claude --print` subprocess; prompt via stdin (bypasses 32k Windows cmd limit) |
| **Parallel execution** | Agents within a phase run in `ThreadPoolExecutor`; phases are sequential so dev always has requirements first |
| **Prompt cache** | Class-level `Agent._prompt_cache` keyed by `role·project·mem_count·skills_mtime·codebase_hash` — rebuilds only when something actually changes; capped at 20 entries with LRU eviction |
| **Per-turn cache** | `_turn_docs`, `_turn_memory`, `_turn_tdd`, `_turn_auto`, `_turn_state` loaded once at the start of `process()` — not re-loaded for every agent call |
| **Role-filtered memory** | PM/BSA see requirements+decisions; Dev/Lead see technical+decisions — no agent reads irrelevant categories |
| **Bash output capture** | `capture_output=True` → printed to terminal AND injected into outcomes so agents can reason about test results |
| **Lesson immediacy** | `_apply_lesson` does three things atomically: persist to disk, evict prompt cache, inject into `self.messages` — active in the next response |
| **Safe context** | Token bar shows `session_tokens / safe_context_tokens` (configurable in `settings.yaml`, default 200k) |
| **TDD mode** | Health check runs automatically after every approved file write; failure feeds directly into lesson extraction |
| **Phase summaries** | Split at `ACTIONS TAKEN:` boundary — narrative capped at 800 chars, actions block at 1500 chars — prevents long agent responses from burying action data |
| **Project state** | `state.md` updated by Haiku in a background thread after every turn (guarded by `_state_lock`) — Aria reads it at turn-start so routing and synthesis reason from a structured snapshot, not raw conversation inference |
| **Clarification gate** | Pre-filter (large-build regex + word count + low context) then one Haiku JSON call — asks one question before wasting a phase on the wrong interpretation |
| **Bench agents** | Routing schema allows any agent; phase executor announces and pulls in bench roles without requiring `/add` — then they return to bench after the phase |
| **Confidence escalation** | If Haiku routing produces a thin plan (≤1 agent, <60 char task) on a long message, automatically re-runs with Sonnet |
| **Intent verification** | Heuristic check — user asked for code but agents produced only prose → surface a clear warning with suggested action |
| **Synthesis per-agent cap** | Each agent response truncated to 1600 chars before synthesis — prevents a single verbose agent from blowing up Aria's context window |
| **Persistent DB connection** | `DBManager` opens one SQLite connection on init and reuses it — no per-query open/close overhead |
| **CLI check cache** | `claude` binary existence verified once per process via `shutil.which()` — subsequent calls skip the check |
| **Module-level regexes** | All hot-path regexes (`_CODE_TASK_RE`, `_IMPL_RE`, `_CORRECTION_RE`, etc.) compiled once at module load — zero per-call compilation cost |
| **Config pass-through** | `settings.yaml` parsed once in `cli.py` and passed as a dict — Orchestrator never re-reads YAML |
| **Shared EXEC instructions** | The "Executing Actions" prompt block defined once as `_EXEC_INSTRUCTIONS` in `agent.py` — injected only for implementation roles (`developer`, `lead`, `qa`, `devops`); non-impl roles never see it |
| **Single-pass file count** | `build_tree()` counts files as it walks the directory tree — no separate `rglob("*")` traversal |
| **Hash-based memory dedup** | `save_project_memory()` compares full normalized content against parsed entries — replaces fragile `[:60]` substring check that caused false positives |
| **Bench agent consultation** | `_get_peer_input` allows any instantiated agent to be consulted via `ASK_COLLEAGUE` — including bench agents (researcher, qa, devops) not on the active roster; only truly non-existent roles are rejected |
| **Bash path normalization** | `normalize_bash_command()` case-insensitively strips absolute paths (write_dir + project_dir + base_dir, longest first) from EXEC:bash commands before `subprocess.run` — prevents WinError 206 even when a codebase is `/load`ed at a different path than the OneDrive project dir; agent prompts also instruct agents to use relative paths since cwd is already set |
| **Export doc update-in-place** | `export_doc()` globs `docs/{type}*.md` before generating — if found, the existing doc's full content is injected into the prompt with "update and enhance" instructions; the file is overwritten in place instead of creating a dated duplicate |
| **Export anti-truncation** | Export prompt explicitly overrides brevity rules: "Write the COMPLETE, full-length document — ignore any brevity rules. Output the entire document with no truncation." Summary extraction raised from 5000→10000 chars |
| **Export docs in loaded codebase** | When a codebase is `/load`ed, `export_doc()` writes to `loaded_path/docs/` (not `projects/<name>/docs/`), file list reflects the loaded codebase, and `load_project_docs()` checks both locations (deduped by filename, loaded path takes priority) |
| **Auto-approve** | `/auto on` auto-approves file writes + safe bash (no interactive prompt); destructive commands (`rm -rf`, `DROP TABLE`, `git push --force`, etc.) matched via `_DESTRUCTIVE_PATTERNS` regex list always require manual confirmation |
| **Always-on auto-pilot** | After synthesis, `_has_actionable_work()` checks for multi-phase routing or ACTIONS TAKEN in responses — if actionable, `_auto_pilot_decide()` asks Haiku if a concrete next step exists; not gated by `/auto` toggle (that only controls approval); `_turn_auto` temporarily set to False during recursion to prevent nested loops; Ctrl+C breaks out cleanly |
| **Auto-pilot safety** | Three guards checked before/after each Haiku call: (1) failure exit — `BASH FAILED` or `HEALTH_CHECK: FAILED` in last response → stop unless the response also contains progress markers (`BASH OK`/`HEALTH_CHECK: PASSED`/`FILE WRITTEN`), meaning the agent is actively fixing things (zero-cost string check, no LLM call); (2) duplicate detection — `SequenceMatcher.ratio() > 0.80` against all previous `next_message` strings → stop on loops; (3) hard cap at `MAX_AUTO_ITERATIONS=5`. Guards 1-3 flag premature stops (`premature: True`) so the loop can distinguish "work done" from "stopped early" |
| **Auto-pilot resume** | When auto-pilot stops prematurely (cap/failure/duplicate), saves `_pending_autopilot` context (original request + last pilot context + stop reason). User types "continue"/"resume"/"go" → `process()` detects this, calls `_run_autopilot_loop()` with the saved context, and the loop picks up where it left off with a fresh iteration counter. Ctrl+C does NOT save pending (user chose to stop). Refactored: inline loop extracted to `_run_autopilot_loop()` — reused by both initial trigger and resume path |
| **Export-aware auto-pilot** | `_augment_pilot_context_for_export()` detects when the last auto-pilot iteration was a doc export (message starts with `[Generated`) and appends the original user request + "intermediate sub-step" signal — prevents Haiku from stalling after doc generation. Export path also saves rich messages with next-step hints from `_EXPORT_NEXT_HINTS` and calls `_update_project_state` before returning |
| **Test suite** | 172 pytest tests covering all optimizations — all written TDD (red→green), run in <7s with zero LLM dependencies |
