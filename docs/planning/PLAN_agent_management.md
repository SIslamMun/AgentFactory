# Plan: Programmatic Agent Creation & CLI Management

## Goal

Add write capabilities to `BlueprintRegistry` (create/update/delete/duplicate blueprints programmatically) and extend `cli.py` with both standalone subcommands and REPL commands for managing agents without editing YAML by hand.

---

## Files to Modify

| File | Change |
|------|--------|
| `src/agent_factory/factory/registry.py` | Add `create`, `update`, `delete`, `duplicate` methods + default template + deep merge + validation |
| `cli.py` | Add `argparse` subcommands + new REPL commands + refactor `main()` |
| `tests/unit/test_registry.py` | Add tests for all new registry methods |

No new files. No new dependencies (argparse is stdlib, yaml and copy are already available).

---

## Part 1: Extend `BlueprintRegistry`

**File:** `src/agent_factory/factory/registry.py`

### 1A. Add `import copy` to imports

```python
# existing imports stay, add:
import copy
```

### 1B. Add `_DEFAULT_BLUEPRINT` constant (after existing `_DEFAULT_BLUEPRINTS_DIR` on line 15)

Full template matching `iowarp_agent.yaml` and `AgentBuilder._build()` fallback defaults:

```python
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

_VALID_AGENT_TYPES = {"rule_based", "llm", "claude"}
```

### 1C. Add `_deep_merge` module-level helper (before the class)

```python
def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge *overrides* into a deep copy of *base*."""
    result = copy.deepcopy(base)
    for key, val in overrides.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result
```

### 1D. Add `_validate_blueprint` method to `BlueprintRegistry` class

```python
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
```

### 1E. Add `_save` method to `BlueprintRegistry` class

```python
def _save(self, name: str, data: dict[str, Any]) -> Path:
    """Write the blueprint dict to a YAML file and return the path."""
    safe_name = "".join(c if c.isalnum() or c in "_-" else "_" for c in name)
    path = self._dir / f"{safe_name}.yaml"
    self._dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    log.info("Saved blueprint to %s", path)
    return path
```

### 1F. Add `create` method

```python
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
```

### 1G. Add `update` method

```python
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
```

### 1H. Add `delete` method

```python
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
```

### 1I. Add `duplicate` method

```python
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
```

### Programmatic usage after implementation

```python
from agent_factory.factory.registry import BlueprintRegistry
from agent_factory.factory.builder import AgentBuilder

# Create agents programmatically
registry = BlueprintRegistry()
registry.load()

registry.create("my_agent")                                          # rule_based, all defaults
registry.create("llm_agent", agent_type="llm", model="llama3.2")    # LLM with model
registry.create("custom", agent_type="claude", cache={"default_ttl": 7200})

# Update
registry.update("my_agent", agent={"type": "llm", "model": "llama3.2:latest"})

# Duplicate + modify
registry.duplicate("iowarp_agent", "my_copy")
registry.update("my_copy", agent={"type": "claude"})

# Build and run
blueprint = registry.get("llm_agent")
built = AgentBuilder().build(blueprint, connect=True)

# Delete
registry.delete("my_copy")
```

---

## Part 2: Extend CLI

**File:** `cli.py`

### 2A. Add `import argparse` and `import yaml` to imports

```python
import argparse
import yaml
```

### 2B. Add `build_parser()` function

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="AgentFactory CLI — manage and run agent blueprints.",
    )
    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create a new agent blueprint")
    p_create.add_argument("name", help="Blueprint name")
    p_create.add_argument(
        "--type", default="rule_based",
        choices=["rule_based", "llm", "claude"],
        help="Agent type (default: rule_based)",
    )
    p_create.add_argument("--model", default=None, help="Model name (for llm/claude)")
    p_create.add_argument(
        "--temperature", type=float, default=None,
        help="Temperature (for llm)",
    )

    # list
    sub.add_parser("list", help="List all available blueprints")

    # show
    p_show = sub.add_parser("show", help="Show blueprint details")
    p_show.add_argument("name", help="Blueprint name")

    # delete
    p_del = sub.add_parser("delete", help="Delete a blueprint")
    p_del.add_argument("name", help="Blueprint name")

    # run
    p_run = sub.add_parser("run", help="Run an agent by blueprint name")
    p_run.add_argument("name", help="Blueprint name to run")
    p_run.add_argument(
        "--type", default=None,
        choices=["rule_based", "llm", "claude"],
        help="Override agent type",
    )

    return parser
```

### 2C. Add standalone command handlers

```python
def cmd_create(args) -> None:
    from agent_factory.factory.registry import BlueprintRegistry

    registry = BlueprintRegistry()
    registry.load()

    kwargs = {}
    if args.model:
        kwargs["model"] = args.model
    if args.temperature is not None:
        kwargs["temperature"] = args.temperature

    try:
        bp = registry.create(args.name, agent_type=args.type, **kwargs)
        ok(f"Created blueprint '{args.name}'")
        show_data("Agent type", bp["agent"]["type"])
        if "model" in bp["agent"]:
            show_data("Model", bp["agent"]["model"])
    except Exception as exc:
        err(str(exc))
        sys.exit(1)


def cmd_list(args) -> None:
    from agent_factory.factory.registry import BlueprintRegistry

    registry = BlueprintRegistry()
    registry.load()

    names = registry.list_blueprints()
    if not names:
        info("No blueprints found.")
        return

    print(f"\n  {BOLD}Available blueprints:{RESET}")
    for name in names:
        bp = registry.get(name)
        agent_type = bp.get("agent", {}).get("type", "?")
        version = bp.get("blueprint", {}).get("version", "?")
        print(f"    {CYAN}{name:20s}{RESET}  type={agent_type:12s}  v{version}")
    print()


def cmd_show(args) -> None:
    from agent_factory.factory.registry import BlueprintRegistry

    registry = BlueprintRegistry()
    registry.load()

    try:
        bp = registry.get(args.name)
        print(f"\n  {BOLD}Blueprint: {args.name}{RESET}\n")
        print(yaml.dump(bp, default_flow_style=False, sort_keys=False))
    except Exception as exc:
        err(str(exc))
        sys.exit(1)


def cmd_delete(args) -> None:
    from agent_factory.factory.registry import BlueprintRegistry

    registry = BlueprintRegistry()
    registry.load()

    try:
        registry.delete(args.name)
        ok(f"Deleted blueprint '{args.name}'")
    except Exception as exc:
        err(str(exc))
        sys.exit(1)


def cmd_run(args) -> None:
    from agent_factory.factory.registry import BlueprintRegistry

    registry = BlueprintRegistry()
    registry.load()

    try:
        blueprint = registry.get(args.name)
    except Exception as exc:
        err(str(exc))
        sys.exit(1)

    if args.type:
        agent_cfg = dict(blueprint.get("agent", {}))
        agent_cfg["type"] = args.type
    else:
        agent_cfg = blueprint.get("agent", {"type": "rule_based"})

    run_interactive(blueprint, agent_cfg, registry)
```

### 2D. Add new REPL command handlers

```python
def handle_list(registry) -> None:
    names = registry.list_blueprints()
    print()
    print(f"  {BOLD}Blueprints:{RESET}")
    for name in names:
        bp = registry.get(name)
        agent_type = bp.get("agent", {}).get("type", "?")
        print(f"    {CYAN}{name}{RESET}  (type={agent_type})")
    print()


def handle_show_blueprint(registry, name: str) -> None:
    try:
        bp = registry.get(name.strip())
        print()
        print(yaml.dump(bp, default_flow_style=False, sort_keys=False))
    except Exception as exc:
        err(str(exc))


def handle_create_repl(registry, args_str: str) -> None:
    parts = args_str.split()
    if not parts:
        err("Usage: create <name> [rule_based|llm|claude]")
        return
    name = parts[0]
    agent_type = parts[1] if len(parts) > 1 else "rule_based"
    try:
        registry.create(name, agent_type=agent_type)
        ok(f"Created blueprint '{name}' (type={agent_type})")
    except Exception as exc:
        err(str(exc))


def handle_delete_repl(registry, name: str) -> None:
    try:
        registry.delete(name.strip())
        ok(f"Deleted blueprint '{name.strip()}'")
    except Exception as exc:
        err(str(exc))


def handle_switch(registry, name, built, trajectory):
    """Switch to a different blueprint. Tears down old agent, builds new one."""
    from agent_factory.core.types import TaskSpec, Trajectory

    try:
        new_bp = registry.get(name.strip())
    except Exception as exc:
        err(str(exc))
        return built, trajectory

    agent_cfg = new_bp.get("agent", {"type": "rule_based"})

    try:
        built.environment.close()
    except Exception:
        pass

    try:
        new_built = build_stack(new_bp, agent_cfg)
    except Exception as exc:
        err(f"Failed to build: {exc}")
        return built, trajectory

    task = TaskSpec(
        task_id="cli_session",
        instruction="Interactive CLI session — agent responds to user instructions.",
    )
    new_built.environment.reset(task)
    new_trajectory = Trajectory(task=task)

    print(f"  {BOLD}Agent:{RESET} {agent_description(new_built)}")
    ok(f"Switched to '{name.strip()}'")
    print()
    return new_built, new_trajectory


def handle_configure(args_str: str, built, registry) -> None:
    parts = args_str.split(None, 1)
    if len(parts) != 2:
        err("Usage: configure <dotted.key> <value>")
        err("Example: configure agent.type llm")
        err("Example: configure cache.default_ttl 7200")
        return

    key_path, raw_value = parts

    # Parse value: try JSON first (for numbers, bools, objects), else string
    try:
        value = json.loads(raw_value)
    except (ValueError, json.JSONDecodeError):
        value = raw_value

    # Navigate blueprint dict to set the value
    keys = key_path.split(".")
    bp = built.blueprint
    target = bp
    for k in keys[:-1]:
        if k not in target or not isinstance(target[k], dict):
            target[k] = {}
        target = target[k]
    target[keys[-1]] = value

    ok(f"Set {key_path} = {value!r}")
    info("Rebuild the agent (use 'switch' or restart) for changes to take effect.")

    # Persist to YAML if blueprint is in registry
    bp_name = bp.get("blueprint", {}).get("name", "")
    if bp_name and bp_name in registry:
        try:
            registry.update(bp_name, **{keys[0]: bp.get(keys[0], {})})
            info(f"Saved to {bp_name}.yaml")
        except Exception as exc:
            err(f"Failed to save: {exc}")
```

### 2E. Refactor `main()` — extract `run_interactive()` and add dual-mode dispatch

The existing `main()` function body (from infrastructure check through the REPL loop) becomes `run_interactive(blueprint, agent_cfg, registry)`.

The new `main()` parses args:
- No subcommand → load default blueprint, show agent selection menu, call `run_interactive()`
- Subcommand → dispatch to `cmd_create`, `cmd_list`, `cmd_show`, `cmd_delete`, `cmd_run`

```python
def run_interactive(blueprint: dict, agent_cfg: dict, registry) -> None:
    """Run the interactive REPL with a given blueprint and agent config."""
    from agent_factory.core.types import TaskSpec, Trajectory

    banner()

    if not check_infrastructure(blueprint):
        err("Infrastructure check failed.")
        sys.exit(1)

    try:
        built = build_stack(blueprint, agent_cfg)
    except Exception as exc:
        err(f"Failed to build agent stack: {exc}")
        sys.exit(1)

    print(f"  {BOLD}Agent:{RESET} {agent_description(built)}")
    print(f"  {BOLD}Environment:{RESET} {type(built.environment).__name__}")
    print(f"  Type {CYAN}'help'{RESET} for commands, {CYAN}'quit'{RESET} to exit.")
    print()

    task = TaskSpec(
        task_id="cli_session",
        instruction="Interactive CLI session — agent responds to user instructions.",
    )
    built.environment.reset(task)
    trajectory = Trajectory(task=task)

    # REPL loop
    while True:
        try:
            raw = input(f"  {BOLD}agent>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not raw:
            continue

        cmd = raw.lower()

        try:
            if cmd in ("quit", "exit"):
                break
            elif cmd == "help":
                handle_help()
            elif cmd == "status":
                handle_status(built, trajectory)
            elif cmd == "observe":
                handle_observe(built)
            elif cmd == "history":
                handle_history(trajectory)
            elif cmd == "agent":
                handle_agent(built)
            elif cmd == "list":
                handle_list(registry)
            elif cmd.startswith("show "):
                handle_show_blueprint(registry, raw[5:])
            elif cmd.startswith("create "):
                handle_create_repl(registry, raw[7:])
            elif cmd.startswith("delete "):
                handle_delete_repl(registry, raw[7:])
            elif cmd.startswith("switch "):
                built, trajectory = handle_switch(registry, raw[7:], built, trajectory)
            elif cmd.startswith("configure "):
                handle_configure(raw[10:], built, registry)
            elif cmd.startswith("manual "):
                trajectory = handle_manual(raw[7:], built, trajectory)
            else:
                # Natural language → agent
                trajectory = run_agent_loop(raw, built, trajectory)
        except Exception as exc:
            err(f"Unexpected error: {exc}")
            print()

    # Cleanup
    print(f"  {DIM}Cleaning up...{RESET}")
    try:
        built.environment.close()
    except Exception:
        pass
    print(f"  Goodbye.")
    print()


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None:
        # No subcommand → original interactive flow
        from agent_factory.core.types import TaskSpec, Trajectory
        from agent_factory.factory.registry import BlueprintRegistry

        banner()

        try:
            registry = BlueprintRegistry()
            registry.load()
            blueprint = registry.get("iowarp_agent")
        except Exception as exc:
            err(f"Failed to load blueprint: {exc}")
            sys.exit(1)

        agent_cfg = select_agent_type()
        run_interactive(blueprint, agent_cfg, registry)
    elif args.command == "create":
        cmd_create(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "run":
        cmd_run(args)
```

### 2F. Update `HELP_TEXT`

```python
HELP_TEXT = f"""
  {BOLD}Commands:{RESET}
    {CYAN}help{RESET}                          Show this message
    {CYAN}status{RESET}                        Trajectory stats and cache stats
    {CYAN}observe{RESET}                       Show current environment observation
    {CYAN}history{RESET}                       Show all steps taken with rewards
    {CYAN}manual <action> <json_params>{RESET} Bypass agent, send action directly
    {CYAN}agent{RESET}                         Show current agent info
    {CYAN}list{RESET}                          List all available blueprints
    {CYAN}show <name>{RESET}                   Show a blueprint's full config
    {CYAN}create <name> [type]{RESET}          Create a new blueprint
    {CYAN}delete <name>{RESET}                 Delete a blueprint
    {CYAN}switch <name>{RESET}                 Switch to a different blueprint
    {CYAN}configure <key> <value>{RESET}       Set a config value (dotted path)
    {CYAN}quit{RESET} / {CYAN}exit{RESET}                    Clean up and exit

  Anything else is treated as {BOLD}natural language{RESET} and sent to the agent.
"""
```

---

## Part 3: Tests

**File:** `tests/unit/test_registry.py`

Add these test methods to the existing `TestBlueprintRegistry` class:

```python
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
    assert bp["cache"]["key_prefix"] == "iowarp"       # preserved
    assert bp["cache"]["hosts"][0]["host"] == "127.0.0.1"  # preserved
```

---

## Implementation Order

1. **`registry.py`** — add constants, helpers, and 4 public methods. This is the foundation.
2. **`test_registry.py`** — add all 12 tests, run `pytest tests/unit/test_registry.py -v` to verify.
3. **`cli.py`** — add argparse, standalone handlers, REPL handlers, refactor `main()`.

---

## Verification Checklist

1. `pytest tests/unit/test_registry.py -v` — all 18 tests pass (6 existing + 12 new)
2. `python3 cli.py list` — shows `iowarp_agent`
3. `python3 cli.py create my_llm --type llm --model llama3.2` — creates YAML, prints confirmation
4. `python3 cli.py show my_llm` — prints full blueprint YAML
5. `python3 cli.py list` — shows both `iowarp_agent` and `my_llm`
6. `python3 cli.py delete my_llm` — removes it
7. `python3 cli.py` → REPL → `create test_agent llm` → `list` → `switch test_agent` → `delete test_agent`
8. `python3 cli.py run iowarp_agent --type llm` — loads blueprint, overrides type, enters REPL
9. `python3 -c "from agent_factory.factory.registry import BlueprintRegistry; r = BlueprintRegistry(); r.load(); r.create('api_test'); print(r.list_blueprints())"` — programmatic API works
