# AgentFactory

A multi-agent reinforcement learning framework for intelligent data management. Features LLM-based coordination, two-tier storage architecture (IOWarp + Memcached), and specialized agents for ingestion and retrieval with reward-shaped learning.

**Key Features:**
- 🤖 **Multi-Agent Coordination** - LLM router delegates to specialized agents
- 🗄️ **Two-Tier Storage** - Fast cache (Memcached) + persistent storage (IOWarp)
- 🧠 **Natural Language Interface** - No SQL or API calls, just describe what you want
- ⚡ **Cache-Aside Pattern** - Automatic caching with fallback to persistent storage
- 🎯 **Reward Shaping** - RL feedback guides agent optimization
- 🔍 **Auto-Discovery** - New agents automatically integrated into coordinator

**Repository:** https://github.com/SIslamMun/AgentFactory

## System Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    USER COMMANDS                              │
│              (Natural Language Interface)                     │
└────────────────────────┬─────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│                   COORDINATOR AGENT                           │
│              (LLM-Based Intelligent Router)                   │
│  • Parses natural language commands                          │
│  • Routes to appropriate specialized agent                   │
│  • Auto-discovers available agents from registry            │
└────────────┬─────────────────────────┬───────────────────────┘
             ↓                         ↓
┌────────────────────────┐  ┌──────────────────────────┐
│   INGESTOR AGENT       │  │   RETRIEVER AGENT        │
│   (Data Loading)       │  │   (Data Access)          │
│   • assimilate only    │  │   • query                │
│                        │  │   • retrieve             │
│                        │  │   • prune (cache evict)  │
└────────┬───────────────┘  └──────────┬───────────────┘
         └──────────────┬───────────────┘
                        ↓
┌──────────────────────────────────────────────────────────────┐
│              IOWARP ENVIRONMENT                               │
│           (Action Executor + Reward Engine)                   │
│  • Executes actions (assimilate/query/retrieve/prune/destroy)│
│  • Calculates rewards (cache hit +0.30, miss +0.20, etc.)   │
│  • Manages two-tier storage coordination                     │
└────────────────────────┬─────────────────────────────────────┘
                         ↓
┌──────────────────────────────────────────────────────────────┐
│              TWO-TIER STORAGE INFRASTRUCTURE                  │
│  ┌──────────────────────┐       ┌──────────────────────┐    │
│  │   MEMCACHED          │       │     IOWARP           │    │
│  │   (Cache Layer)      │       │  (Persistent Layer)  │    │
│  │                      │       │                      │    │
│  │  • 512MB capacity    │       │  • 8GB shared memory │    │
│  │  • 1-hour TTL        │       │  • Permanent storage │    │
│  │  • LRU eviction      │       │  • Zero-copy access  │    │
│  │  • Sub-ms latency    │       │  • Memory-mapped I/O │    │
│  └──────────────────────┘       └──────────────────────┘    │
└──────────────────────────────────────────────────────────────┘

DATA FLOW PATTERNS:
  Ingest:    Write to both IOWarp + Memcached (write-through)
  Query:     Read from Memcached only (fast enumeration)
  Retrieve:  Check Memcached first → IOWarp fallback (cache-aside)
  Prune:     Evict from Memcached only (cache management)
  Destroy:   Delete from both IOWarp + Memcached (permanent)
```

## Key Concepts

### 1. Multi-Agent Coordination

**CoordinatorAgent** uses LLM (Claude) to parse natural language and route commands:
- `"load file::data.md as docs"` → Routes to **IngestorAgent**
- `"search all data"` → Routes to **RetrieverAgent**
- `"get file.md from docs"` → Routes to **RetrieverAgent**

**Auto-Discovery:** Coordinator scans `configs/blueprints/` and loads all available agents automatically.

### 2. Two-Tier Storage

| Tier | Purpose | Size | TTL | Speed | Eviction |
|------|---------|------|-----|-------|----------|
| **Memcached** | Hot data cache | 512MB | 1 hour | Sub-ms | LRU automatic |
| **IOWarp** | Persistent storage | 8GB | Permanent | Memory-mapped | Manual (destroy) |

**Benefits:**
- Fast reads from cache (80-90% hit rate typical)
- Persistent storage survives cache flushes
- Automatic healing (cache miss → IOWarp fallback → re-cache)

### 3. Cache Operations

#### Prune (Cache Eviction)
- **Purpose:** Remove specific blobs from Memcached only
- **IOWarp:** Data preserved
- **Usage:** `prune api_reference.md from docs`
- **Result:** Cache freed, data accessible via IOWarp fallback

#### Destroy (Permanent Deletion)
- **Purpose:** Delete entire tag from both tiers
- **IOWarp:** Tag deleted
- **Memcached:** All entries invalidated
- **Usage:** `destroy old_experiments`
- **Result:** Data permanently removed

See [docs/demo/PRUNE_VS_DESTROY.md](docs/demo/PRUNE_VS_DESTROY.md) for details.

## Quick Start

### Prerequisites

- Python 3.10+
- Docker and Docker Compose
- (Optional) Claude Code CLI for coordinator agent

### 1. Start Infrastructure

```bash
docker-compose up -d
```

Starts IOWarp bridge (tcp://127.0.0.1:5560) and Memcached (127.0.0.1:11211).

### 2. Install Dependencies

```bash
pip install -e ".[dev]"
# or with uv:
uv pip install -e ".[dev]"
```

### 3. Run Demo

#### Single Agent Mode
```bash
uv run cli.py run iowarp_agent

agent> ingest file::data/sample_docs/api_reference.md as docs
agent> query docs
agent> get api_reference.md from docs
agent> status
```

#### Multi-Agent Coordinator Mode
```bash
uv run cli.py run coordinator_agent

agent> load file::data/sample_docs/api_reference.md as docs
  → Coordinator routing to 'ingestor' agent
  
agent> search all data
  → Coordinator routing to 'retriever' agent
  
agent> get api_reference.md from docs
  → Coordinator routing to 'retriever' agent
```

**See [docs/demo/COMPLETE_DEMO.md](docs/demo/COMPLETE_DEMO.md) for complete step-by-step demos!**

## 📚 Documentation

Comprehensive documentation organized by category:

### For Presentations & Demos
- **[SYSTEM_ARCHITECTURE_EXPLAINED.md](docs/architecture/SYSTEM_ARCHITECTURE_EXPLAINED.md)** - Complete system explanation for academic presentations
- **[COMPLETE_DEMO.md](docs/demo/COMPLETE_DEMO.md)** - Step-by-step demo commands with expected output
- **[VALIDATION_RESULTS.md](docs/demo/VALIDATION_RESULTS.md)** - Test execution results proving system works

### For Developers
- **[PRUNE_VS_DESTROY.md](docs/demo/PRUNE_VS_DESTROY.md)** - Cache eviction vs permanent deletion guide
- **[COORDINATOR_ANALYSIS.md](docs/architecture/COORDINATOR_ANALYSIS.md)** - Multi-agent coordination design
- **[HOW_IT_WORKS.md](docs/architecture/HOW_IT_WORKS.md)** - System internals and operation

**Full documentation index:** [docs/README.md](docs/README.md)

## Project Structure

```
AgentFactory/
├── src/agent_factory/
│   ├── agents/                      # Agent implementations
│   │   ├── iowarp_agent.py          # Rule-based keyword matching
│   │   ├── llm_agent.py             # Ollama LLM-backed
│   │   ├── claude_agent.py          # Claude CLI-backed
│   │   ├── ingestor_agent.py        # Specialized for data loading
│   │   ├── retriever_agent.py       # Specialized for data access
│   │   └── coordinator_agent.py     # LLM-based router (NEW!)
│   ├── core/                        # Types, protocols, errors
│   │   ├── types.py                 # Action, Observation, StepResult
│   │   ├── protocols.py             # Agent, Environment protocols
│   │   └── errors.py                # Exception hierarchy
│   ├── environments/
│   │   └── iowarp_env.py            # Action executor + reward engine
│   ├── iowarp/                      # IOWarp integration
│   │   ├── client.py                # ZeroMQ bridge client
│   │   ├── cache.py                 # Memcached cache-aside wrapper
│   │   ├── uri_resolver.py          # URI scheme resolution
│   │   └── models.py                # Pydantic request/response models
│   ├── factory/                     # Builder and registry
│   │   ├── builder.py               # Agent builder with auto-discovery
│   │   └── registry.py              # Blueprint CRUD + persistence
│   └── orchestration/               # Multi-agent pipeline (legacy)
│       ├── dag.py                   # Pipeline DAG
│       └── executor.py              # Pipeline executor
├── configs/
│   └── blueprints/                  # Agent configurations
│       ├── coordinator_agent.yaml   # Multi-agent coordinator (NEW!)
│       ├── ingestor_agent.yaml      # Data loading specialist (NEW!)
│       ├── retriever_agent.yaml     # Data access specialist (NEW!)
│       └── iowarp_agent.yaml        # Single rule-based agent
├── docs/                            # Documentation (organized!)
│   ├── architecture/                # System design docs
│   ├── demo/                        # Demo guides & validation
│   └── planning/                    # Development roadmaps
├── tests/                           # 182 tests total
│   ├── unit/                        # Unit tests (no Docker)
│   ├── integration/                 # Integration tests (with Docker)
│   └── e2e/                         # End-to-end tests
├── docker/
│   └── iowarp/                      # IOWarp container
├── cli.py                           # Interactive CLI (1068 lines)
├── pyproject.toml                   # Project metadata
└── docker-compose.yml               # Infrastructure setup
```

**Total Implementation:** ~6,300 lines of Python, 182 passing tests ✅

### 4. Available Actions

| Action | Description | Parameters | Scope |
|--------|-------------|------------|-------|
| `assimilate` | Ingest files into IOWarp + cache | `src` (URI), `dst` (tag), `format` | Write-through both tiers |
| `query` | Search cached data by pattern | `tag_pattern` (glob) | Memcached only |
| `retrieve` | Get specific blob | `tag`, `blob_name` | Cache-aside (cache → IOWarp fallback) |
| `prune` | Evict blobs from cache | `tag`, `blob_names` (list) | Memcached only |
| `destroy` | Permanently delete tag | `tags` (tag or list) | Both IOWarp + Memcached |
| `list_blobs` | List blobs under tag | `tag_pattern` (glob) | IOWarp query |

### 5. Agent Types

| Type | Backend | Description | Use Case |
|------|---------|-------------|----------|
| `iowarp_agent` | Rule-based | Keyword matching (regex) | Fast, offline, deterministic |
| `llm` | Ollama | Local LLM reasoning | Privacy, offline, customizable |
| `claude` | Claude CLI | Claude Sonnet reasoning | Best quality, requires auth |
| `ingestor` | Any above | Specialized for data loading | Multi-agent coordination |
| `retriever` | Any above | Specialized for data access | Multi-agent coordination |
| `coordinator` | Claude CLI | Routes to specialized agents | Multi-agent orchestration |

### 6. Reward Shaping

Reinforcement learning rewards guide agent behavior:

| Event | Reward | Meaning |
|-------|--------|---------|
| Cache HIT (retrieve) | **+0.30** | Best case - fast cache access |
| Cache MISS (IOWarp fallback) | **+0.20** | Slower but data found |
| Successful ingest | **+0.10** | Data loaded successfully |
| Successful query | **+0.10** | Search completed |
| Prune/Destroy | **+0.05** | Cleanup operation |
| Error/Failure | **-0.50** | Penalty for mistakes |

**Agents learn to maximize cache hits for better performance!**

## URI Schemes

| Scheme | Example | Description |
|--------|---------|-------------|
| `file::` | `file::data/x.csv` | Single file |
| `folder::` | `folder::./data/docs` | All files in directory (recursive) |
| `hdf5::` | `hdf5::data/x.h5` | HDF5 file (native IOWarp) |
| `mem::` | `mem::tag/blob` | Read from memcached cache |

## CLI Commands

### Single-Agent Mode

| Command | Description |
|---------|-------------|
| `help` | Show available commands |
| `status` | Trajectory stats and cache hit rate |
| `history` | All steps with rewards |
| `list` | List all available blueprints |
| `quit` / `exit` | Clean shutdown |
| *(natural language)* | Sent to agent for processing |

### CLI Subcommands

```bash
# List all agent blueprints
uv run cli.py list

# Run specific agent
uv run cli.py run iowarp_agent
uv run cli.py run coordinator_agent

# Create new blueprint
uv run cli.py create my_agent --type llm --model llama3.2

# Show blueprint config
uv run cli.py show my_agent

# Delete blueprint
uv run cli.py delete my_agent
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run only unit tests (no Docker needed)
pytest tests/unit/ -v

# Run integration tests (requires Docker)
docker-compose up -d
pytest tests/integration/ -v

# Check test count
pytest tests/ --collect-only
# Collected: 182 items
```

**Test Coverage:** 182 tests across unit, integration, and e2e categories

## Advanced Features

### Blueprint Management

Blueprints configure agents and infrastructure. Managed programmatically or via CLI.

```python
from agent_factory.factory.registry import BlueprintRegistry

registry = BlueprintRegistry()
registry.load()

# Create/update/delete
registry.create("my_agent", agent_type="llm", model="llama3.2")
registry.update("my_agent", agent={"type": "claude"})
registry.delete("my_agent")
```

### Distributed Mode

Multi-node deployment with multiple IOWarp bridges and memcached nodes:

```bash
docker-compose -f docker-compose.distributed.yml up -d
uv run cli.py run iowarp_distributed
```

Uses consistent hashing for cache distribution across nodes.

## Contributing

See [docs/planning/](docs/planning/) for roadmap and feature plans.

## License

MIT License - See LICENSE file for details.

## Citation

```bibtex
@software{agentfactory2026,
  title={AgentFactory: Multi-Agent Reinforcement Learning for Data Management},
  author={Islam, Shazzadul},
  year={2026},
  url={https://github.com/SIslamMun/AgentFactory}
}
```

---

**Built with:** Python, IOWarp, Memcached, Docker, Claude AI, Pydantic, pytest
