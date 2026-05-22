"""
Parses agent responses for executable actions (file writes, shell commands)
and prompts the user for permission before running them.

Agents signal an action by wrapping content in a tagged code block:

    EXEC:file:path/to/file.py
    ```
    <file content>
    ```

    EXEC:bash
    ```
    npm install && npm run build
    ```

File changes are collected and shown as a compact summary with diff stats —
NEW / +added -removed lines. One "apply all?" prompt for the whole batch.
Bash commands are confirmed individually.
"""
import difflib
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

console = Console()


def normalize_bash_command(
    cmd: str,
    project_dir: Path,
    extra_dirs: list[Path] | None = None,
) -> str:
    """Replace absolute paths in a bash command with relative paths.

    Agents sometimes emit full absolute paths (e.g. the OneDrive path) in
    EXEC:bash commands. On Windows this can exceed MAX_PATH (260 chars) and
    trigger WinError 206. Since subprocess already runs with cwd=project_dir,
    relative paths work correctly and avoid the length issue.

    When a codebase is /loaded at a short path (e.g. C:\\uishift\\backend2),
    agents may still reference the long OneDrive project_dir or the
    family-agents base_dir. Pass those as extra_dirs so they get stripped too.
    Longest paths are stripped first so nested paths don't partially match.
    """
    dirs = [project_dir]
    if extra_dirs:
        dirs.extend(extra_dirs)
    # Sort longest-first so e.g. base_dir/projects/app/ is tried before base_dir/
    dirs.sort(key=lambda d: len(str(d)), reverse=True)

    for d in dirs:
        abs_str = str(d)
        for variant in (abs_str, abs_str.replace("\\", "/")):
            for sep in (variant + "\\", variant + "/", variant):
                idx = cmd.lower().find(sep.lower())
                while idx != -1:
                    cmd = cmd[:idx] + cmd[idx + len(sep):]
                    idx = cmd.lower().find(sep.lower())
    return cmd


@dataclass
class Action:
    kind: Literal["file", "bash"]
    label: str       # file path or command summary
    content: str     # file content or bash script
    agent_name: str


def parse_actions(response_text: str, agent_name: str) -> list[Action]:
    """Extract EXEC: tagged blocks from an agent response."""
    actions: list[Action] = []

    chunks = re.split(r"(?=EXEC:(?:file:|bash))", response_text, flags=re.IGNORECASE)

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk.upper().startswith("EXEC:"):
            continue

        file_match = re.match(
            r"EXEC:file:([^\n]+)\n"
            r"```[^\n]*\n"
            r"(.*?)"
            r"```",
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if file_match:
            path = file_match.group(1).strip()
            content = file_match.group(2).strip()
            if content:
                actions.append(Action(kind="file", label=path, content=content, agent_name=agent_name))
            continue

        bash_match = re.match(
            r"EXEC:bash\s*\n"
            r"```[^\n]*\n"
            r"(.*?)"
            r"```",
            chunk,
            re.IGNORECASE | re.DOTALL,
        )
        if bash_match:
            content = bash_match.group(1).strip()
            if content:
                lines = content.splitlines()
                label = (lines[0] if lines else "shell command")[:80]
                actions.append(Action(kind="bash", label=label, content=content, agent_name=agent_name))

    return actions


def _diff_stats(old: str, new: str) -> tuple[int, int, int]:
    """Return (added, removed, changed_lines) between old and new content."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    added = removed = 0
    for line in difflib.unified_diff(old_lines, new_lines, lineterm=""):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
    return added, removed


def _show_diff(old: str, new: str, path: str):
    """Print a colour-coded unified diff for a file change."""
    old_lines = old.splitlines(keepends=True)
    new_lines = new.splitlines(keepends=True)
    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"  {path} (current)",
        tofile=f"  {path} (proposed)",
        lineterm="",
    ))
    if not diff:
        console.print("  [dim](no textual changes detected)[/dim]")
        return
    text = Text()
    for line in diff:
        if line.startswith("+++") or line.startswith("---"):
            text.append(line + "\n", style="dim")
        elif line.startswith("@@"):
            text.append(line + "\n", style="cyan dim")
        elif line.startswith("+"):
            text.append(line + "\n", style="green")
        elif line.startswith("-"):
            text.append(line + "\n", style="red")
        else:
            text.append(line + "\n", style="dim")
    console.print(text)


def _show_bash_action(action: Action):
    syntax = Syntax(action.content, "bash", theme="monokai")
    console.print(
        Panel(
            syntax,
            title="[bold]Run command[/bold]",
            border_style="yellow",
        )
    )


def run_health_check(cmd: str, cwd: Path) -> tuple[bool, str]:
    """
    Run a health-check command (e.g. import check or pytest --collect-only).
    Returns (passed, output_text).
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, "Health check timed out after 60 seconds."
    except Exception as e:
        return False, f"Health check error: {e}"


def prompt_and_execute(
    actions: list[Action],
    project_dir: Path,
    tdd_health_cmd: str | None = None,
    tdd_cwd: Path | None = None,
    normalize_dirs: list[Path] | None = None,
) -> list[str]:
    """
    File changes: show a compact summary with diff stats, one 'apply all?' prompt.
    If the user types 'd' at the prompt, the full diff is shown before re-asking.
    Bash commands: confirmed individually (higher risk).
    Returns outcome strings fed back to the agent pipeline.
    """
    if not actions:
        return []

    outcomes: list[str] = []
    file_actions = [a for a in actions if a.kind == "file"]
    bash_actions  = [a for a in actions if a.kind == "bash"]

    # ── File changes — one collective prompt ─────────────────────────
    if file_actions:
        console.print()

        agents_involved = sorted({a.agent_name for a in file_actions})
        agent_str = " & ".join(f"[bold yellow]{n}[/bold yellow]" for n in agents_involved)
        n = len(file_actions)
        console.print(
            f"{agent_str} want{'s' if len(agents_involved) == 1 else ''} to write "
            f"[bold]{n}[/bold] file{'s' if n > 1 else ''} to [cyan]{project_dir}[/cyan]:"
        )

        # Compact file table with diff stats
        table = Table(show_header=False, box=None, padding=(0, 1, 0, 0))
        table.add_column("icon", style="dim", no_wrap=True)
        table.add_column("path", style="cyan", no_wrap=True)
        table.add_column("stats", no_wrap=True)
        table.add_column("preview", style="dim")

        file_states: dict[str, dict] = {}  # label → {is_new, old_content, added, removed}
        for a in file_actions:
            dest = (project_dir / a.label).resolve()
            is_new = not dest.exists()
            old_content = ""
            added = removed = 0
            if not is_new:
                try:
                    old_content = dest.read_text(encoding="utf-8", errors="replace")
                    added, removed = _diff_stats(old_content, a.content)
                except Exception:
                    is_new = True  # treat as new if unreadable
            else:
                added = len(a.content.splitlines())

            file_states[a.label] = {
                "is_new": is_new,
                "old_content": old_content,
                "added": added,
                "removed": removed,
            }

            if is_new:
                stats = Text("NEW", style="bold green")
                stats.append(f"  +{added}", style="green")
            else:
                stats = Text()
                if added:
                    stats.append(f"+{added} ", style="green")
                if removed:
                    stats.append(f"-{removed}", style="red")
                if not added and not removed:
                    stats.append("unchanged", style="dim")

            lines = a.content.splitlines()
            preview = (lines[0][:50].strip() + "…") if lines and len(lines[0]) > 50 else (lines[0].strip() if lines else "")
            icon = "✨" if is_new else "✏ "
            table.add_row(icon, a.label, stats, preview)

        console.print(table)
        console.print("[dim]  d = show diff · y = apply · N = skip[/dim]")

        while True:
            raw = console.input(
                f"\n  Apply {'all ' if n > 1 else ''}{'change' if n == 1 else 'changes'}? [d/y/N] "
            ).strip().lower()
            if raw == "d":
                # Show diffs for all changed (non-new) files
                console.print()
                for a in file_actions:
                    state = file_states[a.label]
                    if state["is_new"]:
                        suffix = Path(a.label).suffix.lstrip(".") or "text"
                        console.print(f"\n[bold green]✨ NEW[/bold green]  [cyan]{a.label}[/cyan]")
                        console.print(Syntax(a.content[:3000], suffix, theme="monokai", line_numbers=True))
                    else:
                        console.print(f"\n[bold yellow]✏  DIFF[/bold yellow]  [cyan]{a.label}[/cyan]")
                        _show_diff(state["old_content"], a.content, a.label)
                console.print()
                console.print("[dim]  d = show diff again · y = apply · N = skip[/dim]")
                continue
            approved = raw in ("y", "yes")
            break

        if approved:
            console.print()
            for a in file_actions:
                dest = (project_dir / a.label).resolve()
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(a.content, encoding="utf-8")
                state = file_states[a.label]
                if state["is_new"]:
                    console.print(f"  [green]✓[/green]  {a.label}  [dim green](new)[/dim green]")
                else:
                    console.print(
                        f"  [green]✓[/green]  {a.label}  "
                        f"[green]+{state['added']}[/green] [red]-{state['removed']}[/red]"
                    )
                outcomes.append(f"FILE WRITTEN: {a.label}")
            console.print()

            # ── TDD health check — runs automatically after every approved write ──
            if tdd_health_cmd:
                check_dir = tdd_cwd or project_dir
                console.print(
                    f"[dim cyan]🧪 TDD health check running…[/dim cyan]  "
                    f"[dim]{tdd_health_cmd[:80]}[/dim]"
                )
                passed, output = run_health_check(tdd_health_cmd, check_dir)
                if passed:
                    console.print("  [bold green]✓ Health check passed[/bold green]\n")
                    outcomes.append("HEALTH_CHECK: PASSED")
                else:
                    console.print("  [bold red]✗ Health check FAILED[/bold red]")
                    # Show last 20 lines of output — enough for the agent to diagnose
                    lines = output.splitlines()
                    snippet = "\n".join(lines[-20:]) if len(lines) > 20 else output
                    console.print(f"[dim red]{snippet}[/dim red]\n")
                    outcomes.append(f"HEALTH_CHECK: FAILED\n{snippet}")
        else:
            console.print("  [dim]Changes skipped.[/dim]\n")
            for a in file_actions:
                outcomes.append(f"FILE SKIPPED: {a.label}")

    # ── Bash commands — individual prompts ───────────────────────────
    for action in bash_actions:
        console.print()
        console.print(f"[bold yellow]{action.agent_name}[/bold yellow] wants to run:")
        _show_bash_action(action)
        approved = Confirm.ask("  Allow?", default=False)

        if approved:
            console.print("  [dim]Running…[/dim]\n")
            # Normalize absolute paths to relative — prevents WinError 206
            # on long OneDrive paths where cmd.exe exceeds MAX_PATH.
            safe_cmd = normalize_bash_command(action.content, project_dir, normalize_dirs)
            # Capture output so we can: (a) print it for the user, and
            # (b) inject it back into the agent pipeline so the agent can
            # reason about test results, errors, etc.
            result = subprocess.run(
                safe_cmd,
                shell=True,
                cwd=project_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            output = (result.stdout + result.stderr).strip()

            # Print the captured output so the user still sees it
            if output:
                console.print(output)
                console.print()

            if result.returncode == 0:
                console.print("  [green]✓ Done[/green]  (exit 0)\n")
                # Cap output fed back to agents at 3000 chars to avoid token explosion
                snippet = output[-3000:] if len(output) > 3000 else output
                outcomes.append(
                    f"BASH OK: {action.label}\nOUTPUT:\n{snippet}" if snippet
                    else f"BASH OK: {action.label}"
                )
            else:
                console.print(f"  [red]✗ Exited {result.returncode}[/red]\n")
                snippet = output[-3000:] if len(output) > 3000 else output
                outcomes.append(
                    f"BASH FAILED (exit {result.returncode}): {action.label}\nOUTPUT:\n{snippet}"
                    if snippet
                    else f"BASH FAILED (exit {result.returncode}): {action.label}"
                )
        else:
            console.print("  [dim]Skipped.[/dim]")
            outcomes.append(f"BASH SKIPPED: {action.label}")

    return outcomes
