"""CoordinatorAgent — routes natural language commands to specialized agents.

Uses an LLM backend (typically ClaudeAgent) to parse user commands and
delegate to the appropriate specialized agent (IngestorAgent or RetrieverAgent).

The coordinator enables natural language multi-agent interaction without
predefined pipelines. You can say "ingest folder://data as research_docs"
and the coordinator will parse the intent, route to IngestorAgent, and execute.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_factory.core.types import Action, Observation

log = logging.getLogger(__name__)

COORDINATOR_SYSTEM_PROMPT = """\
You are a coordinator agent that routes user commands to specialized agents.

ROUTING LOGIC:
Analyze the user's intent and pick the most appropriate agent:

- Use "ingestor" for: loading, ingesting, importing, uploading, assimilating data (WRITE operations)
- Use "retriever" for: querying, searching, finding, listing, retrieving, getting, deleting, pruning, destroying data (READ and DELETE operations)

KEY RULE: ALL deletion operations (prune, destroy, delete, remove) go to "retriever"

YOUR JOB:
Parse the user command and decide which agent should handle it. Simplify the
command into a clear instruction for that agent.

CRITICAL: Preserve URI formats exactly! URIs use :: (double colon) not slashes:
- "file::path" NOT "file://path"
- "folder::path" NOT "folder:///path"
When you see folder::/path, write folder::/path exactly as-is.

EXAMPLES:

User: "ingest folder::data/sample_docs as research_docs"
→ {"thought": "User wants to load data", "agent": "ingestor", "instruction": "assimilate folder::data/sample_docs research_docs arrow"}

User: "retrieve all blobs from research_docs"
→ {"thought": "User wants to list stored data", "agent": "retriever", "instruction": "list all blobs in research_docs"}

User: "query research_docs for HDF5"
→ {"thought": "User wants to search", "agent": "retriever", "instruction": "query research_docs for HDF5"}

User: "load file::path/doc.txt as mydoc"
→ {"thought": "User wants to load a file", "agent": "ingestor", "instruction": "assimilate file::path/doc.txt mydoc arrow"}

User: "delete research_docs"
→ {"thought": "User wants to permanently delete data", "agent": "retriever", "instruction": "destroy research_docs"}

User: "prune old_file.txt from cache"
→ {"thought": "User wants to evict from cache", "agent": "retriever", "instruction": "prune old_file.txt from cache"}

RESPONSE FORMAT (JSON only):
{
  "thought": "brief reasoning about which agent to use",
  "agent": "ingestor" or "retriever" or other available agent,
  "instruction": "simplified command for the chosen agent"
}

IMPORTANT: Respond with ONLY the JSON object. No markdown, no code fences.
"""


class CoordinatorAgent:
    """Routes natural language commands to specialized agents.

    Satisfies the ``Agent`` protocol from ``agent_factory.core.protocols``.
    
    The coordinator uses an LLM (backend) to parse user intent and delegates
    to one of the registered specialized BuiltAgent instances. Each agent is
    fully standalone with its own environment reference, but they all share
    the same underlying infrastructure (client, cache, resolver).
    """

    def __init__(
        self,
        backend: Any,  # LLM agent (ClaudeAgent, LLMAgent, etc.)
        agents: dict[str, Any],  # {"ingestor": BuiltAgent, "retriever": BuiltAgent}
    ) -> None:
        """Initialize coordinator with an LLM backend and specialized agents.
        
        Args:
            backend: LLM agent for parsing commands (typically ClaudeAgent)
            agents: Dictionary mapping agent names to BuiltAgent instances
        """
        self._backend = backend
        self._agents = agents
        self._last_routing: dict[str, Any] = {}

    def think(self, observation: Observation) -> str:
        """Parse command using LLM and decide routing."""
        # Build prompt for LLM to parse routing decision
        routing_prompt = f"{COORDINATOR_SYSTEM_PROMPT}\n\nUser command: {observation.text}"
        
        # Call Claude CLI directly with our custom system prompt
        import subprocess
        import shutil
        
        cli = shutil.which("claude")
        if not cli:
            log.error("Claude CLI not found")
            self._last_routing = {
                "agent": "retriever",
                "instruction": observation.text,
                "thought": "Claude CLI not available"
            }
            return "Coordinator: Claude CLI not available, defaulting to retriever"
        
        try:
            result = subprocess.run(
                [
                    cli,
                    "-p",
                    "--model", "sonnet",
                    "--system-prompt", COORDINATOR_SYSTEM_PROMPT,
                    "--tools", "",
                    "--no-session-persistence",
                    f"User command: {observation.text}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            if result.returncode != 0:
                log.warning(f"Claude CLI error: {result.stderr}")
                self._last_routing = {
                    "agent": "retriever",
                    "instruction": observation.text,
                    "thought": "Claude CLI error"
                }
                return "Coordinator: Claude CLI error, defaulting to retriever"
            
            response_text = result.stdout.strip()
            log.debug(f"Claude response: {response_text}")
            
            # Parse JSON from response
            if response_text.startswith("```"):
                # Strip markdown code fences
                lines = response_text.split("\n")
                lines = [l for l in lines if not l.strip().startswith("```")]
                response_text = "\n".join(lines).strip()
            
            routing = json.loads(response_text)
            self._last_routing = routing
            
            agent_name = routing.get("agent", "retriever")
            routing_thought = routing.get("thought", "No reasoning provided")
            
            return (
                f"Coordinator decision: Route to '{agent_name}'\n"
                f"Reasoning: {routing_thought}"
            )
            
        except json.JSONDecodeError as exc:
            log.warning(f"Failed to parse routing JSON: {exc}")
            log.warning(f"Response was: {response_text}")
            # Default to retriever for read operations
            self._last_routing = {
                "agent": "retriever",
                "instruction": observation.text,
                "thought": "Parsing failed, defaulting to retriever"
            }
            return "Coordinator: JSON parsing failed, defaulting to retriever"
        except Exception as exc:
            log.error(f"Coordinator routing error: {exc}")
            self._last_routing = {
                "agent": "retriever",
                "instruction": observation.text,
                "thought": f"Error: {exc}"
            }
            return f"Coordinator error: {exc}"

    def act(self, observation: Observation) -> Action:
        """Delegate to the chosen specialized agent."""
        if not self._last_routing:
            # If think() wasn't called, call it now
            self.think(observation)
        
        routing = self._last_routing
        self._last_routing = {}
        
        agent_name = routing.get("agent", "retriever")
        instruction = routing.get("instruction", observation.text)
        
        # Get the specialized BuiltAgent
        built_agent = self._agents.get(agent_name)
        if built_agent is None:
            log.error(f"No agent found for role '{agent_name}'")
            # Default to retriever
            built_agent = self._agents.get("retriever")
            if built_agent is None:
                # No retriever either, return a safe query action
                log.error("No retriever agent available either")
                return Action(name="query", params={"tag_pattern": "*"})
        
        # Create observation for specialized agent
        agent_obs = Observation(
            text=instruction,
            data=observation.data,
            done=observation.done,
        )
        
        log.info(f"Coordinator: Routing to {agent_name} with instruction: {instruction}")
        print(f"\n  \033[36m→ Coordinator routing to '{agent_name}' agent\033[0m")
        print(f"    Instruction: {instruction}\n")
        
        # Delegate to the specialized agent (extract .agent from BuiltAgent)
        return built_agent.agent.act(agent_obs)
