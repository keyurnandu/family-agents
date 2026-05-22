"""Tests for document export: no truncation, update existing docs, loaded codebase."""
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestExportFindsExistingDoc:
    """When a doc of the same type already exists, export_doc should
    pass its content to the agent so the agent can update it."""

    def test_existing_doc_content_in_prompt(self, base_dir, config):
        """If requirements-doc-2026-05-20.md exists, export_doc should
        include its content in the export_prompt so the agent updates it."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()

        orch = Orchestrator(
            base_dir=base_dir,
            project_name="test-proj",
            db=db,
            display=display,
            config=config,
        )

        # Create an existing requirements doc
        docs_dir = base_dir / "projects" / "test-proj" / "docs"
        docs_dir.mkdir(parents=True)
        existing = docs_dir / "requirements-doc-2026-05-20.md"
        existing.write_text("# Requirements\n## Epic 1\nLogin feature", encoding="utf-8")

        # Mock agent.respond to capture the prompt it receives
        captured_prompts = []
        def fake_respond(task, context, history_text, **kwargs):
            captured_prompts.append(task)
            return "# Updated Requirements\n## Epic 1\nLogin feature\n## Epic 2\nPayments"

        # Mock the summary call
        with patch.object(orch.agents["bsa"], "respond", side_effect=fake_respond), \
             patch("orchestrator.call_claude", return_value="• Login\n• Payments"):
            orch.export_doc("requirements")

        assert len(captured_prompts) == 1
        prompt = captured_prompts[0]
        # Should mention the existing doc
        assert "requirements-doc-2026-05-20.md" in prompt
        # Should contain existing doc content
        assert "Login feature" in prompt
        # Should instruct to update
        assert "update" in prompt.lower() or "enhance" in prompt.lower()

    def test_existing_doc_overwritten_not_duplicated(self, base_dir, config):
        """Export should overwrite the existing doc, not create a dated duplicate."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()

        orch = Orchestrator(
            base_dir=base_dir,
            project_name="test-proj",
            db=db,
            display=display,
            config=config,
        )

        docs_dir = base_dir / "projects" / "test-proj" / "docs"
        docs_dir.mkdir(parents=True)
        existing = docs_dir / "requirements-doc-2026-05-20.md"
        existing.write_text("# Old Requirements", encoding="utf-8")

        with patch.object(orch.agents["bsa"], "respond", return_value="# New Requirements"), \
             patch("orchestrator.call_claude", return_value="• Updated"):
            orch.export_doc("requirements")

        # Should have overwritten existing, not created a new dated file
        md_files = list(docs_dir.glob("requirements-doc*.md"))
        assert len(md_files) == 1, f"Expected 1 requirements doc, found {len(md_files)}: {md_files}"
        # Content should be the new version
        assert md_files[0].read_text(encoding="utf-8") == "# New Requirements"

    def test_no_existing_doc_creates_new(self, base_dir, config):
        """When no existing doc exists, a new one is created (no regression)."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()

        orch = Orchestrator(
            base_dir=base_dir,
            project_name="test-proj",
            db=db,
            display=display,
            config=config,
        )

        with patch.object(orch.agents["bsa"], "respond", return_value="# Requirements"), \
             patch("orchestrator.call_claude", return_value="• Item 1"):
            orch.export_doc("requirements")

        docs_dir = base_dir / "projects" / "test-proj" / "docs"
        md_files = list(docs_dir.glob("requirements-doc*.md"))
        assert len(md_files) == 1
        assert md_files[0].read_text(encoding="utf-8") == "# Requirements"


class TestExportNoTruncation:
    """Export prompts should override brevity rules and not truncate."""

    def test_export_prompt_overrides_brevity(self, base_dir, config):
        """The export prompt should explicitly tell the agent to write
        the COMPLETE document without brevity constraints."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()

        orch = Orchestrator(
            base_dir=base_dir,
            project_name="test-proj",
            db=db,
            display=display,
            config=config,
        )

        captured_prompts = []
        def fake_respond(task, context, history_text, **kwargs):
            captured_prompts.append(task)
            return "# Full doc content"

        with patch.object(orch.agents["bsa"], "respond", side_effect=fake_respond), \
             patch("orchestrator.call_claude", return_value="• Summary"):
            orch.export_doc("requirements")

        prompt = captured_prompts[0]
        # Should override brevity / tell agent to be thorough
        lower = prompt.lower()
        assert "complete" in lower and ("truncat" in lower or "brevity" in lower or "full" in lower), (
            "Export prompt should tell agent to write the complete document without truncation"
        )

    def test_summary_uses_full_content(self, base_dir, config):
        """The summary extraction should not truncate at 5000 chars."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()

        orch = Orchestrator(
            base_dir=base_dir,
            project_name="test-proj",
            db=db,
            display=display,
            config=config,
        )

        # Generate a long doc (8000 chars)
        long_content = "# Requirements\n" + ("x" * 100 + "\n") * 80  # ~8080 chars
        captured_summary_prompts = []

        def fake_call_claude(prompt, system_prompt=None, model=None):
            captured_summary_prompts.append(prompt)
            return "• Summary"

        with patch.object(orch.agents["bsa"], "respond", return_value=long_content), \
             patch("orchestrator.call_claude", side_effect=fake_call_claude):
            orch.export_doc("requirements")

        # The summary prompt should include more than 5000 chars
        assert len(captured_summary_prompts) == 1
        summary_prompt = captured_summary_prompts[0]
        # Should include content beyond the old 5000 char limit
        assert len(summary_prompt) > 5000


class TestExportDocsInLoadedCodebase:
    """When a codebase is /loaded, docs should go into the loaded codebase's
    docs/ folder — not the internal projects/<name>/docs/."""

    def test_docs_created_in_loaded_path(self, base_dir, config, tmp_path):
        """Export should write docs to loaded_path/docs/ when a codebase is loaded."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()

        orch = Orchestrator(
            base_dir=base_dir,
            project_name="test-proj",
            db=db,
            display=display,
            config=config,
        )

        # Simulate a loaded codebase at a separate path
        loaded_dir = tmp_path / "external-codebase"
        loaded_dir.mkdir()
        (loaded_dir / "src").mkdir()
        (loaded_dir / "src" / "app.py").write_text("print('hello')", encoding="utf-8")
        orch.loaded_path = loaded_dir

        with patch.object(orch.agents["bsa"], "respond", return_value="# Requirements for external"), \
             patch("orchestrator.call_claude", return_value="• External req"):
            orch.export_doc("requirements")

        # Doc should be in the loaded codebase's docs/ folder
        loaded_docs = loaded_dir / "docs"
        assert loaded_docs.exists(), "docs/ should be created in the loaded codebase"
        md_files = list(loaded_docs.glob("requirements-doc*.md"))
        assert len(md_files) == 1
        assert "external" in md_files[0].read_text(encoding="utf-8").lower()

        # Should NOT be in the internal projects/ path
        internal_docs = base_dir / "projects" / "test-proj" / "docs"
        internal_md = list(internal_docs.glob("requirements-doc*.md")) if internal_docs.exists() else []
        assert len(internal_md) == 0, "Doc should NOT be in internal projects/ when codebase is loaded"

    def test_existing_doc_in_loaded_path_updated(self, base_dir, config, tmp_path):
        """If docs/ already has a requirements doc in the loaded codebase,
        it should be found and updated, not duplicated."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()

        orch = Orchestrator(
            base_dir=base_dir,
            project_name="test-proj",
            db=db,
            display=display,
            config=config,
        )

        loaded_dir = tmp_path / "external-codebase"
        loaded_dir.mkdir()
        docs_dir = loaded_dir / "docs"
        docs_dir.mkdir()
        existing = docs_dir / "requirements-doc-2026-05-01.md"
        existing.write_text("# Old Reqs\nLogin only", encoding="utf-8")
        orch.loaded_path = loaded_dir

        captured_prompts = []
        def fake_respond(task, context, history_text, **kwargs):
            captured_prompts.append(task)
            return "# Updated Reqs\nLogin + Payments"

        with patch.object(orch.agents["bsa"], "respond", side_effect=fake_respond), \
             patch("orchestrator.call_claude", return_value="• Updated"):
            orch.export_doc("requirements")

        # Should have updated the existing file, not created a new one
        md_files = list(docs_dir.glob("requirements-doc*.md"))
        assert len(md_files) == 1, f"Expected 1 file, got {len(md_files)}: {md_files}"
        assert md_files[0].name == "requirements-doc-2026-05-01.md"  # same file
        assert "Payments" in md_files[0].read_text(encoding="utf-8")

        # Prompt should have included existing doc content
        assert "Login only" in captured_prompts[0]

    def test_file_list_from_loaded_path(self, base_dir, config, tmp_path):
        """The file list in the export prompt should reflect the loaded codebase,
        not the internal projects/ folder."""
        from orchestrator import Orchestrator
        from utils.db_manager import DBManager

        db = DBManager(base_dir / "db" / "conversations.db")
        display = MagicMock()

        orch = Orchestrator(
            base_dir=base_dir,
            project_name="test-proj",
            db=db,
            display=display,
            config=config,
        )

        loaded_dir = tmp_path / "external-codebase"
        loaded_dir.mkdir()
        (loaded_dir / "package.json").write_text("{}", encoding="utf-8")
        (loaded_dir / "src").mkdir()
        (loaded_dir / "src" / "index.ts").write_text("export {}", encoding="utf-8")
        orch.loaded_path = loaded_dir

        captured_prompts = []
        def fake_respond(task, context, history_text, **kwargs):
            captured_prompts.append(task)
            return "# Architecture"

        with patch.object(orch.agents["lead"], "respond", side_effect=fake_respond), \
             patch("orchestrator.call_claude", return_value="• Arch"):
            orch.export_doc("architecture")

        prompt = captured_prompts[0]
        assert "package.json" in prompt
        assert "index.ts" in prompt
