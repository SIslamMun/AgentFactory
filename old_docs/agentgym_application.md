# Applying AgentGym to Phagocyte

## Table of Contents
- [Overview](#overview)
- [Understanding Phagocyte](#understanding-phagocyte)
- [AgentGym Key Concepts](#agentgym-key-concepts)
- [Application Strategy](#application-strategy)
- [Implementation Guide](#implementation-guide)
- [Use Cases](#use-cases)
- [Implementation Roadmap](#implementation-roadmap)

---

## Overview

This document describes how to apply the **AgentGym** framework (from the paper "AgentGym: Evolving Large Language Model-based Agents across Diverse Environments") to transform Phagocyte from a manual pipeline into a self-improving, autonomous research agent system.

**Paper**: [AgentGym: Evolving Large Language Model-based Agents across Diverse Environments](https://arxiv.org/abs/2406.04151)

**Goal**: Enable Phagocyte agents to learn from experience, evolve across different tasks, and autonomously execute the entire research → RAG pipeline.

---

## Understanding Phagocyte

### Current Architecture

Phagocyte is an end-to-end RAG pipeline for academic research:

```
Research → Parse Papers → Ingest → Process → RAG Database
   ↓           ↓            ↓         ↓          ↓
 Gemini    DOI/arXiv    PDF→MD    Chunk +    LanceDB
Research   Downloads            Embed    Vector Store
```

### Modules

| Module | Purpose | Current Status |
|--------|---------|----------------|
| **researcher** | AI-powered research using Gemini | Manual command execution |
| **parser** | Extract & download academic papers | Manual command execution |
| **ingestor** | Convert docs (PDF/Web/GitHub) → Markdown | Manual command execution |
| **processor** | Chunk + Embed → LanceDB RAG database | Manual command execution |

### Current Capabilities

✅ **What Phagocyte Has:**
- End-to-end RAG pipeline
- MCP servers for each module
- CLI interface for all operations
- Comprehensive documentation
- AST-aware chunking
- Multiple embedding models

❌ **What's Missing:**
- No agent training/evolution system
- No multi-task learning across modules
- No self-improvement mechanism
- No trajectory-based learning
- Manual parameter tuning required

---

## AgentGym Key Concepts

### Trinity of Agent Evolution

AgentGym identifies three key pillars for building generally-capable, self-evolving agents:

#### 1. Diverse Environments

```
Multiple training grounds where agents can explore and learn
- Not isolated to one task
- Real-time feedback
- Concurrent exploration across domains
```

**AgentGym has**: 14 environment types, 89 task types (Web, Embodied, Tool Using, Code, etc.)

**Phagocyte equivalent**: 4 module environments (Research, Parser, Ingestor, Processor)

#### 2. Trajectory Dataset

```
High-quality examples of successful task executions
- Format: (instruction, thought, action, observation, reward)
- Used for behavioral cloning (initial training)
- Bootstrap agent with basic capabilities
```

**Source for Phagocyte**:
- Logged successful pipeline runs
- Expert demonstrations
- Existing QA pairs from HDF5_QA_Generator

#### 3. Evolution Method (AgentEvol)

```
Self-improvement through environmental feedback
- Start with base agent (trained on trajectories)
- Agent explores environments
- Learns from successes and failures
- Continuously improves
```

**Key insight**: Agents learn by doing, not just imitating!

### Training Pipeline

```
┌─────────────────────────────────────────────────┐
│ Step 1: Behavioral Cloning                      │
│ Train base agent on expert trajectories         │
│ Agent learns: How to execute each module        │
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│ Step 2: AgentEvol (Self-Evolution)              │
│ Agent explores environments & self-improves     │
│ Agent learns: Optimal strategies, error recovery│
└─────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────┐
│ Step 3: Evaluation                              │
│ Test on held-out benchmark tasks                │
│ Measure: Success rate, efficiency, adaptation   │
└─────────────────────────────────────────────────┘
```

---

## Application Strategy

### Phagocyte as Multi-Environment System

Each Phagocyte module becomes a training environment:

```python
environments = {
    "research_env": {
        "task": "Conduct research on a topic",
        "action_space": [
            "deep_research",      # --mode directed
            "quick_research",     # --mode undirected
            "extract_citations"   # Parse report
        ],
        "observation": "research_report + citations + quality_score",
        "reward": "citation_count * quality_score"
    },
    
    "parser_env": {
        "task": "Extract and download papers from text",
        "action_space": [
            "parse_refs",         # Extract references
            "retrieve_doi",       # Download by DOI
            "batch_download",     # Batch processing
            "verify_citations"    # Verify against CrossRef
        ],
        "observation": "papers_found + download_status + error_messages",
        "reward": "download_success_rate"
    },
    
    "ingestor_env": {
        "task": "Convert documents to clean markdown",
        "action_space": [
            "ingest_pdf",         # PDF → Markdown
            "crawl_web",          # Website crawling
            "filter_toc",         # Remove TOC pages
            "describe_images",    # VLM descriptions
            "clone_repo"          # Git repo ingestion
        ],
        "observation": "markdown_quality + images_processed + errors",
        "reward": "markdown_completeness * readability_score"
    },
    
    "processor_env": {
        "task": "Chunk and embed documents for RAG",
        "action_space": [
            "chunk_only",         # Fast chunking
            "embed_low",          # Low quality (fast)
            "embed_medium",       # Medium quality
            "embed_high",         # High quality
            "incremental",        # Only new files
            "filter_clean"        # Quality filtering
        ],
        "observation": "chunks_created + embedding_dims + errors + search_quality",
        "reward": "chunk_quality * search_relevance * efficiency"
    }
}
```

### Trajectory Format

```json
{
  "trajectory_id": "phagocyte_run_001",
  "environment": "full_pipeline",
  "instruction": "Research HDF5 and build a RAG database",
  "steps": [
    {
      "step": 1,
      "environment": "research_env",
      "thought": "I need to conduct comprehensive research on HDF5 to get quality citations",
      "action": "phagocyte research 'HDF5 file format best practices' --mode directed -o ./output",
      "observation": "Research completed. Found 45 citations. Quality score: 0.92. Report saved.",
      "reward": 0.9,
      "state": "success"
    },
    {
      "step": 2,
      "environment": "parser_env",
      "thought": "Research looks good. Now extract references for downloading papers",
      "action": "phagocyte parse refs ./output/research_report.md --export-batch",
      "observation": "Extracted 45 references. Created batch.json with 42 downloadable papers.",
      "reward": 0.93,
      "state": "success"
    },
    {
      "step": 3,
      "environment": "parser_env",
      "thought": "Download papers with appropriate concurrency to avoid rate limits",
      "action": "phagocyte parse batch ./output/batch.json -o ./papers --concurrent 3",
      "observation": "Downloaded 38/42 papers (90.5% success). 4 failed due to paywalls.",
      "reward": 0.85,
      "state": "partial_success"
    },
    {
      "step": 4,
      "environment": "ingestor_env",
      "thought": "Convert papers to markdown and enable image descriptions for better RAG",
      "action": "phagocyte ingest batch ./papers -o ./markdown --describe-images",
      "observation": "Processed 38 PDFs. Generated markdown with VLM descriptions for 127 figures.",
      "reward": 0.95,
      "state": "success"
    },
    {
      "step": 5,
      "environment": "processor_env",
      "thought": "Use medium quality embeddings for balance between speed and accuracy",
      "action": "phagocyte process run ./markdown -o ./lancedb --text-profile medium --incremental",
      "observation": "Created 7690 text chunks, 446 code chunks, 135 image chunks. Database ready.",
      "reward": 0.98,
      "state": "success"
    }
  ],
  "final_reward": 0.92,
  "total_time": 1847.3,
  "success": true
}
```

---

## Implementation Guide

### Phase 1: Environment Wrappers

Create Python wrappers for each module that provide a gym-like interface.

#### Example: ProcessorEnv

```python
# src/agent_gym/environments/processor_env.py

from dataclasses import dataclass
from typing import Tuple, Dict, List
import subprocess
import re

@dataclass
class EnvState:
    """State returned after each environment step"""
    observation: str
    reward: float
    done: bool
    info: Dict

class ProcessorEnv:
    """
    Environment for training processor agents.
    
    Wraps the processor module CLI as a gym-like environment.
    Agent learns to optimize chunking and embedding parameters.
    """
    
    def __init__(self, workspace: str, db_path: str):
        self.workspace = workspace
        self.db_path = db_path
        self.current_task = None
        
        # Available actions
        self.actions = {
            "chunk_only": "--chunk-only",
            "embed_low": "--text-profile low --code-profile low",
            "embed_medium": "--text-profile medium --code-profile low",
            "embed_high": "--text-profile high --code-profile high",
            "incremental": "--incremental",
            "clean": "--clean",
            "filter": "--detect-toc --remove",
        }
    
    def reset(self, task: str) -> str:
        """Start a new task."""
        self.current_task = task
        return f"Task: {task}\nWorkspace: {self.workspace}\nDatabase: {self.db_path}"
    
    def step(self, action: str) -> EnvState:
        """
        Execute action and return result.
        
        Args:
            action: Action key from self.actions
            
        Returns:
            EnvState with observation, reward, done flag, and info
        """
        if action not in self.actions:
            return EnvState(
                observation=f"Invalid action: {action}",
                reward=0.0,
                done=True,
                info={"error": "invalid_action"}
            )
        
        # Build command
        action_flags = self.actions[action]
        cmd = f"uv run processor process {self.workspace} -o {self.db_path} {action_flags}"
        
        # Execute
        result = subprocess.run(
            cmd,
            capture_output=True,
            shell=True,
            text=True,
            timeout=600
        )
        
        # Parse results
        reward = self._calculate_reward(result)
        done = result.returncode == 0
        observation = self._parse_output(result)
        
        return EnvState(
            observation=observation,
            reward=reward,
            done=done,
            info={
                "cmd": cmd,
                "return_code": result.returncode,
                "action": action
            }
        )
    
    def _calculate_reward(self, result) -> float:
        """
        Calculate reward based on execution result.
        
        Reward components:
        - 0.4: Base reward for success
        - 0.3: Chunk quality (number and distribution)
        - 0.2: No errors
        - 0.1: Efficiency (time taken)
        """
        if result.returncode != 0:
            return 0.0
        
        output = result.stdout
        reward = 0.4  # Base success reward
        
        # Reward for chunks created
        chunk_match = re.search(r'(\d+)\s+chunks', output)
        if chunk_match:
            chunks = int(chunk_match.group(1))
            # Normalize to 0-0.3 range
            reward += min(chunks / 10000, 0.3)
        
        # Reward for no errors
        if 'Errors: 0' in output or 'errors=0' in output:
            reward += 0.2
        
        # Reward for efficiency (inversely proportional to time)
        time_match = re.search(r'(\d+\.?\d*)\s*seconds', output)
        if time_match:
            time_taken = float(time_match.group(1))
            efficiency_bonus = max(0, 0.1 * (1 - time_taken / 1000))
            reward += efficiency_bonus
        
        return min(reward, 1.0)
    
    def _parse_output(self, result) -> str:
        """Parse command output into structured observation."""
        if result.returncode != 0:
            return f"Error: {result.stderr}"
        
        output = result.stdout
        
        # Extract key metrics
        chunks_created = self._extract_metric(output, r'(\d+)\s+chunks')
        errors = self._extract_metric(output, r'Errors:\s*(\d+)')
        time_taken = self._extract_metric(output, r'(\d+\.?\d*)\s*seconds')
        
        return f"Chunks created: {chunks_created}, Errors: {errors}, Time: {time_taken}s"
    
    def _extract_metric(self, text: str, pattern: str) -> str:
        """Extract metric from text using regex."""
        match = re.search(pattern, text)
        return match.group(1) if match else "N/A"
```

#### Example: ResearchEnv

```python
# src/agent_gym/environments/research_env.py

class ResearchEnv:
    """Environment for training research agents."""
    
    def __init__(self, output_dir: str):
        self.output_dir = output_dir
        self.actions = {
            "deep_research": "--mode directed",
            "quick_research": "--mode undirected",
            "no_research": "--mode no-research",
        }
    
    def step(self, action: str, topic: str) -> EnvState:
        """Execute research command."""
        action_flags = self.actions.get(action, "")
        cmd = f"uv run phagocyte research '{topic}' {action_flags} -o {self.output_dir}"
        
        result = subprocess.run(cmd, capture_output=True, shell=True, text=True)
        
        # Parse citations and quality
        citations = self._count_citations(result.stdout)
        quality = self._assess_quality(result.stdout)
        
        reward = (citations / 50) * 0.6 + quality * 0.4  # Weighted reward
        
        return EnvState(
            observation=f"Citations: {citations}, Quality: {quality:.2f}",
            reward=min(reward, 1.0),
            done=result.returncode == 0,
            info={"citations": citations, "quality": quality}
        )
```

### Phase 2: Trajectory Collection

#### Method 1: Log Existing Runs

```python
# src/agent_gym/trajectory_logger.py

import json
import time
from pathlib import Path
from typing import List, Dict

class TrajectoryLogger:
    """Log Phagocyte executions as trajectories for training."""
    
    def __init__(self, output_dir: str = "./trajectories"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.current_trajectory = None
    
    def start_trajectory(self, instruction: str, trajectory_id: str = None):
        """Start logging a new trajectory."""
        if trajectory_id is None:
            trajectory_id = f"traj_{int(time.time())}"
        
        self.current_trajectory = {
            "trajectory_id": trajectory_id,
            "instruction": instruction,
            "steps": [],
            "start_time": time.time(),
        }
    
    def log_step(self, environment: str, thought: str, action: str, 
                  observation: str, reward: float, state: str):
        """Log a single step in the trajectory."""
        if self.current_trajectory is None:
            raise ValueError("No active trajectory. Call start_trajectory() first.")
        
        step = {
            "step": len(self.current_trajectory["steps"]) + 1,
            "environment": environment,
            "thought": thought,
            "action": action,
            "observation": observation,
            "reward": reward,
            "state": state,
            "timestamp": time.time()
        }
        
        self.current_trajectory["steps"].append(step)
    
    def finish_trajectory(self, success: bool):
        """Finish and save the current trajectory."""
        if self.current_trajectory is None:
            return
        
        self.current_trajectory.update({
            "final_reward": self._calculate_final_reward(),
            "total_time": time.time() - self.current_trajectory["start_time"],
            "success": success,
            "end_time": time.time()
        })
        
        # Save to file
        output_file = self.output_dir / f"{self.current_trajectory['trajectory_id']}.json"
        with open(output_file, 'w') as f:
            json.dump(self.current_trajectory, f, indent=2)
        
        self.current_trajectory = None
    
    def _calculate_final_reward(self) -> float:
        """Calculate average reward across all steps."""
        if not self.current_trajectory["steps"]:
            return 0.0
        
        rewards = [step["reward"] for step in self.current_trajectory["steps"]]
        return sum(rewards) / len(rewards)
```

#### Method 2: Convert Existing QA Pairs

```python
# src/agent_gym/qa_to_trajectories.py

def convert_qa_to_trajectory(qa_pair: Dict) -> Dict:
    """
    Convert HDF5_QA_Generator output to trajectory format.
    
    QA pairs represent successful RAG retrievals, which can be
    reverse-engineered into processor trajectories.
    """
    return {
        "trajectory_id": f"qa_{qa_pair['id']}",
        "environment": "processor_env",
        "instruction": f"Process documents to answer: {qa_pair['question']}",
        "steps": [
            {
                "step": 1,
                "environment": "processor_env",
                "thought": "I need to chunk and embed documents for RAG",
                "action": "phagocyte process run ./docs -o ./lancedb",
                "observation": f"Created chunks. Can now answer: {qa_pair['answer']}",
                "reward": 1.0,
                "state": "success"
            }
        ],
        "final_reward": 1.0,
        "success": True
    }
```

### Phase 3: AgentEvol Implementation

```python
# src/agent_gym/agentevol.py

import random
import lancedb
from typing import List, Dict

class PhagocyteAgentEvol:
    """
    Self-evolution system for Phagocyte agents across all 4 environments.
    
    Based on AgentGym's AgentEvol method:
    - Start with base agent (trained on expert trajectories)
    - Let it explore all 4 Phagocyte environments
    - Learn from successful interactions
    - Evolve to handle new research topics automatically
    """
    
    def __init__(self, base_agent, rag_db_path: str):
        """
        Initialize AgentEvol system.
        
        Args:
            base_agent: Pre-trained agent (from behavioral cloning)
            rag_db_path: Path to LanceDB RAG database
        """
        self.agent = base_agent
        self.rag = lancedb.connect(rag_db_path)
        
        # All 4 Phagocyte environments
        self.envs = {
            "research": ResearchEnv("./agent_output"),
            "parser": ParserEnv("./agent_output"),
            "ingestor": IngestorEnv("./agent_output"),
            "processor": ProcessorEnv("./agent_output/markdown", "./agent_output/lancedb")
        }
        
        self.successful_trajectories = []
        self.failed_trajectories = []
        
    def explore_and_evolve(self, num_iterations: int = 1000):
        """
        Main evolution loop - agent explores and improves.
        
        Process:
        1. Sample environment and task
        2. Agent attempts task
        3. Get reward based on success
        4. If reward > threshold, add to training set
        5. Periodically retrain agent on successful trajectories
        
        Args:
            num_iterations: Number of exploration iterations
        """
        print(f"Starting AgentEvol with {num_iterations} iterations...")
        
        for i in range(num_iterations):
            # 1. Sample random environment
            env_name = random.choice(list(self.envs.keys()))
            env = self.envs[env_name]
            
            # 2. Sample task from that environment
            task = self.sample_task(env_name)
            
            # 3. Agent attempts task
            print(f"\n[Iteration {i+1}/{num_iterations}] Environment: {env_name}")
            print(f"Task: {task}")
            
            trajectory = self.agent.interact_with_env(env, task)
            
            # 4. Calculate reward
            reward = self.evaluate_trajectory(trajectory, env)
            
            # 5. Store trajectory based on success
            if reward > 0.7:  # Success threshold
                self.successful_trajectories.append(trajectory)
                print(f"✓ Success! Reward: {reward:.2f}")
            else:
                self.failed_trajectories.append(trajectory)
                print(f"✗ Failed. Reward: {reward:.2f}")
            
            # 6. Periodically retrain agent on successful trajectories
            if i % 100 == 0 and len(self.successful_trajectories) > 10:
                print(f"\n→ Retraining agent at iteration {i}...")
                self.finetune_agent()
                self.save_checkpoint(i)
        
        # Final training
        print("\n→ Final training on all successful trajectories...")
        self.finetune_agent()
        self.save_checkpoint("final")
        
        # Print statistics
        self.print_statistics()
    
    def sample_task(self, env_name: str) -> str:
        """
        Sample a task based on environment type.
        Uses existing RAG database to generate realistic tasks.
        """
        if env_name == "research":
            # Sample research topics from existing papers
            table = self.rag.open_table("text_chunks")
            sample = table.to_pandas().sample(1)
            content = sample.iloc[0]['content']
            # Extract topic from content
            topic = content.split('.')[0][:50]
            return f"Research: {topic}"
        
        elif env_name == "parser":
            tasks = [
                "Extract references from research report",
                "Download papers by DOI batch",
                "Verify citations against CrossRef"
            ]
            return random.choice(tasks)
        
        elif env_name == "ingestor":
            tasks = [
                "Convert PDF documents to markdown",
                "Crawl documentation website",
                "Filter TOC pages from crawled docs"
            ]
            return random.choice(tasks)
        
        elif env_name == "processor":
            tasks = [
                "Process markdown files with low quality embeddings",
                "Process with medium quality embeddings",
                "Incremental processing of new files only"
            ]
            return random.choice(tasks)
    
    def evaluate_trajectory(self, trajectory: Dict, env) -> float:
        """
        Evaluate if trajectory was successful.
        Checks actual system state, not just agent claims.
        """
        # Get final step reward
        if not trajectory["steps"]:
            return 0.0
        
        final_reward = trajectory["steps"][-1]["reward"]
        
        # Verify actual outcomes
        if env.name == "research":
            # Check if research file was created and has citations
            report_path = Path("./agent_output/research_report.md")
            if report_path.exists():
                content = report_path.read_text()
                citation_count = content.count("doi.org") + content.count("arxiv.org")
                return min(citation_count / 20, 1.0)
        
        elif env.name == "parser":
            # Check if papers were actually downloaded
            papers_dir = Path("./agent_output/papers")
            if papers_dir.exists():
                paper_count = len(list(papers_dir.glob("*.pdf")))
                return min(paper_count / 10, 1.0)
        
        elif env.name == "ingestor":
            # Check if markdown files were created with good quality
            markdown_dir = Path("./agent_output/markdown")
            if markdown_dir.exists():
                md_files = list(markdown_dir.glob("*.md"))
                if md_files:
                    avg_quality = self.assess_markdown_quality(md_files)
                    return avg_quality
        
        elif env.name == "processor":
            # Check if database was created and has chunks
            db_path = Path("./agent_output/lancedb")
            if db_path.exists():
                try:
                    db = lancedb.connect(str(db_path))
                    tables = db.table_names()
                    if "text_chunks" in tables or "code_chunks" in tables:
                        return 1.0
                except:
                    pass
        
        return final_reward
    
    def assess_markdown_quality(self, md_files: List[Path]) -> float:
        """Assess quality of markdown files."""
        qualities = []
        
        for md_file in md_files[:10]:  # Sample first 10
            content = md_file.read_text()
            
            # Quality metrics
            has_headers = bool(re.search(r'^#{1,6}\s', content, re.MULTILINE))
            has_content = len(content) > 500
            has_code = "```" in content
            not_too_many_links = content.count("http") < len(content) / 100
            
            quality = sum([has_headers, has_content, has_code, not_too_many_links]) / 4
            qualities.append(quality)
        
        return sum(qualities) / len(qualities) if qualities else 0.0
    
    def finetune_agent(self):
        """
        Retrain agent on accumulated successful trajectories.
        Uses behavioral cloning on self-generated data.
        """
        if len(self.successful_trajectories) < 5:
            print("Not enough successful trajectories for finetuning")
            return
        
        # Convert trajectories to training format
        training_data = self.prepare_training_data(self.successful_trajectories)
        
        # Finetune with low learning rate (preserve existing knowledge)
        print(f"Finetuning on {len(training_data)} successful trajectories...")
        self.agent.finetune(
            training_data,
            epochs=1,
            learning_rate=1e-5,
            batch_size=4
        )
    
    def prepare_training_data(self, trajectories: List[Dict]) -> List[Dict]:
        """Convert trajectories to training format."""
        training_samples = []
        
        for traj in trajectories:
            for step in traj["steps"]:
                # Create training sample
                sample = {
                    "instruction": traj["instruction"],
                    "context": self._build_context(traj, step),
                    "thought": step["thought"],
                    "action": step["action"],
                    "expected_outcome": step["observation"]
                }
                training_samples.append(sample)
        
        return training_samples
    
    def _build_context(self, trajectory: Dict, current_step: Dict) -> str:
        """Build context string from previous steps."""
        context_parts = []
        
        for step in trajectory["steps"]:
            if step["step"] >= current_step["step"]:
                break
            context_parts.append(
                f"Action: {step['action']}\n"
                f"Result: {step['observation']}\n"
            )
        
        return "\n".join(context_parts)
    
    def save_checkpoint(self, iteration):
        """Save agent checkpoint."""
        checkpoint_path = Path(f"./agent_gym/checkpoints/agent_iter_{iteration}.pt")
        checkpoint_path.parent.mkdir(exist_ok=True, parents=True)
        self.agent.save(checkpoint_path)
        print(f"Checkpoint saved: {checkpoint_path}")
    
    def print_statistics(self):
        """Print evolution statistics."""
        total = len(self.successful_trajectories) + len(self.failed_trajectories)
        success_rate = len(self.successful_trajectories) / total if total > 0 else 0
        
        print("\n" + "="*60)
        print("AGENTEVOL STATISTICS")
        print("="*60)
        print(f"Total iterations: {total}")
        print(f"Successful: {len(self.successful_trajectories)} ({success_rate:.1%})")
        print(f"Failed: {len(self.failed_trajectories)}")
        print(f"Final success rate: {success_rate:.1%}")
        print("="*60)
```

---

## Use Cases

### Use Case 1: Autonomous Research Pipeline

**Before (Manual)**:
```bash
# User must execute each step manually
phagocyte research "quantum computing error correction"
phagocyte parse refs ./output/research_report.md --export-batch
phagocyte parse batch ./output/batch.json -o ./papers
phagocyte ingest batch ./papers -o ./markdown
phagocyte process run ./markdown -o ./lancedb
```

**After (Autonomous Agent)**:
```bash
# Single command - agent handles everything
phagocyte agent auto-research "quantum computing error correction"

# Agent autonomously:
# 1. Researches topic with optimal parameters
# 2. Extracts references
# 3. Downloads papers (retries on failure)
# 4. Converts to markdown (filters quality)
# 5. Creates RAG database (chooses embedding quality)
# 6. Returns searchable database
```

### Use Case 2: Adaptive Parameter Selection

**Problem**: User doesn't know which embedding quality to use

**Agent Learning**:
- Tries different profiles on sample data
- Measures search relevance
- Learns: low for drafts, medium for general, high for research papers
- Automatically selects optimal profile based on content

### Use Case 3: Error Recovery

**Problem**: Paper downloads fail due to paywalls

**Agent Learning**:
- Detects download failures
- Tries alternative sources (arXiv, PubMed, institution proxy)
- Learns which sources work for which publishers
- Adapts strategy based on success patterns

---

## Implementation Roadmap

### Week 1-2: Environment Setup

**Tasks:**
- [ ] Create environment wrappers for all 4 modules
- [ ] Define action/observation spaces
- [ ] Implement reward functions
- [ ] Test individual environments

**Deliverables:**
- `src/agent_gym/environments/{research,parser,ingestor,processor}_env.py`
- Unit tests for each environment
- Documentation

### Week 3-4: Trajectory Collection

**Tasks:**
- [ ] Implement trajectory logger
- [ ] Log 50+ successful pipeline runs
- [ ] Convert existing QA pairs to trajectories
- [ ] Create trajectory validation system

**Deliverables:**
- `src/agent_gym/trajectory_logger.py`
- `trajectories/phagocyte_expert.json` (100+ trajectories)
- Trajectory statistics and analysis

### Week 5-6: Base Agent Training

**Tasks:**
- [ ] Implement behavioral cloning trainer
- [ ] Train on expert trajectories
- [ ] Evaluate on held-out test set
- [ ] Establish baseline performance

**Deliverables:**
- `src/agent_gym/train_base_agent.py`
- Base agent checkpoint
- Evaluation metrics

### Week 7-10: AgentEvol Implementation

**Tasks:**
- [ ] Implement exploration loop
- [ ] Implement reward calculation
- [ ] Implement periodic retraining
- [ ] Monitor agent improvement

**Deliverables:**
- `src/agent_gym/agentevol.py`
- Evolution metrics and visualizations
- Evolved agent checkpoints

### Week 11-12: Integration & Deployment

**Tasks:**
- [ ] Create `phagocyte agent` CLI command
- [ ] Benchmark against manual pipeline
- [ ] Write comprehensive documentation
- [ ] Deploy for user testing

**Deliverables:**
- `phagocyte agent auto-research` command
- Performance comparison report
- User guide

---

## Expected Outcomes

### Performance Improvements

| Metric | Manual Pipeline | Evolved Agent | Improvement |
|--------|----------------|---------------|-------------|
| Time to RAG Database | 30-60 min | 20-40 min | 25-35% faster |
| Success Rate | 85% | 95% | +10% |
| Parameter Tuning | Manual | Automatic | Eliminated |
| Error Recovery | Manual | Automatic | Eliminated |
| Adaptation to New Domains | Poor | Excellent | Significant |

### Key Benefits

1. **Automation**: Single command replaces 5-step manual process
2. **Optimization**: Agent learns optimal parameters for each scenario
3. **Robustness**: Automatic error recovery and alternative strategies
4. **Generalization**: Adapts to new research domains without retraining
5. **Continuous Improvement**: Gets better over time through self-evolution

---

## References

- **AgentGym Paper**: [https://arxiv.org/abs/2406.04151](https://arxiv.org/abs/2406.04151)
- **AgentGym GitHub**: [https://github.com/WooooDyy/AgentGym](https://github.com/WooooDyy/AgentGym)
- **Phagocyte Documentation**: [../README.md](../README.md)
- **Agent Factory Guide**: [agent_factory_guide.md](agent_factory_guide.md)

---

## Appendix: Code Examples

### Complete Example: Training and Evolution

```python
# train_and_evolve.py

import asyncio
from pathlib import Path
from agent_gym import (
    ResearchEnv, ParserEnv, IngestorEnv, ProcessorEnv,
    TrajectoryLogger, PhagocyteAgent, PhagocyteAgentEvol
)

async def main():
    # Step 1: Collect trajectories
    logger = TrajectoryLogger("./trajectories")
    
    # Log a successful run
    logger.start_trajectory("Research HDF5 and build RAG database")
    
    # ... execute pipeline steps and log each one ...
    
    logger.finish_trajectory(success=True)
    
    # Step 2: Train base agent
    print("Training base agent on expert trajectories...")
    agent = PhagocyteAgent.from_trajectories(
        "./trajectories/*.json",
        model="llama-3.1-8b",
        epochs=3
    )
    
    # Step 3: Self-evolution
    print("Starting agent evolution...")
    evolver = PhagocyteAgentEvol(
        base_agent=agent,
        rag_db_path="./HDF5_Phagocyte/RAG"
    )
    
    evolver.explore_and_evolve(iterations=1000)
    
    # Step 4: Save evolved agent
    agent.save("./models/phagocyte_agent_evolved.pt")
    print("Agent training complete!")

if __name__ == "__main__":
    asyncio.run(main())
```

---

**This transforms Phagocyte from a manual pipeline into a self-improving research agent!** 🚀
