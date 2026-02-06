"""BlueprintRegistry — discovers, loads, and manages agent blueprint YAML files."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any

import yaml

from agent_factory.core.errors import BlueprintError

log = logging.getLogger(__name__)

_DEFAULT_BLUEPRINTS_DIR = Path(__file__).resolve().parents[3] / "configs" / "blueprints"

_DEFAULT_BLUEPRINT: dict[str, Any] = {
    "blueprint": {
        "name": "",
        "version": "0.1.0",
        "description": "",
    },
    "iowarp": {
        "bridge_endpoint": "tcp://127.0.0.1:5560",
        "connect_timeout_ms": 5000,
        "request_timeout_ms": 30000,
    },
    "cache": {
        "hosts": [{"host": "127.0.0.1", "port": 11211}],
        "key_prefix": "iowarp",
        "default_ttl": 3600,
        "max_value_size": 10485760,
    },
    "uri_resolver": {
        "temp_dir": "/tmp/agent-factory/uri-cache",
        "supported_schemes": ["file::", "hdf5::", "folder::", "mem::"],
    },
    "environment": {
        "type": "iowarp",
        "default_format": "arrow",
        "reward": {
            "cache_hit": 0.3,
            "cache_miss": 0.2,
            "assimilate_success": 0.1,
            "query_success": 0.1,
            "prune_success": 0.05,
            "error": -0.5,
        },
    },
    "agent": {
        "type": "rule_based",
    },
}

_VALID_AGENT_TYPES = {"rule_based", "llm", "claude", "ingestor", "retriever"}


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *overrides* into a deep copy of *base*."""
    result = copy.deepcopy(base)
    for key, val in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


class BlueprintRegistry:
    """Registry of available agent blueprints.

    Scans a directory for ``*.yaml`` files and indexes them by the
    ``blueprint.name`` field.  Also supports programmatic creation,
    update, deletion, and duplication of blueprints.
    """

    def __init__(self, blueprints_dir: str | Path | None = None) -> None:
        self._dir = Path(blueprints_dir) if blueprints_dir else _DEFAULT_BLUEPRINTS_DIR
        self._blueprints: dict[str, dict[str, Any]] = {}

    def load(self) -> None:
        """Scan the blueprints directory and load all YAML files."""
        if not self._dir.is_dir():
            raise BlueprintError(f"Blueprints directory not found: {self._dir}")

        for path in sorted(self._dir.glob("*.yaml")):
            try:
                with open(path) as f:
                    data = yaml.safe_load(f)
                name = data.get("blueprint", {}).get("name")
                if not name:
                    log.warning("Skipping %s — no blueprint.name field", path.name)
                    continue
                self._blueprints[name] = data
                log.info("Loaded blueprint '%s' from %s", name, path.name)
            except Exception as exc:
                log.warning("Failed to load %s: %s", path.name, exc)

    def get(self, name: str) -> dict[str, Any]:
        """Return the parsed blueprint dict for *name*."""
        if name not in self._blueprints:
            raise BlueprintError(
                f"Blueprint '{name}' not found. "
                f"Available: {list(self._blueprints.keys())}"
            )
        return self._blueprints[name]

    def list_blueprints(self) -> list[str]:
        """Return names of all loaded blueprints."""
        return list(self._blueprints.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._blueprints

    # ── Validation ────────────────────────────────────────────────────────

    def _validate_blueprint(self, data: dict[str, Any]) -> None:
        """Raise BlueprintError if the blueprint dict is structurally invalid."""
        bp_meta = data.get("blueprint", {})
        name = bp_meta.get("name", "")
        if not name or not isinstance(name, str):
            raise BlueprintError("Blueprint must have a non-empty 'blueprint.name' string.")

        agent_type = data.get("agent", {}).get("type", "rule_based")
        if agent_type not in _VALID_AGENT_TYPES:
            raise BlueprintError(
                f"Invalid agent type '{agent_type}'. "
                f"Valid types: {', '.join(sorted(_VALID_AGENT_TYPES))}"
            )

    # ── Persistence ───────────────────────────────────────────────────────

    def _save(self, name: str, data: dict[str, Any]) -> Path:
        """Write the blueprint dict to a YAML file and return the path."""
        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        path = self._dir / f"{safe_name}.yaml"
        self._dir.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        log.info("Saved blueprint to %s", path)
        return path

    # ── CRUD operations ───────────────────────────────────────────────────

    def create(
        self,
        name: str,
        agent_type: str = "rule_based",
        **overrides: Any,
    ) -> dict[str, Any]:
        """Create a new blueprint from defaults, save to YAML, and register it.

        *overrides* are section-level dicts merged into the default template.
        Convenience kwargs ``model`` and ``temperature`` are moved into the
        ``agent`` section automatically.

        Returns the final blueprint dict.

        Raises BlueprintError if *name* already exists or agent_type is invalid.
        """
        if name in self._blueprints:
            raise BlueprintError(f"Blueprint '{name}' already exists.")

        # Build agent config from explicit params
        agent_cfg: dict[str, Any] = {"type": agent_type}
        if "model" in overrides:
            agent_cfg["model"] = overrides.pop("model")
        if "temperature" in overrides:
            agent_cfg["temperature"] = overrides.pop("temperature")

        merged_overrides: dict[str, Any] = {
            "blueprint": {"name": name},
            "agent": agent_cfg,
        }
        # Merge any remaining section-level overrides (e.g. cache={...})
        merged_overrides = _deep_merge(merged_overrides, overrides)

        data = _deep_merge(_DEFAULT_BLUEPRINT, merged_overrides)
        self._validate_blueprint(data)
        self._save(name, data)
        self._blueprints[name] = data
        log.info("Created blueprint '%s'", name)
        return data

    def update(self, name: str, **overrides: Any) -> dict[str, Any]:
        """Update an existing blueprint with new values and re-save.

        *overrides* are section-level dicts deep-merged into the current blueprint.

        Returns the updated blueprint dict.

        Raises BlueprintError if *name* does not exist.
        """
        if name not in self._blueprints:
            raise BlueprintError(
                f"Blueprint '{name}' not found. "
                f"Available: {list(self._blueprints.keys())}"
            )

        current = self._blueprints[name]
        updated = _deep_merge(current, overrides)
        self._validate_blueprint(updated)
        self._save(name, updated)
        self._blueprints[name] = updated
        log.info("Updated blueprint '%s'", name)
        return updated

    def delete(self, name: str) -> None:
        """Delete a blueprint from disk and the in-memory registry.

        Raises BlueprintError if *name* does not exist.
        """
        if name not in self._blueprints:
            raise BlueprintError(
                f"Blueprint '{name}' not found. "
                f"Available: {list(self._blueprints.keys())}"
            )

        safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
        path = self._dir / f"{safe_name}.yaml"
        if path.exists():
            path.unlink()
            log.info("Deleted blueprint file: %s", path)

        del self._blueprints[name]
        log.info("Deleted blueprint '%s'", name)

    def duplicate(self, src_name: str, dst_name: str) -> dict[str, Any]:
        """Clone an existing blueprint under a new name.

        Returns the new blueprint dict.

        Raises BlueprintError if *src_name* does not exist or *dst_name* already exists.
        """
        if src_name not in self._blueprints:
            raise BlueprintError(
                f"Source blueprint '{src_name}' not found. "
                f"Available: {list(self._blueprints.keys())}"
            )
        if dst_name in self._blueprints:
            raise BlueprintError(f"Blueprint '{dst_name}' already exists.")

        data = copy.deepcopy(self._blueprints[src_name])
        data["blueprint"]["name"] = dst_name
        self._validate_blueprint(data)
        self._save(dst_name, data)
        self._blueprints[dst_name] = data
        log.info("Duplicated '%s' as '%s'", src_name, dst_name)
        return data
