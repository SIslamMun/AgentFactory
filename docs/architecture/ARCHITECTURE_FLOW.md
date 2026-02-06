# AgentFactory Complete Process Flow

## 🏗️ System Architecture

```
┌──────────────┐
│     User     │
│   Terminal   │
└──────┬───────┘
       │ Types command: "ingest /path/folder into tag: docs"
       ▼
┌──────────────────────────────────────────────────────────────┐
│                         CLI (cli.py)                          │
│  • Reads user input                                           │
│  • Routes to command handlers or agent loop                   │
└──────┬───────────────────────────────────────────────────────┘
       │ Creates Observation(text="ingest /path/folder...")
       ▼
┌──────────────────────────────────────────────────────────────┐
│                    Agent (iowarp_agent.py)                    │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  1. think(observation)                                 │  │
│  │     • Matches "ingest" keyword → "assimilate" action   │  │
│  │     • Returns thought string                           │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  2. act(observation)                                   │  │
│  │     • Extracts URI from text                           │  │
│  │     • Auto-detects folder vs file                      │  │
│  │     • Extracts tag name ("docs")                       │  │
│  │     • Returns Action(name="assimilate", params={...})  │  │
│  └────────────────────────────────────────────────────────┘  │
└──────┬───────────────────────────────────────────────────────┘
       │ Action: assimilate
       │ Params: {src: "folder::/path", dst: "docs", format: "arrow"}
       ▼
┌──────────────────────────────────────────────────────────────┐
│              Environment (iowarp_env.py)                      │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  1. URI Resolution (uri_resolver.py)                   │  │
│  │     folder::/path → ["file::/path/file1.md",          │  │
│  │                      "file::/path/file2.md",          │  │
│  │                      "file::/path/file3.md"]          │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  2. Call IOWarp Bridge                                 │  │
│  │     client.context_bundle(src=[...], dst="docs")       │  │
│  └────────────────────────────────────────────────────────┘  │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  3. Write-Through Cache                                │  │
│  │     For each file:                                     │  │
│  │       • Read file content                              │  │
│  │       • cache.put("docs", "filename", data)            │  │
│  └────────────────────────────────────────────────────────┘  │
└──────┬───────────────────────────────────────────────────────┘
       │ ZMQ Request over TCP (port 5560)
       ▼
┌──────────────────────────────────────────────────────────────┐
│         IOWarp Bridge (Docker: bridge.py)                     │
│  • Receives JSON-RPC request                                  │
│  • Dispatches to handler: handle_context_bundle()             │
│  • Calls C++ runtime: wrp_cee.context_bundle(...)             │
└──────┬───────────────────────────────────────────────────────┘
       │ Python-C++ binding (wrp_cee extension module)
       ▼
┌──────────────────────────────────────────────────────────────┐
│            IOWarp C++ Runtime (chimaera)                      │
│  • Reads file contents from disk                              │
│  • Stores in internal data structures                         │
│  • Tags data with "docs" label                                │
│  • Manages heterogeneous storage (RAM/NVMe/SSD)               │
│  • Returns success status                                     │
└──────┬───────────────────────────────────────────────────────┘
       │ Returns to Python bridge
       ▼
┌──────────────────────────────────────────────────────────────┐
│                   IOWarp Bridge (bridge.py)                   │
│  • Returns JSON response: {"result": {"status": "ok"}}        │
└──────┬───────────────────────────────────────────────────────┘
       │ ZMQ Response
       ▼
┌──────────────────────────────────────────────────────────────┐
│              Environment (iowarp_env.py)                      │
│  • Receives result                                            │
│  • Calculates reward (+0.10 for success)                      │
│  • Creates Observation with result text                       │
│  • Returns StepResult(observation, reward)                    │
└──────┬───────────────────────────────────────────────────────┘
       │ StepResult
       ▼
┌──────────────────────────────────────────────────────────────┐
│                         CLI (cli.py)                          │
│  • Appends action/result to trajectory                        │
│  • Displays result to user                                    │
│  • Shows reward and cache stats                               │
└──────┬───────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│     User     │  Sees: "Assimilated 3 file(s) into tag 'docs'.
│   Terminal   │        Cached 3 blob(s). Reward: +0.10"
└──────────────┘
```

---

## 🔄 Detailed Component Interactions

### **1. Agent Think/Act Cycle**

```python
# User input → Observation
obs = Observation(text="ingest /path/to/folder into tag: docs")

# Agent thinks
thought = agent.think(obs)
# → "Observation matches '\bingest\b' → will perform 'assimilate'."

# Agent acts
action = agent.act(obs)
# → Action(name="assimilate", params={
#       "src": "folder::/path/to/folder",
#       "dst": "docs",
#       "format": "arrow"
#    })
```

**Key Agent Logic:**
1. Pattern matching: `\bingest\b` → `assimilate` action
2. URI extraction: Finds path, checks if dir/file, adds scheme
3. Tag extraction: Finds `tag: docs` pattern
4. Returns structured `Action` object

---

### **2. URI Resolution Flow**

```python
# Input
src = "folder::/path/to/folder"

# URIResolver.resolve(src)
resolver._resolve_folder(src)
  → Path("/path/to/folder").rglob("*")
  → [file1.md, file2.md, file3.md]
  → ["file::/path/to/folder/file1.md",
     "file::/path/to/folder/file2.md",
     "file::/path/to/folder/file3.md"]

# Returns list of file:: URIs
```

**Supported URI Schemes:**
- `file::/path` - Single file (passthrough to IOWarp)
- `folder::/dir` - Recursively expand all files
- `hdf5::/path` - HDF5 file (passthrough)
- `mem::tag/blob` - Retrieve from cache, write temp file

---

### **3. IOWarp Bridge Protocol (ZMQ JSON-RPC)**

```python
# Request (Python → Bridge)
{
    "method": "context_bundle",
    "params": {
        "src": ["file::/path/file1.md", "file::/path/file2.md"],
        "dst": "docs",
        "format": "arrow"
    }
}

# Bridge calls C++ runtime
wrp_cee.context_bundle(src=[...], dst="docs", format="arrow")

# Response (Bridge → Python)
{
    "result": {
        "status": "ok",
        "tag": "docs"
    }
}
```

---

### **4. Cache Write-Through Strategy**

```python
# After successful IOWarp ingestion
for uri in resolved:
    if uri.startswith("file::"):
        path = uri[7:]  # Remove "file::" prefix
        with open(path, "rb") as f:
            blob_data = f.read()
        
        blob_name = path.rsplit("/", 1)[-1]  # Extract filename
        
        # Write to Memcached
        cache.put(tag="docs", blob_name="file1.md", data=blob_data)
```

**Cache Key Format:**
```
af:docs:file1.md  →  <blob data bytes>
```

---

### **5. Cache Read (Retrieve Action)**

```python
# User: "retrieve file1.md from tag: docs"

# Step 1: Check cache first (cache-aside pattern)
cached = cache.get(tag="docs", blob_name="file1.md")

if cached:
    # Cache HIT
    reward = +0.30  # Higher reward for cache hit
    return StepResult(
        observation=Observation(text="Retrieved from cache (hit)"),
        reward=0.30
    )
else:
    # Cache MISS - fetch from IOWarp
    data = client.context_retrieve(tag="docs", blob_name="file1.md")
    
    # Re-populate cache
    cache.put("docs", "file1.md", data)
    
    reward = +0.20  # Lower reward for cache miss
    return StepResult(
        observation=Observation(text="Retrieved from IOWarp (cache miss)"),
        reward=0.20
    )
```

---

### **6. Reward Structure**

```python
class RewardConfig:
    assimilate_success = 0.10   # Successfully ingested data
    query_success = 0.10        # Successfully queried
    retrieve_hit = 0.30         # Retrieved from cache (fast)
    retrieve_miss = 0.20        # Retrieved from IOWarp (slower)
    prune_success = 0.05        # Successfully deleted
    error = -0.50               # Any operation failed
```

**Goal:** Encourage cache hits (faster, higher reward)

---

### **7. Trajectory Tracking**

```python
class Trajectory:
    steps: list[tuple[Action, StepResult]]
    
    def total_reward(self) -> float:
        return sum(result.reward for _, result in self.steps)
    
    def cache_hit_rate(self) -> float:
        hits = sum(1 for a, r in self.steps 
                   if r.reward == 0.30)  # Cache hits
        misses = sum(1 for a, r in self.steps 
                     if r.reward == 0.20)  # Cache misses
        
        if hits + misses == 0:
            return 0.0
        return hits / (hits + misses)
```

---

## 📊 Data Flow Example: Full Session

```
User: ingest /path/old_docs into tag: docs

1. CLI creates Observation("ingest /path/old_docs into tag: docs")
2. Agent.think() → "matches 'ingest' → assimilate"
3. Agent.act() → Action(assimilate, {src: "folder::/path/old_docs", dst: "docs"})
4. URIResolver: folder::/path/old_docs → [file::/path/old_docs/file1.md, ...]
5. IOWarpClient → ZMQ → Bridge → C++ Runtime (ingests 3 files)
6. Cache.put("docs", "file1.md", <bytes>)  ×3 files
7. Environment returns: Observation("Assimilated 3 files"), reward=+0.10
8. CLI displays result + trajectory stats

---

User: retrieve file1.md from tag: docs

1. CLI creates Observation("retrieve file1.md from tag: docs")
2. Agent.think() → "matches 'retrieve' → retrieve"
3. Agent.act() → Action(retrieve, {tag: "docs", blob_name: "file1.md"})
4. Environment: cache.get("docs", "file1.md")
5. Cache HIT → returns <bytes>
6. Environment returns: Observation("Retrieved from cache"), reward=+0.30
7. CLI displays content preview + [HIT] indicator

---

User: status

Trajectory: 2 steps | Total reward: 0.40
Cache: 1 hit(s), 0 miss(es) (100% hit rate)
```

---

## 🔧 Key Technologies

| Component | Technology | Purpose |
|-----------|------------|---------|
| **CLI** | Python (Rich-like formatting) | User interface |
| **Agent** | Python (Regex pattern matching) | Natural language → Actions |
| **Environment** | Python | Action execution orchestration |
| **IOWarp Bridge** | Python (ZMQ server) | RPC bridge to C++ runtime |
| **IOWarp Runtime** | C++ (chimaera) | High-performance I/O engine |
| **Cache** | Memcached (pymemcache) | Key-value cache |
| **Communication** | ZMQ (JSON-RPC) | Python ↔ Bridge messaging |

---

## 🎯 Design Patterns

1. **Agent Protocol**: `think()` / `act()` interface
2. **Environment Protocol**: `step()` / `observe()` / `close()`
3. **Cache-Aside**: Check cache first, then fallback to storage
4. **Write-Through**: Write to cache when ingesting data
5. **URI Schemes**: Extensible `scheme::target` format
6. **ZMQ Request-Reply**: Synchronous RPC over TCP
7. **Factory Pattern**: AgentBuilder constructs full stack

---

## 🚀 Performance Optimizations

1. **Memcached** - Fast in-memory caching (microsecond latency)
2. **ZMQ** - High-performance messaging (zero-copy where possible)
3. **URI Resolution** - Batch file operations
4. **Write-Through Cache** - Avoid roundtrip on first retrieve
5. **Reward System** - Incentivize cache hits

---

## 🔐 Configuration Files

### Blueprint (YAML)
```yaml
# configs/blueprints/iowarp_agent.yaml
agent:
  type: rule_based

environment:
  type: iowarp
  iowarp:
    bridge_endpoint: tcp://127.0.0.1:5560
  cache:
    hosts:
      - host: 127.0.0.1
        port: 11211
  rewards:
    retrieve_hit: 0.30
    retrieve_miss: 0.20
```

This blueprint drives the entire system configuration!
