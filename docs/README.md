# Documentation Structure

This folder contains all AgentFactory documentation organized by category.

## 📁 Folder Structure

```
docs/
├── architecture/          # System design and architecture documentation
│   ├── SYSTEM_ARCHITECTURE_EXPLAINED.md    # Complete system explanation for professor
│   ├── COORDINATOR_ANALYSIS.md             # Coordinator agent design analysis
│   ├── agent_factory_design.md             # Original design document
│   ├── HOW_IT_WORKS.md                     # System operation guide
│   └── flow.md                             # Data flow diagrams
│
├── demo/                  # Demo guides and validation results
│   ├── COMPLETE_DEMO.md                    # Step-by-step demo commands
│   ├── PRUNE_VS_DESTROY.md                 # Cache eviction vs deletion guide
│   └── VALIDATION_RESULTS.md               # Test validation evidence
│
└── planning/              # Development plans and roadmaps
    └── PLAN_agent_management.md            # Agent management feature plans
```

## 📖 Quick Reference

### For Professor Presentation
Start here:
1. [SYSTEM_ARCHITECTURE_EXPLAINED.md](architecture/SYSTEM_ARCHITECTURE_EXPLAINED.md) - Complete system overview
2. [COMPLETE_DEMO.md](demo/COMPLETE_DEMO.md) - Live demo commands
3. [VALIDATION_RESULTS.md](demo/VALIDATION_RESULTS.md) - Proof that it works

### For Developers
1. [HOW_IT_WORKS.md](architecture/HOW_IT_WORKS.md) - System internals
2. [COORDINATOR_ANALYSIS.md](architecture/COORDINATOR_ANALYSIS.md) - Multi-agent coordination
3. [PRUNE_VS_DESTROY.md](demo/PRUNE_VS_DESTROY.md) - Cache management operations

### For Planning
1. [PLAN_agent_management.md](planning/PLAN_agent_management.md) - Future features

## 🔍 Document Descriptions

### Architecture Documentation

**SYSTEM_ARCHITECTURE_EXPLAINED.md**
- Comprehensive system explanation for academic presentation
- Component details (IOWarp, Memcached, BlobCache, Agents)
- Two-tier storage architecture
- Data flow diagrams
- Performance characteristics
- Use cases and examples

**COORDINATOR_ANALYSIS.md**
- Multi-agent coordinator design
- Comparison: Pipeline vs Dynamic Coordination
- Auto-discovery mechanism
- Shared infrastructure architecture
- Implementation options

**agent_factory_design.md**
- Original design document
- Core concepts and principles
- Blueprint system design

**HOW_IT_WORKS.md**
- System operation details
- Component interactions
- Code walkthrough

**flow.md**
- Data flow diagrams
- Request/response flows
- State transitions

### Demo Documentation

**COMPLETE_DEMO.md**
- Three complete demo scenarios:
  1. IOWarp Agent (single agent, cache-aside)
  2. Cache Flush Test (persistence verification)
  3. Coordinator Agent (multi-agent routing)
- Step-by-step commands with expected output
- Quick command reference
- Architecture recap

**PRUNE_VS_DESTROY.md**
- Cache eviction (prune) vs permanent deletion (destroy)
- Comparison tables
- Use case examples
- Error handling
- CLI usage examples
- Implementation details

**VALIDATION_RESULTS.md**
- Test execution results
- Evidence that prune/destroy work correctly
- Performance metrics
- Behavioral verification
- Demo commands for professor

### Planning Documentation

**PLAN_agent_management.md**
- Agent lifecycle management plans
- Blueprint CRUD operations
- Future enhancements

## 🎯 Getting Started

**For a quick demo:**
```bash
# Read the demo guide
cat docs/demo/COMPLETE_DEMO.md

# Run the demo
docker-compose up -d
uv run cli.py run iowarp_agent
```

**To understand the system:**
```bash
# Read architecture first
cat docs/architecture/SYSTEM_ARCHITECTURE_EXPLAINED.md

# Then check how it works
cat docs/architecture/HOW_IT_WORKS.md
```

**To understand cache operations:**
```bash
# Read the guide
cat docs/demo/PRUNE_VS_DESTROY.md

# See the validation
cat docs/demo/VALIDATION_RESULTS.md
```

## 📝 Additional Documentation

- Root `README.md` - Quick start and installation
- `old_docs/` - Legacy documentation (archived)

## 🔄 Document Maintenance

**When adding new documentation:**
1. Determine category (architecture/demo/planning)
2. Place in appropriate folder
3. Update this README.md
4. Use clear, descriptive filenames
5. Include date in validation/test documents

**Naming conventions:**
- Architecture: Descriptive names (e.g., `COORDINATOR_ANALYSIS.md`)
- Demo: Action-oriented (e.g., `COMPLETE_DEMO.md`)
- Validation: Include results (e.g., `VALIDATION_RESULTS.md`)
- Planning: Prefix with `PLAN_` (e.g., `PLAN_feature_name.md`)
