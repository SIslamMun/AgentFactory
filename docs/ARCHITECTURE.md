# AgentFactory — Architecture & Design Document

## Table of Contents

- [Overview](#overview)
- [High-Level Architecture](#high-level-architecture)
- [Project Structure](#project-structure)
- [Layer 1: Core Types & Protocols](#layer-1-core-types--protocols)
- [Layer 2: Agents](#layer-2-agents)
- [Layer 3: Environment](#layer-3-environment)
- [Layer 4: IOWarp Infrastructure](#layer-4-iowarp-infrastructure)
- [Layer 5: Docker & The CTE Bridge](#layer-5-docker--the-cte-bridge)
- [Layer 6: Factory & Registry](#layer-6-factory--registry)
- [Layer 7: Orchestration (Pipelines)](#layer-7-orchestration-pipelines)
- [Layer 8: CLI](#layer-8-cli)
- [Data Flow Patterns](#data-flow-patterns)
- [Complete Request Lifecycle](#complete-request-lifecycle)
- [Design Patterns](#design-patterns)
- [Key Problems Solved](#key-problems-solved)
- [How to Run](#how-to-run)

---

## Overview

AgentFactory is a **multi-agent reinforcement learning framework** for intelligent data management. It allows users to interact with agents via natural language (e.g., "ingest this folder", "get that file"), and the system determines the appropriate action — using LLMs for reasoning, IOWarp for persistent storage, and Memcached for fast caching.

**Key Technologies:**

- Python 3.10+
- ZeroMQ (bridge communication between host and IOWarp container)
- Memcached (fast caching layer)
- IOWarp / Chimaera (persistent distributed storage engine)
- Claude Code CLI / Ollama (LLM backends for agent reasoning)
- Pydantic (data validation for JSON-RPC messages)
- PyYAML (blueprint configuration)

---

## High-Level Architecture

```
+------------------------------------------------------------------+
|                          USER (CLI)                               |
|    "ingest folder::./data/test_docs as research"                  |
+-------------------------------+----------------------------------+
                                |
                                v
+------------------------------------------------------------------+
|                    COORDINATOR AGENT                              |
|    Uses Claude Sonnet to parse intent -> routes to sub-agent      |
|    "This is an ingest command -> route to ingestor"               |
+---------------+-------------------------------+------------------+
                |                               |
      +---------v----------+          +---------v---------+
      |    INGESTOR        |          |    RETRIEVER      |
      |    Agent           |          |    Agent          |
      |  (assimilate only) |          |  (query, retrieve,|
      |                    |          |   list, destroy,  |
      |                    |          |   prune)          |
      +---------+----------+          +---------+---------+
                |                               |
                +---------------+---------------+
                                |
                                v
+------------------------------------------------------------------+
|                    IOWARP ENVIRONMENT                             |
|    Executes actions, computes rewards, manages two-tier storage   |
|                                                                   |
|    +------------------+          +--------------------+           |
|    |   MEMCACHED      |<-------->|   IOWARP (CTE)    |           |
|    |   (fast cache)   |          | (persistent store) |           |
|    |   Port 11211     |          | Shared memory IPC  |           |
|    +------------------+          +--------------------+           |
+------------------------------------------------------------------+
```

---

## Project Structure

```
AgentFactory/
|-- src/agent_factory/                     # Main source code
|   |-- core/                              # Core abstractions and types
|   |   |-- types.py                       # Frozen dataclass value objects
|   |   |-- protocols.py                   # PEP 544 structural protocols
|   |   +-- errors.py                      # Exception hierarchy
|   |
|   |-- factory/                           # Agent instantiation
|   |   |-- builder.py                     # AgentBuilder orchestration
|   |   +-- registry.py                    # BlueprintRegistry (YAML configs)
|   |
|   |-- iowarp/                            # IOWarp client and infrastructure
|   |   |-- client.py                      # ZeroMQ REQ client
|   |   |-- models.py                      # Pydantic JSON-RPC models
|   |   |-- cache.py                       # BlobCache (memcached wrapper)
|   |   +-- uri_resolver.py                # Extended URI scheme resolver
|   |
|   |-- agents/                            # Agent implementations
|   |   |-- iowarp_agent.py                # Rule-based keyword agent
|   |   |-- llm_agent.py                   # Ollama-powered agent
|   |   |-- claude_agent.py                # Claude Code CLI agent
|   |   |-- ingestor_agent.py              # Wrapper: assimilate only
|   |   |-- retriever_agent.py             # Wrapper: query/retrieve/list/destroy/prune
|   |   +-- coordinator_agent.py           # LLM router to specialized agents
|   |
|   |-- environments/                      # Environment implementations
|   |   +-- iowarp_env.py                  # IOWarpEnvironment (action executor)
|   |
|   +-- orchestration/                     # Multi-agent pipeline execution
|       |-- dag.py                         # PipelineDAG (topological sort)
|       |-- executor.py                    # PipelineExecutor
|       +-- messages.py                    # PipelineContext (variable resolution)
|
|-- docker/                                # Container definitions
|   +-- iowarp/
|       |-- Dockerfile                     # IOWarp container build
|       |-- bridge.py                      # ZeroMQ REP bridge (in container)
|       |-- wrp_cee.py                     # CTE wrapper (subprocess + stub)
|       |-- cte_helper.cpp                 # C++ binary for CTE operations
|       |-- CMakeLists.txt                 # CMake build for cte_helper
|       |-- wrp_conf.yaml                  # IOWarp runtime config
|       +-- wrp_cee_ctypes.py              # Alternative ctypes approach
|
|-- configs/                               # Configuration
|   |-- blueprints/                        # Agent blueprint YAML files
|   |   |-- coordinator_agent.yaml
|   |   |-- ingestor_agent.yaml
|   |   |-- retriever_agent.yaml
|   |   +-- iowarp_agent.yaml
|   +-- pipelines/
|       +-- ingest_retrieve.yaml           # Example pipeline DAG
|
|-- tests/                                 # Test suite
|   |-- unit/                              # Unit tests (no external deps)
|   |-- integration/                       # Integration tests (requires Docker)
|   +-- e2e/                               # End-to-end tests
|
|-- data/                                  # Sample/test data
|   |-- sample_docs/
|   +-- test_docs/
|
|-- docker-compose.yml                     # Infrastructure (IOWarp + Memcached)
|-- cli.py                                 # Interactive CLI REPL
|-- pyproject.toml                         # Package metadata
+-- README.md
```

---

## Layer 1: Core Types & Protocols

**Location:** `src/agent_factory/core/`

The foundation layer. Defines the "language" that every component speaks.

### Types (`core/types.py`)

All types are **frozen dataclasses** (immutable value objects):

| Type | Purpose | Key Fields |
|------|---------|------------|
| `TaskSpec` | Describes a task for the agent | `task_id`, `instruction`, `metadata` |
| `Observation` | What the agent sees | `text`, `data`, `done` |
| `Action` | What the agent decides to do | `name`, `params` |
| `StepResult` | Outcome of one step | `observation`, `reward`, `done`, `info` |
| `Trajectory` | History of all steps | `task`, `steps` (list of action+result) |
| `PipelineStep` | One step in a pipeline DAG | `name`, `agent_role`, `inputs`, `outputs`, `depends_on` |
| `PipelineSpec` | Full pipeline definition | `pipeline_id`, `description`, `steps` |

### Protocols (`core/protocols.py`)

PEP 544 structural protocols — contracts that components must satisfy:

```python
@runtime_checkable
class Agent(Protocol):
    def think(self, observation: Observation) -> str: ...
    def act(self, observation: Observation) -> Action: ...

@runtime_checkable
class Environment(Protocol):
    def reset(self, task: TaskSpec) -> Observation: ...
    def step(self, action: Action) -> StepResult: ...
    def observe(self) -> Observation: ...
    def close(self) -> None: ...
```

Any class with these methods works — no inheritance needed (duck typing).

### Errors (`core/errors.py`)

Custom exception hierarchy:

```
IOWarpError (base)
  |-- BridgeConnectionError    # ZeroMQ communication failures
  |-- CacheError               # Memcached failures
  |-- URIResolveError          # URI scheme resolution failures
  |-- BlueprintError           # Blueprint loading/validation
  +-- PipelineError            # Pipeline definition/execution
```

---

## Layer 2: Agents

**Location:** `src/agent_factory/agents/`

Six agent types, all implementing the same `think()` + `act()` interface.

### Base Agents (Do the Reasoning)

| Agent | File | How It Decides | Speed | Intelligence |
|-------|------|---------------|-------|-------------|
| `IOWarpAgent` | `iowarp_agent.py` | Keyword regex matching | Instant | Low (rule-based) |
| `LLMAgent` | `llm_agent.py` | Ollama (llama3.2 local) | ~2s | Medium |
| `ClaudeAgent` | `claude_agent.py` | Claude Code CLI (`claude -p`) | ~4s | High |

#### IOWarpAgent (Rule-Based)

Maps keywords to actions using ordered regex rules (first match wins):

| Keywords | Action |
|----------|--------|
| `ingest`, `assimilate`, `import`, `load` | `assimilate` |
| `find`, `search`, `query` | `query` |
| `list` | `list_blobs` |
| `get`, `retrieve`, `fetch`, `read` | `retrieve` |
| `destroy`, `delete`, `remove` | `destroy` |
| `prune`, `evict` | `prune` |

Includes parameter extractors for URIs, tags, blob names, and cache-bypass keywords.

#### ClaudeAgent

Calls the locally installed Claude Code CLI:

```bash
claude -p \
  --model sonnet \
  --system-prompt "You are an IOWarp agent..." \
  --tools "" \
  --no-session-persistence \
  "{observation_text}"
```

Returns JSON: `{"thought": "...", "action": "...", "params": {...}}`

No API key needed — uses the user's existing Claude Code session.

#### LLMAgent

Uses Ollama Python SDK to call a local LLM (e.g., llama3.2). Same JSON response format as ClaudeAgent.

### Wrapper Agents (Constrain Actions)

These wrap any base agent and enforce action constraints using the **decorator pattern**:

| Wrapper | Wraps | Allowed Actions | Purpose |
|---------|-------|----------------|---------|
| `IngestorAgent` | Any base agent | `assimilate` only | Data loading specialist |
| `RetrieverAgent` | Any base agent | `query`, `retrieve`, `list_blobs`, `destroy`, `prune` | Data access specialist |

How it works:

```
User input
  -> RetrieverAgent.act()
       -> Prepends context: "You are a data-access specialist..."
       -> ClaudeAgent.act()       <-- does the actual thinking
       -> If action not in allowed set -> default to "query"
       -> Returns constrained action
```

### CoordinatorAgent (Orchestrator)

Routes natural language commands to the appropriate sub-agent using Claude:

```
User: "ingest folder::./data as research"
  -> CoordinatorAgent.think()
       -> claude -p: "Parse this command..."
       -> Claude returns: {"agent": "ingestor", "instruction": "assimilate ..."}
  -> CoordinatorAgent.act()
       -> self._agents["ingestor"].agent.act(instruction)
       -> IngestorAgent handles it
```

**Routing rules:**
- **Ingestor** for: loading, ingesting, importing, uploading, assimilating (WRITE operations)
- **Retriever** for: querying, searching, finding, listing, retrieving, getting, deleting, pruning (READ/DELETE operations)

---

## Layer 3: Environment

**Location:** `src/agent_factory/environments/iowarp_env.py`

The environment **executes actions** and **computes rewards**. It manages the two-tier storage system.

### Action Handlers

| Action | What Happens | Touches IOWarp? | Touches Cache? | Reward |
|--------|-------------|-----------------|----------------|--------|
| `assimilate` | Resolve URIs -> write to IOWarp -> write-through cache | Yes (write) | Yes (write) | +0.10 |
| `query` | Query IOWarp first, fallback to cache | Yes (read) | Fallback only | +0.10 |
| `retrieve` | Check cache -> miss -> fetch from IOWarp -> re-cache | Fallback | Yes (read/write) | +0.30 (hit) / +0.20 (miss) |
| `list_blobs` | List all blobs for a tag pattern | Yes (read) | No | +0.10 |
| `prune` | Evict specific blob(s) from **cache only** | **No** | Yes (delete) | +0.05 |
| `destroy` | Delete entire tag from **both** stores | Yes (delete) | Yes (delete) | +0.05 |
| (error) | Any failure | - | - | -0.50 |

### Reward Configuration

```python
@dataclass
class RewardConfig:
    cache_hit: float = 0.3           # Fast path rewarded most
    cache_miss: float = 0.2          # IOWarp fallback still good
    assimilate_success: float = 0.1  # Data ingestion
    query_success: float = 0.1       # Data discovery
    prune_success: float = 0.05      # Cache management
    error: float = -0.5              # Negative signal
```

### Prune vs Destroy

| | Prune | Destroy |
|---|-------|---------|
| **Scope** | Specific blob(s) | Entire tag(s) |
| **Cache** | Evicts from memcached | Invalidates from memcached |
| **IOWarp** | **Data remains** | **Data deleted permanently** |
| **Use case** | Cache management / refresh | Permanent deletion |
| **After prune** | Next retrieve = cache miss -> re-fetch from IOWarp | Data is gone |

---

## Layer 4: IOWarp Infrastructure

**Location:** `src/agent_factory/iowarp/`

Four components connecting the Python application to IOWarp:

### Client (`client.py`)

ZeroMQ REQ client that communicates with the bridge inside the Docker container:

```
Python App  --ZMQ REQ-->  bridge.py (Docker)
              JSON-RPC        |
                              v
                          wrp_cee.py
                              |
                              v
                          cte_helper (C++ binary)
                              |
                              v
                          IOWarp CTE (shared memory)
```

**Features:**
- Single or multi-endpoint support
- Round-robin load balancing across peers
- Automatic failover (marks failed peers as down, retries others)
- Socket recreation after timeouts

**API:**
- `context_bundle(src, dst, format)` — Assimilate data
- `context_query(tag_pattern, blob_pattern)` — Query for blobs
- `context_retrieve(tag, blob_name)` — Retrieve blob data
- `context_destroy(tags)` — Destroy tags

### Cache (`cache.py`)

Memcached wrapper implementing cache-aside pattern:

- **Key format:** `iowarp:{tag}:{blob_name}` (SHA-256 hashed if >250 bytes)
- **Single node:** `pymemcache.Client`
- **Multi-node:** `pymemcache.HashClient` (consistent-hash sharding)
- **Stats tracking:** hit/miss counts for reward computation

**API:**
- `get(tag, blob_name) -> bytes | None`
- `put(tag, blob_name, data, ttl=None)`
- `delete(tag, blob_name) -> bool`
- `invalidate_tag(tag, blob_names=None) -> int`

### URI Resolver (`uri_resolver.py`)

Expands extended URI schemes into `file::` URIs the bridge understands:

| Scheme | Behavior |
|--------|----------|
| `file::/path` | Passthrough (single file) |
| `folder::/dir` | Recursive glob -> list of `file::` URIs |
| `mem::tag/blob` | Read from cache -> temp file -> `file::` URI |
| `hdf5::/path` | Passthrough (native IOWarp) |

### Models (`models.py`)

Pydantic models for the JSON-RPC protocol between client and bridge:

- `BridgeRequest(method, params, id)`
- `BridgeResponse(result, error, id)`
- `BundleParams`, `BundleResult`
- `QueryParams`, `QueryResultModel`
- `RetrieveParams`, `RetrieveResultModel`
- `DestroyParams`, `DestroyResult`

---

## Layer 5: Docker & The CTE Bridge

**Location:** `docker/iowarp/`

### The Problem

IOWarp's Python extension (`wrp_cte_core_ext.so`) links **both** LLVM's `libc++` and GCC's `libstdc++` simultaneously. This causes a `std::bad_cast` error on import — an ABI conflict that cannot be fixed without rebuilding IOWarp itself.

### The Solution

Bypass the broken Python extension entirely. Use a **C++ subprocess helper** that communicates via JSON over stdin/stdout:

```
Python (wrp_cee.py)
    |
    |  stdin: {"cmd": "put", "tag": "research", "blob": "alpha.txt", "data": "48656c6c6f"}
    |  stdout: {"status": "ok"}
    |
    v
C++ Binary (cte_helper)
    |
    |  CTE API calls (shared memory IPC)
    |
    v
IOWarp Chimaera Runtime (CTE pool + RAM storage)
```

### Component Details

#### `cte_helper.cpp`

C++ binary compiled against IOWarp's native libraries:

- Connects to Chimaera runtime as a client
- Reads JSON commands from stdin, writes JSON responses to stdout
- **Commands:** `put`, `get`, `get_size`, `list_blobs`, `tag_query`, `del_blob`, `del_tag`, `ping`, `quit`
- Binary data encoded as hex for JSON safety

#### `wrp_cee.py`

Python wrapper that manages the cte_helper subprocess:

```python
# Initialization
_helper_proc = subprocess.Popen(
    ["/usr/local/bin/cte_helper"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True, bufsize=1,
)
# Read lines until JSON ready message
for _ in range(50):
    line = _helper_proc.stdout.readline().strip()
    if line.startswith("{"):
        ready = json.loads(line)
        break
```

- Thread-safe command queue with lock
- Falls back to in-memory stub if cte_helper is unavailable
- Stub returns `{"stub": true}` marker for transparency

#### `bridge.py`

ZeroMQ REP server running inside the Docker container:

- Listens on `tcp://0.0.0.0:5560`
- Receives JSON-RPC requests from host's `IOWarpClient`
- Dispatches to `wrp_cee` module
- Hex-encodes binary data for JSON transport

#### `wrp_conf.yaml`

IOWarp runtime configuration. The **compose section** is critical — without it, no storage targets exist and all PutBlob calls fail with error 11:

```yaml
chimaera:
  work_orchestrator:
    max_workers: 4
  queue_manager:
    max_depth: 16384
    batch_size: 16

compose:
  - mod_name: wrp_cte_core
    pool_name: wrp_cte_core
    pool_query: local
    pool_id: "512.0"
    storage:
      - path: "ram::cte_ram_cache"
        bdev_type: "ram"
        capacity_limit: "2GB"
        score: 1.0
```

#### `Dockerfile`

```dockerfile
FROM iowarp/iowarp:latest
USER root

# Install build dependencies
RUN apt-get update -qq && \
    apt-get install -y -qq --no-install-recommends \
        cmake pkg-config libelf-dev libyaml-cpp-dev libopenmpi-dev \
        libcereal-dev libboost-all-dev libpgm-dev libxml2-dev \
        libzmq3-dev libnorm-dev libsodium-dev && \
    pip3 install --no-cache-dir --break-system-packages pyzmq pydantic

# Build cte_helper
COPY cte_helper.cpp CMakeLists.txt /tmp/cte_build/
RUN cd /tmp/cte_build && mkdir build && cd build && \
    cmake .. -DCMAKE_BUILD_TYPE=Release && \
    make -j$(nproc) && \
    cp cte_helper /usr/local/bin/cte_helper

COPY bridge.py wrp_cee.py /opt/agent-factory/
COPY wrp_conf.yaml /etc/iowarp/wrp_conf.yaml

ENV WRP_RUNTIME_CONF=/etc/iowarp/wrp_conf.yaml

CMD ["sh", "-c", "chimaera_start_runtime & sleep 5 && python3 /opt/agent-factory/bridge.py"]
```

#### `docker-compose.yml`

```yaml
services:
  iowarp:
    build: ./docker/iowarp
    network_mode: host
    ipc: shareable
    shm_size: "8g"            # 8GB shared memory for CTE
    volumes:
      - .:/workspace
      - ./data:/data
    environment:
      - BRIDGE_PORT=5560

  memcached:
    image: memcached:1.6-alpine
    network_mode: host
    command: memcached -m 512 -I 8m -p 11211
    # 512MB memory, 8MB max item size
```

---

## Layer 6: Factory & Registry

**Location:** `src/agent_factory/factory/`

### BlueprintRegistry (`registry.py`)

Discovers, loads, validates, and manages agent blueprint YAML files:

- **`load()`** — Scans `configs/blueprints/*.yaml`
- **`get(name)`** — Returns parsed blueprint dict
- **`list_blueprints()`** — Returns all blueprint names
- **`create(name, agent_type)`** — Create new blueprint from defaults
- **`update(name, **overrides)`** — Modify existing blueprint
- **`delete(name)`** — Remove blueprint file
- **`duplicate(src, dst)`** — Clone a blueprint

### Default Blueprint Structure

```yaml
blueprint:
  name: my_agent
  version: 0.1.0
  description: "..."

iowarp:
  bridge_endpoint: tcp://127.0.0.1:5560
  connect_timeout_ms: 5000
  request_timeout_ms: 30000

cache:
  hosts:
    - host: 127.0.0.1
      port: 11211
  key_prefix: iowarp
  default_ttl: 3600
  max_value_size: 10485760

uri_resolver:
  temp_dir: /tmp/agent-factory/uri-cache
  supported_schemes: ['file::', 'hdf5::', 'folder::', 'mem::']

environment:
  type: iowarp
  default_format: arrow
  reward:
    cache_hit: 0.3
    cache_miss: 0.2
    assimilate_success: 0.1
    query_success: 0.1
    prune_success: 0.05
    error: -0.5

agent:
  type: rule_based    # or llm, claude, ingestor, retriever, coordinator
```

### AgentBuilder (`builder.py`)

Takes a blueprint dict and wires everything together:

```
Blueprint YAML
    |
    v
AgentBuilder.build(blueprint)
    |
    |-- _build_infra()
    |     -> IOWarpClient (ZMQ connection to bridge)
    |     -> BlobCache (Memcached connection)
    |     -> URIResolver (URI scheme expansion)
    |     -> IOWarpEnvironment (action execution + rewards)
    |
    |-- if type == "coordinator":
    |     _build_coordinator_with_agents()
    |       |-- Build Claude backend for routing
    |       |-- BlueprintRegistry.load() -> scan all blueprints
    |       |-- For each non-coordinator blueprint:
    |       |     Build specialized agent
    |       |     Wrap in BuiltAgent with SHARED infrastructure
    |       +-- Return CoordinatorAgent(backend, agents_dict)
    |
    |-- else: _build_agent(agent_cfg)
    |     rule_based  -> IOWarpAgent
    |     llm         -> LLMAgent(ollama)
    |     claude      -> ClaudeAgent(cli)
    |     ingestor    -> IngestorAgent(backend)
    |     retriever   -> RetrieverAgent(backend)
    |
    +-- Return BuiltAgent(client, cache, resolver, environment, agent, blueprint)
```

**Key design:** All sub-agents share the **same infrastructure** (one client, one cache, one environment). An ingest through the ingestor and a retrieve through the retriever hit the same IOWarp and the same Memcached.

### BuiltAgent

```python
@dataclass
class BuiltAgent:
    client: IOWarpClient
    cache: BlobCache
    resolver: URIResolver
    environment: IOWarpEnvironment
    agent: Any               # Satisfies Agent protocol
    blueprint: dict[str, Any]
```

---

## Layer 7: Orchestration (Pipelines)

**Location:** `src/agent_factory/orchestration/`

For predefined multi-step pipelines (alternative to coordinator's dynamic routing).

### PipelineDAG (`dag.py`)

Validates and topologically sorts pipeline steps using Kahn's algorithm:

- Checks for duplicate step names
- Validates dependency references exist
- Verifies agent roles are known
- Detects cycles (raises `PipelineError`)

### PipelineExecutor (`executor.py`)

Executes steps in topological order:

1. Resolve `${step_name.key}` input references from prior outputs
2. Build `Observation` from resolved inputs
3. Call `agent.think(obs)` then `agent.act(obs)`
4. Call `environment.step(action)`
5. Store `StepOutput` in context

### PipelineContext (`messages.py`)

Accumulates step outputs and enables variable resolution:

```yaml
# Example pipeline config
steps:
  - name: ingest
    agent_role: ingestor
    inputs: {src: "folder::./data", dst: "research"}
  - name: retrieve
    agent_role: retriever
    depends_on: [ingest]
    inputs: {tag: "${ingest.tag}"}     # References output from ingest step
```

---

## Layer 8: CLI

**Location:** `cli.py`

Interactive REPL for driving the full AgentFactory pipeline.

### Usage

```bash
# Run a specific blueprint
python3 cli.py run coordinator_agent

# Run with agent type override
python3 cli.py run iowarp_agent --type claude

# Interactive mode (select blueprint interactively)
python3 cli.py

# Blueprint management
python3 cli.py list
python3 cli.py show coordinator_agent
python3 cli.py create my_agent --type llm --model llama3.2
python3 cli.py delete my_agent

# Pipeline mode
python3 cli.py --pipeline configs/pipelines/ingest_retrieve.yaml
```

### REPL Commands

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `status` | Trajectory stats and cache hit rate |
| `observe` | Show current environment observation |
| `history` | Show all steps with rewards |
| `manual <action> <json>` | Bypass agent, send action directly |
| `agent` | Show current agent info |
| `list` | List all blueprints |
| `show <name>` | Show a blueprint's full config |
| `create <name> [type]` | Create a new blueprint |
| `switch <name>` | Switch to a different blueprint |
| `quit` / `exit` | Clean up and exit |
| *(anything else)* | Treated as natural language for the agent |

### Example Session

```
$ python3 cli.py run coordinator_agent

  AgentFactory Interactive CLI
  ----------------------------

  Checking infrastructure...
    IOWarp bridge (tcp://127.0.0.1:5560) ................... OK
    Memcached (127.0.0.1:11211) ............................ OK

  Agent: CoordinatorAgent
  Type 'help' for commands, 'quit' to exit.

  agent> ingest folder::./data/test_docs as research
    -> Coordinator routing to 'ingestor' agent
    Action: assimilate
    Result: Assimilated 3 file(s) into tag 'research'. Cached 3 blob(s).
    Reward: +0.10

  agent> get alpha.txt from research
    -> Coordinator routing to 'retriever' agent
    Result: Retrieved 'alpha.txt' from cache (hit).
    Reward: +0.30

  agent> prune alpha.txt from research
    -> Coordinator routing to 'retriever' agent
    Result: Pruned 1 blob(s) from cache. Data remains in IOWarp.
    Reward: +0.05

  agent> get alpha.txt from research
    -> Coordinator routing to 'retriever' agent
    Result: Retrieved 'alpha.txt' from IOWarp (cache miss, now cached).
    Reward: +0.20

  agent> status
    Trajectory: 4 steps | Total reward: 0.65
    Cache: 1 hit(s), 1 miss(es) (50% hit rate)
```

---

## Data Flow Patterns

### 1. Assimilation (Write-Through)

```
User: "ingest folder::./data/test_docs as research"
  |
  v
Agent.act() -> Action(name="assimilate", params={src, dst, format})
  |
  v
Environment._do_assimilate()
  |-- URIResolver.resolve("folder::./data/test_docs")
  |     -> ["file::alpha.txt", "file::metrics.csv", "file::results.json"]
  |
  |-- IOWarpClient.context_bundle(src=[...], dst="research")
  |     -> ZMQ -> bridge.py -> wrp_cee -> cte_helper -> CTE PutBlob()
  |
  |-- Write-through cache:
  |     cache.put("research", "alpha.txt", bytes)
  |     cache.put("research", "metrics.csv", bytes)
  |     cache.put("research", "results.json", bytes)
  |
  +-- Return StepResult(reward=+0.10)
```

### 2. Retrieval (Cache-Aside)

```
User: "get alpha.txt from research"
  |
  v
Agent.act() -> Action(name="retrieve", params={tag, blob_name})
  |
  v
Environment._do_retrieve()
  |-- cache.get("research", "alpha.txt")
  |     |
  |     |-- Cache HIT -> return data immediately (reward=+0.30)
  |     |
  |     +-- Cache MISS:
  |           |-- IOWarpClient.context_retrieve(tag, blob_name)
  |           |     -> ZMQ -> bridge -> wrp_cee -> cte_helper -> CTE GetBlob()
  |           |-- cache.put("research", "alpha.txt", data)   # populate cache
  |           +-- return data (reward=+0.20)
  |
  +-- Optional: skip_cache=True -> bypass cache, go straight to IOWarp
```

### 3. Prune (Cache Eviction Only)

```
User: "prune alpha.txt from research"
  |
  v
Agent.act() -> Action(name="prune", params={tag, blob_names=["alpha.txt"]})
  |
  v
Environment._do_prune()
  |-- cache.invalidate_tag("research", blob_names=["alpha.txt"])
  |     -> Deletes key "iowarp:research:alpha.txt" from Memcached
  |
  |-- IOWarp data is NOT touched (remains in persistent storage)
  |
  +-- Return StepResult(reward=+0.05)

Next retrieve of alpha.txt:
  -> Cache MISS -> fetch from IOWarp -> re-cache -> data intact
```

### 4. Destroy (Permanent Deletion)

```
User: "destroy research"
  |
  v
Agent.act() -> Action(name="destroy", params={tags=["research"]})
  |
  v
Environment._do_destroy()
  |-- IOWarpClient.context_destroy(tags=["research"])
  |     -> Deletes tag + all blobs from CTE persistent storage
  |
  |-- cache.invalidate_tag("research", all_blob_names)
  |     -> Deletes all cache entries for this tag
  |
  +-- Return StepResult(reward=+0.05)
       Data is GONE from both tiers.
```

### 5. Multi-Agent Coordination

```
User: "ingest folder::./data as research"
  |
  v
CoordinatorAgent.think(obs)
  |-- Calls: claude -p --model sonnet "User command: ingest..."
  |-- Claude returns: {"agent": "ingestor", "instruction": "assimilate ..."}
  +-- Stores routing decision
  |
  v
CoordinatorAgent.act(obs)
  |-- Looks up self._agents["ingestor"]
  |     -> BuiltAgent containing IngestorAgent
  |-- Creates Observation(text="assimilate folder::./data research arrow")
  |-- IngestorAgent.act(obs)
  |     -> Prepends ingestor context
  |     -> ClaudeAgent.act()   <-- backend does the thinking
  |     -> Verifies action.name == "assimilate"
  +-- Returns Action -> Environment executes it
```

---

## Complete Request Lifecycle

Full trace for `"ingest folder::./data/test_docs as research"`:

```
1. CLI
   - Reads user input
   - Creates Observation(text="ingest folder::./data/test_docs as research")

2. CoordinatorAgent.think(obs)
   - Spawns subprocess: claude -p --model sonnet --system-prompt "..." "User command: ..."
   - Claude Sonnet analyzes intent: "This is an ingest/write operation"
   - Returns JSON: {"agent": "ingestor", "instruction": "assimilate folder::./data/test_docs research arrow"}
   - Stores routing: {agent: "ingestor", instruction: "..."}

3. CoordinatorAgent.act(obs)
   - Retrieves routing from step 2
   - Looks up self._agents["ingestor"] -> BuiltAgent
   - Creates new Observation with the parsed instruction
   - Delegates: IngestorAgent.act(new_obs)

4. IngestorAgent.act(obs)
   - Prepends context: "You are an ingestion specialist..."
   - Delegates to backend: ClaudeAgent.act(augmented_obs)
   - ClaudeAgent returns: Action(name="assimilate", params={src, dst, format})
   - IngestorAgent verifies action.name == "assimilate" (passes)
   - Returns Action to coordinator

5. CoordinatorAgent returns Action to CLI

6. CLI calls: built.environment.step(action)

7. IOWarpEnvironment._do_assimilate(params)
   a. URIResolver.resolve("folder::./data/test_docs")
      - Path.rglob("*") -> finds alpha.txt, metrics.csv, results.json
      - Returns ["file::./data/test_docs/alpha.txt", ...]

   b. IOWarpClient.context_bundle(src=[...], dst="research", format="arrow")
      - Serializes to JSON-RPC: {"method": "context_bundle", "params": {...}}
      - Sends via ZeroMQ REQ socket to tcp://127.0.0.1:5560

   c. bridge.py (inside Docker container) receives request
      - Dispatches to handle_context_bundle()
      - Calls wrp_cee.context_bundle(src, dst, format)

   d. wrp_cee.py sends to cte_helper subprocess
      - stdin: {"cmd": "put", "tag": "research", "blob": "alpha.txt", "data": "5468697320..."}
      - cte_helper calls CTE PutBlob() via shared memory IPC
      - stdout: {"status": "ok"}
      - Repeats for each file

   e. Response bubbles back: wrp_cee -> bridge -> ZMQ -> IOWarpClient

   f. Write-through cache:
      - Reads each local file as bytes
      - cache.put("research", "alpha.txt", bytes) -> Memcached SET
      - Repeats for each file

   g. Returns StepResult:
      - observation: "Assimilated 3 file(s) into tag 'research'. Cached 3 blob(s)."
      - reward: +0.10
      - data: {tag: "research", files: 3, cached: 3}

8. CLI displays result, updates trajectory, shows reward
```

---

## Design Patterns

| Pattern | Where Used | Why |
|---------|-----------|-----|
| **Protocol-based interfaces** | `core/protocols.py` | Loose coupling via duck typing (PEP 544) |
| **Factory** | `factory/builder.py` | Configuration-driven agent creation |
| **Decorator** | IngestorAgent / RetrieverAgent wrapping backends | Constrain actions without modifying base agents |
| **Strategy** | Multiple agent implementations | Swappable reasoning engines (rules / Ollama / Claude) |
| **Cache-aside** | `iowarp_env.py` retrieve | Fast reads with automatic cache population on miss |
| **Write-through** | `iowarp_env.py` assimilate | Immediate cache consistency at ingestion time |
| **Router** | CoordinatorAgent | LLM-based intelligent command delegation |
| **Registry** | BlueprintRegistry | Dynamic agent discovery from YAML files |
| **Round-robin + failover** | IOWarpClient | Load balancing across multiple bridge endpoints |
| **Topological sort** | PipelineDAG (Kahn's algorithm) | Safe dependency-ordered pipeline execution |
| **Subprocess bridge** | cte_helper.cpp | Bypass ABI-incompatible Python extension |

---

## Key Problems Solved

| Problem | Root Cause | Solution |
|---------|-----------|---------|
| `std::bad_cast` on Python import | ABI conflict: `wrp_cte_core_ext.so` links both `libc++` (LLVM) and `libstdc++` (GCC) | Built `cte_helper` C++ binary that communicates via JSON stdin/stdout, bypassing the broken Python extension entirely |
| PutBlob error 11 (no storage targets) | Missing `compose` section in `wrp_conf.yaml` | Added compose section with CTE pool + RAM storage target configuration |
| Query returned 0 matches | `_do_query` used fragile `stats cachedump` from memcached as primary source | Changed to query IOWarp first (source of truth), fall back to cache |
| "destroy research" extracted wrong tag | `_extract_tag` had no regex for `destroy X` pattern | Added `destroy\|delete\|remove\|query\|find\|search\|list` pattern |
| Docker build permission denied | IOWarp base image runs as non-root user | Added `USER root` to Dockerfile |
| C++ log messages mixed with JSON output | `cte_helper` wrote logs to stdout before JSON ready message | Redirect stderr to DEVNULL, scan lines until finding JSON (`{` prefix) |

---

## How to Run

### Prerequisites

```bash
# Start infrastructure
docker-compose up -d --build

# Wait for health checks
docker-compose ps   # Both should show "healthy"
```

### Interactive Mode (Coordinator)

```bash
python3 cli.py run coordinator_agent
```

Then type natural language commands:

```
agent> ingest folder::./data/test_docs as research
agent> query research for all blobs
agent> get alpha.txt from research
agent> prune alpha.txt from research
agent> get alpha.txt from research          # cache miss -> IOWarp fetch
agent> destroy research
agent> status
```

### Interactive Mode (Rule-Based)

```bash
python3 cli.py run iowarp_agent
```

Same commands work, but uses instant keyword matching instead of LLM.

### Blueprint Management

```bash
python3 cli.py list                                    # List all blueprints
python3 cli.py show coordinator_agent                  # Show config
python3 cli.py create my_agent --type claude            # Create new
python3 cli.py delete my_agent                          # Delete
```
