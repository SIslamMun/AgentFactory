"""Tests for BlueprintRegistry."""

from __future__ import annotations

import pytest

from agent_factory.core.errors import BlueprintError
from agent_factory.factory.registry import BlueprintRegistry


class TestBlueprintRegistry:
    def test_load_from_configs(self):
        reg = BlueprintRegistry()
        reg.load()
        assert "iowarp_agent" in reg
        assert "iowarp_agent" in reg.list_blueprints()

    def test_get_blueprint(self):
        reg = BlueprintRegistry()
        reg.load()
        bp = reg.get("iowarp_agent")
        assert bp["blueprint"]["name"] == "iowarp_agent"
        assert "iowarp" in bp
        assert "cache" in bp
        assert "environment" in bp

    def test_get_missing_raises(self):
        reg = BlueprintRegistry()
        reg.load()
        with pytest.raises(BlueprintError, match="not found"):
            reg.get("nonexistent")

    def test_nonexistent_dir_raises(self, tmp_path):
        reg = BlueprintRegistry(tmp_path / "nope")
        with pytest.raises(BlueprintError, match="not found"):
            reg.load()

    def test_custom_dir(self, tmp_path):
        # Write a minimal blueprint
        (tmp_path / "test.yaml").write_text(
            "blueprint:\n  name: custom\n  version: '1.0'\n"
        )
        reg = BlueprintRegistry(tmp_path)
        reg.load()
        assert "custom" in reg
        bp = reg.get("custom")
        assert bp["blueprint"]["version"] == "1.0"

    def test_skip_bad_yaml(self, tmp_path):
        (tmp_path / "bad.yaml").write_text("not: valid: yaml: [")
        (tmp_path / "good.yaml").write_text(
            "blueprint:\n  name: ok\n  version: '1'\n"
        )
        reg = BlueprintRegistry(tmp_path)
        reg.load()
        assert "ok" in reg

    # ── Create ────────────────────────────────────────────────────────────

    def test_create_blueprint(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        bp = reg.create("my_agent")
        assert "my_agent" in reg
        assert bp["blueprint"]["name"] == "my_agent"
        assert bp["agent"]["type"] == "rule_based"
        assert (tmp_path / "my_agent.yaml").exists()

    def test_create_with_agent_type(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        bp = reg.create("llm_agent", agent_type="llm", model="llama3.2:latest")
        assert bp["agent"]["type"] == "llm"
        assert bp["agent"]["model"] == "llama3.2:latest"

    def test_create_duplicate_raises(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        reg.create("agent1")
        with pytest.raises(BlueprintError, match="already exists"):
            reg.create("agent1")

    def test_create_invalid_agent_type_raises(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        with pytest.raises(BlueprintError, match="Invalid agent type"):
            reg.create("bad", agent_type="nonexistent")

    # ── Update ────────────────────────────────────────────────────────────

    def test_update_blueprint(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        reg.create("agent1")
        bp = reg.update("agent1", agent={"type": "llm", "model": "llama3.2"})
        assert bp["agent"]["type"] == "llm"
        assert bp["agent"]["model"] == "llama3.2"
        # Original fields preserved
        assert bp["cache"]["default_ttl"] == 3600

    def test_update_nonexistent_raises(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        with pytest.raises(BlueprintError, match="not found"):
            reg.update("nope", agent={"type": "llm"})

    # ── Delete ────────────────────────────────────────────────────────────

    def test_delete_blueprint(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        reg.create("agent1")
        assert (tmp_path / "agent1.yaml").exists()
        reg.delete("agent1")
        assert "agent1" not in reg
        assert not (tmp_path / "agent1.yaml").exists()

    def test_delete_nonexistent_raises(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        with pytest.raises(BlueprintError, match="not found"):
            reg.delete("nope")

    # ── Duplicate ─────────────────────────────────────────────────────────

    def test_duplicate_blueprint(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        reg.create("original", agent_type="llm", model="llama3.2")
        bp = reg.duplicate("original", "clone")
        assert "clone" in reg
        assert bp["blueprint"]["name"] == "clone"
        assert bp["agent"]["type"] == "llm"
        assert (tmp_path / "clone.yaml").exists()

    def test_duplicate_to_existing_raises(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        reg.create("a")
        reg.create("b")
        with pytest.raises(BlueprintError, match="already exists"):
            reg.duplicate("a", "b")

    # ── Persistence & deep merge ──────────────────────────────────────────

    def test_create_persists_and_reloads(self, tmp_path):
        reg1 = BlueprintRegistry(tmp_path)
        reg1.create("persistent_agent", agent_type="claude")
        # New registry instance should find the saved YAML
        reg2 = BlueprintRegistry(tmp_path)
        reg2.load()
        assert "persistent_agent" in reg2
        assert reg2.get("persistent_agent")["agent"]["type"] == "claude"

    def test_deep_merge_preserves_nested(self, tmp_path):
        reg = BlueprintRegistry(tmp_path)
        reg.create("agent1")
        # Update only cache.default_ttl, everything else should survive
        reg.update("agent1", cache={"default_ttl": 9999})
        bp = reg.get("agent1")
        assert bp["cache"]["default_ttl"] == 9999
        assert bp["cache"]["key_prefix"] == "iowarp"  # preserved
        assert bp["cache"]["hosts"][0]["host"] == "127.0.0.1"  # preserved
