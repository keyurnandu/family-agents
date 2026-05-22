def test_conftest_fixtures(base_dir, config):
    assert (base_dir / "config" / "settings.yaml").exists()
    assert (base_dir / "memory" / "roles").exists()
    assert "team" in config
    assert "agent_personas" in config
