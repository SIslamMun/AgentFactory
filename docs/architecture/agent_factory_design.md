# Agent Factory: Universal Agent Training & Deployment Platform

> **Goal**: Build a universal agent platform that can create, run, train, and continuously
> improve specialized agents for end-to-end scientific workflows.
>
> **Based on**: AgentGym (Xi et al., 2024) — paper 2406.04151
> Extensions beyond the paper are labeled **[Our Extension]** or **[From AgentGym-RL]** (paper 2509.08755).

---

## Table of Contents

- [1. Three-Layer Architecture](#1-three-layer-architecture)
- [2. Agent Factory — Layer 1](#2-agent-factory--layer-1)
- [3. Agent Templates — Layer 2](#3-agent-templates--layer-2)
- [4. AgentGym — Layer 3](#4-agentgym--layer-3)
  - [4.1 Architecture](#41-architecture)
  - [4.2 Three Environment Types](#42-three-environment-types)
  - [4.3 AgentEvol (Corrected)](#43-agentevol-corrected)
  - [4.4 Our Extensions](#44-our-extensions)
  - [4.5 Unified Training Pipeline](#45-unified-training-pipeline)
  - [4.6 AgentTraj Data Format](#46-agenttraj-data-format)
  - [4.7 Reward System](#47-reward-system)
  - [4.8 Fine-Tuning Infrastructure](#48-fine-tuning-infrastructure)
- [5. End-to-End Walkthrough](#5-end-to-end-walkthrough)
- [6. Core Protocols & Types](#6-core-protocols--types)
- [7. Package Structure](#7-package-structure)
- [8. Configuration Examples](#8-configuration-examples)
- [9. Technology Stack & Implementation Phases](#9-technology-stack--implementation-phases)
- [10. References](#10-references)

---

## 1. Three-Layer Architecture

**Diagram 1 — Master Architecture**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 1: AGENT FACTORY  (Central Management & Lifecycle)                  │
│                                                                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │   Registry   │  │  Scheduler   │  │  Monitoring   │  │  Lifecycle   │ │
│  │  blueprints  │  │  task queue  │  │  metrics      │  │  create →    │ │
│  │  instances   │  │  routing     │  │  alerts       │  │  train →     │ │
│  │  checkpoints │  │  priority    │  │  dashboards   │  │  deploy      │ │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘ │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   v
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 2: AGENT TEMPLATES  (Domain-Agnostic Reusable Blueprints)           │
│                                                                            │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  Blueprint = action_space + system_prompt + llm_backbone            │ │
│  │             + env_binding + reward_fn                                │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐           │
│  │ Processor  │ │ Researcher │ │ DevOps     │ │ Any Domain │           │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘           │
│  ┌──────────────────────────────────────────┐                           │
│  │  Orchestrator Agent (DAG coordination)   │                           │
│  └──────────────────────────────────────────┘                           │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   v
┌─────────────────────────────────────────────────────────────────────────────┐
│  LAYER 3: AGENTGYM  (Environments + Training + Evaluation)                 │
│                                                                            │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐       │
│  │  Fine-Tuning     │  │  Training /      │  │  Evaluation      │       │
│  │  Environments    │  │  Practice Envs   │  │  Environments    │       │
│  │  (expert demos)  │  │  (exploration)   │  │  (held-out)      │       │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘       │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  AgentEvol: BC (Phase 0) → Explore-Learn loop (M=4 iterations)     │ │
│  │  Default: reward-weighted SFT  |  Extensions: GRPO, DPO, PPO       │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │  Unsloth LoRA/QLoRA  |  safetensors  |  JSONL trajectories         │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Layer 1 — Agent Factory**: The central manager. Stores blueprints and trained agents in a
  registry, routes tasks via a scheduler, monitors performance, and manages the full lifecycle
  (create, configure, train, evaluate, deploy, evolve).

- **Layer 2 — Agent Templates**: Reusable blueprints that define what an agent CAN do.
  Each blueprint specifies an action space, system prompt, LLM backbone, environment binding,
  and reward function. An Orchestrator Agent coordinates multi-agent DAG pipelines.

- **Layer 3 — AgentGym**: Where agents learn. Contains three environment types (fine-tuning,
  training/practice, evaluation), the AgentEvol self-improvement method, trajectory storage,
  and fine-tuning infrastructure powered by Unsloth.

---

## 2. Agent Factory — Layer 1

### Agent Lifecycle

**Diagram 2 — Agent Lifecycle Flow**

```
┌──────────┐    ┌───────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  CREATE  │───>│ CONFIGURE │───>│  TRAIN   │───>│ EVALUATE │───>│  DEPLOY  │
│          │    │           │    │          │    │          │    │          │
│ Load     │    │ Set LLM,  │    │ BC +     │    │ Benchmark│    │ Serve in │
│ blueprint│    │ bind env, │    │ AgentEvol│    │ held-out │    │ prod,    │
│ from     │    │ load data │    │ (M iters)│    │ tasks    │    │ monitor, │
│ registry │    │           │    │          │    │          │    │ log      │
└──────────┘    └───────────┘    └──────────┘    └─────┬────┘    └──────────┘
                                                       │ if FAIL
                                                       v
                                                  ┌──────────┐
                                                  │ RE-TRAIN │
                                                  └──────────┘
```

- **CREATE**: Instantiate agent from blueprint. Assign unique ID. Status = CREATED.
- **CONFIGURE**: Bind LLM backend, system prompt, environment, load expert trajectories.
- **TRAIN**: Run AgentEvol (BC then explore-learn iterations) in AgentGym.
- **EVALUATE**: Run agent on held-out benchmark. If success >= threshold, PASS.
- **DEPLOY**: Register in active pool. Monitor continuously. If performance drops, re-train.

### Factory Internals

**Diagram 3 — Factory Components**

```
┌─────────────────────────────────────────────────────────────────┐
│                         AGENT FACTORY                           │
│                                                                 │
│  ┌─────────────────┐   ┌─────────────────┐                    │
│  │ AgentRegistry   │   │ AgentBuilder    │                    │
│  │                 │   │                 │                    │
│  │ .register()     │   │ .from_yaml()    │                    │
│  │ .get_blueprint()│   │ .instantiate()  │                    │
│  │ .list_agents()  │   │ .configure()    │                    │
│  └─────────────────┘   └─────────────────┘                    │
│                                                                 │
│  ┌─────────────────┐   ┌─────────────────┐                    │
│  │ VersionStore    │   │ MetricsCollector│                    │
│  │                 │   │                 │                    │
│  │ .save_ckpt()    │   │ .record()       │                    │
│  │ .load_ckpt()    │   │ .compare()      │                    │
│  │ .list_versions()│   │ .alert()        │                    │
│  └─────────────────┘   └─────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Agent Templates — Layer 2

### Blueprint Structure

**Diagram 4 — Blueprint Anatomy**

```
┌──────────────────────────────────────────────────────┐
│                   AGENT BLUEPRINT                     │
│                                                      │
│  name: "processor_agent"                             │
│  description: "Document processing specialist"       │
│                                                      │
│  ┌────────────────────────────────────────────────┐ │
│  │ Action Space                                    │ │
│  │   chunk_only | process_low | process_medium     │ │
│  │   process_high | incremental                    │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ System Prompt                                   │ │
│  │   "You are a document processing expert..."     │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ LLM Backbone                                    │ │
│  │   model: llama3.1:8b  backend: ollama | vllm   │ │
│  └────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────┐ │
│  │ Environment Binding: processor_env              │ │
│  │ Reward Function: weighted composite             │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────┘
```

**Agent Types**:
- **PromptAgent**: API-based (zero/few-shot). No trainable weights. Uses LLM directly.
- **LoRAAgent**: Trainable weights via Unsloth LoRA. Loads adapter on top of frozen base model.

**Example Domains** (any domain can define its own):

| Domain | Actions | Reward |
|--------|---------|--------|
| Processor | chunk, process_low/med/high | quality + speed |
| Researcher | deep_research, extract_cites | citation count + quality |
| DevOps | deploy, monitor, scale | uptime + latency |
| Data Analysis | query_sql, visualize, report | accuracy + completeness |

### Orchestrator / DAG Pipeline

**Diagram 5 — Pipeline Coordination**

```
┌──────────────────────────────────────────────────────────────┐
│                  ORCHESTRATOR AGENT                           │
│                                                              │
│  User: "Research HDF5 and build RAG database"                │
│                                                              │
│  ┌────────────┐    ┌────────────┐    ┌────────────┐        │
│  │ Research   │───>│ Parser     │───>│ Ingestor   │──┐     │
│  │ Agent      │    │ Agent      │    │ Agent      │  │     │
│  └────────────┘    └────────────┘    └────────────┘  │     │
│                                                       v     │
│                                              ┌────────────┐ │
│                                              │ Processor  │ │
│                                              │ Agent      │ │
│                                              └────────────┘ │
│                                                              │
│  Capabilities:                                               │
│  - Task decomposition into subtasks                          │
│  - Agent delegation based on capabilities                    │
│  - Dependency management (DAG execution)                     │
│  - Result aggregation across pipeline steps                  │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. AgentGym — Layer 3

This is the core training layer. It implements the AgentGym paper's decoupled architecture,
three environment types, and the corrected AgentEvol algorithm.

### 4.1 Architecture

**Diagram 6 — AgentGym Client-Server Architecture**

```
┌─────────────────────────────────────────────────────────────────┐
│                      AGENTGYM ARCHITECTURE                      │
│                  (Decoupled Client-Server Design)               │
│                                                                 │
│  ┌──────────────────────────────┐                              │
│  │      AgentController         │                              │
│  │  (coordinates agent with     │                              │
│  │   multiple EnvServers)       │                              │
│  │                              │                              │
│  │  - Manages single policy     │                              │
│  │    across ALL environments   │                              │
│  │  - Routes agent to envs      │                              │
│  │  - Collects trajectories     │                              │
│  └──────────┬───────────────────┘                              │
│             │                                                   │
│     ┌───────┴────────┬──────────────────┐                      │
│     v                v                  v                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────┐                │
│  │EnvServer │  │EnvServer │  │ EnvServer    │                │
│  │(Proc)    │  │(Research)│  │ (Parser)     │                │
│  │          │  │          │  │              │                │
│  │ /reset   │  │ /reset   │  │ /reset       │                │
│  │ /step    │  │ /step    │  │ /step        │                │
│  │ /observe │  │ /observe │  │ /observe     │                │
│  │ /actions │  │ /actions │  │ /actions     │                │
│  └──────────┘  └──────────┘  └──────────────┘                │
│                                                                 │
│  DUAL MODE:                                                    │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │ LocalEnvAdapter  (in-process, default) — fast, debug    │  │
│  │ RemoteEnvClient  (HTTP, distributed)   — scalable       │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                 │
│  Same environment code works in both modes.                    │
│  EnvClient provides unified Python interface for either.       │
└─────────────────────────────────────────────────────────────────┘
```

Key paper concepts:
- **EnvServer**: HTTP microservice wrapping a domain tool. Endpoints: `/reset`, `/step`,
  `/observation`, `/available_actions`.
- **EnvClient**: Python wrapper giving a unified `env.reset()` / `env.step()` interface.
- **AgentController**: Coordinates one agent policy with multiple environments simultaneously.
- **Single policy**: One model is trained across ALL environments (not per-env models).

### 4.2 Three Environment Types

**Diagram 7 — Environment Types**

```
┌─────────────────────────────────────────────────────────────────┐
│              THREE ENVIRONMENT TYPES                             │
│          (Same protocol, different usage context)                │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  FINE-TUNING ENVIRONMENTS                                │   │
│  │                                                          │   │
│  │  Purpose: Collect expert demonstrations (AgentTraj)      │   │
│  │  Usage:   Experts run tasks, trajectories are logged     │   │
│  │  Output:  AgentTraj dataset (JSONL) for Behavioral       │   │
│  │           Cloning (Phase 0)                              │   │
│  │  Mode:    RECORD                                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  TRAINING / PRACTICE ENVIRONMENTS                        │   │
│  │                                                          │   │
│  │  Purpose: Agent explores and generates trajectories      │   │
│  │  Usage:   During AgentEvol EXPLORE phase (iterations     │   │
│  │           1..M). Agent acts, gets rewards, trajectories  │   │
│  │           scored and filtered.                           │   │
│  │  Output:  Exploration trajectories for LEARN phase       │   │
│  │  Mode:    TRAIN                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  EVALUATION ENVIRONMENTS                                 │   │
│  │                                                          │   │
│  │  Purpose: Benchmark agent on held-out tasks              │   │
│  │  Usage:   Agent tested but NOT trained. Produces metrics │   │
│  │           (success rate, avg reward, steps, wall time).  │   │
│  │  Output:  Performance report                             │   │
│  │  Mode:    INFERENCE                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  All three share the same Environment Protocol:                │
│    reset(task) -> observation                                  │
│    step(action) -> StepResult(obs, reward, done, info)         │
│    get_observation() -> current state                          │
│    available_actions() -> list of valid actions                 │
└─────────────────────────────────────────────────────────────────┘
```

### 4.3 AgentEvol (Corrected)

> **Critical correction**: The original AgentGym paper (2406.04151) describes AgentEvol as
> BC (one-time) followed by an iterative **explore-learn loop** (M=4 iterations). There is
> NO "Self-Critique" stage in the paper. The default training method is **reward-weighted SFT**
> derived from a variational inference objective — NOT GRPO/DPO/PPO.

**Diagram 8 — AgentEvol Overview (Paper-Accurate)**

```
┌─────────────────────────────────────────────────────────────────┐
│                    AGENTEVOL (from paper 2406.04151)            │
│                                                                 │
│  PHASE 0 (one-time): BEHAVIORAL CLONING                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                                                          │   │
│  │  AgentTraj dataset ──> SFT via Unsloth LoRA ──> π_bc    │   │
│  │  (expert demos)        (cross-entropy loss)    (policy)  │   │
│  │                                                          │   │
│  │  Result: Agent imitates expert behavior                  │   │
│  └─────────────────────────────┬───────────────────────────┘   │
│                                 │                               │
│                                 v                               │
│  PHASE 1..M (iterative, M=4): EXPLORE-LEARN LOOP               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                                                          │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │ EXPLORE                                           │   │   │
│  │  │                                                   │   │   │
│  │  │  Deploy current policy π_i across ALL envs        │   │   │
│  │  │  For each instruction:                            │   │   │
│  │  │    Generate K=3 trajectories (different rollouts) │   │   │
│  │  │    Score each with reward function                │   │   │
│  │  │    Filter: keep trajectories with reward > τ      │   │   │
│  │  └────────────────────┬──────────────────────────────┘   │   │
│  │                        │                                  │   │
│  │                        v                                  │   │
│  │  ┌──────────────────────────────────────────────────┐   │   │
│  │  │ LEARN                                             │   │   │
│  │  │                                                   │   │   │
│  │  │  Merge new trajectories with ORIGINAL BC data     │   │   │
│  │  │  (NOT previous iteration — ablation shows this    │   │   │
│  │  │   is critical to prevent catastrophic forgetting) │   │   │
│  │  │                                                   │   │   │
│  │  │  Train via reward-weighted SFT:                   │   │   │
│  │  │    L = -Σ r(τ) · log π(a|s)                      │   │   │
│  │  │  (derived from variational inference objective)   │   │   │
│  │  │                                                   │   │   │
│  │  │  Update policy: π_i → π_{i+1}                    │   │   │
│  │  └────────────────────┬──────────────────────────────┘   │   │
│  │                        │                                  │   │
│  │                        v                                  │   │
│  │                   [Repeat M times]                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  KEY PAPER DETAILS:                                            │
│  • K=3 trajectory samples per instruction                      │
│  • Data merging with ORIGINAL BC data each iteration           │
│  • Reward-weighted SFT from variational inference objective    │
│  • Single policy trained across ALL environments simultaneously│
│  • M=4 iterations in paper experiments                         │
└─────────────────────────────────────────────────────────────────┘
```

**Diagram 9 — Single Iteration Detail**

```
┌─────────────────────────────────────────────────────────────────┐
│              AGENTEVOL: SINGLE ITERATION (i)                    │
│                                                                 │
│  Current policy: π_i                                           │
│                                                                 │
│  ┌─ EXPLORE ──────────────────────────────────────────────┐    │
│  │                                                         │    │
│  │  For each instruction in task pool:                     │    │
│  │                                                         │    │
│  │    instruction: "Process 500 markdown files"            │    │
│  │                                                         │    │
│  │    ┌──────────┐  ┌──────────┐  ┌──────────┐           │    │
│  │    │ Rollout 1│  │ Rollout 2│  │ Rollout 3│  (K=3)    │    │
│  │    │ r = 0.92 │  │ r = 0.45 │  │ r = 0.87 │           │    │
│  │    │ KEEP     │  │ DISCARD  │  │ KEEP     │           │    │
│  │    └──────────┘  └──────────┘  └──────────┘           │    │
│  │                                                         │    │
│  │  Filter threshold: τ = 0.7                              │    │
│  │  Output: D_explore (high-reward trajectories)           │    │
│  └─────────────────────────────────┬───────────────────────┘    │
│                                     │                            │
│                                     v                            │
│  ┌─ LEARN ────────────────────────────────────────────────┐    │
│  │                                                         │    │
│  │  ┌───────────────┐     ┌───────────────┐               │    │
│  │  │ D_explore     │     │ D_bc          │               │    │
│  │  │ (this iter)   │  +  │ (ORIGINAL BC  │               │    │
│  │  │               │     │  data, fixed) │               │    │
│  │  └───────┬───────┘     └───────┬───────┘               │    │
│  │          └─────────┬───────────┘                        │    │
│  │                    v                                     │    │
│  │          ┌─────────────────┐                            │    │
│  │          │ Reward-Weighted │                            │    │
│  │          │ SFT Training    │                            │    │
│  │          │                 │                            │    │
│  │          │ L = -Σ r(τ) ·  │                            │    │
│  │          │   log π(a|s)   │                            │    │
│  │          └────────┬────────┘                            │    │
│  │                   v                                      │    │
│  │          Updated policy: π_{i+1}                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─ EVALUATE (optional, every N iterations) ──────────────┐    │
│  │  Run π_{i+1} on held-out benchmark → log metrics        │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 Our Extensions

These are additions beyond the original AgentGym paper. Each is clearly labeled.

**Diagram 10 — [Our Extension] Self-Critique**

```
┌─────────────────────────────────────────────────────────────────┐
│              [OUR EXTENSION] SELF-CRITIQUE                      │
│                                                                 │
│  Added after each EXPLORE phase (before LEARN):                │
│                                                                 │
│  ┌─ EXPLORE output ───────────────────────────────────┐        │
│  │  Successful trajectories (r > τ)                    │        │
│  │  Failed trajectories     (r < τ)                    │        │
│  └────────────────────┬────────────────────────────────┘        │
│                        v                                         │
│  ┌─ SELF-CRITIQUE ────────────────────────────────────┐        │
│  │                                                     │        │
│  │  For each failure:                                  │        │
│  │    1. Agent analyzes: "What went wrong?"            │        │
│  │    2. Find similar successful trajectory            │        │
│  │    3. Contrast: failure vs success                  │        │
│  │    4. Generate improvement hypothesis               │        │
│  │                                                     │        │
│  │  Example:                                           │        │
│  │    Failure: "Used high profile on 10k files→timeout"│        │
│  │    Success: "Used medium profile on 8k files→0.89"  │        │
│  │    Hypothesis: "If files > 5000, prefer medium"     │        │
│  │                                                     │        │
│  │  Output: critique insights fed into LEARN phase     │        │
│  │          as additional training signal               │        │
│  └─────────────────────────────────────────────────────┘        │
│                                                                 │
│  This is NOT from the original paper. We add it to accelerate  │
│  learning from failures via explicit contrastive reasoning.     │
└─────────────────────────────────────────────────────────────────┘
```

**Diagram 11 — [From AgentGym-RL] Alternative Training Methods**

```
┌─────────────────────────────────────────────────────────────────┐
│         [FROM AGENTGYM-RL] ALTERNATIVE TRAINING METHODS         │
│         (Paper 2509.08755 — follow-up to AgentGym)              │
│                                                                 │
│  Instead of reward-weighted SFT, can substitute:               │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │ GRPO         │  │ DPO          │  │ PPO          │         │
│  │              │  │              │  │              │         │
│  │ Group        │  │ Direct       │  │ Proximal     │         │
│  │ Relative     │  │ Preference   │  │ Policy       │         │
│  │ Policy Opt.  │  │ Optimization │  │ Optimization │         │
│  │              │  │              │  │              │         │
│  │ Generate N   │  │ Preferred /  │  │ Reward model │         │
│  │ responses,   │  │ rejected     │  │ + clipped    │         │
│  │ compare      │  │ trajectory   │  │ surrogate    │         │
│  │ within group │  │ pairs        │  │ objective    │         │
│  │              │  │              │  │              │         │
│  │ No reward    │  │ No reward    │  │ Requires     │         │
│  │ model needed │  │ model needed │  │ reward model │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
│                                                                 │
│  Also available: RLOO, REINFORCE++                             │
│                                                                 │
│  DEFAULT (paper):  reward-weighted SFT                         │
│  ALTERNATIVES:     GRPO > DPO > PPO (ordered by simplicity)   │
│                                                                 │
│  All integrate into the LEARN phase of AgentEvol.              │
│  Swap via training config: method: reward_weighted_sft | grpo  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.5 Unified Training Pipeline

Training is ONE continuous process. BC is Phase 0 of AgentEvol, not a separate system.

**Diagram 12 — Unified Training Pipeline**

```
┌─────────────────────────────────────────────────────────────────┐
│                  UNIFIED TRAINING PIPELINE                       │
│                                                                 │
│  Expert Demonstrations                                         │
│       │                                                         │
│       v                                                         │
│  ┌─────────────────────────────────────┐                       │
│  │  AgentTraj Dataset (JSONL)          │                       │
│  │  {from: "human"/"gpt", loss: T/F}  │                       │
│  └──────────────────┬──────────────────┘                       │
│                      │                                          │
│                      v                                          │
│  ┌─────────────────────────────────────┐                       │
│  │  Phase 0: Behavioral Cloning       │                       │
│  │  (one-time SFT via Unsloth LoRA)   │                       │
│  │                                     │                       │
│  │  Input:  AgentTraj (expert demos)   │                       │
│  │  Output: π_bc (base policy)         │                       │
│  │  Checkpoint: ckpt/agent/phase0_bc/  │                       │
│  └──────────────────┬──────────────────┘                       │
│                      │                                          │
│                      v                                          │
│  ┌─────────────────────────────────────┐                       │
│  │  Phase 1..M: AgentEvol Loop (M=4)  │                       │
│  │                                     │                       │
│  │  ┌─────────────────────────────┐   │                       │
│  │  │ EXPLORE                      │   │                       │
│  │  │  Deploy π_i across all envs  │   │                       │
│  │  │  K=3 rollouts per task       │   │                       │
│  │  │  Filter by reward threshold  │   │                       │
│  │  └──────────────┬──────────────┘   │                       │
│  │                  v                   │                       │
│  │  ┌─────────────────────────────┐   │                       │
│  │  │ [Our Extension] CRITIQUE    │   │                       │
│  │  │  Analyze failures (optional)│   │                       │
│  │  └──────────────┬──────────────┘   │                       │
│  │                  v                   │                       │
│  │  ┌─────────────────────────────┐   │                       │
│  │  │ LEARN                        │   │                       │
│  │  │  Merge D_explore + D_bc      │   │                       │
│  │  │  Train: reward-weighted SFT  │   │                       │
│  │  │  (or GRPO/DPO/PPO alt.)     │   │                       │
│  │  │  π_i → π_{i+1}              │   │                       │
│  │  └──────────────┬──────────────┘   │                       │
│  │                  v                   │                       │
│  │  ┌─────────────────────────────┐   │                       │
│  │  │ EVALUATE (every N iters)    │   │                       │
│  │  │  Held-out benchmark metrics │   │                       │
│  │  └──────────────┬──────────────┘   │                       │
│  │                  │                   │                       │
│  │           [Repeat M times]          │                       │
│  └──────────────────┬──────────────────┘                       │
│                      │                                          │
│                      v                                          │
│  ┌─────────────────────────────────────┐                       │
│  │  Output: Trained LoRA adapter       │                       │
│  │  Format: safetensors (no pickle)    │                       │
│  │  Checkpoint: ckpt/agent/evolved/    │                       │
│  └─────────────────────────────────────┘                       │
└─────────────────────────────────────────────────────────────────┘
```

### 4.6 AgentTraj Data Format

All training data uses a conversation format stored as JSONL (never pickle):

```json
{
  "conversations": [
    {
      "from": "human",
      "loss": false,
      "value": "You are in processor_env. Files: 1000 markdown in ./docs/. Task: process for RAG."
    },
    {
      "from": "gpt",
      "loss": true,
      "value": "Thought: Large dataset, 1000 files. Medium quality balances speed and retrieval.\nAction: process_medium\nObservation: 7690 chunks created, search quality: 0.89"
    },
    {
      "from": "human",
      "loss": false,
      "value": "Result: 7690 chunks, quality 0.89, time 45s. Choose next action."
    },
    {
      "from": "gpt",
      "loss": true,
      "value": "Thought: Quality is 0.89 which exceeds threshold. Task complete.\nAction: done"
    }
  ],
  "metadata": {
    "environment": "processor_env",
    "total_reward": 0.89,
    "success": true,
    "trajectory_id": "traj_001"
  }
}
```

- `from: "human"` = environment observations/prompts. `loss: false` (don't train on these).
- `from: "gpt"` = agent responses. `loss: true` (train on these).
- Storage: `trajectories/*.jsonl` (appendable, git-friendly).

### 4.7 Reward System

**Diagram 13 — Reward System**

```
┌─────────────────────────────────────────────────────────────────┐
│                       REWARD SYSTEM                             │
│                                                                 │
│  ┌─ OPTION A: Composable Reward Functions (default) ────────┐ │
│  │                                                           │ │
│  │  class WeightedReward(RewardFunction):                    │ │
│  │      weights = {                                          │ │
│  │          "success":    0.4,                               │ │
│  │          "quality":    0.3,                               │ │
│  │          "efficiency": 0.2,                               │ │
│  │          "no_errors":  0.1                                │ │
│  │      }                                                    │ │
│  │                                                           │ │
│  │  reward = Σ weight_i × component_i                        │ │
│  │                                                           │ │
│  │  Domain-specific: each env defines its own components.    │ │
│  │  Used by: reward-weighted SFT, GRPO, DPO                 │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌─ OPTION B: Learned Reward Model (for PPO) ──────────────┐ │
│  │                                                           │ │
│  │  Labeled trajectories ──> Train classifier ──> RewardModel│ │
│  │                                                           │ │
│  │  Input:  (instruction, trajectory_steps)                  │ │
│  │  Output: reward_score (0.0 to 1.0)                        │ │
│  │                                                           │ │
│  │  Training data:                                           │ │
│  │    Expert success → 1.0  |  Partial → 0.5  |  Fail → 0.0│ │
│  │                                                           │ │
│  │  Used by: PPO (per-step reward signal)                    │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  RewardFunction Protocol:                                      │
│    score(trajectory) -> float                                  │
│    score_step(step) -> float  (optional, for PPO)              │
└─────────────────────────────────────────────────────────────────┘
```

### 4.8 Fine-Tuning Infrastructure

**Unsloth** is the primary fine-tuning engine:

| Feature | Value |
|---------|-------|
| Speed | 2x faster than standard HuggingFace |
| VRAM | 50% less (8B model in ~6GB with QLoRA 4-bit) |
| Method | LoRA / QLoRA adapters on frozen base model |
| Output | safetensors format (secure, no pickle) |
| Models | Llama 3.1, Mistral, Gemma 2, Phi-3, Qwen 2.5 |

Training config:

```yaml
unsloth:
  base_model: meta-llama/Meta-Llama-3.1-8B
  max_seq_length: 4096
  load_in_4bit: true             # QLoRA mode
  lora_r: 16                     # LoRA rank
  lora_alpha: 16
  lora_dropout: 0.0
  target_modules:
    - q_proj
    - k_proj
    - v_proj
    - o_proj
    - gate_proj
    - up_proj
    - down_proj
  save_format: safetensors       # Never pickle
```

---

## 5. End-to-End Walkthrough

**Diagram 14 — Complete Agent Journey**

```
┌─────────────────────────────────────────────────────────────────┐
│             END-TO-END WALKTHROUGH: Processor Agent              │
│                                                                 │
│  1. CREATE                                                      │
│     factory.create_agent("processor")                          │
│     -> Load blueprint from registry                            │
│     -> Instantiate with unique ID, empty memory                │
│     -> Status: CREATED                                         │
│                           │                                     │
│                           v                                     │
│  2. CONFIGURE                                                   │
│     -> Bind LLM: ollama / llama3.1:8b                          │
│     -> Bind env: processor_env                                 │
│     -> Load 50 expert trajectories                             │
│     -> Status: CONFIGURED                                      │
│                           │                                     │
│                           v                                     │
│  3. TRAIN                                                       │
│     Phase 0: BC on 50 expert trajectories                      │
│       -> SFT via Unsloth LoRA -> π_bc                          │
│     Phase 1..4: AgentEvol iterations                           │
│       -> EXPLORE: K=3 rollouts across envs                     │
│       -> LEARN: merge + reward-weighted SFT                    │
│       -> π_bc → π_1 → π_2 → π_3 → π_4                        │
│     -> Status: TRAINED                                         │
│                           │                                     │
│                           v                                     │
│  4. EVALUATE                                                    │
│     -> Run on 100 held-out benchmark tasks                     │
│     -> Results:                                                │
│                                                                 │
│        ┌─────────────────┬─────────┬──────────┬──────────┐     │
│        │ Version         │ Success │ Avg Time │ Quality  │     │
│        ├─────────────────┼─────────┼──────────┼──────────┤     │
│        │ Prompt baseline │ 55%     │ 180s     │ 0.65     │     │
│        │ After BC        │ 72%     │ 145s     │ 0.78     │     │
│        │ After Iter 4    │ 89%     │ 118s     │ 0.91     │     │
│        └─────────────────┴─────────┴──────────┴──────────┘     │
│                                                                 │
│     -> 89% >= 85% threshold -> PASS                            │
│     -> Status: EVALUATED                                       │
│                           │                                     │
│                           v                                     │
│  5. DEPLOY                                                      │
│     -> Register in active agent pool                           │
│     -> Production inference with monitoring                    │
│     -> Every execution logged as trajectory                    │
│     -> If performance drops -> factory.evolve_agent()          │
│     -> Status: DEPLOYED                                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Core Protocols & Types

**Diagram 15 — Protocol Hierarchy**

```
┌─────────────────────────────────────────────────────────────────┐
│                   CORE PROTOCOLS (PEP 544)                      │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Environment Protocol                                     │   │
│  │                                                          │   │
│  │  reset(task: TaskSpec) -> Observation                    │   │
│  │  step(action: Action) -> StepResult                     │   │
│  │  get_observation() -> Observation                       │   │
│  │  available_actions() -> list[Action]                    │   │
│  │  close() -> None                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Agent Protocol                                           │   │
│  │                                                          │   │
│  │  think(observation: Observation) -> str                  │   │
│  │  act(thought: str) -> Action                            │   │
│  │  set_mode(mode: AgentMode) -> None                      │   │
│  │                                                          │   │
│  │  AgentMode = TRAIN | INFERENCE                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ LLMBackend Protocol                                      │   │
│  │                                                          │   │
│  │  generate(messages: list[dict], **kwargs) -> str         │   │
│  │  Implementations: OllamaBackend, VLLMBackend,           │   │
│  │                   OpenAICompatBackend                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ RewardFunction Protocol                                  │   │
│  │                                                          │   │
│  │  score(trajectory: Trajectory) -> float                  │   │
│  │  score_step(step: Step) -> float   # optional           │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  CORE DATA TYPES (frozen dataclasses, JSON-serializable):      │
│                                                                 │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐        │
│  │ TaskSpec      │ │ Observation   │ │ Action        │        │
│  │               │ │               │ │               │        │
│  │ .task_id      │ │ .text         │ │ .name         │        │
│  │ .instruction  │ │ .structured   │ │ .params       │        │
│  │ .env_id       │ │ .metadata     │ │ .metadata     │        │
│  └───────────────┘ └───────────────┘ └───────────────┘        │
│                                                                 │
│  ┌───────────────┐ ┌───────────────────────────────────┐      │
│  │ StepResult    │ │ Trajectory                         │      │
│  │               │ │                                    │      │
│  │ .observation  │ │ .trajectory_id                     │      │
│  │ .reward       │ │ .steps: list[Step]                 │      │
│  │ .done         │ │ .total_reward                      │      │
│  │ .info         │ │ .success                           │      │
│  └───────────────┘ │ .metadata                          │      │
│                     └───────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 7. Package Structure

**Diagram 16 — Source Tree**

```
src/agent_factory/
├── __init__.py
│
├── core/                           # Shared types and protocols
│   ├── types.py                    # TaskSpec, Observation, Action, StepResult, Trajectory
│   ├── protocols.py                # Environment, Agent, LLMBackend, RewardFn protocols
│   └── errors.py                   # Custom exceptions
│
├── environments/                   # Environment layer
│   ├── base_env.py                 # Base environment + ToolRunner (safe subprocess)
│   ├── env_server.py               # FastAPI server (remote mode: /reset, /step, etc.)
│   ├── env_client.py               # HTTP client (remote) + LocalEnvAdapter (in-process)
│   └── rewards.py                  # Composable reward functions + RewardFunction protocol
│
├── agents/                         # Agent layer
│   ├── react_loop.py               # Base ReAct agent (think-act-observe loop)
│   ├── prompt_agent.py             # PromptAgent: API-based (zero/few-shot)
│   ├── lora_agent.py               # LoRAAgent: trainable weights (Unsloth-backed)
│   ├── memory.py                   # Structured experience buffer
│   └── llm_backends/               # LLM provider abstractions
│       ├── ollama.py
│       ├── vllm_backend.py
│       └── openai_compat.py
│
├── training/                       # Training infrastructure
│   ├── agentevol/                  # AgentEvol method
│   │   ├── evolver.py              # Main orchestrator: Phase 0 (BC) + Phase 1..M loop
│   │   ├── bc.py                   # Behavioral Cloning (Phase 0, SFT)
│   │   ├── explorer.py             # EXPLORE: K-sampling, scoring, filtering
│   │   └── self_critique.py        # [Our Extension] failure analysis + improvement
│   ├── methods/                    # Training method implementations
│   │   ├── reward_weighted_sft.py  # [Paper] default: reward-weighted SFT
│   │   ├── grpo.py                 # [AgentGym-RL] Group Relative Policy Optimization
│   │   ├── dpo.py                  # [AgentGym-RL] Direct Preference Optimization
│   │   └── ppo.py                  # [AgentGym-RL] Proximal Policy Optimization
│   ├── trajectory_store.py         # JSONL trajectory storage
│   ├── trajectory_logger.py        # Capture trajectories during runs
│   ├── evaluator.py                # Benchmark runner + metrics
│   └── curriculum.py               # Task difficulty scheduling
│
├── factory/                        # Agent Factory (Layer 1)
│   ├── registry.py                 # Blueprint + trained agent registry
│   ├── builder.py                  # Instantiate agents from YAML blueprints
│   ├── versioning.py               # Checkpoint management
│   └── metrics.py                  # Performance tracking + comparison
│
├── orchestration/                  # Multi-agent coordination
│   ├── dag.py                      # DAG pipeline definition
│   ├── executor.py                 # Pipeline execution engine
│   └── messages.py                 # Inter-agent message types
│
└── cli.py                          # CLI entry point
```

---

## 8. Configuration Examples

### Agent Blueprint (YAML)

```yaml
# configs/blueprints/processor.yaml
name: processor_agent
description: "Document processing specialist"
type: lora                       # "prompt" (API-based) or "lora" (trainable)

llm:
  backend: ollama
  model: llama3.1:8b
  temperature: 0.3
  max_tokens: 2048

system_prompt: |
  You are a document processing expert. Think step-by-step:
  1. Assess document type and volume
  2. Choose appropriate quality profile
  3. Execute and verify results

environment: processor_env

reward:
  type: weighted_composite
  weights:
    success: 0.4
    chunk_quality: 0.3
    efficiency: 0.2
    no_errors: 0.1
```

### Environment (YAML)

```yaml
# configs/environments/processor_env.yaml
name: processor_env
description: "Training environment for document processor"

tool:
  command: ["uv", "run", "processor", "process"]   # shell=False
  timeout_seconds: 600

actions:
  chunk_only:
    flags: ["--chunk-only"]
    description: "Fast chunking without embedding"
  process_low:
    flags: ["--text-profile", "low"]
    description: "Low quality (fastest)"
  process_medium:
    flags: ["--text-profile", "medium"]
    description: "Balanced quality/speed"
  process_high:
    flags: ["--text-profile", "high"]
    description: "Best quality (slowest)"
```

### Training (YAML)

```yaml
# configs/training/agentevol_processor.yaml
agent_blueprint: processor_agent
environments: [processor_env]

# ── Unsloth / LoRA (shared across phases) ──
unsloth:
  base_model: meta-llama/Meta-Llama-3.1-8B
  max_seq_length: 4096
  load_in_4bit: true
  lora_r: 16
  lora_alpha: 16
  target_modules: [q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj]
  save_format: safetensors

# ── Phase 0: Behavioral Cloning ──
phase_0_bc:
  expert_trajectories: trajectories/expert/processor/*.jsonl
  epochs: 10
  lr: 2e-5
  batch_size: 4
  gradient_accumulation_steps: 4
  output_dir: checkpoints/processor/phase0_bc/

# ── Phase 1..M: AgentEvol Loop ──
agentevol:
  M: 4                              # Number of iterations
  K: 3                              # Trajectories per instruction
  reward_threshold: 0.7             # τ for filtering

  # Default method (from paper)
  method: reward_weighted_sft

  # Alternative methods [From AgentGym-RL]:
  # method: grpo
  # grpo:
  #   group_size: 4
  #   kl_coeff: 0.05

  merge_with_bc_data: true           # Critical: merge with ORIGINAL BC data
  lr: 2e-5
  epochs_per_iteration: 3
  output_dir: checkpoints/processor/evolved/

# ── [Our Extension] Self-Critique ──
self_critique:
  enabled: true
  critique_llm: ollama/llama3.1:8b
  failure_threshold: 0.5

# ── Evaluation ──
evaluation:
  benchmark: configs/benchmarks/processor_benchmark.jsonl
  run_every_n_iterations: 1
  metrics: [success_rate, avg_reward, avg_steps, wall_time]
```

### Pipeline (YAML)

```yaml
# configs/pipelines/full_rag_pipeline.yaml
pipeline_id: full_rag
description: "Complete Research -> RAG pipeline"

steps:
  - name: research
    agent: researcher
    inputs: { topic: "${pipeline.topic}" }
    outputs: [report_path]

  - name: parse
    agent: parser
    inputs: { report: "${research.report_path}" }
    outputs: [papers_dir]
    depends_on: [research]

  - name: ingest
    agent: ingestor
    inputs: { input_dir: "${parse.papers_dir}" }
    outputs: [markdown_dir]
    depends_on: [parse]

  - name: process
    agent: processor
    inputs: { workspace: "${ingest.markdown_dir}" }
    outputs: [lancedb_path]
    depends_on: [ingest]

retry_policy:
  max_retries: 3
  backoff: exponential
```

---

## 9. Technology Stack & Implementation Phases

### Technology Stack

| Component | Technology | Why |
|-----------|-----------|-----|
| Language | Python 3.11+ | ML ecosystem |
| Project mgmt | uv + hatchling | Modern, fast |
| CLI | Click + Rich | Clean output |
| Config | YAML (ruamel.yaml) | Human-readable |
| HTTP env services | FastAPI + httpx | AgentGym pattern |
| LLM (unified) | litellm | Any provider |
| LLM (local) | Ollama, vLLM | Local inference |
| Fine-tuning | Unsloth | Fast LoRA, consumer GPU |
| RL training | trl (HuggingFace) | GRPO, DPO, PPO [AgentGym-RL] |
| Model weights | safetensors | Secure (no pickle) |
| Trajectories | JSONL | Appendable, readable |
| Testing | pytest | Standard |

### Implementation Phases

**Phase 1: Foundation**
- Core types + protocols (`core/`)
- PromptAgent with ReAct loop (`agents/`)
- One environment: ProcessorEnv with safe ToolRunner (`environments/`)
- Trajectory logger + JSONL store (`training/`)
- Basic factory: create agent from YAML, run in env (`factory/`)
- CLI: `agent-factory run --blueprint processor --task "..."`

**Phase 2: Behavioral Cloning + Evaluation**
- Collect expert trajectories (20-50 per environment)
- BehavioralCloning with Unsloth LoRA SFT (`training/agentevol/bc.py`)
- LoRAAgent that loads trained adapter (`agents/lora_agent.py`)
- Evaluator + benchmark tasks (`training/evaluator.py`)
- Compare: BC agent vs prompt-only baseline

**Phase 3: AgentEvol Loop**
- Explorer with K-sampling across environments (`training/agentevol/explorer.py`)
- Reward-weighted SFT (`training/methods/reward_weighted_sft.py`)
- Data merging with original BC data
- AgentEvol orchestrator: Phase 0 + iterations (`training/agentevol/evolver.py`)
- Build remaining environments (Research, Parser, Ingestor)

**Phase 4: Extensions + Orchestration**
- Self-Critique engine [Our Extension] (`training/agentevol/self_critique.py`)
- GRPO/DPO/PPO trainers [From AgentGym-RL] (`training/methods/`)
- Orchestrator agent for multi-agent pipelines (`orchestration/`)
- HTTP environment services (`environments/env_server.py`)
- Curriculum scheduler (`training/curriculum.py`)

### What NOT to Build

- Agent marketplace (premature)
- Custom distributed training framework (use existing: Unsloth, trl)
- GUI dashboard (CLI-first)
- Multi-GPU sharding (single-GPU with QLoRA is sufficient for 8B models)

### Verification Plan

- [ ] Each concept appears exactly once (grep for duplicates)
- [ ] All AgentEvol claims match paper 2406.04151
- [ ] Extensions labeled [Our Extension] or [From AgentGym-RL]
- [ ] All 16 diagrams present and use ASCII box-drawing style
- [ ] K=3, M=4, reward-weighted SFT as default
- [ ] Data merging with ORIGINAL BC data documented
- [ ] Three env types: Fine-Tuning, Training/Practice, Evaluation
- [ ] Training unified as one process (BC = Phase 0)

---

## 10. References

| Paper / Tool | Link |
|---|---|
| AgentGym (Xi et al., 2024) | [arxiv.org/abs/2406.04151](https://arxiv.org/abs/2406.04151) |
| AgentGym-RL (2025) | [arxiv.org/abs/2509.08755](https://arxiv.org/abs/2509.08755) |
| AgentGym GitHub | [github.com/WooooDyy/AgentGym](https://github.com/WooooDyy/AgentGym) |
| Unsloth | [github.com/unslothai/unsloth](https://github.com/unslothai/unsloth) |
| trl (HuggingFace) | [github.com/huggingface/trl](https://github.com/huggingface/trl) |
| safetensors | [github.com/huggingface/safetensors](https://github.com/huggingface/safetensors) |
| ReAct (Yao et al., 2022) | [arxiv.org/abs/2210.03629](https://arxiv.org/abs/2210.03629) |
