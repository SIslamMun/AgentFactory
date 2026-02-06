"""AgentBuilder — assembles a fully wired agent stack from a blueprint.

Given a blueprint dict (from the registry), instantiates:
    IOWarpClient → BlobCache → URIResolver → IOWarpEnvironment → Agent

Also provides ``build_pipeline()`` for multi-agent pipeline orchestration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agent_factory.core.errors import BlueprintError
from agent_factory.environments.iowarp_env import IOWarpEnvironment, RewardConfig
from agent_factory.iowarp.cache import BlobCache
from agent_factory.iowarp.client import IOWarpClient
from agent_factory.iowarp.uri_resolver import URIResolver

log = logging.getLogger(__name__)


@dataclass
class BuiltAgent:
    """All wired components returned by the builder."""

    client: IOWarpClient
    cache: BlobCache
    resolver: URIResolver
    environment: IOWarpEnvironment
    agent: Any  # Satisfies Agent protocol (IOWarpAgent | LLMAgent | ClaudeAgent)
    blueprint: dict[str, Any]


@dataclass
class BuiltPipeline:
    """All wired components for a multi-agent pipeline."""

    client: IOWarpClient
    cache: BlobCache
    resolver: URIResolver
    environment: IOWarpEnvironment
    agents: dict[str, Any]  # role -> Agent
    executor: Any  # PipelineExecutor
    dag: Any  # PipelineDAG
    blueprint: dict[str, Any]


class AgentBuilder:
    """Builds an agent stack from a blueprint configuration dict."""

    def build(self, blueprint: dict[str, Any], *, connect: bool = True) -> BuiltAgent:
        """Instantiate all components defined in *blueprint*.

        If *connect* is True (default) the client and cache will be
        connected immediately.  Set to False for testing without Docker.
        """
        try:
            return self._build(blueprint, connect=connect)
        except BlueprintError:
            raise
        except Exception as exc:
            raise BlueprintError(f"Failed to build agent: {exc}") from exc

    def build_pipeline(
        self,
        blueprint: dict[str, Any],
        pipeline_def: dict[str, Any],
        *,
        connect: bool = True,
    ) -> BuiltPipeline:
        """Build a multi-agent pipeline from blueprint + pipeline definition.

        *blueprint* provides infrastructure config (iowarp, cache, etc.).
        *pipeline_def* provides agent definitions and pipeline steps.
        """
        from agent_factory.orchestration.dag import PipelineDAG
        from agent_factory.orchestration.executor import PipelineExecutor

        try:
            # Build shared infrastructure
            client, cache, resolver, environment = self._build_infra(
                blueprint, connect=connect
            )

            # Build agents from pipeline definition
            agents_cfg = pipeline_def.get("agents", {})
            agents: dict[str, Any] = {}
            for role, cfg in agents_cfg.items():
                agents[role] = self._build_agent(cfg)

            # Parse and validate DAG
            dag = PipelineDAG.from_dict(
                pipeline_def,
                known_roles=frozenset(agents.keys()),
            )

            # Create executor
            executor = PipelineExecutor(environment, agents)

            return BuiltPipeline(
                client=client,
                cache=cache,
                resolver=resolver,
                environment=environment,
                agents=agents,
                executor=executor,
                dag=dag,
                blueprint=blueprint,
            )

        except BlueprintError:
            raise
        except Exception as exc:
            raise BlueprintError(f"Failed to build pipeline: {exc}") from exc

    def _build_infra(
        self, bp: dict[str, Any], connect: bool
    ) -> tuple[IOWarpClient, BlobCache, URIResolver, IOWarpEnvironment]:
        """Build shared infrastructure components."""
        # -- IOWarp client ---------------------------------------------------
        iowarp_cfg = bp.get("iowarp", {})
        endpoints = iowarp_cfg.get("bridge_endpoints")
        if not endpoints:
            endpoints = [iowarp_cfg.get("bridge_endpoint", "tcp://127.0.0.1:5560")]
        client = IOWarpClient(
            endpoints=endpoints,
            connect_timeout_ms=iowarp_cfg.get("connect_timeout_ms", 5000),
            request_timeout_ms=iowarp_cfg.get("request_timeout_ms", 30000),
        )

        # -- Cache -----------------------------------------------------------
        cache_cfg = bp.get("cache", {})
        hosts_raw = cache_cfg.get("hosts", [{"host": "127.0.0.1", "port": 11211}])
        cache_hosts = [
            (h.get("host", "127.0.0.1"), h.get("port", 11211))
            for h in hosts_raw
        ]
        cache = BlobCache(
            hosts=cache_hosts,
            key_prefix=cache_cfg.get("key_prefix", "iowarp"),
            default_ttl=cache_cfg.get("default_ttl", 3600),
        )

        # -- URI resolver ----------------------------------------------------
        resolver_cfg = bp.get("uri_resolver", {})
        resolver = URIResolver(
            cache=cache,
            temp_dir=resolver_cfg.get("temp_dir", "/tmp/agent-factory/uri-cache"),
        )

        # -- Environment -----------------------------------------------------
        env_cfg = bp.get("environment", {})
        reward_raw = env_cfg.get("reward", {})
        reward_config = RewardConfig(
            cache_hit=reward_raw.get("cache_hit", 0.3),
            cache_miss=reward_raw.get("cache_miss", 0.2),
            assimilate_success=reward_raw.get("assimilate_success", 0.1),
            query_success=reward_raw.get("query_success", 0.1),
            prune_success=reward_raw.get("prune_success", 0.05),
            error=reward_raw.get("error", -0.5),
        )
        environment = IOWarpEnvironment(
            client=client,
            cache=cache,
            resolver=resolver,
            default_format=env_cfg.get("default_format", "arrow"),
            reward_config=reward_config,
        )

        # -- Connect if requested -------------------------------------------
        if connect:
            log.info("Connecting client and cache...")
            client.connect()
            cache.connect()

        return client, cache, resolver, environment

    def _build(self, bp: dict[str, Any], connect: bool) -> BuiltAgent:
        client, cache, resolver, environment = self._build_infra(bp, connect=connect)

        # -- Agent -----------------------------------------------------------
        agent_cfg = bp.get("agent", {})
        agent_type = agent_cfg.get("type", "rule_based")
        
        # Special handling for coordinator: build specialized agents with shared infra
        if agent_type == "coordinator":
            agent = self._build_coordinator_with_agents(
                agent_cfg, client, cache, resolver, environment
            )
        else:
            agent = self._build_agent(agent_cfg)

        return BuiltAgent(
            client=client,
            cache=cache,
            resolver=resolver,
            environment=environment,
            agent=agent,
            blueprint=bp,
        )

    def _build_coordinator_with_agents(
        self,
        agent_cfg: dict[str, Any],
        client: IOWarpClient,
        cache: BlobCache,
        resolver: URIResolver,
        environment: IOWarpEnvironment,
    ) -> Any:
        """Build coordinator with full BuiltAgent instances sharing infrastructure.
        
        Auto-discovers all available agents from the registry and builds them
        as standalone BuiltAgent instances that share the coordinator's infrastructure.
        """
        from agent_factory.agents.coordinator_agent import CoordinatorAgent
        from agent_factory.factory.registry import BlueprintRegistry
        
        # Build LLM backend for parsing
        backend_cfg: dict[str, Any] = {
            "type": agent_cfg.get("backend", "claude"),
        }
        if "model" in agent_cfg:
            backend_cfg["model"] = agent_cfg["model"]
        if "temperature" in agent_cfg:
            backend_cfg["temperature"] = agent_cfg["temperature"]
        backend = AgentBuilder._build_agent(backend_cfg)
        
        # Auto-discover agents from registry
        registry = BlueprintRegistry()
        registry.load()
        all_blueprints = registry.list_blueprints()
        
        # Build specialized agents as full BuiltAgent instances
        agents: dict[str, BuiltAgent] = {}
        
        for blueprint_name in all_blueprints:
            # Skip coordinator itself to avoid recursion
            if blueprint_name == "coordinator_agent":
                continue
            
            try:
                agent_bp = registry.get(blueprint_name)
                agent_sub_cfg = agent_bp.get("agent", {})
                agent_type = agent_sub_cfg.get("type", "rule_based")
                
                # Determine role based on agent type
                if agent_type == "ingestor":
                    role = "ingestor"
                elif agent_type == "retriever":
                    role = "retriever"
                else:
                    # Generic agents use their blueprint name as role
                    role = blueprint_name.replace("_agent", "")
                
                # Build the specialized agent wrapper
                specialized_agent = AgentBuilder._build_agent(agent_sub_cfg)
                
                # Create BuiltAgent with shared infrastructure
                agents[role] = BuiltAgent(
                    client=client,       # SHARED
                    cache=cache,         # SHARED
                    resolver=resolver,   # SHARED
                    environment=environment,  # SHARED
                    agent=specialized_agent,  # Unique wrapper
                    blueprint=agent_bp,
                )
                log.info(f"Coordinator: Auto-discovered and built '{role}' agent from '{blueprint_name}'")
            except Exception as exc:
                log.warning(f"Coordinator: Skipping blueprint '{blueprint_name}': {exc}")
        
        if not agents:
            log.warning("Coordinator: No agents were auto-discovered!")
        else:
            log.info(f"Coordinator: Managing {len(agents)} agents: {', '.join(agents.keys())}")
        
        return CoordinatorAgent(backend, agents)

    @staticmethod
    def _build_agent(agent_cfg: dict[str, Any]) -> Any:
        """Instantiate the right agent based on ``agent.type``."""
        agent_type = agent_cfg.get("type", "rule_based")

        if agent_type == "rule_based":
            from agent_factory.agents.iowarp_agent import IOWarpAgent
            return IOWarpAgent()

        if agent_type == "llm":
            from agent_factory.agents.llm_agent import LLMAgent
            return LLMAgent(
                model=agent_cfg.get("model", "llama3.2:latest"),
                temperature=agent_cfg.get("temperature", 0.1),
            )

        if agent_type == "claude":
            from agent_factory.agents.claude_agent import ClaudeAgent
            return ClaudeAgent(
                model=agent_cfg.get("model", "sonnet"),
            )

        if agent_type == "ingestor":
            from agent_factory.agents.ingestor_agent import IngestorAgent
            backend_cfg: dict[str, Any] = {
                "type": agent_cfg.get("backend", "rule_based"),
            }
            # Forward model/temperature to backend when applicable
            if "model" in agent_cfg:
                backend_cfg["model"] = agent_cfg["model"]
            if "temperature" in agent_cfg:
                backend_cfg["temperature"] = agent_cfg["temperature"]
            backend = AgentBuilder._build_agent(backend_cfg)
            return IngestorAgent(
                backend,
                default_tag=agent_cfg.get("default_tag", "default"),
                default_format=agent_cfg.get("default_format", "arrow"),
            )

        if agent_type == "retriever":
            from agent_factory.agents.retriever_agent import RetrieverAgent
            backend_cfg = {
                "type": agent_cfg.get("backend", "rule_based"),
            }
            if "model" in agent_cfg:
                backend_cfg["model"] = agent_cfg["model"]
            if "temperature" in agent_cfg:
                backend_cfg["temperature"] = agent_cfg["temperature"]
            backend = AgentBuilder._build_agent(backend_cfg)
            return RetrieverAgent(
                backend,
                default_tag_pattern=agent_cfg.get("default_tag_pattern", "*"),
            )

        if agent_type == "coordinator":
            from agent_factory.agents.coordinator_agent import CoordinatorAgent
            
            # Build LLM backend for parsing
            backend_cfg: dict[str, Any] = {
                "type": agent_cfg.get("backend", "claude"),
            }
            if "model" in agent_cfg:
                backend_cfg["model"] = agent_cfg["model"]
            if "temperature" in agent_cfg:
                backend_cfg["temperature"] = agent_cfg["temperature"]
            backend = AgentBuilder._build_agent(backend_cfg)
            
            return CoordinatorAgent(backend, agents={})

        raise BlueprintError(
            f"Unknown agent type '{agent_type}'. "
            f"Valid types: rule_based, llm, claude, ingestor, retriever, coordinator"
        )
