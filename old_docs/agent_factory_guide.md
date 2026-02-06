# Building an Agent Factory for Phagocyte

## Table of Contents
- [What is an Agent Factory?](#what-is-an-agent-factory)
- [Architecture Overview](#architecture-overview)
- [Implementation Guide](#implementation-guide)
- [Advanced Features](#advanced-features)
- [Implementation Roadmap](#implementation-roadmap)
- [Key Benefits](#key-benefits)

## What is an Agent Factory?

**Think of it like a factory that produces specialized workers:**
- Car factory → produces cars
- **Agent factory** → produces AI agents trained for specific tasks

An agent factory is a system that:
1. **Creates** AI agents with specific capabilities
2. **Trains** them on relevant tasks
3. **Evolves** them based on performance
4. **Deploys** them for real-world work
5. **Manages** multiple agents working together

---

## Architecture Overview

### 3-Layer System

```
┌─────────────────────────────────────────┐
│         AGENT FACTORY (Manager)         │
│  - Creates new agents                   │
│  - Assigns tasks                        │
│  - Monitors performance                 │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│         AGENT TEMPLATES (Blueprints)    │
│  - Research Agent                       │
│  - Parser Agent                         │
│  - Ingestor Agent                       │
│  - Processor Agent                      │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│       ENVIRONMENT WRAPPERS (Training)   │
│  - ResearchEnv                          │
│  - ParserEnv                            │
│  - IngestorEnv                          │
│  - ProcessorEnv                         │
└─────────────────────────────────────────┘
```

### Component Description

| Component | Purpose | Example |
|-----------|---------|---------|
| **Agent Factory** | Central manager that creates and coordinates agents | `factory.create_agent("processor")` |
| **Agent Templates** | Pre-defined agent types with specialized capabilities | `ProcessorAgent`, `ResearchAgent` |
| **Environment Wrappers** | Training grounds where agents learn | `ProcessorEnv` wraps the processor CLI |

---

## Implementation Guide

### Step 1: Create Environment Wrappers

Each Phagocyte module becomes a training environment where agents can learn.

#### ProcessorEnv Example

```python
# src/agent_factory/environments/processor_env.py
from dataclasses import dataclass
from typing import Tuple, Dict
import subprocess

@dataclass
class EnvState:
    """State returned after each environment step"""
    observation: str
    reward: float
    done: bool
    info: Dict

class ProcessorEnv:
    """Environment for training processor agents"""
    
    def __init__(self, workspace: str):
        self.workspace = workspace
        self.actions = {
            "chunk_only": "--chunk-only",
            "clean": "--clean",
            "process_low": "--text-profile low",
            "process_medium": "--text-profile medium",
            "process_high": "--text-profile high",
            "filter_toc": "--detect-toc",
        }
    
    def reset(self, task: str) -> str:
        """Start new task"""
        self.task = task
        return f"Task: {task}\nWorkspace: {self.workspace}"
    
    def step(self, action: str) -> EnvState:
        """
        Execute action and return result
        
        Args:
            action: Action string (e.g., "--chunk-only")
            
        Returns:
            EnvState with observation, reward, done flag, and info
        """
        # Run the actual processor command
        cmd = f"uv run processor process {self.workspace} {action}"
        result = subprocess.run(cmd, capture_output=True, shell=True)
        
        # Calculate reward based on success
        reward = self._calculate_reward(result)
        
        # Check if done
        done = result.returncode == 0
        
        observation = result.stdout.decode() if done else result.stderr.decode()
        
        return EnvState(
            observation=observation,
            reward=reward,
            done=done,
            info={"cmd": cmd, "return_code": result.returncode}
        )
    
    def _calculate_reward(self, result) -> float:
        """
        Calculate reward based on result quality
        
        Reward components:
        - 0.5: Base reward for success
        - 0.3: Bonus for number of chunks created
        - 0.2: Bonus for no errors
        """
        if result.returncode != 0:
            return 0.0
        
        output = result.stdout.decode()
        reward = 0.5  # Base reward for success
        
        # Reward for chunks created
        if "chunks created" in output:
            chunks = int(output.split("chunks created:")[1].split()[0])
            reward += min(chunks / 10000, 0.3)  # Up to 0.3 bonus
        
        # Reward for no errors
        if "Errors: 0" in output:
            reward += 0.2
        
        return min(reward, 1.0)
```

#### Other Environment Examples

```python
# src/agent_factory/environments/research_env.py
class ResearchEnv:
    """Environment for training research agents"""
    
    def __init__(self):
        self.actions = {
            "research": "phagocyte research",
            "deep_research": "phagocyte research --mode directed",
            "quick_research": "phagocyte research --mode undirected",
        }
    
    def step(self, action: str, topic: str) -> EnvState:
        # Execute research command
        # Return results, citations found, quality metrics
        pass

# src/agent_factory/environments/parser_env.py
class ParserEnv:
    """Environment for training parser agents"""
    
    def __init__(self):
        self.actions = {
            "parse_refs": "phagocyte parse refs",
            "batch_download": "phagocyte parse batch",
            "retrieve_single": "phagocyte parse retrieve",
        }
    
    def step(self, action: str, input_file: str) -> EnvState:
        # Execute parser command
        # Return download success rate, papers acquired
        pass

# src/agent_factory/environments/ingestor_env.py
class IngestorEnv:
    """Environment for training ingestor agents"""
    
    def __init__(self):
        self.actions = {
            "ingest_batch": "phagocyte ingest batch",
            "with_images": "phagocyte ingest batch --describe-images",
            "filter_first": "phagocyte ingest filter --detect-toc --remove",
        }
    
    def step(self, action: str, input_dir: str) -> EnvState:
        # Execute ingestor command
        # Return conversion quality, image descriptions
        pass
```

---

### Step 2: Define Agent Templates

#### Base Agent Class

```python
# src/agent_factory/agents/base_agent.py
from abc import ABC, abstractmethod
from typing import List, Dict
import pickle
from pathlib import Path

class BaseAgent(ABC):
    """Base class for all agents"""
    
    def __init__(self, name: str, model: str = "gpt-4"):
        self.name = name
        self.model = model
        self.memory = []  # Experience replay buffer
        self.performance_history = []
        self.learned_strategies = {}
    
    @abstractmethod
    def think(self, observation: str) -> str:
        """
        Generate reasoning/thought based on observation
        
        Args:
            observation: Current state observation
            
        Returns:
            Reasoning thought as string
        """
        pass
    
    @abstractmethod
    def act(self, thought: str, available_actions: List[str]) -> str:
        """
        Choose action based on thought
        
        Args:
            thought: Reasoning from think()
            available_actions: List of possible actions
            
        Returns:
            Chosen action
        """
        pass
    
    def remember(self, experience: Dict):
        """
        Store experience for learning
        
        Args:
            experience: Dict with thought, action, observation, reward, etc.
        """
        self.memory.append(experience)
        
        # Keep only recent experiences (memory limit)
        if len(self.memory) > 1000:
            self.memory = self.memory[-1000:]
    
    def learn(self):
        """
        Learn from experiences in memory
        
        Implementation can use:
        - Behavioral cloning
        - Reinforcement learning
        - Evolution strategies
        """
        # Analyze successful experiences (high rewards)
        successful = [exp for exp in self.memory if exp.get('reward', 0) > 0.7]
        
        # Extract patterns
        for exp in successful:
            task_type = self._classify_task(exp['observation'])
            action = exp['action']
            
            # Store successful strategy
            if task_type not in self.learned_strategies:
                self.learned_strategies[task_type] = []
            self.learned_strategies[task_type].append(action)
    
    def _classify_task(self, observation: str) -> str:
        """Classify task type from observation"""
        # Simple classification based on keywords
        if "api" in observation.lower() or "documentation" in observation.lower():
            return "api_docs"
        elif "research" in observation.lower() or "paper" in observation.lower():
            return "research_papers"
        elif "code" in observation.lower() or "repository" in observation.lower():
            return "code_repos"
        else:
            return "general"
    
    def _query_llm(self, prompt: str) -> str:
        """Query language model for reasoning"""
        # TODO: Implement using OpenAI/Anthropic/etc
        # For now, return placeholder
        return "Placeholder LLM response"
    
    def save(self, path: str):
        """Save agent state"""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'wb') as f:
            pickle.dump(self, f)
    
    @classmethod
    def load(cls, path: str) -> 'BaseAgent':
        """Load agent from file"""
        with open(path, 'rb') as f:
            return pickle.load(f)
```

#### Processor Agent

```python
# src/agent_factory/agents/processor_agent.py
from .base_agent import BaseAgent
from typing import List

class ProcessorAgent(BaseAgent):
    """Agent specialized for document processing"""
    
    def __init__(self):
        super().__init__("ProcessorAgent")
        
        # Pre-seeded strategies from expert knowledge
        self.learned_strategies = {
            "api_docs": [
                "--text-profile medium",
                "--detect-toc",
                "--chunk-only",  # Test first
            ],
            "research_papers": [
                "--text-profile high",
                "--describe-images",
            ],
            "code_repos": [
                "--code-profile high",
                "--keep-source",
                "--table-mode both",
            ],
            "web_crawl": [
                "--detect-toc",
                "--chunk-only",  # Verify first
                "--clean",  # Then full process
            ],
        }
    
    def think(self, observation: str) -> str:
        """
        Analyze task and plan approach
        
        Reasoning process:
        1. Classify content type
        2. Check learned strategies
        3. Plan step-by-step approach
        """
        task_type = self._classify_task(observation)
        known_strategies = self.learned_strategies.get(task_type, [])
        
        prompt = f"""
You are a document processing expert agent.

Task: {observation}

Content type detected: {task_type}

Previously successful strategies for {task_type}:
{chr(10).join(f'  - {s}' for s in known_strategies)}

Think step-by-step:
1. What type of content is this?
2. What challenges might it have (e.g., TOC pages, complex figures)?
3. Should I test with --chunk-only first?
4. What processing profile is appropriate?
5. What's my complete strategy?

Provide your reasoning:
"""
        
        thought = self._query_llm(prompt)
        return thought
    
    def act(self, thought: str, available_actions: List[str]) -> str:
        """
        Choose best action based on reasoning
        
        Args:
            thought: Reasoning from think()
            available_actions: List like ['chunk_only', 'process_medium', ...]
            
        Returns:
            Chosen action
        """
        prompt = f"""
Reasoning: {thought}

Available actions:
{chr(10).join(f'  - {a}' for a in available_actions)}

Choose the single best action for this step.
Return only the action name, no explanation.
"""
        
        action = self._query_llm(prompt).strip()
        
        # Fallback to safe default if invalid
        if action not in available_actions:
            action = "chunk_only"  # Conservative default
        
        return action
    
    def execute(self, task: str) -> Dict:
        """
        Execute complete task autonomously
        
        This is the production mode - agent runs without training wheels
        """
        from ..environments.processor_env import ProcessorEnv
        
        # Create environment
        env = ProcessorEnv(workspace=task)
        observation = env.reset(task)
        
        trajectory = []
        done = False
        
        while not done and len(trajectory) < 10:  # Max 10 steps
            # Think and act
            thought = self.think(observation)
            action = self.act(thought, list(env.actions.keys()))
            
            # Execute
            state = env.step(env.actions[action])
            
            # Store
            trajectory.append({
                "thought": thought,
                "action": action,
                "observation": observation,
                "result": state.observation,
                "reward": state.reward,
            })
            
            # Update
            observation = state.observation
            done = state.done
        
        return {
            "success": done,
            "trajectory": trajectory,
            "total_reward": sum(step['reward'] for step in trajectory),
        }
```

#### Other Agent Types

```python
# src/agent_factory/agents/research_agent.py
class ResearchAgent(BaseAgent):
    """Agent specialized for research tasks"""
    
    def __init__(self):
        super().__init__("ResearchAgent")
        self.learned_strategies = {
            "technical_topic": ["--mode directed", "--artifact citations"],
            "broad_exploration": ["--mode undirected"],
        }
    
    # Implement think() and act() for research-specific logic

# src/agent_factory/agents/parser_agent.py
class ParserAgent(BaseAgent):
    """Agent specialized for parsing and paper retrieval"""
    
    def __init__(self):
        super().__init__("ParserAgent")
        self.learned_strategies = {
            "many_papers": ["--concurrent 5"],
            "verify_first": ["--dry-run"],
        }
    
    # Implement think() and act() for parser-specific logic

# src/agent_factory/agents/ingestor_agent.py
class IngestorAgent(BaseAgent):
    """Agent specialized for document ingestion"""
    
    def __init__(self):
        super().__init__("IngestorAgent")
        self.learned_strategies = {
            "research_papers": ["--describe-images"],
            "web_docs": ["filter --detect-toc first", "then batch"],
        }
    
    # Implement think() and act() for ingestor-specific logic
```

---

### Step 3: Build the Agent Factory

```python
# src/agent_factory/factory.py
from typing import Dict, Type, List
from pathlib import Path
import pickle
import random

from .agents import BaseAgent, ProcessorAgent, ResearchAgent, ParserAgent, IngestorAgent
from .environments import ProcessorEnv, ResearchEnv, ParserEnv, IngestorEnv

class AgentFactory:
    """
    Factory for creating and managing agents
    
    The factory handles:
    - Agent creation and registration
    - Training across environments
    - Performance monitoring
    - Agent persistence (save/load)
    - Multi-agent orchestration
    """
    
    def __init__(self):
        # Registry of agent types
        self.agent_registry: Dict[str, Type[BaseAgent]] = {
            "processor": ProcessorAgent,
            "research": ResearchAgent,
            "parser": ParserAgent,
            "ingestor": IngestorAgent,
        }
        
        # Registry of environments
        self.env_registry: Dict[str, Type] = {
            "processor": ProcessorEnv,
            "research": ResearchEnv,
            "parser": ParserEnv,
            "ingestor": IngestorEnv,
        }
        
        # Active agents
        self.agents: Dict[str, BaseAgent] = {}
        
        # Training trajectories
        self.trajectories: List[Dict] = []
        
        # Performance metrics
        self.metrics: Dict[str, List[float]] = {}
    
    def create_agent(self, agent_type: str, name: str = None) -> BaseAgent:
        """
        Create a new agent
        
        Args:
            agent_type: Type of agent ('processor', 'research', etc.)
            name: Optional custom name for the agent
            
        Returns:
            Newly created agent instance
        """
        if agent_type not in self.agent_registry:
            raise ValueError(f"Unknown agent type: {agent_type}. Available: {list(self.agent_registry.keys())}")
        
        agent_class = self.agent_registry[agent_type]
        agent = agent_class()
        
        name = name or f"{agent_type}_{len(self.agents)}"
        self.agents[name] = agent
        
        print(f"✅ Created agent: {name}")
        return agent
    
    def train_agent(
        self, 
        agent_name: str, 
        env_type: str,
        num_episodes: int = 100,
        verbose: bool = True
    ):
        """
        Train an agent in an environment
        
        Args:
            agent_name: Name of agent to train
            env_type: Type of environment
            num_episodes: Number of training episodes
            verbose: Print progress
        """
        agent = self.agents[agent_name]
        env = self.env_registry[env_type]()
        
        if verbose:
            print(f"🎓 Training {agent_name} for {num_episodes} episodes...")
        
        for episode in range(num_episodes):
            # Reset environment with new task
            task = self._sample_task(env_type)
            observation = env.reset(task)
            
            trajectory = []
            done = False
            total_reward = 0
            steps = 0
            max_steps = 20
            
            while not done and steps < max_steps:
                # Agent thinks
                thought = agent.think(observation)
                
                # Agent acts
                action = agent.act(thought, list(env.actions.keys()))
                
                # Environment responds
                state = env.step(env.actions[action])
                
                # Store experience
                experience = {
                    "thought": thought,
                    "action": action,
                    "observation": observation,
                    "next_observation": state.observation,
                    "reward": state.reward,
                    "done": state.done,
                }
                
                agent.remember(experience)
                trajectory.append(experience)
                
                observation = state.observation
                done = state.done
                total_reward += state.reward
                steps += 1
            
            # Store trajectory
            self.trajectories.append({
                "agent": agent_name,
                "env": env_type,
                "episode": episode,
                "trajectory": trajectory,
                "total_reward": total_reward,
                "steps": steps,
            })
            
            # Track metrics
            if agent_name not in self.metrics:
                self.metrics[agent_name] = []
            self.metrics[agent_name].append(total_reward)
            
            # Agent learns from episode
            if episode % 10 == 0:
                agent.learn()
                avg_reward = sum(self.metrics[agent_name][-10:]) / 10
                if verbose:
                    print(f"Episode {episode}: Reward = {total_reward:.2f}, Avg(last 10) = {avg_reward:.2f}")
        
        if verbose:
            final_avg = sum(self.metrics[agent_name][-20:]) / 20
            print(f"✅ Training complete! Final avg reward: {final_avg:.2f}")
    
    def deploy_agent(self, agent_name: str, task: str) -> Dict:
        """
        Deploy trained agent to perform task
        
        Args:
            agent_name: Name of agent to deploy
            task: Task description or path
            
        Returns:
            Task execution result
        """
        agent = self.agents[agent_name]
        
        print(f"🚀 Deploying {agent_name} for task: {task}")
        
        # Agent autonomously performs task
        result = agent.execute(task)
        
        if result['success']:
            print(f"✅ Task completed successfully! Reward: {result['total_reward']:.2f}")
        else:
            print(f"❌ Task failed. Reward: {result['total_reward']:.2f}")
        
        return result
    
    def save_agents(self, path: str):
        """
        Save all trained agents
        
        Args:
            path: Directory path to save agents
        """
        Path(path).mkdir(parents=True, exist_ok=True)
        
        for name, agent in self.agents.items():
            agent_path = f"{path}/{name}.pkl"
            agent.save(agent_path)
        
        # Save factory state
        factory_state = {
            "metrics": self.metrics,
            "trajectories": self.trajectories,
        }
        with open(f"{path}/factory_state.pkl", 'wb') as f:
            pickle.dump(factory_state, f)
        
        print(f"💾 Saved {len(self.agents)} agents to {path}")
    
    def load_agents(self, path: str):
        """
        Load trained agents
        
        Args:
            path: Directory path containing saved agents
        """
        path = Path(path)
        
        for file in path.glob("*.pkl"):
            if file.name == "factory_state.pkl":
                # Load factory state
                with open(file, 'rb') as f:
                    state = pickle.load(f)
                    self.metrics = state['metrics']
                    self.trajectories = state['trajectories']
            else:
                # Load agent
                agent = BaseAgent.load(str(file))
                self.agents[file.stem] = agent
        
        print(f"📂 Loaded {len(self.agents)} agents from {path}")
    
    def evaluate_agent(self, agent_name: str, env_type: str, num_episodes: int = 10) -> Dict:
        """
        Evaluate agent performance
        
        Args:
            agent_name: Agent to evaluate
            env_type: Environment to test in
            num_episodes: Number of test episodes
            
        Returns:
            Evaluation metrics
        """
        agent = self.agents[agent_name]
        env = self.env_registry[env_type]()
        
        rewards = []
        success_count = 0
        
        print(f"📊 Evaluating {agent_name} on {num_episodes} episodes...")
        
        for i in range(num_episodes):
            task = self._sample_task(env_type)
            observation = env.reset(task)
            
            done = False
            total_reward = 0
            steps = 0
            
            while not done and steps < 20:
                thought = agent.think(observation)
                action = agent.act(thought, list(env.actions.keys()))
                state = env.step(env.actions[action])
                
                total_reward += state.reward
                observation = state.observation
                done = state.done
                steps += 1
            
            rewards.append(total_reward)
            if done:
                success_count += 1
        
        metrics = {
            "avg_reward": sum(rewards) / len(rewards),
            "success_rate": success_count / num_episodes,
            "rewards": rewards,
        }
        
        print(f"Results: Avg Reward = {metrics['avg_reward']:.2f}, Success Rate = {metrics['success_rate']:.1%}")
        
        return metrics
    
    def _sample_task(self, env_type: str) -> str:
        """Sample a task for training/testing"""
        tasks = {
            "processor": [
                "Process HDF5 documentation",
                "Process PyTorch API docs",
                "Process research papers on ML",
                "Process web-crawled documentation",
            ],
            "research": [
                "Research HDF5 best practices",
                "Research RAG techniques",
                "Research embedding models",
            ],
            "parser": [
                "Extract references from research report",
                "Download papers from citation list",
                "Retrieve papers by DOI",
            ],
            "ingestor": [
                "Convert PDF papers to markdown",
                "Ingest web documentation",
                "Process GitHub repository",
            ],
        }
        
        return random.choice(tasks.get(env_type, ["Generic task"]))
```

---

### Step 4: Multi-Agent Orchestration

```python
# src/agent_factory/pipeline.py
from typing import Dict, List
from .factory import AgentFactory

class AgentPipeline:
    """
    Orchestrate multiple agents for complex workflows
    
    This enables agents to work together on multi-step tasks,
    similar to how Phagocyte's modules work in sequence.
    """
    
    def __init__(self, factory: AgentFactory):
        self.factory = factory
        self.execution_log = []
    
    def execute_full_pipeline(self, research_topic: str, output_dir: str) -> Dict:
        """
        Execute complete Phagocyte pipeline with agents
        
        Pipeline steps:
        1. Research agent finds relevant papers
        2. Parser agent downloads them
        3. Ingestor agent converts to markdown
        4. Processor agent builds RAG database
        
        Args:
            research_topic: Topic to research
            output_dir: Output directory for results
            
        Returns:
            Pipeline execution results
        """
        print(f"🔄 Starting full pipeline for: {research_topic}")
        print(f"📁 Output directory: {output_dir}")
        
        results = {}
        
        # Step 1: Research
        print("\n🔬 Step 1: Research")
        research_result = self.factory.deploy_agent(
            "research_v1", 
            f"Research {research_topic} and find relevant papers"
        )
        results['research'] = research_result
        self.execution_log.append(("research", research_result))
        
        if not research_result['success']:
            return {"success": False, "failed_at": "research", "results": results}
        
        # Step 2: Parse references
        print("\n📚 Step 2: Parse references and download papers")
        parser_result = self.factory.deploy_agent(
            "parser_v1",
            f"Parse references from {research_result['output']} and download papers"
        )
        results['parser'] = parser_result
        self.execution_log.append(("parser", parser_result))
        
        if not parser_result['success']:
            return {"success": False, "failed_at": "parser", "results": results}
        
        # Step 3: Ingest documents
        print("\n📄 Step 3: Convert documents to markdown")
        ingestor_result = self.factory.deploy_agent(
            "ingestor_v1",
            f"Ingest papers from {parser_result['output']} to markdown"
        )
        results['ingestor'] = ingestor_result
        self.execution_log.append(("ingestor", ingestor_result))
        
        if not ingestor_result['success']:
            return {"success": False, "failed_at": "ingestor", "results": results}
        
        # Step 4: Process into RAG database
        print("\n🔮 Step 4: Build RAG database")
        processor_result = self.factory.deploy_agent(
            "processor_v1",
            f"Process {ingestor_result['output']} into RAG database at {output_dir}"
        )
        results['processor'] = processor_result
        self.execution_log.append(("processor", processor_result))
        
        print("\n✅ Pipeline complete!")
        
        return {
            "success": processor_result['success'],
            "results": results,
            "execution_log": self.execution_log
        }
    
    def execute_custom_pipeline(self, steps: List[tuple]) -> Dict:
        """
        Execute custom pipeline with specified agent sequence
        
        Args:
            steps: List of (agent_name, task) tuples
            
        Example:
            steps = [
                ("research_v1", "Research topic"),
                ("processor_v1", "Process documents"),
            ]
        """
        results = {}
        
        for agent_name, task in steps:
            print(f"\n▶️  Executing: {agent_name}")
            result = self.factory.deploy_agent(agent_name, task)
            results[agent_name] = result
            
            if not result['success']:
                return {
                    "success": False,
                    "failed_at": agent_name,
                    "results": results
                }
        
        return {"success": True, "results": results}
```

---

## Advanced Features

### 1. Agent Evolution

Continuously improve agents based on performance metrics.

```python
# src/agent_factory/evolution.py
from typing import Dict
from .factory import AgentFactory

class AgentEvolver:
    """Evolve agents based on performance"""
    
    def __init__(self, factory: AgentFactory):
        self.factory = factory
        self.evolution_history = []
    
    def evolve_agent(
        self, 
        agent_name: str, 
        env_type: str,
        performance_threshold: float = 0.7
    ):
        """
        Evolve agent if underperforming
        
        Args:
            agent_name: Agent to evolve
            env_type: Environment to train in
            performance_threshold: Minimum acceptable performance
        """
        agent = self.factory.agents[agent_name]
        
        # Analyze recent performance
        recent_rewards = self.factory.metrics.get(agent_name, [])[-100:]
        if not recent_rewards:
            print(f"⚠️  No performance data for {agent_name}")
            return
        
        avg_reward = sum(recent_rewards) / len(recent_rewards)
        
        print(f"📊 {agent_name} current performance: {avg_reward:.2f}")
        
        if avg_reward < performance_threshold:
            # Agent needs improvement
            print(f"⚠️  {agent_name} underperforming (threshold: {performance_threshold:.2f})")
            print(f"🔄 Starting evolution training...")
            
            # Retrain with more difficult tasks
            self.factory.train_agent(
                agent_name, 
                env_type, 
                num_episodes=50,
                verbose=True
            )
            
            # Re-evaluate
            new_avg = sum(self.factory.metrics[agent_name][-20:]) / 20
            improvement = new_avg - avg_reward
            
            self.evolution_history.append({
                "agent": agent_name,
                "before": avg_reward,
                "after": new_avg,
                "improvement": improvement,
            })
            
            print(f"✅ Evolution complete! Improvement: {improvement:+.2f}")
        else:
            print(f"✅ {agent_name} performing well")
    
    def evolve_all_agents(self):
        """Evolve all agents that need improvement"""
        for agent_name in self.factory.agents.keys():
            # Determine environment type from agent name
            env_type = agent_name.split('_')[0]  # e.g., "processor_v1" -> "processor"
            
            if env_type in self.factory.env_registry:
                self.evolve_agent(agent_name, env_type)
```

### 2. Agent Marketplace

Share and discover trained agents.

```python
# src/agent_factory/marketplace.py
import json
from typing import List, Dict
from pathlib import Path
from .agents import BaseAgent

class AgentMarketplace:
    """
    Share and discover trained agents
    
    Agents can be:
    - Published to a shared repository
    - Downloaded and used by others
    - Rated and reviewed
    """
    
    def __init__(self, repo_path: str = "./agent_marketplace"):
        self.repo_path = Path(repo_path)
        self.repo_path.mkdir(parents=True, exist_ok=True)
        self.index_file = self.repo_path / "index.json"
        self._load_index()
    
    def _load_index(self):
        """Load marketplace index"""
        if self.index_file.exists():
            with open(self.index_file) as f:
                self.index = json.load(f)
        else:
            self.index = {"agents": []}
    
    def _save_index(self):
        """Save marketplace index"""
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def publish_agent(
        self, 
        agent: BaseAgent, 
        metadata: Dict
    ) -> str:
        """
        Publish agent to marketplace
        
        Args:
            agent: Agent to publish
            metadata: Agent metadata (description, author, performance, etc.)
            
        Returns:
            Agent ID in marketplace
        """
        # Generate agent ID
        agent_id = f"{agent.name}_{len(self.index['agents'])}"
        
        # Save agent
        agent_path = self.repo_path / f"{agent_id}.pkl"
        agent.save(str(agent_path))
        
        # Add to index
        entry = {
            "id": agent_id,
            "name": agent.name,
            "type": type(agent).__name__,
            "file": str(agent_path),
            **metadata
        }
        self.index["agents"].append(entry)
        self._save_index()
        
        print(f"✅ Published agent: {agent_id}")
        return agent_id
    
    def download_agent(self, agent_id: str) -> BaseAgent:
        """
        Download agent from marketplace
        
        Args:
            agent_id: ID of agent to download
            
        Returns:
            Loaded agent instance
        """
        # Find in index
        entry = next((a for a in self.index["agents"] if a["id"] == agent_id), None)
        if not entry:
            raise ValueError(f"Agent {agent_id} not found in marketplace")
        
        # Load agent
        agent = BaseAgent.load(entry["file"])
        print(f"📥 Downloaded agent: {agent_id}")
        
        return agent
    
    def search_agents(
        self, 
        agent_type: str = None,
        min_performance: float = None
    ) -> List[Dict]:
        """
        Search for agents in marketplace
        
        Args:
            agent_type: Filter by agent type (e.g., "ProcessorAgent")
            min_performance: Filter by minimum performance
            
        Returns:
            List of matching agent entries
        """
        results = self.index["agents"]
        
        if agent_type:
            results = [a for a in results if a["type"] == agent_type]
        
        if min_performance:
            results = [a for a in results if a.get("performance", 0) >= min_performance]
        
        return results
    
    def list_agents(self):
        """List all agents in marketplace"""
        print("\n📚 Available Agents:")
        for agent in self.index["agents"]:
            print(f"  • {agent['id']}: {agent.get('description', 'No description')}")
            print(f"    Performance: {agent.get('performance', 'N/A')}")
            print(f"    Author: {agent.get('author', 'Unknown')}")
```

### 3. Performance Monitoring

Track and visualize agent performance over time.

```python
# src/agent_factory/monitor.py
import matplotlib.pyplot as plt
from typing import Dict, List
from .factory import AgentFactory

class PerformanceMonitor:
    """Monitor and visualize agent performance"""
    
    def __init__(self, factory: AgentFactory):
        self.factory = factory
    
    def plot_training_progress(self, agent_name: str, save_path: str = None):
        """
        Plot agent training progress
        
        Args:
            agent_name: Agent to plot
            save_path: Optional path to save figure
        """
        if agent_name not in self.factory.metrics:
            print(f"No metrics for {agent_name}")
            return
        
        rewards = self.factory.metrics[agent_name]
        
        plt.figure(figsize=(10, 6))
        plt.plot(rewards, alpha=0.3, label='Episode Reward')
        
        # Moving average
        window = 20
        if len(rewards) >= window:
            moving_avg = [sum(rewards[i:i+window])/window 
                         for i in range(len(rewards)-window+1)]
            plt.plot(range(window-1, len(rewards)), moving_avg, 
                    label=f'Moving Average (window={window})', linewidth=2)
        
        plt.xlabel('Episode')
        plt.ylabel('Reward')
        plt.title(f'{agent_name} Training Progress')
        plt.legend()
        plt.grid(alpha=0.3)
        
        if save_path:
            plt.savefig(save_path)
            print(f"📊 Saved plot to {save_path}")
        else:
            plt.show()
    
    def generate_report(self, output_file: str = "agent_report.md"):
        """Generate comprehensive performance report"""
        with open(output_file, 'w') as f:
            f.write("# Agent Performance Report\n\n")
            
            for agent_name, rewards in self.factory.metrics.items():
                avg_reward = sum(rewards) / len(rewards)
                max_reward = max(rewards)
                min_reward = min(rewards)
                
                f.write(f"## {agent_name}\n\n")
                f.write(f"- Episodes: {len(rewards)}\n")
                f.write(f"- Average Reward: {avg_reward:.2f}\n")
                f.write(f"- Max Reward: {max_reward:.2f}\n")
                f.write(f"- Min Reward: {min_reward:.2f}\n\n")
        
        print(f"📄 Generated report: {output_file}")
```

---

## Complete Usage Example

```python
# example_full_usage.py
"""
Complete example showing how to use the Agent Factory system
"""

from agent_factory import AgentFactory, AgentPipeline, AgentEvolver, PerformanceMonitor

# ========================================
# 1. Initialize Factory
# ========================================
factory = AgentFactory()

# ========================================
# 2. Create Agents
# ========================================
print("Creating agents...")
processor_agent = factory.create_agent("processor", name="processor_v1")
research_agent = factory.create_agent("research", name="research_v1")
parser_agent = factory.create_agent("parser", name="parser_v1")
ingestor_agent = factory.create_agent("ingestor", name="ingestor_v1")

# ========================================
# 3. Train Agents
# ========================================
print("\nTraining agents...")

# Train processor agent
factory.train_agent(
    agent_name="processor_v1",
    env_type="processor",
    num_episodes=100,
    verbose=True
)

# Train other agents
factory.train_agent("research_v1", "research", num_episodes=50)
factory.train_agent("parser_v1", "parser", num_episodes=50)
factory.train_agent("ingestor_v1", "ingestor", num_episodes=50)

# ========================================
# 4. Evaluate Agents
# ========================================
print("\nEvaluating agents...")

metrics = factory.evaluate_agent("processor_v1", "processor", num_episodes=10)
print(f"Processor agent performance: {metrics}")

# ========================================
# 5. Save Trained Agents
# ========================================
print("\nSaving agents...")
factory.save_agents("./trained_agents")

# ========================================
# 6. Deploy Single Agent
# ========================================
print("\nDeploying processor agent...")
result = factory.deploy_agent(
    "processor_v1",
    task="Process HDF5_Phagocyte/markdowns into RAG database"
)
print(f"Result: {result}")

# ========================================
# 7. Multi-Agent Pipeline
# ========================================
print("\nExecuting multi-agent pipeline...")
pipeline = AgentPipeline(factory)

full_result = pipeline.execute_full_pipeline(
    research_topic="HDF5 best practices",
    output_dir="./output/hdf5_rag"
)
print(f"Pipeline result: {full_result}")

# ========================================
# 8. Agent Evolution
# ========================================
print("\nEvolving agents...")
evolver = AgentEvolver(factory)

# Evolve underperforming agents
evolver.evolve_all_agents()

# ========================================
# 9. Performance Monitoring
# ========================================
print("\nGenerating performance report...")
monitor = PerformanceMonitor(factory)

# Plot training progress
monitor.plot_training_progress("processor_v1", save_path="training_plot.png")

# Generate report
monitor.generate_report("agent_report.md")

# ========================================
# 10. Load and Reuse Later
# ========================================
print("\nDemo: Loading agents from disk...")

# Start fresh
new_factory = AgentFactory()

# Load previously trained agents
new_factory.load_agents("./trained_agents")

# Use immediately
result = new_factory.deploy_agent("processor_v1", "New task")
```

---

## Implementation Roadmap

### Phase 1: Foundation (Weeks 1-2)

**Week 1**
- [ ] Set up project structure
- [ ] Implement base environment wrapper (ProcessorEnv)
- [ ] Create BaseAgent class
- [ ] Basic AgentFactory skeleton

**Week 2**
- [ ] Implement ProcessorAgent
- [ ] Add training loop
- [ ] Test single agent training
- [ ] Add save/load functionality

### Phase 2: Multi-Agent (Weeks 3-4)

**Week 3**
- [ ] Create ResearchEnv, ParserEnv, IngestorEnv
- [ ] Implement corresponding agent classes
- [ ] Add multi-agent pipeline orchestration
- [ ] Test sequential agent execution

**Week 4**
- [ ] Collect expert trajectories from successful runs
- [ ] Implement behavioral cloning
- [ ] Train agents on real Phagocyte tasks
- [ ] Benchmark against manual execution

### Phase 3: Evolution (Weeks 5-6)

**Week 5**
- [ ] Implement reward calculation for each environment
- [ ] Add self-improvement loop
- [ ] Enable multi-environment training
- [ ] Test agent learning from feedback

**Week 6**
- [ ] Implement AgentEvolver
- [ ] Add performance monitoring
- [ ] Create visualization tools
- [ ] Optimize training hyperparameters

### Phase 4: Production (Weeks 7-8)

**Week 7**
- [ ] Deploy agents for real tasks
- [ ] Implement error handling and recovery
- [ ] Add logging and debugging
- [ ] Create user-friendly CLI

**Week 8**
- [ ] Build agent marketplace
- [ ] Write comprehensive documentation
- [ ] Create tutorial notebooks
- [ ] Package and release

---

## Key Benefits

| Feature | Benefit | Example |
|---------|---------|---------|
| **Reusable Agents** | Train once, use everywhere | Processor agent works on any docs |
| **Continuous Improvement** | Agents get better over time | Learning optimal chunking strategies |
| **Specialization** | Different agents for different tasks | Research vs Processing vs Parsing |
| **Scalability** | Easily add new agent types | New IngestorAgent in minutes |
| **Collaboration** | Share trained agents | Download pre-trained expert agents |
| **Automation** | Reduce manual intervention | Agents choose best strategies |
| **Adaptability** | Handle unexpected scenarios | Agents learn from failures |
| **Reproducibility** | Consistent results | Same agent behavior across runs |

---

## Technical Considerations

### Performance Optimization

1. **Parallel Training**: Train multiple agents simultaneously
2. **Experience Replay**: Reuse past experiences efficiently
3. **Batch Processing**: Process multiple tasks at once
4. **Caching**: Cache LLM responses for repeated patterns

### Error Handling

1. **Graceful Degradation**: Fall back to simpler strategies on failure
2. **Retry Logic**: Automatic retries with backoff
3. **Logging**: Comprehensive logging for debugging
4. **Validation**: Verify agent outputs before proceeding

### Security

1. **Sandboxing**: Run agents in isolated environments
2. **Access Control**: Limit agent permissions
3. **Input Validation**: Sanitize all agent inputs
4. **Audit Logging**: Track all agent actions

---

## Future Enhancements

### Short Term (Next 3 months)
- [ ] Add more environment types (web scraping, data analysis)
- [ ] Implement multi-agent communication
- [ ] Add agent versioning and rollback
- [ ] Create web dashboard for monitoring

### Medium Term (Next 6 months)
- [ ] Implement federated learning across agents
- [ ] Add agent marketplace with ratings/reviews
- [ ] Support for custom agent architectures
- [ ] Integration with external tools (Zapier, etc.)

### Long Term (Next year)
- [ ] Self-modifying agents (agents that improve their own code)
- [ ] Meta-learning across different domains
- [ ] Automatic agent architecture search
- [ ] Community-driven agent ecosystem

---

## References

- **AgentGym Paper**: [https://arxiv.org/abs/2406.04151](https://arxiv.org/abs/2406.04151)
- **Phagocyte GitHub**: [https://github.com/grc-iit/Phagocyte](https://github.com/grc-iit/Phagocyte)
- **ReAct Paper**: [https://arxiv.org/abs/2210.03629](https://arxiv.org/abs/2210.03629)
- **Behavioral Cloning**: [Imitation Learning Survey](https://arxiv.org/abs/1811.06711)

---

## Conclusion

The Agent Factory transforms Phagocyte from a **static pipeline** into a **self-improving system** where AI agents learn optimal strategies through experience. This enables:

- **Autonomous operation** - Agents decide best approaches without manual tuning
- **Continuous learning** - Performance improves with each run
- **Adaptability** - Handles diverse content types automatically
- **Scalability** - Easily extend with new capabilities
- **Community** - Share and benefit from collective learning

**Bottom line**: Agent Factory makes Phagocyte smarter over time, learning from every research project and continuously optimizing its strategies.
