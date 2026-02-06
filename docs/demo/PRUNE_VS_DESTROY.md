# Prune vs Destroy: Cache Management vs Permanent Deletion

## Overview

AgentFactory now supports **two distinct deletion operations**:

| Operation | Scope | What it does | IOWarp | Memcached | Use Case |
|-----------|-------|--------------|--------|-----------|----------|
| **prune** | Blob-level | Cache eviction | ❌ No change | ✅ Delete | Free cache memory, force refresh |
| **destroy** | Tag-level | Permanent deletion | ✅ Delete | ✅ Delete | Remove data entirely |

---

## 1. Prune (Cache Eviction)

**Purpose:** Remove specific blobs from memcached cache without touching persistent storage.

**When to use:**
- Free up cache memory (512MB limit)
- Force data refresh on next access
- Remove stale cached entries
- Cache management / housekeeping

**Command Examples:**
```
prune api_reference.md from docs
evict old_data.csv from research
```

**What happens:**
```
Before:
  IOWarp:    docs/api_reference.md ✓
  Memcached: iowarp:docs:api_reference.md ✓

After PRUNE:
  IOWarp:    docs/api_reference.md ✓ (unchanged!)
  Memcached: iowarp:docs:api_reference.md ✗ (deleted)

Next retrieve:
  Cache: MISS → IOWarp fallback → Re-cache
  Result: Data retrieved from persistent storage, cache healed
```

**Parameters:**
- `tag` (required): Tag name
- `blob_names` (required): List of blob names to evict

**Observation:**
```
Pruned 1 blob(s) from cache. Data remains in IOWarp.
Data: {"tag": "docs", "pruned": ["api_reference.md"], "evicted": 1}
Reward: +0.05
```

**Important:** Prune REQUIRES `blob_names`. You cannot prune an entire tag - use `destroy` for that.

---

## 2. Destroy (Permanent Deletion)

**Purpose:** Permanently delete entire tag(s) from both persistent storage and cache.

**When to use:**
- Remove data you no longer need
- Clean up after experiments
- Delete outdated datasets
- Permanent data removal

**Command Examples:**
```
destroy docs
delete old_experiments
remove temp_data
```

**What happens:**
```
Before:
  IOWarp:    docs/api_reference.md ✓
  IOWarp:    docs/setup_guide.md ✓
  Memcached: iowarp:docs:api_reference.md ✓
  Memcached: iowarp:docs:setup_guide.md ✓

After DESTROY docs:
  IOWarp:    docs/* ✗ (all deleted!)
  Memcached: iowarp:docs:* ✗ (all invalidated!)

Next retrieve:
  Result: Error - tag no longer exists
```

**Parameters:**
- `tags` (required): Tag name or list of tag names

**Observation:**
```
Destroyed 1 tag(s) from IOWarp. Invalidated 2 cache entries.
Data: {"destroyed": ["docs"], "cache_invalidated": 2}
Reward: +0.05
```

**Implementation Details:**
1. Query cache to enumerate all blobs in tag(s)
2. Call IOWarp `context_destroy(tags)` → deletes from persistent storage
3. Call cache `invalidate_tag(tag, blob_names)` → deletes cache entries
4. Both layers now consistent (no stale data)

---

## Comparison Table

### Prune (Cache Eviction)

```python
# User command
"prune api.md from docs"

# Agent action
Action(
    name="prune",
    params={
        "tag": "docs",
        "blob_names": ["api.md"]
    }
)

# Environment execution
def _do_prune(params):
    # 1. Evict from cache only
    invalidated = cache.invalidate_tag(
        tag=params["tag"],
        blob_names=params["blob_names"]
    )
    # 2. IOWarp NOT touched
    return StepResult(
        observation="Pruned N blob(s) from cache. Data remains in IOWarp.",
        reward=+0.05
    )
```

**Result:**
- ✅ Cache entry deleted
- ✅ IOWarp data preserved
- ✅ Next access: Cache MISS → IOWarp fallback → Re-cache

### Destroy (Permanent Deletion)

```python
# User command
"destroy docs"

# Agent action
Action(
    name="destroy",
    params={
        "tags": "docs"  # or ["docs", "temp"]
    }
)

# Environment execution
def _do_destroy(params):
    # 1. Query cache to find all blobs
    matches = cache.query_keys(tag_pattern="docs")
    blob_names = [m["blob_name"] for m in matches]
    
    # 2. Destroy from IOWarp persistent storage
    result = client.context_destroy(tags=params["tags"])
    
    # 3. Invalidate all cache entries
    invalidated = cache.invalidate_tag(
        tag="docs",
        blob_names=blob_names
    )
    
    return StepResult(
        observation="Destroyed N tag(s) from IOWarp. Invalidated M cache entries.",
        reward=+0.05
    )
```

**Result:**
- ✅ IOWarp tag deleted (permanent)
- ✅ All cache entries invalidated
- ✅ Data gone from both tiers

---

## Keyword Mapping

| Keyword | Maps to | Notes |
|---------|---------|-------|
| `prune` | prune | Cache eviction |
| `evict` | prune | Cache eviction |
| `destroy` | destroy | Permanent deletion |
| `delete` | destroy | Permanent deletion |
| `remove` | destroy | Permanent deletion |

**Decision logic:**
- If you say "prune" or "evict" → cache eviction (requires blob names)
- If you say "delete", "remove", "destroy" → permanent deletion (tag-level)

---

## Use Case Examples

### Example 1: Free Cache Memory

**Scenario:** Cache is full (512MB limit), need to evict old data

```
User: "prune old_dataset.csv from research"

Agent: Action(name="prune", params={"tag": "research", "blob_names": ["old_dataset.csv"]})

Environment:
  - Cache: Delete iowarp:research:old_dataset.csv
  - IOWarp: No change
  - Result: "Pruned 1 blob(s) from cache. Data remains in IOWarp."
  
Benefit: Cache memory freed, data still accessible (slower, will re-cache)
```

### Example 2: Force Data Refresh

**Scenario:** File was updated in IOWarp externally, cache has stale copy

```
User: "prune config.yaml from system"

Agent: Action(name="prune", params={"tag": "system", "blob_names": ["config.yaml"]})

Environment:
  - Cache: Delete stale entry
  - IOWarp: No change
  
Next access:
  - Cache MISS
  - Retrieve fresh version from IOWarp
  - Re-cache updated data
  
Benefit: Cache now has fresh data
```

### Example 3: Delete Experiment Data

**Scenario:** Finished experiment, want to remove all data

```
User: "destroy experiment_2024"

Agent: Action(name="destroy", params={"tags": "experiment_2024"})

Environment:
  - Query cache: Found 47 blobs in tag
  - IOWarp: Destroy tag (all 47 files deleted)
  - Cache: Invalidate all 47 entries
  - Result: "Destroyed 1 tag(s) from IOWarp. Invalidated 47 cache entries."
  
Benefit: 8GB freed in IOWarp, cache cleaned up
```

### Example 4: Delete Multiple Tags

**Scenario:** Clean up multiple old experiments

```
User: "destroy temp_data and old_experiments"

Agent: Action(name="destroy", params={"tags": ["temp_data", "old_experiments"]})

Environment:
  - Query cache for both tags
  - IOWarp: Destroy both tags
  - Cache: Invalidate all entries
  - Result: "Destroyed 2 tag(s) from IOWarp. Invalidated 124 cache entries."
  
Benefit: Bulk cleanup, both tiers consistent
```

---

## Error Cases

### Prune without blob_names

```
User: "prune docs"

Agent: Action(name="prune", params={"tag": "docs"})

Environment:
  Error: "Prune requires 'blob_names' parameter. Use 'destroy' to delete entire tags."
  Reward: -0.50

Why: Cache eviction needs specific files. To delete whole tag, use destroy.
```

### Destroy non-existent tag

```
User: "destroy nonexistent"

Agent: Action(name="destroy", params={"tags": "nonexistent"})

Environment:
  IOWarp: context_destroy returns empty list
  Cache: No entries to invalidate
  Result: "Destroyed 0 tag(s) from IOWarp. Invalidated 0 cache entries."
  Reward: +0.05 (not an error, just nothing to delete)
```

---

## CLI Usage

### Interactive Mode

```bash
$ uv run cli.py run iowarp_agent

agent> ingest file::data.md as docs
  → Assimilated 1 file(s)

agent> prune data.md from docs
  → Pruned 1 blob(s) from cache. Data remains in IOWarp.

agent> get data.md from docs
  → Retrieved 'data.md' from IOWarp (fallback). Size: 1234 bytes.
  → Cache: MISS (just pruned!)
  → Reward: +0.20

agent> destroy docs
  → Destroyed 1 tag(s) from IOWarp. Invalidated 1 cache entries.

agent> get data.md from docs
  → Error: Tag 'docs' no longer exists
```

### Coordinator Mode

```bash
$ uv run cli.py run coordinator_agent

agent> load file::data.md as docs
  → Coordinator routing to 'ingestor' agent
  → Assimilated 1 file(s)

agent> evict data.md from docs
  → Coordinator routing to 'retriever' agent
  → Pruned 1 blob(s) from cache

agent> delete docs permanently
  → Coordinator routing to 'retriever' agent
  → Destroyed 1 tag(s) from IOWarp
```

---

## System Prompt Update (for LLM Agents)

```
ACTIONS YOU CAN TAKE:
  prune    — Evict specific blobs from cache (data remains in IOWarp)
             params: tag (tag name), blob_names (list of blob names)
             Use for: cache management, forcing refresh
             
  destroy  — Permanently delete entire tag(s) from both IOWarp and cache
             params: tags (tag name or list)
             Use for: removing data you no longer need
```

---

## Architecture Impact

### Before (Single Operation)

```
┌──────────────────────┐
│ User: "delete docs"  │
└──────────┬───────────┘
           ↓
┌──────────────────────┐
│ Action: prune        │
│ - Destroy IOWarp ✓   │
│ - Invalidate cache ✗ │  ← Bug: cache invalidation didn't work!
└──────────────────────┘

Result: Stale cache entries after deletion
```

### After (Two Operations)

```
┌─────────────────────────────┬─────────────────────────────┐
│ User: "prune api.md"        │ User: "destroy docs"        │
└──────────┬──────────────────┴──────────┬──────────────────┘
           ↓                              ↓
┌──────────────────────┐    ┌───────────────────────────┐
│ Action: prune        │    │ Action: destroy           │
│ - Destroy IOWarp ✗   │    │ - Destroy IOWarp ✓        │
│ - Invalidate cache ✓ │    │ - Invalidate cache ✓      │
└──────────────────────┘    └───────────────────────────┘
           ↓                              ↓
┌──────────────────────┐    ┌───────────────────────────┐
│ Cache: Evicted       │    │ Both tiers: Deleted       │
│ IOWarp: Preserved    │    │ Cache: No stale data      │
└──────────────────────┘    └───────────────────────────┘
```

---

## Testing

```bash
# Test prune (cache eviction)
uv run pytest tests/integration/test_iowarp_env.py::test_prune_cache_only -v

# Test destroy (permanent deletion)
uv run pytest tests/integration/test_iowarp_env.py::test_destroy_tag -v

# Test error case (prune without blob_names)
uv run pytest tests/integration/test_iowarp_env.py::test_prune_requires_blobs -v
```

---

## Summary

**Prune:**
- ✅ Cache eviction (blob-level)
- ✅ Requires blob_names parameter
- ✅ IOWarp data preserved
- ✅ Data accessible via IOWarp fallback
- ✅ Use for cache management

**Destroy:**
- ✅ Permanent deletion (tag-level)
- ✅ Deletes from both IOWarp and memcached
- ✅ Enumerates cache entries before invalidation
- ✅ No stale data possible
- ✅ Use for data removal

**Key insight:** Prune is for **cache management** (temporary), destroy is for **data deletion** (permanent).
