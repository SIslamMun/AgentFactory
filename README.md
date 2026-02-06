# AgentFactory

A multi-agent framework for intelligent data management through IOWarp. Agents reason about user instructions and execute data operations (ingest, query, retrieve, prune) against the IOWarp context engine, with memcached cache-aside caching and reward-shaped trajectories.

## Architecture

```
                         +--------------------------+
                         |       CLI / REPL         |
                         |  (single-agent,          |
                         |   pipeline, or           |
                         |   management mode)       |
                         +----------+---------------+
                                    |
               +--------------------+---------------------+
               |                    |                      |
      Single-Agent Mode    Pipeline Mode         Management Mode
               |                    |                      |
       +-------v--------+  +-------v-----------+  +-------v---------+
       |  Agent          |  |  PipelineExecutor |  | BlueprintRegistry|
       |  (IOWarpAgent,  |  |  (coordinates     |  | create/update/  |
       |   LLMAgent,     |  |   agents in DAG)  |  | delete/duplicate|
       |   ClaudeAgent)  |  +--+-------------+--+  +--------+--------+
       +-------+---------+     |             |              |
               |        +------v-----+ +----v--------+     |
               |        |IngestorAgent| |RetrieverAgent|    |
               |        |(assimilate) | |(query/      |    |
               |        +------+------+ | retrieve/   |    |
               |               |        | list_blobs) |    |
               |               |        +----+--------+    |
               +---+-----------+-------------+-------------+
                   |
          +--------v---------+
          | IOWarpEnvironment |
          | (step/reset/     |
          |  observe/close)  |
          +--------+---------+
                   |
        +----------+----------+
        |                     |
  +-----v------+     +-------v------+
  | IOWarpClient|     |  BlobCache   |
  | (ZeroMQ)   |     | (memcached)  |
  +-----+------+     +-------+------+
        |                     |
  +-----v------+     +-------v------+
  | IOWarp     |     | Memcached    |
  | Container  |     | (Alpine)     |
  +------------+     +--------------+
```

## Quick Start

### Prerequisites

- Python 3.10+
- Docker and Docker Compose
- Claude Code CLI installed and authenticated (for claude agent backend)

### 1. Start Infrastructure

```bash
docker-compose up -d
```

This starts the IOWarp container (with ZeroMQ bridge on port 5560) and Memcached (port 11211).

### 2. Install Dependencies

```bash
pip install -e ".[dev]"
```

### 3. Manage Blueprints (CLI Subcommands)

```bash
# List all blueprints
python3 cli.py list

# Create a new blueprint
python3 cli.py create my_agent --type llm --model llama3.2

# Show full blueprint config
python3 cli.py show my_agent

# Run a specific blueprint
python3 cli.py run my_agent --type claude

# Delete a blueprint
python3 cli.py delete my_agent
```

### 4. Run Single-Agent Mode (Interactive)

```bash
python3 cli.py
```

Select an agent type when prompted:
- **rule_based** -- keyword matching, fast, no external dependency
- **llm** -- Ollama local LLM (requires Ollama running with llama3.2)
- **claude** -- Claude Code CLI (no API key needed, uses your authenticated session)

Then type natural language instructions:

```
agent> ingest folder::./data/sample_docs into tag: docs
agent> query tag: docs
agent> retrieve blob: readme.md from tag: docs
agent> status
agent> history
```

### 5. Run Pipeline Mode

```bash
python3 cli.py --pipeline configs/pipelines/ingest_retrieve.yaml
```

In pipeline mode, agents are coordinated automatically through a DAG:

```
pipeline> run src=folder::./data/sample_docs dst=my_docs
pipeline> info
pipeline> help
```

## Project Structure

```
AgentFactory/
+-- src/agent_factory/
|   +-- core/                        # Types, protocols, errors
|   |   +-- types.py                 # Frozen dataclasses (Action, Observation, etc.)
|   |   +-- protocols.py             # Agent, Environment, RewardFunction protocols
|   |   +-- errors.py                # Exception hierarchy
|   +-- agents/                      # Agent implementations
|   |   +-- iowarp_agent.py          # Rule-based keyword matching
|   |   +-- llm_agent.py             # Ollama LLM-backed
|   |   +-- claude_agent.py          # Claude Code CLI-backed
|   |   +-- ingestor_agent.py        # Constrains backend to assimilate
|   |   +-- retriever_agent.py       # Constrains backend to query/retrieve/list_blobs
|   +-- environments/
|   |   +-- iowarp_env.py            # IOWarpEnvironment (step/reset/observe)
|   +-- orchestration/               # Multi-agent pipeline coordination
|   |   +-- messages.py              # PipelineContext, variable resolution
|   |   +-- dag.py                   # PipelineDAG (validation, topological sort)
|   |   +-- executor.py              # PipelineExecutor (runs agents through DAG)
|   +-- iowarp/                      # IOWarp integration layer
|   |   +-- client.py                # ZeroMQ REQ/REP client
|   |   +-- cache.py                 # BlobCache (memcached wrapper)
|   |   +-- uri_resolver.py          # Extended URI schemes (file::, folder::, etc.)
|   |   +-- models.py                # Pydantic request/response models
|   +-- factory/                     # Builder and registry
|       +-- builder.py               # AgentBuilder (single + pipeline)
|       +-- registry.py              # BlueprintRegistry (CRUD + YAML persistence)
+-- configs/
|   +-- blueprints/
|   |   +-- iowarp_agent.yaml        # Default single-agent blueprint
|   |   +-- iowarp_distributed.yaml  # Multi-node blueprint
|   +-- pipelines/
|       +-- ingest_retrieve.yaml     # Ingest-then-retrieve pipeline (claude backend)
+-- tests/
|   +-- unit/                        # Unit tests (mocked, no Docker needed)
|   +-- integration/                 # Integration tests (require Docker)
|   +-- e2e/                         # End-to-end tests (full stack)
+-- docker/
|   +-- iowarp/Dockerfile            # IOWarp container build
+-- cli.py                           # Interactive CLI entry point
+-- walkthrough.py                   # Automated end-to-end walkthrough
+-- pyproject.toml                   # Project metadata and dependencies
+-- docker-compose.yml               # Single-node infrastructure
+-- docker-compose.distributed.yml   # Multi-node infrastructure
```

## Core Concepts

### Agent Protocol

Every agent implements two methods:

```python
class Agent(Protocol):
    def think(self, observation: Observation) -> str: ...
    def act(self, observation: Observation) -> Action: ...
```

- `think()` produces a reasoning trace (what the agent plans to do)
- `act()` returns an `Action(name, params)` the environment can execute

### Available Actions

| Action | Description | Parameters |
|--------|-------------|------------|
| `assimilate` | Ingest files into IOWarp | `src` (URI), `dst` (tag), `format` |
| `query` | Search for stored data | `tag_pattern` (glob) |
| `retrieve` | Get a specific blob | `tag`, `blob_name` |
| `list_blobs` | List blobs under a tag | `tag_pattern` (glob) |
| `prune` | Delete data | `tags`, optional `blob_names` |

### URI Schemes

| Scheme | Example | Description |
|--------|---------|-------------|
| `file::` | `file::/data/x.csv` | Single file (native IOWarp) |
| `folder::` | `folder::./data/docs` | All files in directory (recursive) |
| `hdf5::` | `hdf5::/data/x.h5` | HDF5 file (native IOWarp) |
| `mem::` | `mem::tag/blob` | Read from memcached cache |

### Agent Types

| Type | Backend | Description |
|------|---------|-------------|
| `rule_based` | None | Keyword matching (fast, offline) |
| `llm` | Ollama | Local LLM reasoning (llama3.2) |
| `claude` | Claude Code CLI | Claude reasoning (no API key needed) |
| `ingestor` | Any of above | Wraps a backend, constrains to `assimilate` |
| `retriever` | Any of above | Wraps a backend, constrains to `query`/`retrieve`/`list_blobs` |

### Reward Shaping

The environment assigns rewards to shape agent behavior:

| Event | Default Reward |
|-------|---------------|
| Cache hit | +0.3 |
| Cache miss (fetched from IOWarp) | +0.2 |
| Successful assimilate | +0.1 |
| Successful query | +0.1 |
| Successful prune | +0.05 |
| Error | -0.5 |

## Blueprint Management

Blueprints can be managed programmatically or through the CLI.

### Programmatic API

```python
from agent_factory.factory.registry import BlueprintRegistry
from agent_factory.factory.builder import AgentBuilder

registry = BlueprintRegistry()
registry.load()

# Create agents programmatically
registry.create("my_agent")                                          # rule_based defaults
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

### CLI Subcommands

```bash
python3 cli.py create my_agent --type llm --model llama3.2
python3 cli.py list
python3 cli.py show my_agent
python3 cli.py delete my_agent
python3 cli.py run iowarp_agent --type claude
```

### REPL Management Commands

Inside the interactive REPL, manage blueprints without leaving the session:

```
agent> list                         # List all blueprints
agent> show iowarp_agent            # Show full config
agent> create test_agent claude     # Create new blueprint
agent> delete test_agent            # Delete a blueprint
agent> switch iowarp_agent          # Switch to different blueprint
agent> configure agent.type llm     # Set config value (dotted path)
```

## Multi-Agent Pipeline

The pipeline orchestration system coordinates specialized agents through a DAG.

### How It Works

1. **PipelineDAG** parses a YAML config, validates dependencies (no cycles, all refs exist), and produces a topologically sorted execution order
2. **PipelineExecutor** iterates through steps in order, resolving `${step_name.key}` variable references from prior step outputs
3. **Specialized agents** (IngestorAgent, RetrieverAgent) wrap a backend agent and constrain its action space

### Pipeline YAML Format

```yaml
pipeline_id: ingest_retrieve
description: "Ingest documents then query and retrieve them"

agents:
  ingestor:
    type: ingestor
    backend: claude          # Use Claude as the reasoning backend
    model: sonnet
    default_tag: docs
    default_format: arrow
  retriever:
    type: retriever
    backend: claude
    model: sonnet

steps:
  - name: ingest_docs
    agent: ingestor
    inputs:
      src: "${pipeline.src}"       # Resolved from CLI run args
      dst: "${pipeline.dst}"
    outputs: [tag, files]

  - name: query_results
    agent: retriever
    inputs:
      tag_pattern: "${ingest_docs.tag}"  # Resolved from step output
    outputs: [matches]
    depends_on: [ingest_docs]

  - name: retrieve_data
    agent: retriever
    inputs:
      tag: "${ingest_docs.tag}"
    depends_on: [query_results]
```

### Variable Resolution

- `${pipeline.key}` -- resolved from CLI `run` arguments (e.g., `run src=folder::./data dst=docs`)
- `${step_name.key}` -- resolved from a prior step's output data

### Writing Custom Pipelines

1. Create a YAML file in `configs/pipelines/`
2. Define agents with their type and backend
3. Define steps with inputs (using `${...}` references), outputs, and `depends_on`
4. Run with: `python3 cli.py --pipeline configs/pipelines/your_pipeline.yaml`

## Blueprints

Blueprints configure the infrastructure stack (IOWarp bridge, memcached, URI resolver, environment rewards). They live in `configs/blueprints/`.

The pipeline mode uses the blueprint for infrastructure and the pipeline YAML for agent/step definitions. Single-agent mode uses the blueprint for everything.

## Testing

```bash
# Run all unit tests (no Docker needed)
pytest tests/unit/ -v

# Run integration tests (requires Docker)
docker-compose up -d
pytest tests/integration/ -v

# Run everything
pytest tests/ -v

# Skip integration/e2e tests
pytest tests/ -m "not integration and not e2e"
```

### Test Coverage

| Test File | What It Tests |
|-----------|---------------|
| `test_agents.py` | IOWarpAgent, LLMAgent, ClaudeAgent, builder dispatch |
| `test_ingestor_agent.py` | IngestorAgent constrains to assimilate |
| `test_retriever_agent.py` | RetrieverAgent constrains to query/retrieve/list_blobs |
| `test_dag.py` | DAG validation, cycle detection, topological sort |
| `test_executor.py` | Pipeline execution, variable resolution, error handling |
| `test_types.py` | Frozen dataclass immutability and defaults |
| `test_cache.py` | BlobCache operations, distributed hashing |
| `test_uri_resolver.py` | URI scheme resolution |
| `test_registry.py` | Blueprint CRUD, persistence, deep merge, validation |

## Configuration Reference

### Blueprint Fields

```yaml
blueprint:
  name: "my_agent"
  description: "..."

iowarp:
  bridge_endpoint: "tcp://127.0.0.1:5560"   # Single bridge
  # bridge_endpoints: [...]                  # Multiple bridges (round-robin)
  connect_timeout_ms: 5000
  request_timeout_ms: 30000

cache:
  hosts:
    - host: "127.0.0.1"
      port: 11211
  key_prefix: "iowarp"
  default_ttl: 3600

uri_resolver:
  temp_dir: "/tmp/agent-factory/uri-cache"

environment:
  default_format: arrow
  reward:
    cache_hit: 0.3
    cache_miss: 0.2
    assimilate_success: 0.1
    query_success: 0.1
    prune_success: 0.05
    error: -0.5

agent:
  type: claude              # rule_based | llm | claude
  model: sonnet             # For llm: "llama3.2:latest", for claude: "sonnet"
```

### CLI Commands (Single-Agent Mode)

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `status` | Trajectory stats and cache hit rate |
| `observe` | Current environment observation |
| `history` | All steps with rewards |
| `manual <action> <json>` | Bypass agent, execute action directly |
| `agent` | Show agent info |
| `list` | List all available blueprints |
| `show <name>` | Show a blueprint's full config |
| `create <name> [type]` | Create a new blueprint |
| `delete <name>` | Delete a blueprint |
| `switch <name>` | Switch to a different blueprint |
| `configure <key> <value>` | Set a config value (dotted path) |
| `quit` / `exit` | Clean shutdown |
| *(anything else)* | Natural language sent to the agent |

### CLI Commands (Pipeline Mode)

| Command | Description |
|---------|-------------|
| `run key=value ...` | Execute pipeline with given variables |
| `info` | Show pipeline steps and agents |
| `help` | Show available commands |
| `quit` / `exit` | Clean shutdown |

### CLI Subcommands (Standalone)

| Command | Description |
|---------|-------------|
| `python3 cli.py create <name> --type <type> [--model <m>]` | Create a new blueprint |
| `python3 cli.py list` | List all blueprints |
| `python3 cli.py show <name>` | Show blueprint YAML |
| `python3 cli.py delete <name>` | Delete a blueprint |
| `python3 cli.py run <name> [--type <type>]` | Run a blueprint interactively |
| `python3 cli.py --pipeline <path.yaml>` | Pipeline mode |

## Distributed Mode

For multi-node deployments with multiple IOWarp bridges and memcached nodes:

```bash
docker-compose -f docker-compose.distributed.yml up -d
```

Use `configs/blueprints/iowarp_distributed.yaml` which configures multiple bridge endpoints and cache hosts with consistent hashing.
