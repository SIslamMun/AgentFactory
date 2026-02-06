#!/usr/bin/env python3
"""
AgentFactory Interactive CLI
============================

Single-file interactive REPL that drives the full AgentFactory pipeline:
  - Choose agent type (rule_based, llm, claude)
  - Type natural language instructions for the agent
  - Watch the agent think, act, and see environment responses
  - Track trajectory rewards and cache stats live

Standalone subcommands:
    python3 cli.py create my_agent --type llm --model llama3.2
    python3 cli.py list
    python3 cli.py show my_agent
    python3 cli.py delete my_agent
    python3 cli.py run my_agent --type claude

Interactive mode:
    python3 cli.py
    python3 cli.py --pipeline configs/pipelines/ingest_retrieve.yaml
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from typing import Any

import yaml

# ─── ANSI color constants ────────────────────────────────────────────────

BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"

# ─── Print helpers ───────────────────────────────────────────────────────


def banner() -> None:
    print()
    print(f"  {BOLD}{CYAN}AgentFactory Interactive CLI{RESET}")
    print(f"  {DIM}{'─' * 28}{RESET}")
    print()


def ok(msg: str) -> None:
    print(f"    {GREEN}✓{RESET} {msg}")


def err(msg: str) -> None:
    print(f"    {RED}✗{RESET} {msg}")


def info(msg: str) -> None:
    print(f"    {DIM}{msg}{RESET}")


def show_data(label: str, value: object) -> None:
    print(f"    {CYAN}{label}:{RESET} {value}")


# ─── Infrastructure check ───────────────────────────────────────────────


def check_infrastructure(blueprint: dict[str, Any]) -> bool:
    """Verify all IOWarp bridges and memcached nodes are reachable.

    Returns True if at least one bridge and the cache are alive.
    """
    from agent_factory.iowarp.cache import BlobCache
    from agent_factory.iowarp.client import IOWarpClient

    iowarp_cfg = blueprint.get("iowarp", {})
    endpoints = iowarp_cfg.get("bridge_endpoints")
    if not endpoints:
        endpoints = [iowarp_cfg.get("bridge_endpoint", "tcp://127.0.0.1:5560")]

    cache_cfg = blueprint.get("cache", {})
    hosts_raw = cache_cfg.get("hosts", [{"host": "127.0.0.1", "port": 11211}])

    print(f"  {BOLD}Checking infrastructure...{RESET}")

    # IOWarp bridges
    bridge_ok = 0
    for ep in endpoints:
        label = f"IOWarp bridge ({ep})"
        dots = "." * max(1, 45 - len(label))
        print(f"    {label} {dots} ", end="", flush=True)
        try:
            probe = IOWarpClient(endpoint=ep, connect_timeout_ms=3000)
            probe.connect()
            probe.close()
            print(f"{GREEN}OK{RESET}")
            bridge_ok += 1
        except Exception as exc:
            print(f"{RED}FAIL{RESET}")
            err(f"Bridge not reachable: {exc}")

    if bridge_ok == 0:
        info("Run: docker-compose up -d")
        return False

    if bridge_ok < len(endpoints):
        info(f"{bridge_ok}/{len(endpoints)} bridges reachable (partial)")

    # Memcached nodes
    cache_hosts = [(h.get("host", "127.0.0.1"), h.get("port", 11211)) for h in hosts_raw]
    cache_ok = 0
    for host, port in cache_hosts:
        label = f"Memcached ({host}:{port})"
        dots = "." * max(1, 45 - len(label))
        print(f"    {label} {dots} ", end="", flush=True)
        try:
            probe = BlobCache(hosts=[(host, port)])
            probe.connect()
            probe.close()
            print(f"{GREEN}OK{RESET}")
            cache_ok += 1
        except Exception as exc:
            print(f"{RED}FAIL{RESET}")
            err(f"Memcached not reachable: {exc}")

    if cache_ok == 0:
        return False

    if cache_ok < len(cache_hosts):
        info(f"{cache_ok}/{len(cache_hosts)} cache nodes reachable (partial)")

    print()
    return True


# ─── Agent selection ─────────────────────────────────────────────────────

AGENT_CHOICES = [
    ("rule_based", "keyword matching (fast, no LLM needed)", {}),
    ("llm", "Ollama local LLM (llama3.2)", {"model": "llama3.2:latest", "temperature": 0.1}),
    ("claude", "Claude Code CLI (no API key needed)", {"model": "sonnet"}),
]


def select_agent_type() -> dict[str, Any]:
    """Interactive menu to choose agent type. Returns agent config dict."""
    print(f"  {BOLD}Select agent type:{RESET}")
    for i, (name, desc, _) in enumerate(AGENT_CHOICES, 1):
        print(f"    [{i}] {CYAN}{name:12s}{RESET} — {desc}")

    while True:
        try:
            raw = input(f"  {BOLD}>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)

        if raw in ("1", "2", "3"):
            idx = int(raw) - 1
            name, _, extra = AGENT_CHOICES[idx]
            cfg = {"type": name}
            cfg.update(extra)
            print()
            return cfg

        # Also accept type names directly
        for name, _, extra in AGENT_CHOICES:
            if raw.lower() == name:
                cfg = {"type": name}
                cfg.update(extra)
                print()
                return cfg

        print(f"    {RED}Invalid choice. Enter 1, 2, or 3.{RESET}")


# ─── Build agent stack ───────────────────────────────────────────────────


def build_stack(blueprint: dict[str, Any], agent_cfg: dict[str, Any]):
    """Build the full agent stack from the blueprint with the chosen agent config.

    Returns a BuiltAgent instance.
    """
    from agent_factory.factory.builder import AgentBuilder

    bp = copy.deepcopy(blueprint)
    bp["agent"] = agent_cfg

    print(f"  Building agent stack from blueprint... ", end="", flush=True)
    builder = AgentBuilder()
    built = builder.build(bp, connect=True)
    print(f"{GREEN}done{RESET}")

    return built


def agent_description(built) -> str:
    """Return a human-readable description of the agent."""
    agent = built.agent
    cls = type(agent).__name__
    # Try to get model info for LLM/Claude agents
    model = getattr(agent, "_model", None)
    if model:
        return f"{cls} ({model})"
    return cls


# ─── REPL commands ───────────────────────────────────────────────────────

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


def handle_help() -> None:
    print(HELP_TEXT)


def handle_status(built, trajectory) -> None:
    print()
    print(f"  {BOLD}Trajectory:{RESET} {trajectory.length} steps | "
          f"Total reward: {trajectory.total_reward:.2f}")

    hits = built.cache.hits
    misses = built.cache.misses
    total = hits + misses
    rate = (hits / total * 100) if total else 0
    print(f"  {BOLD}Cache:{RESET} {hits} hit(s), {misses} miss(es) "
          f"({rate:.0f}% hit rate)")

    bridge_nodes = built.client.node_count
    cache_nodes = built.cache.node_count
    if bridge_nodes > 1 or cache_nodes > 1:
        print(f"  {BOLD}Nodes:{RESET} {bridge_nodes} bridge(s), {cache_nodes} cache(s)")
    print()


def handle_observe(built) -> None:
    obs = built.environment.observe()
    print()
    show_data("Observation", obs.text)
    if obs.data:
        show_data("Data", obs.data)
    print()


def handle_history(trajectory) -> None:
    if trajectory.length == 0:
        print()
        info("No steps taken yet.")
        print()
        return

    print()
    print(f"  {BOLD}History ({trajectory.length} steps){RESET}")
    for i, (action, sr) in enumerate(trajectory.steps, 1):
        tag = ""
        if sr.observation.data.get("cache_hit") is True:
            tag = f" {GREEN}[HIT]{RESET}"
        elif sr.observation.data.get("cache_hit") is False:
            tag = f" {YELLOW}[MISS]{RESET}"

        print(f"    {DIM}{i}.{RESET} {CYAN}{action.name:12s}{RESET} "
              f"reward={sr.reward:+.2f}{tag}")
        info(f"   {sr.observation.text}")
    print(f"\n  Total reward: {BOLD}{trajectory.total_reward:.2f}{RESET}")
    print()


def handle_agent(built) -> None:
    print()
    show_data("Agent", agent_description(built))
    show_data("Environment", type(built.environment).__name__)
    show_data("Blueprint", built.blueprint.get("blueprint", {}).get("name", "?"))
    print()


def handle_manual(args_str: str, built, trajectory):
    """Parse 'manual <action> <json_params>' and execute directly.

    Returns the updated trajectory.
    """
    from agent_factory.core.types import Action

    parts = args_str.strip().split(None, 1)
    if not parts:
        err("Usage: manual <action> [json_params]")
        err("Example: manual query {\"tag_pattern\": \"*\"}")
        return trajectory

    action_name = parts[0]
    params: dict[str, Any] = {}
    if len(parts) > 1:
        try:
            params = json.loads(parts[1])
        except json.JSONDecodeError as exc:
            err(f"Invalid JSON params: {exc}")
            return trajectory

    print()
    info(f"Manual action: {action_name}")
    info(f"Params: {params}")

    action = Action(name=action_name, params=params)
    try:
        result = built.environment.step(action)
        trajectory = trajectory.append(action, result)
        print()
        print(f"  {BOLD}Environment response:{RESET}")
        show_data("Result", result.observation.text)
        if result.observation.data:
            show_data("Data", result.observation.data)
        show_data("Reward", f"{result.reward:+.2f}")
        show_retrieve_preview(built, action, result)
    except Exception as exc:
        err(f"Step failed: {exc}")

    print()
    return trajectory


# ─── Retrieve content preview ────────────────────────────────────────────


def show_retrieve_preview(built, action, result) -> None:
    """If the action was a retrieve, show a content preview."""
    if action.name != "retrieve":
        return

    tag = action.params.get("tag")
    blob_name = action.params.get("blob_name")
    if not tag or not blob_name:
        return

    try:
        cached_bytes = built.cache.get(tag, blob_name)
        if cached_bytes:
            snippet = cached_bytes.decode("utf-8", errors="replace")[:400]
            lines = snippet.splitlines()[:8]
            print()
            print(f"    {DIM}── Content preview ──{RESET}")
            for line in lines:
                print(f"    {DIM}│ {line}{RESET}")
            if len(snippet) >= 400 or len(snippet.splitlines()) > 8:
                print(f"    {DIM}│ ...{RESET}")
    except Exception:
        pass


# ─── Agent-driven loop ──────────────────────────────────────────────────


def run_agent_loop(text: str, built, trajectory):
    """Send natural language to agent: think → act → step → display.

    Returns the updated trajectory.
    """
    from agent_factory.core.types import Observation

    obs = Observation(text=text)

    print()
    print(f"  {BOLD}Agent thinking...{RESET}")

    # Think
    try:
        thought = built.agent.think(obs)
        info(f'Thought: "{thought}"')
    except Exception as exc:
        err(f"Agent think() failed: {exc}")
        return trajectory

    # Act
    try:
        action = built.agent.act(obs)
        info(f"Action: {action.name}")
        info(f"Params: {action.params}")
    except Exception as exc:
        err(f"Agent act() failed: {exc}")
        return trajectory

    # Environment step
    try:
        result = built.environment.step(action)
        trajectory = trajectory.append(action, result)
    except Exception as exc:
        err(f"Environment step() failed: {exc}")
        return trajectory

    # Display
    print()
    print(f"  {BOLD}Environment response:{RESET}")
    show_data("Result", result.observation.text)
    if result.observation.data:
        show_data("Data", result.observation.data)

    cache_hit = result.observation.data.get("cache_hit")
    if cache_hit is True:
        show_data("Cache", f"{GREEN}HIT{RESET}")
    elif cache_hit is False:
        show_data("Cache", f"{YELLOW}MISS{RESET}")

    show_data("Reward", f"{result.reward:+.2f}")

    show_retrieve_preview(built, action, result)

    print()
    return trajectory


# ─── New REPL command handlers (blueprint management) ────────────────────


def handle_list(registry) -> None:
    """List all blueprints in the registry."""
    names = registry.list_blueprints()
    print()
    print(f"  {BOLD}Blueprints:{RESET}")
    for name in names:
        bp = registry.get(name)
        agent_type = bp.get("agent", {}).get("type", "?")
        print(f"    {CYAN}{name}{RESET}  (type={agent_type})")
    print()


def handle_show_blueprint(registry, name: str) -> None:
    """Show a blueprint's full config."""
    try:
        bp = registry.get(name.strip())
        print()
        print(yaml.dump(bp, default_flow_style=False, sort_keys=False))
    except Exception as exc:
        err(str(exc))


def handle_create_repl(registry, args_str: str) -> None:
    """Create a new blueprint from the REPL."""
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
    """Delete a blueprint from the REPL."""
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
    """Set a config value using dotted key path."""
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


# ─── Pipeline mode ──────────────────────────────────────────────────────


PIPELINE_HELP_TEXT = f"""
  {BOLD}Pipeline Commands:{RESET}
    {CYAN}run key=value key=value ...{RESET}  Execute the pipeline with given variables
    {CYAN}info{RESET}                         Show pipeline steps and agents
    {CYAN}help{RESET}                         Show this message
    {CYAN}quit{RESET} / {CYAN}exit{RESET}                    Clean up and exit

  Example: {DIM}run src=folder::./data/docs dst=my_tag{RESET}
"""


def pipeline_banner(pipeline_def: dict[str, Any]) -> None:
    print()
    print(f"  {BOLD}{CYAN}AgentFactory Pipeline Mode{RESET}")
    print(f"  {DIM}{'─' * 26}{RESET}")
    pid = pipeline_def.get("pipeline_id", "?")
    desc = pipeline_def.get("description", "")
    print(f"  {BOLD}Pipeline:{RESET} {pid}")
    if desc:
        info(desc)
    print()


def show_pipeline_info(built_pipeline: Any) -> None:
    """Show pipeline steps and agents."""
    print()
    print(f"  {BOLD}Agents:{RESET}")
    for role, agent in built_pipeline.agents.items():
        cls = type(agent).__name__
        print(f"    {CYAN}{role:16s}{RESET} {cls}")

    print()
    print(f"  {BOLD}Steps (execution order):{RESET}")
    for i, step in enumerate(built_pipeline.dag.execution_order, 1):
        deps = ", ".join(step.depends_on) if step.depends_on else "none"
        print(f"    {DIM}{i}.{RESET} {CYAN}{step.name:20s}{RESET} "
              f"agent={step.agent_role:12s} depends_on=[{deps}]")
    print()


def parse_run_args(args_str: str) -> dict[str, str]:
    """Parse 'key=value key=value' into a dict."""
    result: dict[str, str] = {}
    for token in args_str.split():
        if "=" in token:
            key, _, value = token.partition("=")
            result[key] = value
    return result


def run_pipeline(built_pipeline: Any, initial_vars: dict[str, Any]) -> None:
    """Execute the pipeline and display results."""
    from agent_factory.core.types import TaskSpec

    task = TaskSpec(
        task_id="pipeline_run",
        instruction=f"Pipeline run with vars: {initial_vars}",
    )
    built_pipeline.environment.reset(task)

    print()
    print(f"  {BOLD}Executing pipeline...{RESET}")
    print()

    try:
        ctx = built_pipeline.executor.execute(
            built_pipeline.dag,
            task="pipeline_run",
            initial_vars=initial_vars,
        )
    except Exception as exc:
        err(f"Pipeline execution failed: {exc}")
        print()
        return

    # Show results
    for step_name, output in ctx.outputs.items():
        has_error = "error" in output.data
        indicator = f"{RED}FAIL{RESET}" if has_error else f"{GREEN}OK{RESET}"
        print(f"    [{indicator}] {CYAN}{step_name}{RESET}")
        info(f"   {output.observation.text}")
        if output.data:
            for k, v in output.data.items():
                show_data(f"  {k}", v)

    print()
    ok("Pipeline execution complete.")
    print()


def pipeline_main(pipeline_path: str) -> None:
    """Pipeline REPL mode — load a pipeline YAML and execute interactively."""
    from agent_factory.factory.builder import AgentBuilder
    from agent_factory.factory.registry import BlueprintRegistry

    # Load pipeline definition
    try:
        with open(pipeline_path) as f:
            pipeline_def = yaml.safe_load(f)
    except Exception as exc:
        err(f"Failed to load pipeline YAML: {exc}")
        sys.exit(1)

    pipeline_banner(pipeline_def)

    # Load blueprint for infrastructure config
    try:
        registry = BlueprintRegistry()
        registry.load()
        available = registry.list_blueprints()
        if len(available) == 1:
            blueprint_name = available[0]
        else:
            print(f"  {BOLD}Select blueprint:{RESET}")
            for i, name in enumerate(available, 1):
                bp = registry.get(name)
                desc = bp.get("blueprint", {}).get("description", "").strip()
                short = (desc[:50] + "...") if len(desc) > 50 else desc
                print(f"    [{i}] {CYAN}{name}{RESET} — {short}")
            while True:
                try:
                    raw = input(f"  {BOLD}>{RESET} ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    sys.exit(0)
                if raw.isdigit() and 1 <= int(raw) <= len(available):
                    blueprint_name = available[int(raw) - 1]
                    break
                if raw in available:
                    blueprint_name = raw
                    break
                print(f"    {RED}Invalid choice.{RESET}")
            print()
        blueprint = registry.get(blueprint_name)
    except Exception as exc:
        err(f"Failed to load blueprint: {exc}")
        sys.exit(1)

    # Check infrastructure
    if not check_infrastructure(blueprint):
        err("Infrastructure check failed. Please start the required services.")
        sys.exit(1)

    # Build pipeline
    try:
        print(f"  Building pipeline... ", end="", flush=True)
        builder = AgentBuilder()
        built_pipeline = builder.build_pipeline(
            blueprint, pipeline_def, connect=True
        )
        print(f"{GREEN}done{RESET}")
    except Exception as exc:
        err(f"Failed to build pipeline: {exc}")
        sys.exit(1)

    show_pipeline_info(built_pipeline)

    print(f"  Type {CYAN}'help'{RESET} for commands, "
          f"{CYAN}'run key=value ...'{RESET} to execute.")
    print()

    # Pipeline REPL
    while True:
        try:
            raw = input(f"  {BOLD}pipeline>{RESET} ").strip()
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
                print(PIPELINE_HELP_TEXT)
            elif cmd == "info":
                show_pipeline_info(built_pipeline)
            elif cmd.startswith("run"):
                args_str = raw[3:].strip()
                initial_vars = parse_run_args(args_str)
                run_pipeline(built_pipeline, initial_vars)
            else:
                err(f"Unknown command. Type 'help' for available commands.")
        except Exception as exc:
            err(f"Unexpected error: {exc}")
            print()

    # Cleanup
    print(f"  {DIM}Cleaning up...{RESET}")
    try:
        built_pipeline.environment.close()
    except Exception:
        pass
    print(f"  Goodbye.")
    print()


# ─── Standalone subcommand handlers ─────────────────────────────────────


def cmd_create(args) -> None:
    """Handle 'cli.py create <name> --type <type>' subcommand."""
    from agent_factory.factory.registry import BlueprintRegistry

    registry = BlueprintRegistry()
    registry.load()

    kwargs: dict[str, Any] = {}
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


def cmd_list(_args) -> None:
    """Handle 'cli.py list' subcommand."""
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
    """Handle 'cli.py show <name>' subcommand."""
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
    """Handle 'cli.py delete <name>' subcommand."""
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
    """Handle 'cli.py run <name>' subcommand — load blueprint and start REPL."""
    from agent_factory.factory.registry import BlueprintRegistry

    registry = BlueprintRegistry()
    registry.load()

    try:
        blueprint = registry.get(args.name)
    except Exception as exc:
        err(str(exc))
        sys.exit(1)

    if args.type:
        agent_cfg: dict[str, Any] = dict(blueprint.get("agent", {}))
        agent_cfg["type"] = args.type
    else:
        agent_cfg = blueprint.get("agent", {"type": "rule_based"})

    run_interactive(blueprint, agent_cfg, registry)


# ─── Argparse ────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="AgentFactory CLI — manage and run agent blueprints.",
    )
    parser.add_argument(
        "--pipeline", default=None, metavar="PATH",
        help="Run in pipeline mode with the given YAML config",
    )
    sub = parser.add_subparsers(dest="command")

    # create
    p_create = sub.add_parser("create", help="Create a new agent blueprint")
    p_create.add_argument("name", help="Blueprint name")
    p_create.add_argument(
        "--type", default="rule_based",
        choices=["rule_based", "llm", "claude", "ingestor", "retriever"],
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


# ─── Interactive REPL ────────────────────────────────────────────────────


def run_interactive(blueprint: dict[str, Any], agent_cfg: dict[str, Any], registry) -> None:
    """Run the interactive REPL with a given blueprint and agent config."""
    from agent_factory.core.types import TaskSpec, Trajectory

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


# ─── Main ───────────────────────────────────────────────────────────────


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Pipeline mode (--pipeline flag)
    if args.pipeline:
        pipeline_main(args.pipeline)
        return

    # Subcommand dispatch
    if args.command == "create":
        cmd_create(args)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "delete":
        cmd_delete(args)
    elif args.command == "run":
        cmd_run(args)
    else:
        # No subcommand → original interactive flow
        from agent_factory.factory.registry import BlueprintRegistry

        banner()

        try:
            registry = BlueprintRegistry()
            registry.load()
            available = registry.list_blueprints()
            if len(available) == 1:
                blueprint_name = available[0]
            else:
                print(f"  {BOLD}Select blueprint:{RESET}")
                for i, name in enumerate(available, 1):
                    bp = registry.get(name)
                    desc = bp.get("blueprint", {}).get("description", "").strip()
                    short = (desc[:50] + "...") if len(desc) > 50 else desc
                    print(f"    [{i}] {CYAN}{name}{RESET} — {short}")
                while True:
                    try:
                        raw = input(f"  {BOLD}>{RESET} ").strip()
                    except (EOFError, KeyboardInterrupt):
                        print()
                        sys.exit(0)
                    if raw.isdigit() and 1 <= int(raw) <= len(available):
                        blueprint_name = available[int(raw) - 1]
                        break
                    if raw in available:
                        blueprint_name = raw
                        break
                    print(f"    {RED}Invalid choice.{RESET}")
                print()
            blueprint = registry.get(blueprint_name)
        except Exception as exc:
            err(f"Failed to load blueprint: {exc}")
            sys.exit(1)

        # Select agent type
        agent_cfg = select_agent_type()
        run_interactive(blueprint, agent_cfg, registry)


if __name__ == "__main__":
    main()
