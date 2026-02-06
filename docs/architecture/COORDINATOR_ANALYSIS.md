# Coordinator Agent Analysis

## What You Want

**Interactive Multi-Agent Coordination** where you type natural language commands like:
- "ingest folder://data/sample_docs as research_docs"
- "retrieve all blobs from research_docs"
- "query research_docs for HDF5 information"

And the system should:
1. **Parse** your command using an LLM (Claude)
2. **Route** to the appropriate specialized agent (IngestorAgent, RetrieverAgent)
3. **Coordinate** the execution
4. **Return** results

## What Currently Exists

### ✅ Specialized Agents (IMPLEMENTED)
- **IngestorAgent** (`agents/ingestor_agent.py`) - Wraps any backend, constrains to `assimilate` action
- **RetrieverAgent** (`agents/retriever_agent.py`) - Wraps any backend, constrains to `query/retrieve/list_blobs`
- **ClaudeAgent** (`agents/claude_agent.py`) - LLM reasoning backend
- **IOWarpAgent** (`agents/iowarp_agent.py`) - Rule-based backend
- **LLMAgent** (`agents/llm_agent.py`) - Ollama backend

### ✅ Backend Agents (IMPLEMENTED)
All agents satisfy the `Agent` protocol:
```python
class Agent(Protocol):
    def think(self, observation: Observation) -> str: ...
    def act(self, observation: Observation) -> Action: ...
```

### ✅ Pipeline Orchestration (IMPLEMENTED)
- **PipelineDAG** (`orchestration/dag.py`) - Topological sorting, dependency management
- **PipelineExecutor** (`orchestration/executor.py`) - Runs agents through DAG
- **PipelineContext** (`orchestration/messages.py`) - Variable resolution (`${step.key}`)

### ✅ Infrastructure (IMPLEMENTED)
- **AgentBuilder** (`factory/builder.py`) - Can build single agents OR pipelines
- **IOWarpEnvironment** (`environments/iowarp_env.py`) - Executes actions, returns rewards
- **BlueprintRegistry** (`factory/registry.py`) - Loads YAML configs

## What's Missing: OrchestratorAgent

### ❌ Coordinator/Orchestrator Agent (NOT IMPLEMENTED)

The **PipelineExecutor** is NOT an agent - it's a DAG runner that executes **predefined** pipelines from YAML files.

You need a **CoordinatorAgent** that:
1. Takes natural language input
2. **Decides dynamically** which agent(s) to call
3. Routes commands to specialized agents
4. Aggregates results

## Architecture Comparison

### Current: Pipeline Mode (Static DAG)
```
User types: run src=folder://... dst=research_docs
             ↓
       Pipeline YAML defines:
       - Step 1: IngestorAgent (ingest_docs)
       - Step 2: RetrieverAgent (query_results)
       - Step 3: RetrieverAgent (retrieve_data)
             ↓
       PipelineExecutor runs steps in order
             ↓
       All 3 steps execute (predefined)
```

**Problem**: Must define pipeline in advance. Can't handle ad-hoc commands.

### Desired: Coordinator Mode (Dynamic Routing)
```
User types: "ingest folder://data/sample_docs as research_docs"
             ↓
       CoordinatorAgent (Claude LLM)
             ↓
       Parses: action=ingest, src=folder://..., dst=research_docs
             ↓
       Routes to: IngestorAgent
             ↓
       IngestorAgent executes assimilate
             ↓
       Returns result to user

User types: "retrieve all blobs from research_docs"
             ↓
       CoordinatorAgent parses: action=retrieve_all, tag=research_docs
             ↓
       Routes to: RetrieverAgent
             ↓
       RetrieverAgent calls act_compound() → query + retrieve
             ↓
       Returns results to user
```

**Advantage**: Natural language interface, dynamic routing, no YAML needed.

## Implementation Plan

### Option 1: OrchestratorAgent as New Agent Type

Create `src/agent_factory/agents/orchestrator_agent.py`:

```python
class OrchestratorAgent:
    """Routes natural language commands to specialized agents."""
    
    def __init__(
        self,
        agents: dict[str, Any],  # {"ingestor": IngestorAgent, "retriever": RetrieverAgent}
        llm: Any,  # ClaudeAgent for parsing
        environment: IOWarpEnvironment,
    ):
        self._agents = agents
        self._llm = llm
        self._environment = environment
    
    def think(self, observation: Observation) -> str:
        """Use LLM to parse command and decide routing."""
        routing_prompt = f"""
You are a coordinator agent. Parse this command and decide which agent to route to:

Command: {observation.text}

Available agents:
- ingestor: For ingesting/loading/assimilating data
- retriever: For querying/retrieving/listing data

Respond with JSON:
{{
  "thought": "your reasoning",
  "agent": "ingestor" or "retriever",
  "instruction": "simplified instruction for the agent"
}}
"""
        routing_obs = Observation(text=routing_prompt)
        return self._llm.think(routing_obs)
    
    def act(self, observation: Observation) -> Action:
        """Route to appropriate agent and execute."""
        # Parse LLM response
        routing = json.loads(self._llm.act(...).params["response"])
        
        # Route to agent
        agent_name = routing["agent"]
        agent = self._agents[agent_name]
        
        # Create observation for specialized agent
        agent_obs = Observation(text=routing["instruction"])
        
        # Get action from specialized agent
        return agent.act(agent_obs)
```

### Option 2: CLI Enhancement (Simpler)

Modify `cli.py` interactive mode to detect multi-agent intent:

```python
# In run_interactive() REPL loop
if "ingest" in cmd or "load" in cmd:
    # Route to IngestorAgent
    ingestor = agents["ingestor"]
    action = ingestor.act(Observation(text=raw))
    result = environment.step(action)
    
elif "retrieve" in cmd or "query" in cmd or "list" in cmd:
    # Route to RetrieverAgent
    retriever = agents["retriever"]
    action = retriever.act(Observation(text=raw))
    result = environment.step(action)
```

**Problem**: This is just glorified keyword matching - not true coordination.

### Option 3: Hybrid (Recommended)

1. Create **CoordinatorAgent** class that wraps ClaudeAgent
2. Use Claude to parse intent → route to agent
3. Add `--coordinator` flag to CLI
4. Modify `run_interactive()` to use coordinator when enabled

## Files to Create/Modify

### New Files:
1. `src/agent_factory/agents/coordinator_agent.py` - Main coordinator logic
2. `configs/blueprints/coordinator_agent.yaml` - Blueprint config

### Modify Files:
1. `src/agent_factory/factory/builder.py` - Add coordinator agent type
2. `cli.py` - Add coordinator mode option

## Next Steps

Would you like me to:
1. **Implement Option 3** (full OrchestratorAgent with Claude routing)
2. **Implement Option 2** (simpler CLI keyword routing)
3. **Create a prototype** to test the concept first
4. **Something else**?

## Key Design Decision

**Should OrchestratorAgent be an Agent?**

**YES** - Satisfies Agent protocol, can be used in pipelines, consistent architecture
**NO** - It's a meta-agent that delegates, doesn't directly take actions

My recommendation: **YES**, make it an Agent. It should:
- `think()` → parse command, decide routing
- `act()` → delegate to chosen agent, return their action

This way it fits naturally into the existing architecture.
