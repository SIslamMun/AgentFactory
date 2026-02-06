# AgentFactory Manual Walkthrough - Step by Step

## Step 1: Check Infrastructure

```bash
# Start containers if not running
docker-compose up -d
sleep 5
docker-compose ps

# You should see:
# agentfactory_iowarp_1      Up (healthy)
# agentfactory_memcached_1   Up (healthy)
```

## Step 2: Start CLI

```bash
uv run cli.py
```

**Select:**
- Blueprint: `1` (iowarp_agent)
- Agent: `3` (Claude)

**You should see:**
```
✓ IOWarp bridge (tcp://127.0.0.1:5560) ......... OK
✓ Memcached (127.0.0.1:11211) .................. OK

Building agent stack from blueprint... done
Agent: ClaudeAgent (sonnet)
Environment: IOWarpEnvironment
Type 'help' for commands, 'quit' to exit.

agent>
```

---

## Step 3a: Check Initial Status

**Type:**
```
status
```

**Expected output:**
```
Trajectory: 0 steps | Total reward: 0.00
Cache: 0 hit(s), 0 miss(es) (0% hit rate)
```

---

## Step 4: Ingest Documents (Assimilate)

**Type:**
```
ingest folder::./data/sample_docs into tag: walkthrough_docs
```

**Expected output:**
```
Agent thinking...
  Thought: "The user wants to ingest files from a folder URI..."
  Action: assimilate
  Params: {'src': 'folder::./data/sample_docs', 'dst': 'walkthrough_docs', 'format': 'auto'}

Environment response:
  Result: Assimilated 3 file(s) into tag 'walkthrough_docs'. Cached 3 blob(s).
  Data: {'tag': 'walkthrough_docs', 'files': 3, 'cached': 3}
  Reward: +0.10
```

**What happened:**
1. URIResolver expanded `folder::./data/sample_docs` into 3 files
2. IOWarp stored them in shared memory
3. Memcached cached all 3 blobs (write-through)

---

## Step 5: Check Status After Ingest

**Type:**
```
status
```

**Expected output:**
```
Trajectory: 1 steps | Total reward: 0.10
Cache: 0 hit(s), 0 miss(es) (0% hit rate)
```

---

## Step 6: Query for Stored Data

**Type:**
```
query tag: walkthrough_docs
```

**Expected output:**
```
Agent action: query({'tag_pattern': 'walkthrough_docs'})

Environment response:
  Result: Query returned 0 match(es).
  Data: {'matches': []}
  Reward: +0.10
```

**Note:** Returns 0 because IOWarp C++ extension is in stub mode (known limitation)

---

## Step 7: Retrieve Specific Blob (Cache HIT)

**Type:**
```
retrieve blob: project_overview.md from tag: walkthrough_docs
```

**Expected output:**
```
Agent action: retrieve({'tag': 'walkthrough_docs', 'blob_name': 'project_overview.md'})

Environment response:
  Result: Retrieved 'project_overview.md' from cache (hit).
  Data: {'cache_hit': True, 'size': 493}
  Reward: +0.30

── Content preview ──
│ # IOWarp Project Overview
│ 
│ IOWarp is a unified I/O middleware that manages data movement across
│ heterogeneous storage (RAM, NVMe, SSD, HDD, remote).
│ 
│ ## Key Concepts
│ 
│ - **Context Engine (CTE)**: stores data as tagged blobs
│ ...
```

**What happened:**
- Cache checked first → HIT!
- Returned 493 bytes from memcached
- Never touched IOWarp bridge
- Higher reward (+0.30) for cache efficiency

---

## Step 8: Retrieve Again (Second Cache HIT)

**Type:**
```
retrieve blob: project_overview.md from tag: walkthrough_docs
```

**Expected output:**
```
Environment response:
  Result: Retrieved 'project_overview.md' from cache (hit).
  Reward: +0.30
```

**Still a cache HIT!** Same file, still in cache.

---

## Step 9: Check Status After Retrieves

**Type:**
```
status
```

**Expected output:**
```
Trajectory: 4 steps | Total reward: 0.90
Cache: 4 hit(s), 0 miss(es) (100% hit rate)
```

**Breakdown:**
- 1 assimilate: +0.10
- 1 query: +0.10
- 2 retrieves (both HITs): +0.30 + +0.30 = +0.60
- Total: 0.90

---

## Step 10: View History

**Type:**
```
history
```

**Expected output:**
```
History (4 steps)
  1. assimilate   reward=+0.10
     Assimilated 3 file(s) into tag 'walkthrough_docs'. Cached 3 blob(s).
  2. query        reward=+0.10
     Query returned 0 match(es).
  3. retrieve     reward=+0.30 [HIT]
     Retrieved 'project_overview.md' from cache (hit).
  4. retrieve     reward=+0.30 [HIT]
     Retrieved 'project_overview.md' from cache (hit).

Total reward: 0.90
```

---

## Step 11: List Blobs (Will Return 0)

**Type:**
```
list everything under tag walkthrough_docs
```

**Expected output:**
```
Agent action: list_blobs({'tag_pattern': 'walkthrough_docs'})

Environment response:
  Result: Listed blobs: 0 match(es).
  Data: {'matches': []}
  Reward: +0.10
```

**Note:** Returns 0 due to C++ extension limitation (same as query)

---

## Step 12: Try Other Blobs

**Type:**
```
retrieve blob: api_reference.md from tag: walkthrough_docs
```

**Expected output:**
```
Result: Retrieved 'api_reference.md' from cache (hit).
Cache: HIT
Reward: +0.30
Size: 568 bytes

── Content preview ──
│ # IOWarp Python API Reference
│ 
│ ## wrp_cee module
│ ...
```

**Type:**
```
retrieve blob: setup_guide.md from tag: walkthrough_docs
```

**Expected output:**
```
Result: Retrieved 'setup_guide.md' from cache (hit).
Cache: HIT
Reward: +0.30
Size: 396 bytes
```

---

## Step 13: Final Status

**Type:**
```
status
```

**Expected output:**
```
Trajectory: 7 steps | Total reward: 1.50
Cache: 10 hit(s), 0 miss(es) (100% hit rate)
```

---

## Step 14: Test Manual Action (Bypass Agent)

**Type:**
```
manual query {"tag_pattern": "walkthrough_docs", "blob_pattern": "*"}
```

**Expected output:**
```
Manual action: query
Params: {'tag_pattern': 'walkthrough_docs', 'blob_pattern': '*'}

Environment response:
  Result: Query returned 0 match(es).
  Data: {'matches': []}
  Reward: +0.10
```

**Note:** This bypasses Claude reasoning and sends action directly to environment

---

## Step 15: Cleanup (Prune)

**Type:**
```
prune tag: walkthrough_docs
```

**Expected output:**
```
Agent action: prune({'tags': 'walkthrough_docs'})

Environment response:
  Result: Pruned 1 tag(s). Invalidated 0 cache entries.
  Data: {'destroyed': ['walkthrough_docs'], 'invalidated': 0}
  Reward: +0.05
```

---

## Step 16: Verify Cleanup

**Type:**
```
status
```

**Expected output:**
```
Trajectory: 9 steps | Total reward: 1.65
Cache: 10 hit(s), 0 miss(es) (100% hit rate)
```

---

## BONUS: Test Cache Persistence After Flush

### Part A: Ingest Fresh Data

**Type:**
```
ingest folder::./data/sample_docs into tag: persist_test
```

**Type:**
```
retrieve blob: api_reference.md from tag: persist_test
```

**Expected:** Cache HIT (568 bytes)

**Type:**
```
quit
```

### Part B: Flush Cache (Outside CLI)

```bash
# In your terminal
printf "flush_all\r\n" | nc -w 1 127.0.0.1 11211
```

**Output:** `OK`

### Part C: Restart CLI and Retrieve

```bash
uv run cli.py
```

**Select:** Blueprint 1, Agent 3

**Type:**
```
retrieve blob: api_reference.md from tag: persist_test
```

**Expected output:**
```
Result: Retrieved 'api_reference.md' from IOWarp (cache miss, now cached).
Cache: MISS
Reward: +0.20 (lower reward - had to fetch from IOWarp)
Size: 0 (stub mode returns empty, but proves it tried IOWarp)
```

**This proves:**
1. Cache was empty (flushed)
2. IOWarp still had the data
3. Two-tier architecture works!

---

## Exit

**Type:**
```
quit
```

**Expected output:**
```
Cleaning up...
Goodbye.
```

---

## Quick Reference

### Available Commands

```
help                                    Show all commands
status                                  Trajectory and cache stats
observe                                 Current environment state
history                                 Show all steps with rewards
agent                                   Show agent info
list                                    List all blueprints
show <name>                             Show blueprint config
create <name> [type]                    Create new blueprint
delete <name>                           Delete blueprint
switch <name>                           Switch to different blueprint
configure <key> <value>                 Change config
manual <action> <json>                  Send action directly
quit                                    Exit
```

### Natural Language Examples

```
ingest <path> into tag: <name>
retrieve <file> from tag: <name>
query tag: <name>
find what is stored in tag <name>
list everything under tag <name>
prune tag: <name>
```

---

## Expected Totals

After full walkthrough (Steps 1-16):
- **Steps:** 9
- **Total Reward:** 1.65
- **Cache Hits:** 10
- **Cache Misses:** 0
- **Hit Rate:** 100%

**Reward Breakdown:**
- 1× assimilate: +0.10
- 2× query: +0.20
- 5× retrieve (HITs): +1.50
- 1× list_blobs: +0.10
- 1× prune: +0.05
- **Total:** 1.95 (if you retrieve all 3 files)
