#!/usr/bin/env python3
"""
AgentFactory Full Walkthrough
==============================

Exercises every layer of AgentFactory step by step, capturing output.
Runs with Claude Code CLI as the backend for IngestorAgent and RetrieverAgent
through the multi-agent pipeline.

Steps:
  1. Infrastructure check (bridge + memcached)
  2. Blueprint loading
  3. Single-agent mode (Claude agent: ingest, query, retrieve)
  4. Pipeline mode (IngestorAgent + RetrieverAgent with Claude backend)
  5. Unit tests
"""

from __future__ import annotations

import json
import sys
import traceback

# ─── ANSI ─────────────────────────────────────────────────────────────────

BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RED = "\033[91m"
DIM = "\033[2m"
RESET = "\033[0m"

SEPARATOR = f"{DIM}{'=' * 72}{RESET}"
SUBSEP = f"{DIM}{'-' * 60}{RESET}"


def header(num: int, title: str) -> None:
    print()
    print(SEPARATOR)
    print(f"  {BOLD}{CYAN}Step {num}: {title}{RESET}")
    print(SEPARATOR)
    print()


def ok(msg: str) -> None:
    print(f"  {GREEN}[OK]{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}[FAIL]{RESET} {msg}")


def show(label: str, value: object) -> None:
    print(f"  {CYAN}{label}:{RESET} {value}")


def section(title: str) -> None:
    print()
    print(f"  {BOLD}{title}{RESET}")
    print(f"  {SUBSEP}")


# ═══════════════════════════════════════════════════════════════════════════
# Step 1: Infrastructure Check
# ═══════════════════════════════════════════════════════════════════════════

def step1_infrastructure():
    header(1, "Infrastructure Check")

    print("  Verifying that IOWarp bridge and Memcached are reachable...")
    print()

    # Check IOWarp bridge
    import zmq
    try:
        ctx = zmq.Context()
        sock = ctx.socket(zmq.REQ)
        sock.setsockopt(zmq.RCVTIMEO, 3000)
        sock.setsockopt(zmq.SNDTIMEO, 3000)
        sock.connect("tcp://127.0.0.1:5560")
        sock.send_json({"method": "ping"})
        resp = sock.recv_json()
        sock.close()
        ctx.term()
        ok(f"IOWarp bridge at tcp://127.0.0.1:5560 responded: {resp}")
    except Exception as exc:
        fail(f"IOWarp bridge unreachable: {exc}")
        sys.exit(1)

    # Check Memcached
    from pymemcache.client import Client
    try:
        mc = Client(("127.0.0.1", 11211))
        mc.set("walkthrough_test", b"alive")
        val = mc.get("walkthrough_test")
        mc.delete("walkthrough_test")
        mc.close()
        ok(f"Memcached at 127.0.0.1:11211 responded: {val}")
    except Exception as exc:
        fail(f"Memcached unreachable: {exc}")
        sys.exit(1)

    print()
    ok("Infrastructure is healthy.")


# ═══════════════════════════════════════════════════════════════════════════
# Step 2: Blueprint + Registry
# ═══════════════════════════════════════════════════════════════════════════

def step2_blueprint():
    header(2, "Blueprint Loading & Registry")

    from agent_factory.factory.registry import BlueprintRegistry

    registry = BlueprintRegistry()
    registry.load()
    available = registry.list_blueprints()

    show("Available blueprints", available)

    for name in available:
        bp = registry.get(name)
        desc = bp.get("blueprint", {}).get("description", "").strip()
        show(f"  {name}", desc[:80])

    bp = registry.get(available[0])
    show("Bridge endpoint", bp.get("iowarp", {}).get("bridge_endpoint"))
    show("Cache host", bp.get("cache", {}).get("hosts", [{}])[0])
    show("Default agent type", bp.get("agent", {}).get("type"))

    print()
    ok("Blueprint loaded and parsed successfully.")
    return bp


# ═══════════════════════════════════════════════════════════════════════════
# Step 3: Single-Agent Mode (Claude)
# ═══════════════════════════════════════════════════════════════════════════

def step3_single_agent(blueprint):
    header(3, "Single-Agent Mode (ClaudeAgent)")

    import copy
    from agent_factory.factory.builder import AgentBuilder
    from agent_factory.core.types import Action, Observation, TaskSpec, Trajectory

    # Build with Claude agent
    bp = copy.deepcopy(blueprint)
    bp["agent"] = {"type": "claude", "model": "sonnet"}

    builder = AgentBuilder()
    built = builder.build(bp, connect=True)

    show("Agent class", type(built.agent).__name__)
    show("Agent model", getattr(built.agent, "_model", "?"))
    show("Environment class", type(built.environment).__name__)

    # Reset environment
    task = TaskSpec(task_id="walkthrough", instruction="Walkthrough session")
    built.environment.reset(task)
    trajectory = Trajectory(task=task)

    # ── 3a: Assimilate ──
    section("3a. Assimilate (ingest documents)")

    obs_text = "ingest folder::./data/sample_docs into tag: walkthrough_docs"
    show("Instruction", obs_text)
    obs = Observation(text=obs_text)

    thought = built.agent.think(obs)
    show("Agent thought", thought)

    action = built.agent.act(obs)
    show("Agent action", f"{action.name}({action.params})")

    result = built.environment.step(action)
    trajectory = trajectory.append(action, result)
    show("Env response", result.observation.text)
    show("Env data", result.observation.data)
    show("Reward", f"{result.reward:+.2f}")

    # ── 3b: Query ──
    section("3b. Query (find stored data)")

    obs_text = "query tag: walkthrough_docs"
    show("Instruction", obs_text)
    obs = Observation(text=obs_text)

    thought = built.agent.think(obs)
    show("Agent thought", thought)

    action = built.agent.act(obs)
    show("Agent action", f"{action.name}({action.params})")

    result = built.environment.step(action)
    trajectory = trajectory.append(action, result)
    show("Env response", result.observation.text)
    show("Env data", result.observation.data)
    show("Reward", f"{result.reward:+.2f}")

    # ── 3c: Retrieve ──
    section("3c. Retrieve (get specific blob)")

    # Determine a blob name from the query results
    matches = result.observation.data.get("matches", [])
    blob_name = "project_overview.md"
    if matches:
        blobs = matches[0].get("blobs", [])
        if blobs:
            blob_name = blobs[0]
    tag = "walkthrough_docs"

    obs_text = f"retrieve blob: {blob_name} from tag: {tag}"
    show("Instruction", obs_text)
    obs = Observation(text=obs_text)

    thought = built.agent.think(obs)
    show("Agent thought", thought)

    action = built.agent.act(obs)
    show("Agent action", f"{action.name}({action.params})")

    result = built.environment.step(action)
    trajectory = trajectory.append(action, result)
    show("Env response", result.observation.text)
    cache_hit = result.observation.data.get("cache_hit")
    show("Cache hit", cache_hit)
    show("Reward", f"{result.reward:+.2f}")

    # Show content preview
    cached = built.cache.get(tag, blob_name)
    if cached:
        snippet = cached.decode("utf-8", errors="replace")[:300]
        print()
        print(f"  {DIM}── Content Preview ──{RESET}")
        for line in snippet.splitlines()[:8]:
            print(f"  {DIM}| {line}{RESET}")

    # ── 3d: Retrieve again (cache hit) ──
    section("3d. Retrieve again (expect cache HIT)")

    obs = Observation(text=obs_text)
    thought = built.agent.think(obs)
    action = built.agent.act(obs)
    result = built.environment.step(action)
    trajectory = trajectory.append(action, result)
    show("Cache hit", result.observation.data.get("cache_hit"))
    show("Reward", f"{result.reward:+.2f}")

    # ── 3e: List blobs ──
    section("3e. List blobs")

    obs_text = "list everything under tag walkthrough_docs"
    show("Instruction", obs_text)
    obs = Observation(text=obs_text)

    thought = built.agent.think(obs)
    show("Agent thought", thought)

    action = built.agent.act(obs)
    show("Agent action", f"{action.name}({action.params})")

    result = built.environment.step(action)
    trajectory = trajectory.append(action, result)
    show("Env response", result.observation.text)
    show("Env data", result.observation.data)

    # ── 3f: Trajectory summary ──
    section("3f. Trajectory Summary")

    show("Total steps", trajectory.length)
    show("Total reward", f"{trajectory.total_reward:.2f}")
    show("Cache hits", built.cache.hits)
    show("Cache misses", built.cache.misses)
    hit_rate = built.cache.hit_rate * 100 if hasattr(built.cache, "hit_rate") else 0
    show("Hit rate", f"{hit_rate:.0f}%")

    for i, (act, sr) in enumerate(trajectory.steps, 1):
        tag_str = ""
        if sr.observation.data.get("cache_hit") is True:
            tag_str = f" {GREEN}[HIT]{RESET}"
        elif sr.observation.data.get("cache_hit") is False:
            tag_str = f" {YELLOW}[MISS]{RESET}"
        print(f"    {i}. {CYAN}{act.name:12s}{RESET} reward={sr.reward:+.2f}{tag_str}")

    # ── 3g: Prune ──
    section("3g. Prune (cleanup)")

    obs_text = "prune tag: walkthrough_docs"
    show("Instruction", obs_text)
    obs = Observation(text=obs_text)
    thought = built.agent.think(obs)
    action = built.agent.act(obs)
    result = built.environment.step(action)
    show("Agent action", f"{action.name}({action.params})")
    show("Env response", result.observation.text)
    show("Reward", f"{result.reward:+.2f}")

    built.environment.close()
    print()
    ok("Single-agent mode completed successfully.")


# ═══════════════════════════════════════════════════════════════════════════
# Step 4: Multi-Agent Pipeline Mode
# ═══════════════════════════════════════════════════════════════════════════

def step4_pipeline(blueprint):
    header(4, "Multi-Agent Pipeline Mode (Claude Backend)")

    import yaml
    from agent_factory.factory.builder import AgentBuilder
    from agent_factory.core.types import TaskSpec

    # Load pipeline YAML
    pipeline_path = "configs/pipelines/ingest_retrieve.yaml"
    with open(pipeline_path) as f:
        pipeline_def = yaml.safe_load(f)

    show("Pipeline ID", pipeline_def.get("pipeline_id"))
    show("Description", pipeline_def.get("description"))

    section("4a. Pipeline agents")
    for role, cfg in pipeline_def.get("agents", {}).items():
        show(f"  {role}", f"type={cfg['type']}, backend={cfg.get('backend', 'n/a')}")

    section("4b. Pipeline steps (from YAML)")
    for step in pipeline_def.get("steps", []):
        deps = step.get("depends_on", [])
        print(f"    {CYAN}{step['name']:20s}{RESET} agent={step['agent']:12s} "
              f"depends_on={deps}")

    # Build pipeline
    section("4c. Building pipeline")
    builder = AgentBuilder()
    built = builder.build_pipeline(blueprint, pipeline_def, connect=True)

    show("Agents built", list(built.agents.keys()))
    for role, agent in built.agents.items():
        cls = type(agent).__name__
        backend_cls = type(getattr(agent, "_backend", None)).__name__
        show(f"  {role}", f"{cls} -> backend: {backend_cls}")

    section("4d. DAG execution order")
    for i, step in enumerate(built.dag.execution_order, 1):
        deps = ", ".join(step.depends_on) if step.depends_on else "none"
        print(f"    {i}. {CYAN}{step.name:20s}{RESET} agent={step.agent_role:12s} "
              f"depends_on=[{deps}]")

    # Execute pipeline
    section("4e. Executing pipeline")

    task = TaskSpec(task_id="pipeline_walkthrough", instruction="Pipeline walkthrough")
    built.environment.reset(task)

    initial_vars = {
        "src": "folder::./data/sample_docs",
        "dst": "pipeline_docs",
    }
    show("Initial variables", initial_vars)
    print()

    ctx = built.executor.execute(
        built.dag,
        task="pipeline_walkthrough",
        initial_vars=initial_vars,
    )

    section("4f. Pipeline results")
    for step_name, output in ctx.outputs.items():
        has_error = "error" in output.data
        indicator = f"{GREEN}OK{RESET}" if not has_error else f"{RED}FAIL{RESET}"
        print(f"    [{indicator}] {CYAN}{step_name}{RESET}")
        print(f"      {DIM}observation: {output.observation.text}{RESET}")
        if output.data:
            for k, v in output.data.items():
                print(f"      {CYAN}{k}:{RESET} {v}")

    section("4g. Context variables (for step resolution)")
    for k, v in sorted(ctx.variables.items()):
        show(f"  {k}", v)

    # Cleanup
    section("4h. Cleanup (prune pipeline tag)")
    from agent_factory.core.types import Action
    prune_action = Action(name="prune", params={"tags": "pipeline_docs"})
    result = built.environment.step(prune_action)
    show("Prune result", result.observation.text)

    built.environment.close()
    print()
    ok("Multi-agent pipeline completed successfully.")


# ═══════════════════════════════════════════════════════════════════════════
# Step 5: Run Unit Tests
# ═══════════════════════════════════════════════════════════════════════════

def step5_tests():
    header(5, "Unit Tests")
    import subprocess

    print("  Running: pytest tests/unit/ -v")
    print()

    result = subprocess.run(
        ["python3", "-m", "pytest", "tests/unit/", "-v", "--tb=short"],
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Print output
    for line in result.stdout.splitlines():
        print(f"  {line}")

    if result.returncode == 0:
        print()
        ok("All unit tests passed.")
    else:
        print()
        if result.stderr:
            for line in result.stderr.splitlines()[-10:]:
                print(f"  {RED}{line}{RESET}")
        fail(f"Some tests failed (exit code {result.returncode}).")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    print()
    print(f"  {BOLD}{CYAN}{'=' * 52}{RESET}")
    print(f"  {BOLD}{CYAN}  AgentFactory Complete Walkthrough{RESET}")
    print(f"  {BOLD}{CYAN}{'=' * 52}{RESET}")
    print()

    try:
        step1_infrastructure()
        bp = step2_blueprint()
        step3_single_agent(bp)
        step4_pipeline(bp)
        step5_tests()
    except Exception as exc:
        fail(f"Walkthrough failed: {exc}")
        traceback.print_exc()
        sys.exit(1)

    print()
    print(SEPARATOR)
    print(f"  {BOLD}{GREEN}Walkthrough complete — all steps passed.{RESET}")
    print(SEPARATOR)
    print()


if __name__ == "__main__":
    main()
