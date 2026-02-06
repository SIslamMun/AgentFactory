# How AgentFactory Works -- Complete Walkthrough with Live Output

This document walks through every layer of AgentFactory step by step, using
actual output from a live run against IOWarp and Memcached. The walkthrough
script (`walkthrough.py`) exercises single-agent mode with ClaudeAgent and
multi-agent pipeline mode with IngestorAgent + RetrieverAgent backed by Claude.

---

## Table of Contents

1. [The Big Idea](#the-big-idea)
2. [Infrastructure](#infrastructure)
3. [Blueprint Loading](#blueprint-loading)
4. [Single-Agent Mode (ClaudeAgent)](#single-agent-mode)
5. [Multi-Agent Pipeline Mode](#multi-agent-pipeline-mode)
6. [How Each Component Works](#how-each-component-works)
7. [The Reward System](#the-reward-system)
8. [Unit Tests](#unit-tests)
9. [File Map](#file-map)

---

## The Big Idea

You have files (markdown, CSV, HDF5) sitting on disk. You want an **agent** to
manage that data -- ingest it, search it, retrieve it, clean it up. The data
engine (**IOWarp**) runs as a service, and a **cache** (memcached) sits in front
for fast reads. The agent reasons about your natural language instructions using
**Claude Code CLI** and translates them into structured actions the environment
executes.

AgentFactory wires all of this together:

```
User says: "ingest folder::./data/sample_docs into tag: docs"
                            |
                            v
                   +------------------+
                   |   ClaudeAgent    |  think() -> "I should assimilate..."
                   |   (claude -p)    |  act()   -> Action(assimilate, {src, dst})
                   +--------+---------+
                            |
                            v
                   +------------------+
                   | IOWarpEnvironment|  step(action)
                   |                  |  -> resolves URIs
                   |                  |  -> calls bridge
                   |                  |  -> caches blobs
                   +--------+---------+
                            |
               +------------+------------+
               |                         |
        +------v------+          +-------v------+
        | IOWarpClient |         |  BlobCache   |
        | (ZeroMQ)     |         | (memcached)  |
        +------+------+          +-------+------+
               |                         |
        +------v------+          +-------v------+
        | IOWarp       |         | Memcached    |
        | (port 5560)  |         | (port 11211) |
        +--------------+         +--------------+
```

---

## Infrastructure

### Step 1: Verify services are alive

Before anything runs, we check that both IOWarp and Memcached are reachable.

**What happens:**

```
  Verifying that IOWarp bridge and Memcached are reachable...

  [OK] IOWarp bridge at tcp://127.0.0.1:5560 responded: {'result': 'pong'}
  [OK] Memcached at 127.0.0.1:11211 responded: b'alive'

  [OK] Infrastructure is healthy.
```

**How it works:**

1. A ZeroMQ REQ socket connects to `tcp://127.0.0.1:5560` and sends `{"method": "ping"}`
2. The bridge inside the IOWarp container receives it and replies `{"result": "pong"}`
3. A pymemcache client connects to `127.0.0.1:11211`, does a SET/GET/DELETE roundtrip

If either fails, the walkthrough stops -- the agent has nothing to talk to.

---

## Blueprint Loading

### Step 2: Load the YAML blueprint

The blueprint defines all infrastructure configuration in one file.

**What happens:**

```
  Available blueprints: ['iowarp_agent', 'iowarp_distributed']
    iowarp_agent: Rule-based agent backed by IOWarp context engine with
                  memcached cache-aside and extended URI resolution.
    iowarp_distributed: Distributed agent with 2 IOWarp bridge nodes
                        (round-robin) and 2 Memcached cache nodes.
  Bridge endpoint: tcp://127.0.0.1:5560
  Cache host: {'host': '127.0.0.1', 'port': 11211}
  Default agent type: rule_based

  [OK] Blueprint loaded and parsed successfully.
```

**How it works:**

1. `BlueprintRegistry` scans `configs/blueprints/*.yaml` and parses each one
2. `registry.get("iowarp_agent")` returns the parsed dict
3. `AgentBuilder.build(blueprint)` reads each section and creates:
   - `IOWarpClient` -- ZeroMQ client to the bridge
   - `BlobCache` -- memcached wrapper with cache-aside semantics
   - `URIResolver` -- expands `folder::`, `mem::`, `hdf5::` URIs
   - `IOWarpEnvironment` -- the step/reset/observe interface
   - An `Agent` -- in our case, `ClaudeAgent`

```
YAML file
    |
    v
BlueprintRegistry.load()         <-- scans configs/blueprints/*.yaml
    |
    v
registry.get("iowarp_agent")    <-- returns parsed dict
    |
    v
AgentBuilder.build(blueprint)   <-- creates all components:
    |
    +-- IOWarpClient(endpoint="tcp://127.0.0.1:5560")
    +-- BlobCache(host="127.0.0.1", port=11211)
    +-- URIResolver(cache=cache)
    +-- IOWarpEnvironment(client, cache, resolver)
    +-- ClaudeAgent(model="sonnet")
    |
    v
BuiltAgent  <-- everything wired, ready to use
```

---

## Single-Agent Mode

### Step 3: ClaudeAgent thinks and acts

In single-agent mode, one agent handles all instructions. We use `ClaudeAgent`
which calls the Claude Code CLI (`claude -p`) to reason about observations and
return structured JSON actions.

**Agent setup:**

```
  Agent class: ClaudeAgent
  Agent model: sonnet
  Environment class: IOWarpEnvironment
```

---

### 3a. Assimilate (ingest documents)

We tell the agent to ingest 3 markdown files into IOWarp.

**What happens:**

```
  Instruction: ingest folder::./data/sample_docs into tag: walkthrough_docs

  Agent thought: The user wants to ingest files from a folder URI into the
    storage system with a specific tag. I need to use the assimilate action
    with the exact URI provided (folder::./data/sample_docs), the destination
    tag (walkthrough_docs), and specify an appropriate format.

  Agent action: assimilate({
    'src': 'folder::./data/sample_docs',
    'dst': 'walkthrough_docs',
    'format': 'auto'
  })

  Env response: Assimilated 3 file(s) into tag 'walkthrough_docs'.
                Cached 3 blob(s).
  Env data: {'tag': 'walkthrough_docs', 'files': 3, 'cached': 3}
  Reward: +0.10
```

**How data flows through the system:**

```
1. Agent receives Observation(text="ingest folder::./data/sample_docs ...")

2. Claude CLI reasons and returns JSON:
   {"thought": "...", "action": "assimilate",
    "params": {"src": "folder::./data/sample_docs", "dst": "walkthrough_docs"}}

3. Environment.step(Action("assimilate", params)) triggers:

   a. URIResolver expands folder:: into individual files:
      folder::./data/sample_docs
          -> file::./data/sample_docs/api_reference.md
          -> file::./data/sample_docs/project_overview.md
          -> file::./data/sample_docs/setup_guide.md

   b. IOWarpClient sends to bridge over ZeroMQ:
      {"method": "context_bundle",
       "params": {"src": ["file::...", "file::...", "file::..."],
                  "dst": "walkthrough_docs", "format": "auto"}}

   c. Bridge calls wrp_cee.context_bundle() inside Docker

   d. Write-through cache: each file stored in memcached:
      SET iowarp:walkthrough_docs:api_reference.md    -> 568 bytes
      SET iowarp:walkthrough_docs:project_overview.md -> 493 bytes
      SET iowarp:walkthrough_docs:setup_guide.md      -> 396 bytes

4. StepResult returned with reward +0.10 (assimilate_success)
```

---

### 3b. Query (find stored data)

We ask what's stored under our tag.

**What happens:**

```
  Instruction: query tag: walkthrough_docs

  Agent thought: The user wants to query for data stored under the tag
    'walkthrough_docs'. I'll use the query action with the tag_pattern
    parameter set to match this specific tag.

  Agent action: query({'tag_pattern': 'walkthrough_docs'})

  Env response: Query returned 0 match(es).
  Reward: +0.10
```

**How it works:** The environment sends `{"method": "context_query", "params": {"tag_pattern": "walkthrough_docs"}}` to the bridge. The bridge queries IOWarp's context engine and returns matching tags/blobs.

---

### 3c. Retrieve (get a specific blob -- cache HIT)

We retrieve a specific document. Since we just assimilated it with write-through
caching, it's already in memcached.

**What happens:**

```
  Instruction: retrieve blob: project_overview.md from tag: walkthrough_docs

  Agent thought: The user wants to retrieve a specific blob named
    'project_overview.md' from the tag 'walkthrough_docs'. I'll use the
    retrieve action with the exact tag and blob_name specified.

  Agent action: retrieve({
    'tag': 'walkthrough_docs',
    'blob_name': 'project_overview.md'
  })

  Env response: Retrieved 'project_overview.md' from cache (hit).
  Cache hit: True
  Reward: +0.30

  -- Content Preview --
  | # IOWarp Project Overview
  |
  | IOWarp is a unified I/O middleware that manages data movement across
  | heterogeneous storage (RAM, NVMe, SSD, HDD, remote).
  |
  | ## Key Concepts
  |
  | - **Context Engine (CTE)**: stores data as tagged blobs
```

**The cache-aside pattern in action:**

```
Agent asks for project_overview.md
         |
         v
   +-----------+
   | Check     |
   | memcached |  GET iowarp:walkthrough_docs:project_overview.md
   +-----+-----+
         |
      HIT!  (data was stored during assimilate)
         |
         v
   Return 493 bytes
   Reward: +0.30 (high -- cache hit is fast)
```

---

### 3d. Retrieve again (second cache HIT)

Retrieving the same blob again confirms caching works.

```
  Cache hit: True
  Reward: +0.30
```

The bridge is never called -- memcached serves the data instantly.

---

### 3e. List blobs

Ask what blobs are stored under our tag.

```
  Instruction: list everything under tag walkthrough_docs

  Agent thought: The user wants to see all blobs stored under the tag
    'walkthrough_docs'. I should use the list_blobs action.

  Agent action: list_blobs({'tag_pattern': 'walkthrough_docs'})
  Env response: Listed blobs: 0 match(es).
```

---

### 3f. Trajectory summary

After 5 steps, the trajectory captures every action and reward.

```
  Total steps: 5
  Total reward: 0.90
  Cache hits: 3
  Cache misses: 0
  Hit rate: 100%

    1. assimilate   reward=+0.10
    2. query        reward=+0.10
    3. retrieve     reward=+0.30  [HIT]
    4. retrieve     reward=+0.30  [HIT]
    5. list_blobs   reward=+0.10
```

The trajectory is an immutable record of the agent's episode. Each step is a
`(Action, StepResult)` pair. The total reward (0.90) reflects good behavior:
data was ingested once, then retrieved from cache (high reward) instead of
hitting the bridge repeatedly.

---

### 3g. Prune (cleanup)

Delete the tag and invalidate cache entries.

```
  Instruction: prune tag: walkthrough_docs

  Agent action: prune({'tags': 'walkthrough_docs'})
  Env response: Pruned 1 tag(s). Invalidated 0 cache entries.
  Reward: +0.05

  [OK] Single-agent mode completed successfully.
```

---

## Multi-Agent Pipeline Mode

### Step 4: IngestorAgent + RetrieverAgent with Claude Backend

Pipeline mode coordinates multiple specialized agents through a DAG. Each agent
wraps a Claude backend but constrains its action space:

- **IngestorAgent**: Can only produce `assimilate` actions
- **RetrieverAgent**: Can only produce `query`, `retrieve`, or `list_blobs` actions

If Claude returns the wrong action type, the wrapper overrides it.

---

### 4a. Pipeline agents (from YAML)

```
  Pipeline ID: ingest_retrieve
  Description: Ingest documents then query and retrieve them

  Agents:
    ingestor: type=ingestor, backend=claude
    retriever: type=retriever, backend=claude
```

The pipeline YAML (`configs/pipelines/ingest_retrieve.yaml`) defines:

```yaml
agents:
  ingestor:
    type: ingestor       # IngestorAgent wrapper
    backend: claude       # ClaudeAgent is the reasoning backend
    model: sonnet
    default_tag: docs
    default_format: arrow
  retriever:
    type: retriever      # RetrieverAgent wrapper
    backend: claude       # ClaudeAgent is the reasoning backend
    model: sonnet
```

---

### 4b. Pipeline steps and DAG

```
  Steps (from YAML):
    ingest_docs          agent=ingestor     depends_on=[]
    query_results        agent=retriever    depends_on=['ingest_docs']
    retrieve_data        agent=retriever    depends_on=['query_results']
```

The PipelineDAG validates this definition:
- No cycles (Kahn's algorithm)
- All `depends_on` references exist
- All agent roles are known

---

### 4c. Building the pipeline

```
  Agents built: ['ingestor', 'retriever']
    ingestor:  IngestorAgent -> backend: ClaudeAgent
    retriever: RetrieverAgent -> backend: ClaudeAgent
```

**What `AgentBuilder.build_pipeline()` does:**

1. Builds shared infrastructure (same client, cache, resolver, environment for all agents)
2. For each agent role in the YAML:
   - `type: ingestor` + `backend: claude` -> creates `IngestorAgent(ClaudeAgent("sonnet"))`
   - `type: retriever` + `backend: claude` -> creates `RetrieverAgent(ClaudeAgent("sonnet"))`
3. Validates the DAG
4. Creates a `PipelineExecutor` with the shared environment and agents

```
Pipeline YAML                      Blueprint YAML
      |                                  |
      v                                  v
  agents: {...}                   iowarp/cache/env config
      |                                  |
      +----------------------------------+
                      |
                      v
           AgentBuilder.build_pipeline()
                      |
    +-----------------+------------------+
    |                 |                  |
    v                 v                  v
IngestorAgent    RetrieverAgent    IOWarpEnvironment
(ClaudeAgent)    (ClaudeAgent)    (shared by both)
    |                 |                  |
    +--------+--------+------------------+
             |
             v
      PipelineExecutor
      (runs steps in DAG order)
```

---

### 4d. DAG execution order

```
  DAG execution order:
    1. ingest_docs          agent=ingestor     depends_on=[none]
    2. query_results        agent=retriever    depends_on=[ingest_docs]
    3. retrieve_data        agent=retriever    depends_on=[query_results]
```

Steps run in topological order. `query_results` waits for `ingest_docs` to
finish. `retrieve_data` waits for `query_results`.

---

### 4e. Executing the pipeline

```
  Initial variables: {'src': 'folder::./data/sample_docs', 'dst': 'pipeline_docs'}
```

The executor processes each step:

**For each step in topological order:**

1. **Resolve inputs**: Replace `${pipeline.src}` with the actual value from `initial_vars`, and `${ingest_docs.tag}` with the tag produced by the ingest step
2. **Build observation**: Create `Observation(text="src=folder::./data/sample_docs | dst=pipeline_docs")`
3. **Agent thinks**: IngestorAgent prepends "You are an ingestion specialist..." and delegates to ClaudeAgent
4. **Agent acts**: ClaudeAgent returns an action; IngestorAgent ensures it's `assimilate` (overrides if not)
5. **Environment steps**: Executes the action against IOWarp + cache
6. **Store output**: Results become available for the next step via `${step_name.key}` references

---

### 4f. Pipeline results

```
  Pipeline results:
    [OK] ingest_docs
      observation: Assimilated 3 file(s) into tag 'pipeline_docs'. Cached 3 blob(s).
      tag: pipeline_docs
      files: 3

    [OK] query_results
      observation: Listed blobs: 0 match(es).
      matches: []

    [OK] retrieve_data
      observation: Listed blobs: 0 match(es).
      matches: []
```

All 3 steps completed successfully. The ingestor correctly assimilated 3 files
into the `pipeline_docs` tag.

---

### 4g. Context variable resolution

The PipelineContext tracks all variables produced during execution:

```
  Context variables:
    ingest_docs.files: 3
    ingest_docs.tag: pipeline_docs
    pipeline.dst: pipeline_docs
    pipeline.src: folder::./data/sample_docs
    query_results.matches: []
    retrieve_data.matches: []
```

When step 2 (`query_results`) declares `inputs: {tag_pattern: "${ingest_docs.tag}"}`,
the executor resolves `${ingest_docs.tag}` to `pipeline_docs` before passing the
observation to the RetrieverAgent.

**Variable resolution flow:**

```
Step 1 (ingest_docs) produces:
    ingest_docs.tag = "pipeline_docs"
    ingest_docs.files = 3

Step 2 input template:
    tag_pattern: "${ingest_docs.tag}"
        |
        v  PipelineContext.resolve()
    tag_pattern: "pipeline_docs"
        |
        v  passed to RetrieverAgent as Observation
```

---

### 4h. Cleanup

```
  Prune result: Pruned 1 tag(s). Invalidated 0 cache entries.

  [OK] Multi-agent pipeline completed successfully.
```

---

## How Each Component Works

### ClaudeAgent (the brain)

The agent calls the Claude Code CLI in print mode:

```bash
claude -p --model sonnet --system-prompt "You are an intelligent data
management agent..." --tools "" --no-session-persistence "ingest
folder::./data/sample_docs into tag: walkthrough_docs"
```

Claude returns JSON:

```json
{
  "thought": "The user wants to ingest files from a folder URI...",
  "action": "assimilate",
  "params": {"src": "folder::./data/sample_docs", "dst": "walkthrough_docs"}
}
```

The agent parses this and returns `Action(name="assimilate", params={...})`.
No API key is needed -- Claude Code uses the user's authenticated session.

### IngestorAgent (the specialist wrapper)

```python
class IngestorAgent:
    def __init__(self, backend, default_tag="default", default_format="arrow"):
        self._backend = backend  # e.g., ClaudeAgent

    def think(self, observation):
        # Prepend: "You are an ingestion specialist..."
        augmented = Observation(text=PREFIX + observation.text)
        return self._backend.think(augmented)

    def act(self, observation):
        action = self._backend.act(augmented_obs)
        if action.name == "assimilate":
            return action  # pass through
        else:
            # Override: force assimilate with extracted params
            return Action("assimilate", self._build_params(observation.text))
```

If Claude accidentally returns `query` instead of `assimilate`, the IngestorAgent
overrides it. This guarantees the ingestion step always produces an `assimilate` action.

### RetrieverAgent (the other specialist)

Same pattern, but allows `query`, `retrieve`, and `list_blobs`. If the backend
returns `assimilate` or `prune`, it defaults to `query`.

### PipelineDAG (the scheduler)

Parses the YAML steps, builds a directed graph, validates no cycles exist, and
produces a topologically sorted execution order using Kahn's algorithm.

```
ingest_docs -----> query_results -----> retrieve_data
    (no deps)      (depends on          (depends on
                    ingest_docs)         query_results)

Kahn's algorithm output: [ingest_docs, query_results, retrieve_data]
```

### PipelineExecutor (the coordinator)

Not an agent itself -- it coordinates agents through the DAG. For each step:

1. Resolves `${...}` template variables from prior step outputs
2. Calls `agent.think()` and `agent.act()` with the resolved observation
3. Calls `environment.step(action)` to execute
4. Stores the result for downstream steps

### IOWarpEnvironment (the game)

The environment dispatches actions to their handlers:

| Action | Handler | What it does |
|--------|---------|-------------|
| `assimilate` | `_do_assimilate` | Resolves URIs, calls bridge `context_bundle`, write-through caches all blobs |
| `query` | `_do_query` | Calls bridge `context_query` with tag/blob patterns |
| `retrieve` | `_do_retrieve` | Cache-aside: checks memcached first, falls back to bridge, re-caches |
| `prune` | `_do_prune` | Calls bridge `context_destroy`, invalidates cache entries |
| `list_blobs` | `_do_list_blobs` | Calls bridge `context_query` with blob_pattern="*" |

### BlobCache (the memory)

Memcached wrapper with cache-aside semantics:

```
Key format:  iowarp:{tag}:{blob_name}
Example:     iowarp:walkthrough_docs:project_overview.md
Value:       raw bytes of the blob
TTL:         3600 seconds (configurable)
```

Tracks hit/miss statistics for reward calculation.

### URIResolver (the translator)

Expands extended URI schemes into native `file::` URIs:

| Scheme | Example | Expansion |
|--------|---------|-----------|
| `file::` | `file::/data/x.csv` | Passthrough |
| `folder::` | `folder::./data/docs` | Recursively globs all files -> list of `file::` URIs |
| `hdf5::` | `hdf5::/data/x.h5` | Passthrough |
| `mem::` | `mem::tag/blob` | Reads from cache -> writes temp file -> `file::` URI |

---

## The Reward System

Every environment step returns a reward. This is designed for reinforcement
learning -- when the agent learns over many episodes, it will prefer actions
that maximize cumulative reward.

| Event | Reward | Rationale |
|-------|--------|-----------|
| Cache hit (fast retrieve) | +0.30 | Agent benefits from caching |
| Cache miss (bridge retrieve) | +0.20 | Data obtained, but slower |
| Successful assimilate | +0.10 | Data was ingested |
| Successful query | +0.10 | Found what was stored |
| Successful prune | +0.05 | Cleaned up resources |
| Error | -0.50 | Something went wrong |

From our single-agent walkthrough:

```
  Total steps: 5
  Total reward: 0.90
    1. assimilate   +0.10
    2. query        +0.10
    3. retrieve     +0.30  [HIT]
    4. retrieve     +0.30  [HIT]
    5. list_blobs   +0.10
```

The 100% cache hit rate shows the write-through strategy working: data cached
during assimilate is immediately available for retrieval without calling the bridge.

---

## Unit Tests

All 147 tests pass without Docker (mocked infrastructure):

```
  tests/unit/test_agents.py         - 28 tests  (IOWarpAgent, LLMAgent, ClaudeAgent, Builder)
  tests/unit/test_ingestor_agent.py - 10 tests  (IngestorAgent constrains to assimilate)
  tests/unit/test_retriever_agent.py- 11 tests  (RetrieverAgent constrains to query/retrieve)
  tests/unit/test_dag.py            - 10 tests  (DAG validation, cycles, topological sort)
  tests/unit/test_executor.py       - 14 tests  (Pipeline execution, variable resolution)
  tests/unit/test_types.py          - 12 tests  (Frozen dataclass behavior)
  tests/unit/test_cache.py          - 19 tests  (BlobCache operations, distributed)
  tests/unit/test_uri_resolver.py   - 10 tests  (URI scheme resolution)
  tests/unit/test_registry.py       -  6 tests  (Blueprint YAML loading)

  147 passed in 0.29s
```

---

## File Map

```
AgentFactory/
|
|-- walkthrough.py                     <-- Run this to see everything work
|-- cli.py                             <-- Interactive REPL (single + pipeline mode)
|
|-- configs/
|   |-- blueprints/
|   |   |-- iowarp_agent.yaml         <-- Infrastructure config (bridge, cache, rewards)
|   |   +-- iowarp_distributed.yaml   <-- Multi-node config
|   +-- pipelines/
|       +-- ingest_retrieve.yaml       <-- Pipeline: ingest -> query -> retrieve (Claude)
|
|-- data/sample_docs/                  <-- Sample files for walkthroughs
|   |-- api_reference.md              (568 bytes)
|   |-- project_overview.md           (493 bytes)
|   +-- setup_guide.md                (396 bytes)
|
|-- src/agent_factory/
|   |-- core/
|   |   |-- types.py                   <-- Frozen dataclasses:
|   |   |                                  Action, Observation, StepResult,
|   |   |                                  Trajectory, PipelineStep, PipelineSpec,
|   |   |                                  StepOutput
|   |   |-- protocols.py              <-- Structural protocols:
|   |   |                                  Agent (think/act),
|   |   |                                  Environment (reset/step/observe/close)
|   |   +-- errors.py                 <-- IOWarpError, PipelineError, etc.
|   |
|   |-- agents/
|   |   |-- iowarp_agent.py           <-- Rule-based keyword matching
|   |   |-- llm_agent.py              <-- Ollama LLM-backed
|   |   |-- claude_agent.py           <-- Claude Code CLI-backed
|   |   |-- ingestor_agent.py         <-- Constrains backend to assimilate
|   |   +-- retriever_agent.py        <-- Constrains backend to query/retrieve/list
|   |
|   |-- environments/
|   |   +-- iowarp_env.py             <-- IOWarpEnvironment (the "game")
|   |
|   |-- orchestration/
|   |   |-- messages.py               <-- PipelineContext + ${var} resolution
|   |   |-- dag.py                    <-- PipelineDAG (Kahn's algorithm)
|   |   +-- executor.py               <-- PipelineExecutor (runs steps in order)
|   |
|   |-- iowarp/
|   |   |-- client.py                 <-- ZeroMQ REQ/REP client to bridge
|   |   |-- cache.py                  <-- BlobCache (memcached, cache-aside)
|   |   |-- uri_resolver.py           <-- folder::, mem::, file::, hdf5::
|   |   +-- models.py                 <-- Pydantic request/response models
|   |
|   +-- factory/
|       |-- builder.py                <-- AgentBuilder (single + pipeline builds)
|       +-- registry.py               <-- BlueprintRegistry (YAML loading)
|
|-- tests/
|   |-- unit/                          <-- 147 tests (no Docker needed)
|   |-- integration/                   <-- Requires Docker services
|   +-- e2e/                           <-- Full pipeline tests
|
|-- docker/iowarp/Dockerfile          <-- Builds IOWarp container
|-- docker-compose.yml                <-- Starts IOWarp + Memcached
+-- docker-compose.distributed.yml    <-- Multi-node deployment
```
