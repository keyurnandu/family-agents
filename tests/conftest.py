import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml


@pytest.fixture
def base_dir(tmp_path):
    """Create a minimal family-agents directory structure for testing."""
    # Config
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    real_config = Path(__file__).resolve().parent.parent / "config" / "settings.yaml"
    config = yaml.safe_load(real_config.read_text(encoding="utf-8"))
    (config_dir / "settings.yaml").write_text(
        yaml.dump(config, default_flow_style=False), encoding="utf-8"
    )

    # Memory dirs
    roles_dir = tmp_path / "memory" / "roles"
    roles_dir.mkdir(parents=True)
    real_roles = Path(__file__).resolve().parent.parent / "memory" / "roles"
    for md in real_roles.glob("*.md"):
        shutil.copy2(md, roles_dir / md.name)

    (tmp_path / "memory" / "skills").mkdir(parents=True)
    (tmp_path / "memory" / "dynamic").mkdir(parents=True)

    # Projects dir
    (tmp_path / "projects").mkdir()

    # DB dir
    (tmp_path / "db").mkdir()

    return tmp_path


@pytest.fixture
def config(base_dir):
    with open(base_dir / "config" / "settings.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture
def db_path(base_dir):
    return base_dir / "db" / "conversations.db"
