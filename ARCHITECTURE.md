# Family Agents — Architecture Flow Diagram

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

        PH -->|all phases done| SYNTH[6 · Synthesis\n_trim_for_synthesis\nstrips EXEC + condenses OUTPUT\nAria writes final summary]

        SYNTH --> DISP[Display to user\n+ token bar\n% of safe_context_tokens\ndefault 200k]
    end

    %% ─────────────────────────────────────────────
    subgraph AGENT_SYS["💻  agents/agent.py  —  Specialist Agents"]
        AG_CALL[agent.call task]

        AG_CALL --> PCACHE{Prompt cache hit?\nkey = role · project\n· mem_count · skills_mtime\n· codebase_hash}

        PCACHE -->|miss| BUILD_SP[Build system prompt\n① role guide  memory/roles/role.md\n② role-filtered memory\n   PM/BSA → requirements+decisions\n   Dev/Lead → technical+decisions\n③ skills files  auto-learned.md\n④ codebase context if loaded\n⑤ per-turn docs injected]

        PCACHE -->|hit| CLAUDE_CALL

        BUILD_SP --> STORE_CACHE[Store in Agent._prompt_cache\nclass-level dict]
        STORE_CACHE --> CLAUDE_CALL

        CLAUDE_CALL[claude --print subprocess\nprompt via stdin\nno API key needed]

        CLAUDE_CALL --> AG_RESP[Agent response text\nwith optional EXEC: blocks]
    end

    %% ─────────────────────────────────────────────
    subgraph AE["⚙️  action_executor.py  —  Action Executor"]
        AE_PARSE[Parse EXEC: blocks\nvia regex split]

        AE_PARSE --> FILE_PATH[EXEC:file:path\nShow diff stats table\nNEW +added  EDIT +added -removed\nd=show full diff  y=apply  N=skip\nOne collective prompt for batch]

        AE_PARSE --> BASH_PATH[EXEC:bash\nIndividual confirm prompt\nsubprocess capture_output=True\nprint to terminal AND inject to outcomes\ncapped at 3000 chars]

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
    end

    %% ─────────────────────────────────────────────
    subgraph MEM["🗄️  Memory Layer"]
        DB[(SQLite\ndb_manager.py\nprojects · messages\ntimestamps)]

        MD_MEM[(memory/dynamic/project/\nmemory.md\ndecisions · requirements\ntechnical · notes · epic-plans)]

        MD_SKILLS[(memory/skills/role/\nauto-learned.md\ncustom skill files .md)]

        MD_ROLES[(memory/roles/role.md\nrole identity · responsibilities\nbehaviours · output format)]
    end

    %% ─────────────────────────────────────────────
    %% Cross-subgraph connections
    PAR --> AG_CALL
    AEXEC --> AE_PARSE
    LCHK --> APPLY
    TC --> MD_MEM
    TC --> MD_SKILLS
    BUILD_SP --> MD_MEM
    BUILD_SP --> MD_SKILLS
    BUILD_SP --> MD_ROLES
    PROCESS --> DB
    DISP --> USER
    REDO --> PROCESS
    PASTE --> PROCESS
    EXPORT --> PROCESS
    RETRO_CMD -.->|triggers| PROCESS

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
| **Prompt cache** | Class-level `Agent._prompt_cache` keyed by `role·project·mem_count·skills_mtime·codebase_hash` — rebuilds only when something actually changes |
| **Per-turn cache** | `_turn_docs`, `_turn_memory`, `_turn_tdd` loaded once at the start of `process()` — not re-loaded for every agent call |
| **Role-filtered memory** | PM/BSA see requirements+decisions; Dev/Lead see technical+decisions — no agent reads irrelevant categories |
| **Bash output capture** | `capture_output=True` → printed to terminal AND injected into outcomes so agents can reason about test results |
| **Lesson immediacy** | `_apply_lesson` does three things atomically: persist to disk, evict prompt cache, inject into `self.messages` — active in the next response |
| **Safe context** | Token bar shows `session_tokens / safe_context_tokens` (configurable in `settings.yaml`, default 200k) |
| **TDD mode** | Health check runs automatically after every approved file write; failure feeds directly into lesson extraction |
| **Phase summaries** | Split at `ACTIONS TAKEN:` boundary — narrative capped at 800 chars, actions block at 1500 chars — prevents long agent responses from burying action data |
