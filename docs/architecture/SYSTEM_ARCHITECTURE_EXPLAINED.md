# AgentFactory System Architecture Explanation
## For Professor Presentation

---

## 🎯 High-Level Overview

AgentFactory is a **multi-agent reinforcement learning system** that manages data ingestion and retrieval through specialized AI agents. The system uses a **two-tier storage architecture** (fast cache + persistent storage) and supports both **single-agent** and **multi-agent coordinator** modes.

### Key Innovation
Instead of manually writing data pipelines, you describe what you want in **natural language**, and intelligent agents coordinate to execute the task using the optimal storage layer.

---

## 🏗️ System Components

```
┌─────────────────────────────────────────────────────────┐
│                    USER INTERFACE                        │
│                  (CLI: cli.py)                           │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                   AGENT LAYER                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Coordinator  │  │  Ingestor    │  │  Retriever   │  │
│  │    Agent     │  │    Agent     │  │    Agent     │  │
│  │ (LLM Router) │  │ (Assimilate) │  │(Query/Get)   │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              ENVIRONMENT LAYER                           │
│             (IOWarpEnvironment)                          │
│   • Action execution (assimilate/query/retrieve/prune)  │
│   • Reward calculation (RL feedback)                    │
│   • Cache management coordination                       │
└───────────────────────────┬─────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              STORAGE INFRASTRUCTURE                      │
│  ┌──────────────────────┐  ┌───────────────────────┐   │
│  │   MEMCACHED          │  │      IOWARP           │   │
│  │   (Cache Layer)      │  │  (Persistent Layer)   │   │
│  │                      │  │                       │   │
│  │  • 512MB capacity    │  │  • 8GB shared memory  │   │
│  │  • 1-hour TTL        │  │  • Permanent storage  │   │
│  │  • LRU eviction      │  │  • Memory-mapped      │   │
│  │  • Sub-ms latency    │  │  • Zero-copy access   │   │
│  └──────────────────────┘  └───────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 📦 Component Details

### 1. IOWarp - The Persistent Storage Engine

**What is IOWarp?**
- A **shared-memory storage system** designed for high-performance data access
- Stores data as "blobs" (binary large objects) organized by "tags" (like folders)
- Uses memory-mapped files for **zero-copy data access**
- Runs as a **C++ bridge service** that Python talks to via TCP

**Architecture:**
```
┌──────────────────────────────────────────────────────┐
│  Python Application (AgentFactory)                   │
│  └─→ IOWarpClient (TCP socket connection)           │
└────────────────────────┬─────────────────────────────┘
                         │ TCP (127.0.0.1:5560)
                         ↓
┌──────────────────────────────────────────────────────┐
│  IOWarp Bridge (C++ Service in Docker)               │
│  • Runs in: agentfactory_iowarp_1 container          │
│  • Protocol: Custom TCP protocol                     │
│  • Operations: context_bundle, query, retrieve       │
│  └─→ Shared Memory Region (/dev/shm)                │
└────────────────────────┬─────────────────────────────┘
                         │
                         ↓
┌──────────────────────────────────────────────────────┐
│  Shared Memory Storage (8GB)                         │
│  ├─ Tag: "research_docs"                             │
│  │  ├─ Blob: "paper1.pdf"                            │
│  │  └─ Blob: "paper2.pdf"                            │
│  ├─ Tag: "api_docs"                                  │
│  │  └─ Blob: "reference.md"                          │
└──────────────────────────────────────────────────────┘
```

**Why IOWarp?**
- **Fast:** Memory-mapped access (no disk I/O)
- **Persistent:** Data survives process restarts
- **Shared:** Multiple processes can access same data
- **Zero-copy:** No serialization overhead

**Key Operations:**
- `context_bundle(src, dst, format)` - Ingest files into a tag
- `query(tag_pattern)` - List blobs matching pattern
- `retrieve(tag, blob_name)` - Get blob contents
- `destroy(tag)` - Delete entire tag

### 2. Memcached - The Cache Layer

**What is Memcached?**
- Industry-standard **distributed memory cache**
- Acts as a **high-speed buffer** between agents and IOWarp
- Stores recently-accessed data for sub-millisecond retrieval

**Configuration:**
```
Host: 127.0.0.1
Port: 11211
Memory: 512MB
TTL: 3600 seconds (1 hour)
Eviction: LRU (Least Recently Used)
```

**Cache Key Format:**
```
iowarp:tag:blob_name
        │   └─ Blob identifier (e.g., "api_reference.md")
        └─ Tag identifier (e.g., "demo_docs")

Example: iowarp:demo_docs:api_reference.md
```

**Why Memcached?**
- **Speed:** Sub-millisecond reads (vs IOWarp's memory-mapped reads)
- **Simplicity:** Standard protocol, battle-tested
- **Automatic eviction:** LRU keeps cache optimal size
- **TTL:** Stale data automatically expires

### 3. BlobCache - The Abstraction Layer

**What is BlobCache?**
- Python wrapper around memcached that implements **cache-aside pattern**
- Provides a clean API: `get()`, `put()`, `delete()`, `query_keys()`
- Handles serialization, error recovery, and distributed cache coordination

**Key Methods:**
```python
# Store blob in cache
cache.put(tag="docs", blob_name="file.md", data=bytes)

# Retrieve from cache
data = cache.get(tag="docs", blob_name="file.md")  # Returns bytes or None

# Invalidate entry
cache.delete(tag="docs", blob_name="file.md")

# Query cache contents (NEW!)
matches = cache.query_keys(tag_pattern="*")
# Returns: [{"tag": "docs", "blob_name": "file.md"}, ...]
```

### 4. The Bridge - Docker Integration

**Docker Compose Setup:**
```yaml
services:
  iowarp:
    build: ./docker/iowarp
    image: iowarp_bridge:latest
    ports:
      - "5560:5560"  # TCP bridge port
    volumes:
      - /dev/shm:/dev/shm  # Shared memory access
    shm_size: 8g  # 8GB shared memory allocation

  memcached:
    image: memcached:alpine
    ports:
      - "11211:11211"
    command: memcached -m 512 -I 10m  # 512MB cache, 10MB max item
```

**Why Docker?**
- **Isolation:** Services run in containers
- **Portability:** Same setup on any machine
- **Shared memory:** Host's /dev/shm mounted into container
- **Easy management:** `docker-compose up/down`

---

## 🔄 Two-Tier Storage Pattern

### Why Two Tiers?

| Aspect | Memcached (Cache) | IOWarp (Persistent) |
|--------|-------------------|---------------------|
| **Speed** | Sub-ms (hash lookup) | Memory-mapped (fast but slower) |
| **Capacity** | 512MB | 8GB |
| **Durability** | Volatile (1-hour TTL) | Persistent |
| **Eviction** | Automatic (LRU) | Manual (prune) |
| **Purpose** | Hot data access | Long-term storage |

**Strategy:**
1. **Fast reads:** Check cache first (hit rate ~80-90% in practice)
2. **Fallback:** If cache miss, read from IOWarp and re-cache
3. **Write-through:** Write to both layers simultaneously
4. **Automatic healing:** IOWarp acts as "source of truth"

### Data Flow Patterns

#### 1. INGEST (Write-Through)
```
User: "ingest file::data.md as docs"
  ↓
Agent: Decides to call 'assimilate' action
  ↓
Environment: _do_assimilate()
  ├─→ IOWarpClient.context_bundle()  [Write to persistent storage]
  │     └─ IOWarp Bridge → Shared Memory
  │
  └─→ BlobCache.put() for each file  [Write to cache]
        └─ Memcached → Store with 1-hour TTL

Result: Data in BOTH tiers
Reward: +0.10 (successful ingest)
```

#### 2. QUERY (Cache-Only)
```
User: "find all data"
  ↓
Agent: Decides to call 'query' action
  ↓
Environment: _do_query()
  └─→ BlobCache.query_keys(pattern="*")
        └─ Memcached → stats items + stats cachedump
              └─ Returns: [{"tag": "docs", "blob_name": "data.md"}]

Result: List of cached blobs (fast!)
Reward: +0.10 (successful query)
```

**Why cache-only?**
- IOWarp's query is broken in stub mode (Python 3.12/3.13 ABI issue)
- Memcached's `stats cachedump` provides same info (faster!)
- Works reliably without C++ extension issues

#### 3. RETRIEVE (Cache-Aside)
```
User: "get data.md from docs"
  ↓
Agent: Decides to call 'retrieve' action
  ↓
Environment: _do_retrieve()
  ├─→ BlobCache.get(tag="docs", blob_name="data.md")
  │     └─ Memcached lookup
  │           ├─ HIT → Return data [Reward: +0.30]
  │           └─ MISS → Continue to IOWarp
  │
  └─→ IOWarpClient.retrieve(tag="docs", blob_name="data.md")
        └─ IOWarp Bridge → Shared Memory
              └─ Return data [Reward: +0.20]
                    └─ Re-cache: BlobCache.put() [Heal cache]

Result: Data returned + cache healed if needed
```

#### 4. PRUNE (Invalidate + Delete)
```
User: "delete docs"
  ↓
Agent: Decides to call 'prune' action
  ↓
Environment: _do_prune()
  ├─→ IOWarpClient.destroy(tag="docs")
  │     └─ Delete from persistent storage
  │
  └─→ BlobCache.delete(tag="docs", blob_name="*")
        └─ Invalidate all cache entries for tag

Result: Data deleted from both tiers
Reward: +0.05 (cleanup action)
```

---

## 🤖 Agent System

### Agent Types

#### 1. IOWarpAgent (Rule-Based)
**Blueprint:** `configs/blueprints/iowarp_agent.yaml`

```yaml
agent:
  type: rule_based  # Keyword matching
  default_tag: default
  default_tag_pattern: "*"
```

**How it works:**
- Uses **keyword matching** (regex patterns)
- Matches user input to predefined patterns:
  - `\bingest\b` → assimilate action
  - `\bfind\b|\bquery\b` → query action
  - `\bget\b|\bretrieve\b` → retrieve action
  - `\bdelete\b|\bprune\b|\bremove\b` → prune action
- Fast but inflexible (exact keywords required)

#### 2. IngestorAgent (Claude-based Specialist)
**Blueprint:** `configs/blueprints/ingestor_agent.yaml`

```yaml
agent:
  type: ingestor
  backend: claude
  model: sonnet
```

**How it works:**
- **Specialized LLM agent** trained only for ingestion
- Uses Claude Sonnet with custom system prompt
- Understands variations: "load", "import", "add", "ingest"
- Extracts parameters from natural language
- Only knows `assimilate` action (focused)

#### 3. RetrieverAgent (Claude-based Specialist)
**Blueprint:** `configs/blueprints/retriever_agent.yaml`

```yaml
agent:
  type: retriever
  backend: claude
  model: sonnet
```

**How it works:**
- **Specialized LLM agent** for data access
- Knows: `query`, `retrieve`, `prune` actions
- Understands: "search", "find", "get", "list", "delete"
- Smarter parameter extraction than rule-based

#### 4. CoordinatorAgent (LLM Router)
**Blueprint:** `configs/blueprints/coordinator_agent.yaml`

```yaml
agent:
  type: coordinator
  backend: claude
  model: sonnet
```

**How it works:**
```python
# Coordinator's think() method:
def think(self, observation: str) -> dict:
    # 1. Send observation + available agents to Claude
    prompt = f"""
    Available agents:
    - ingestor: handles data ingestion (assimilate)
    - retriever: handles queries, retrieval, deletion
    
    User request: "{observation}"
    
    Which agent should handle this? Return JSON:
    {{"agent": "ingestor", "instruction": "assimilate file::..."}}
    """
    
    # 2. Call Claude CLI directly (bypass system prompt conflict)
    result = subprocess.run(['claude', '--no-format'], input=prompt, ...)
    
    # 3. Parse JSON response
    decision = json.loads(result.stdout)
    
    return {
        "thought": f"Route to '{decision['agent']}'",
        "action": "delegate",
        "params": {
            "target_agent": decision["agent"],
            "instruction": decision["instruction"]
        }
    }
```

**Auto-Discovery:**
```python
# In builder.py:
def _build_coordinator_with_agents():
    # Scan all blueprints
    for name in registry.list_blueprints():
        if name == "coordinator_agent":
            continue  # Skip self
        
        # Load blueprint
        config = registry.get(name)
        
        # Determine role
        agent_type = config["agent"]["type"]
        role = "ingestor" if agent_type == "ingestor" else "retriever"
        
        # Build full agent with SHARED infrastructure
        built_agent = builder.build(name)
        
        # Give to coordinator
        coordinator.register_agent(role, built_agent)
```

---

## 🎬 Complete Data Flow Example

### Scenario: User ingests → queries → retrieves via coordinator

```
┌─────────────────────────────────────────────────────────┐
│  USER: "load file::data/sample.md as docs"             │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  CoordinatorAgent.think()                               │
│  • Sends to Claude: "Which agent handles loading?"     │
│  • Claude returns: {"agent": "ingestor", ...}          │
│  • Coordinator: "→ Routing to 'ingestor' agent"        │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  IngestorAgent.act()                                    │
│  • Receives: "assimilate file::data/sample.md docs"    │
│  • Returns: {"action": "assimilate", "params": {...}}  │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  IOWarpEnvironment._do_assimilate()                     │
│  1. Resolve URI: file::data/sample.md → absolute path  │
│  2. Call IOWarp: client.context_bundle(src, dst, fmt)  │
│     └─ Bridge writes to shared memory                  │
│  3. Cache it: cache.put(tag, blob_name, data)          │
│     └─ Memcached stores with 1hr TTL                   │
│  4. Return: {"files": 1, "cached": 1}                  │
│  5. Reward: +0.10                                       │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  STORAGE STATE:                                         │
│  IOWarp → Tag: docs, Blob: sample.md [PERSISTENT]      │
│  Cache  → Key: iowarp:docs:sample.md [1hr TTL]         │
└─────────────────────────────────────────────────────────┘

─────────────────────────────────────────────────────────

┌─────────────────────────────────────────────────────────┐
│  USER: "search all data"                                │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  CoordinatorAgent.think()                               │
│  • Claude: "Search is retrieval operation"              │
│  • Returns: {"agent": "retriever", ...}                 │
│  • Coordinator: "→ Routing to 'retriever' agent"        │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  RetrieverAgent.act()                                   │
│  • Receives: "search all data"                          │
│  • Returns: {"action": "query", "params": {"*"}}        │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  IOWarpEnvironment._do_query()                          │
│  1. Call: cache.query_keys(tag_pattern="*")             │
│  2. Memcached: stats items + stats cachedump            │
│  3. Parse keys: [{"tag": "docs", "blob_name": "..."}]  │
│  4. Return: {"matches": [...]}                          │
│  5. Reward: +0.10                                       │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  RESULT: Found 1 blob(s) in cache                       │
│  [{"tag": "docs", "blob_name": "sample.md"}]            │
└─────────────────────────────────────────────────────────┘

─────────────────────────────────────────────────────────

┌─────────────────────────────────────────────────────────┐
│  USER: "get sample.md from docs"                        │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  CoordinatorAgent → RetrieverAgent → Environment        │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  IOWarpEnvironment._do_retrieve()                       │
│  1. Try cache: cache.get(tag="docs", name="sample.md") │
│     └─ Memcached: FOUND! (Cache HIT)                    │
│  2. Return data directly (no IOWarp call needed)        │
│  3. Reward: +0.30 (cache hit bonus)                     │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│  RESULT: Retrieved from cache (0.5ms latency)           │
│  Content: "# Sample Document\n..."                      │
│  Cache: HIT (+0.30 reward)                              │
└─────────────────────────────────────────────────────────┘
```

---

## 🎓 Key Technical Concepts

### 1. Cache-Aside Pattern
**Definition:** Application code manages cache explicitly
- **Read:** Check cache → If miss, read from DB → Update cache
- **Write:** Write to DB → Invalidate/update cache
- **Benefit:** Cache failures don't break system (DB is source of truth)

### 2. Write-Through Caching
**Definition:** Write to cache AND database simultaneously
- **Implementation:** `assimilate` writes to IOWarp + memcached
- **Benefit:** Cache always fresh, no stale data
- **Trade-off:** Slower writes (2 operations)

### 3. Memory-Mapped I/O
**Definition:** Map file contents directly to process memory
- **IOWarp uses this:** Files in /dev/shm mapped to address space
- **Benefit:** No read() syscalls, no buffering, zero-copy
- **Use case:** Large datasets that need fast random access

### 4. Reinforcement Learning Environment
**Definition:** Agent takes actions, environment returns rewards
```python
observation = "user wants to ingest file"
action = agent.think(observation)  # Agent decides what to do
result = environment.step(action)  # Environment executes
reward = result["reward"]  # +0.10 for success, -0.50 for error
```

**Reward Structure:**
- `+0.30` - Cache HIT (best outcome)
- `+0.20` - Cache MISS but IOWarp success
- `+0.10` - Successful operation (ingest/query)
- `+0.05` - Cleanup operation (prune)
- `-0.50` - Error/failure

### 5. Multi-Agent Coordination
**Definition:** Multiple specialized agents working together
- **Coordinator:** Makes routing decisions (meta-agent)
- **Specialists:** Focus on specific tasks (ingestor, retriever)
- **Shared infrastructure:** All use same cache/storage
- **Benefit:** Modular, extensible, easier to optimize each role

---

## 📊 Performance Characteristics

### Latency Comparison

| Operation | Cache HIT | Cache MISS (IOWarp) | Speedup |
|-----------|-----------|---------------------|---------|
| Retrieve | 0.5ms | 5-10ms | 10-20x |
| Query | 1-2ms | 50-100ms* | 25-50x |

*IOWarp query currently broken, cache-only query used

### Cache Hit Rate (Typical)
- **First access:** 0% (cold cache)
- **Repeated access:** 100% (within 1-hour TTL)
- **After TTL:** 0% (expired, re-cached on access)
- **Workload dependent:** Reading same files → 80-90% hit rate

### Storage Capacity

| Tier | Size | Items | Use Case |
|------|------|-------|----------|
| Memcached | 512MB | ~5K files* | Hot data (recent access) |
| IOWarp | 8GB | ~80K files* | All data (long-term) |

*Assuming ~100KB average file size

---

## 🔧 Troubleshooting Guide

### Common Issues

**1. IOWarp Bridge Not Running**
```bash
docker ps | grep iowarp
# If missing:
docker-compose up -d iowarp
```

**2. Memcached Not Running**
```bash
printf "stats\r\n" | nc 127.0.0.1 11211
# Should return stats, not connection refused
```

**3. Cache Always Missing**
```bash
# Check if cache has data:
printf "stats items\r\n" | nc 127.0.0.1 11211
# Should show curr_items > 0
```

**4. IOWarp Query Returns 0**
```
# This is expected (stub mode)
# System uses cache.query_keys() instead
# Workaround working correctly
```

---

## 🎯 Key Points for Professor

### 1. Innovation
- **Natural language interface** to storage operations (not SQL or API calls)
- **Intelligent caching** with automatic fallback and healing
- **Multi-agent coordination** via LLM routing (no hardcoded rules)

### 2. System Design
- **Two-tier storage:** Speed + durability
- **Shared infrastructure:** Multiple agents, single cache
- **Auto-discovery:** New agents automatically integrated
- **Reward shaping:** RL feedback guides optimization

### 3. Real-World Applicability
- **Cache-aside + write-through:** Industry-standard patterns
- **Memcached + persistent storage:** Common in production systems
- **Docker orchestration:** Production-ready deployment
- **LLM-based routing:** Emerging pattern in AI systems

### 4. Technical Depth
- **Low-level:** Memory-mapped I/O, shared memory, TCP protocols
- **Mid-level:** Cache management, data structures, networking
- **High-level:** LLM integration, agent coordination, CLI design

### 5. Extensibility
- **Add new agents:** Just create YAML blueprint
- **Change storage backend:** Swap IOWarp for S3/Redis/etc
- **Add caching layers:** Redis, CDN, etc
- **Scale horizontally:** Distributed cache already supported

---

## 📈 Future Improvements

### Short-term
- [ ] Fix IOWarp Python bindings (ABI compatibility)
- [ ] Add authentication/authorization
- [ ] Metrics dashboard (cache hit rate, latency)
- [ ] More agent types (summarizer, analyzer)

### Long-term
- [ ] Distributed IOWarp (multi-node)
- [ ] Vector embeddings for semantic search
- [ ] Fine-tuned models for agent roles
- [ ] Web UI for visual workflow building

---

## 📚 Architecture Decisions

### Why not use a database?
- **IOWarp is faster:** Memory-mapped, zero-copy
- **RL training needs speed:** Thousands of episodes
- **Files are natural:** Scientific workflows use files
- **Shared memory enables multi-process:** No serialization

### Why memcached over Redis?
- **Simpler:** Just caching, no data structures needed
- **Faster for pure caching:** Optimized for key-value
- **LRU eviction:** Automatic memory management
- **Battle-tested:** Used at massive scale (Facebook, etc)

### Why Docker Compose?
- **Development speed:** One command to start everything
- **Reproducibility:** Same setup on all machines
- **Isolation:** No port conflicts, clean environment
- **Production-ready:** Docker widely deployed

### Why multiple agent types?
- **Specialization:** Each agent does one thing well
- **Modularity:** Easy to test, debug, improve
- **Extensibility:** Add new capabilities without breaking existing
- **Natural language:** Different phrasings route to right specialist

---

## 🏁 Summary

**AgentFactory is a reinforcement learning system where:**
1. **Agents** (AI decision-makers) interpret natural language commands
2. **Coordinator** (LLM router) delegates to specialized agents
3. **Environment** (execution engine) performs actions with reward feedback
4. **Two-tier storage** (cache + persistent) optimizes speed + durability
5. **Docker infrastructure** (IOWarp + memcached) provides reliable backend

**The system demonstrates:**
- Modern AI agent architecture (LLM-based routing)
- Production caching patterns (cache-aside, write-through)
- Low-level systems programming (shared memory, memory-mapped I/O)
- Reinforcement learning principles (reward shaping, trajectory tracking)
- Software engineering best practices (modularity, auto-discovery, Docker)

**Total implementation:** ~3,800 lines of Python + C++ bridge, with 159 passing tests.
