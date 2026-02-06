"Does the agent ingest?"                                                                                                                                                      
  No. The agent just says "I want to assimilate". The environment does the actual ingestion — it resolves URIs, talks to IOWarp over ZeroMQ, and writes to memcached.           
                                                                                                                                                                                
  "Who is the agent?"                                                                                                                                                           
  The agent is a Python class with two methods:                                                                                                                                 
  - think(observation) — reads text, returns a reasoning string                                                                                                                 
  - act(observation) — reads text, returns an Action(name="...", params={...})                                                                                                  
                                                                                                                                                                                
  Right now it's keyword matching (sees "load" → picks "assimilate"). Later it'll be an LLM.                                                                                    
                                                                                                                                                                                
  "How does it work?"                                                                                                                                                           
  Like a conversation:                                                                                                                                                          
                                                                                                                                                                                
  Round 1:                                                                                                                                                                      
    User says:         "Load files from folder::./data/sample_docs"                                                                                                             
    Agent reads it →   sees "load" → picks action "assimilate"                                                                                                                  
    Environment does → resolves URIs, sends to IOWarp, caches in memcached                                                                                                      
    Environment says → "Assimilated 3 files. Cached 3 blobs." reward=0.1                                                                                                        
                                                                                                                                                                                
  Round 2:                                                                                                                                                                      
    User says:         "Get blob: project_overview.md"                                                                                                                          
    Agent reads it →   sees "get" → picks action "retrieve"                                                                                                                     
    Environment does → checks memcached → HIT → returns the file                                                                                                                
    Environment says → "Retrieved from cache (hit)." reward=0.3                                                                                                                 
                                                                                                                                                                                
  Round 3:                                                                                                                                                                      
    User says:         "Delete tag: docs"                                                                                                                                       
    Agent reads it →   sees "delete" → picks action "prune"                                                                                                                     
    Environment does → tells IOWarp to delete, evicts from memcached                                                                                                            
    Environment says → "Pruned 1 tag." reward=0.05                                                                                                                              
                                                                                                                                                                                
  Agent = brain (picks what to do). Environment = hands (does the actual work with IOWarp + memcached).      
















   How AgentFactory Works — Step by Step                                                                                                                                         
                                                                                                                                                                                
  Let me explain the full picture based on the codebase:                                                                                                                        
                                                                                                                                                                                
  What You've Built So Far                                                                                                                                                      
                                                                                                                                                                                
  AgentFactory is not about creating a new type of AI agent from scratch. It's a framework for assembling, configuring, and running agents that interact with an I/O middleware 
  called IOWarp. Think of it as a factory assembly line:                                                                                                                        
                                                                                                                                                                                
  The Pipeline (what exists now)                                                                                                                                                
                                                                                                                                                                                
  1. CONFIGURE (Blueprint YAML)                                                                                                                                                 
     └── configs/blueprints/iowarp_agent.yaml                                                                                                                                   
         Defines: which agent type, cache settings, bridge endpoint, reward values                                                                                              
                                                                                                                                                                                
  2. BUILD (AgentBuilder)                                                                                                                                                       
     └── Reads the blueprint, wires up:                                                                                                                                         
         IOWarpClient → BlobCache → URIResolver → IOWarpEnvironment → Agent                                                                                                     
                                                                                                                                                                                
  3. INTERACT (Environment + Agent loop)                                                                                                                                        
     └── Agent receives Observation → thinks → chooses Action → Environment executes                                                                                            
         Actions: assimilate, query, retrieve, prune, list_blobs                                                                                                                
                                                                                                                                                                                
  4. TRACK (Trajectory + Rewards)                                                                                                                                               
     └── Every step is logged with a reward signal (+0.3 cache hit, -0.5 error, etc.)                                                                                           
                                                                                                                                                                                
  The Concrete Flow When You Run cli.py                                                                                                                                         
                                                                                                                                                                                
  Step 1: Infrastructure comes up                                                                                                                                               
    - Docker container runs IOWarp (the storage/context engine) + ZeroMQ bridge                                                                                                 
    - Memcached runs for caching                                                                                                                                                
                                                                                                                                                                                
  Step 2: You pick an agent type                                                                                                                                                
    - rule_based: keyword matching (no LLM needed)                                                                                                                              
    - llm: Ollama local LLM (llama3.2)                                                                                                                                          
    - claude: Claude API                                                                                                                                                        
                                                                                                                                                                                
  Step 3: You type natural language                                                                                                                                             
    "ingest the markdown files from folder::./data/sample_docs into tag: docs"                                                                                                  
                                                                                                                                                                                
  Step 4: Agent processes your instruction                                                                                                                                      
    - think(): "The user wants to ingest files..." (reasoning)                                                                                                                  
    - act():   Action(name="assimilate", params={src: "folder::...", dst: "docs"})                                                                                              
                                                                                                                                                                                
  Step 5: Environment executes the action                                                                                                                                       
    - URIResolver resolves folder:: → individual file:: URIs                                                                                                                    
    - IOWarpClient sends them to the bridge (ZeroMQ → Docker container)                                                                                                         
    - BlobCache stores copies in memcached (write-through caching)                                                                                                              
    - Returns StepResult with observation + reward                                                                                                                              
                                                                                                                                                                                
  Step 6: You can retrieve data back                                                                                                                                            
    "retrieve project_overview.md from tag docs"                                                                                                                                
    → Cache HIT (from memcached, fast) → reward +0.30                                                                                                                           
    → Cache MISS (from IOWarp bridge, slower) → reward +0.20                                                                                                                    
                                                                                                                                                                                
  Step 7: Track everything                                                                                                                                                      
    - Trajectory records all (action, result) pairs                                                                                                                             
    - Rewards accumulate: cache hits get higher rewards than misses                                                                                                             
                                                                                                                                                                                
  What Each Component Does                                                                                                                                                      
  ┌───────────────────────────────┬────────────────────────────────────────────────────────────────────┐                                                                        
  │           Component           │                                Role                                │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ IOWarp (Docker)               │ The actual storage/context engine — stores data, answers queries   │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ ZeroMQ Bridge                 │ JSON-RPC interface between Python and the IOWarp C++ engine        │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ Memcached                     │ Cache layer — avoids hitting IOWarp for repeated reads             │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ BlobCache                     │ Python wrapper around memcached with hit/miss tracking             │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ URIResolver                   │ Translates folder::, file::, mem:: URIs to what the bridge expects │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ IOWarpEnvironment             │ RL-style environment: reset(), step(action), observe(), rewards    │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ Agent (rule_based/llm/claude) │ Decides what action to take given observations                     │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ Trajectory                    │ Records all steps + rewards for evaluation                         │                                                                        
  ├───────────────────────────────┼────────────────────────────────────────────────────────────────────┤                                                                        
  │ Blueprint                     │ YAML config that tells the builder how to wire everything          │                                                                        
  └───────────────────────────────┴────────────────────────────────────────────────────────────────────┘                                                                        
  The Bigger Vision (build → config → train → evaluate → evolve → deploy)                                                                                                       
                                                                                                                                                                                
  What's implemented now covers build and config and basic interact. The reward signals in the trajectory are the foundation for the train → evaluate → evolve cycle:           
                                                                                                                                                                                
  1. Build — AgentBuilder.build(blueprint) ✅ done                                                                                                                              
  2. Config — Blueprint YAML + agent type selection ✅ done                                                                                                                     
  3. Interact/Run — Environment loop with think()/act()/step() ✅ done (demo.py, cli.py)                                                                                        
  4. Evaluate — Trajectory tracks rewards (cache hit +0.3, error -0.5) ✅ foundation done                                                                                       
  5. Train — Use accumulated trajectories to improve agent behavior (future work)                                                                                               
  6. Evolve — Swap agent types, tune hyperparams based on evaluation (future work)                                                                                              
  7. Deploy — Package and serve the best agent (future work)                                                                                                                    
                                                                                                                                                                                
  To Run and Demo                                                                                                                                                               
                                                                                                                                                                                
  # 1. Start infrastructure                                                                                                                                                     
  docker run -d --name af-iowarp --network host --shm-size 8g agentfactory_iowarp:latest                                                                                        
                                                                                                                                                                                
  # 2. Run the interactive CLI                                                                                                                                                  
  python3 cli.py                                                                                                                                                                
                                                                                                                                                                                
  # 3. Pick agent type (1 for rule_based, simplest)                                                                                                                             
  # 4. Try these commands:                                                                                                                                                      
  #    ingest the markdown files from folder::./data/sample_docs into tag: docs                                                                                                 
  #    query tag_pattern: docs                                                                                                                                                  
  #    retrieve project_overview.md from tag: docs                                                                                                                              
  #    status                                                                                                                                                                   
  #    history                                                                                                                                                                  
  #    quit                                                                                                                                                                     
                                                                                                                                                                                
  The demo.py runs a scripted version of this same flow end-to-end (no user input needed), while cli.py lets you drive it interactively.                                        
                                                              