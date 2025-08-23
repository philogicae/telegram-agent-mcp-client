from datetime import datetime
from logging import CRITICAL, Formatter, StreamHandler, getLogger
from os import environ, getenv
from sys import stdout
from typing import Any

from dotenv import load_dotenv
from google.genai.types import ThinkingConfig
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.edges import EntityEdge
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.gemini_client import (  # type: ignore
    GeminiClient,
    LLMConfig,
)
from graphiti_core.nodes import EntityNode, EpisodeType
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

from .utils import Singleton, format_date, sort_edges

environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"
logger = getLogger()
logger.setLevel(CRITICAL)
console_handler = StreamHandler(stdout)
console_handler.setLevel(CRITICAL)
console_handler.setFormatter(Formatter("%(name)s - %(levelname)s - %(message)s"))
logger.addHandler(console_handler)

load_dotenv()
neo4j_uri = getenv("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = getenv("NEO4J_USER", "neo4j")
neo4j_password = getenv("NEO4J_PASSWORD")
api_key = getenv("GEMINI_API_KEY")


class GraphRAG(Singleton):
    graphiti: Graphiti | Any
    api_key = api_key
    model = "gemini-2.5-flash-lite"
    small_model = "gemini-2.5-flash-lite"
    temperature = 0
    thinking_budget = 512
    embedding_model = "gemini-embedding-001"
    embedding_dim = 3072

    @staticmethod
    async def init(think: bool = True, clear: bool = False) -> "GraphRAG":
        obj = GraphRAG()
        if not hasattr(obj, "graphiti"):
            llm_config = LLMConfig(
                api_key=obj.api_key,
                model=obj.model,
                small_model=obj.small_model,
                temperature=obj.temperature,
            )
            thinking_config = (
                ThinkingConfig(thinking_budget=obj.thinking_budget)
                if think and obj.thinking_budget
                else None
            )
            embedder_config = GeminiEmbedderConfig(
                api_key=obj.api_key,
                embedding_dim=obj.embedding_dim,
                embedding_model=obj.embedding_model,
            )
            obj.graphiti = Graphiti(
                neo4j_uri,
                neo4j_user,
                neo4j_password,
                llm_client=GeminiClient(
                    config=llm_config,
                    thinking_config=thinking_config,
                ),
                embedder=GeminiEmbedder(
                    config=embedder_config,
                ),
                cross_encoder=GeminiRerankerClient(
                    config=llm_config,
                ),
            )
            if clear:
                await obj.clear()
            else:
                await obj.init_graph()
        return obj

    # Utils
    async def init_graph(self) -> None:
        await self.graphiti.build_indices_and_constraints()

    async def clear(self) -> None:
        await clear_data(self.graphiti.driver)
        await self.init_graph()

    def _format_mem_nodes(self, nodes: list[EntityNode]) -> str:
        results: list[str] = []
        if nodes:
            sorted_nodes = sorted(
                nodes,
                key=lambda x: x.created_at,
            )
            for node in sorted_nodes:
                start: Any = node.created_at
                date = f"[{format_date(start)}] " if start else ""
                results.append(date + f"<{node.name}>: {node.summary}")
        return "\n".join(results)

    def _format_mem_edges(self, edges: list[EntityEdge]) -> str:
        results: list[str] = []
        if edges:
            sorted_edges = sorted(
                edges,
                key=sort_edges,
            )
            unique_edges = set()
            for edge in sorted_edges:
                if edge.fact not in unique_edges:
                    unique_edges.add(edge.fact)
                    start: Any = edge.valid_at or edge.created_at
                    date = ""
                    if start:
                        date += f"[{format_date(start)}"
                        end_str = "] "
                        end = edge.expired_at or edge.invalid_at
                        if end and end > start:
                            end_str = f" to {format_date(end)}] "
                        date += end_str
                    results.append(date + f"<{edge.name}>: {edge.fact}")
        return "\n".join(results)

    # Methods
    async def add(
        self,
        content: list[tuple[str, str]],  # [(user, message), ...]
        chat_id: Any,
        source: str = "Group Chat",
    ) -> Any:
        date = datetime.now()
        results = await self.graphiti.add_episode(
            name=f"{source.lower().replace(' ', '_')}_{chat_id}_on_{date.strftime('%Y-%m-%d_%H-%M-%S')}",
            episode_body="\n".join([f"{user}: {message}" for user, message in content]),
            reference_time=date,
            group_id=str(chat_id),
            source=EpisodeType.message,
            source_description=source,
        )
        return {
            "stats": {k: len(v) for k, v in results.model_dump().items()},
            "nodes": self._format_mem_nodes(results.nodes),
            "edges": self._format_mem_edges(results.edges),
        }

    async def search_memories(
        self, content: str, user: str, chat_id: Any, limit: int = 10
    ) -> list[EntityEdge]:
        return await self.graphiti.search(
            query=f"{user}: {content}",
            group_ids=[str(chat_id)],
            num_results=limit,
        )

    async def search(
        self, content: str, user: str, chat_id: Any, limit: int = 10
    ) -> str:
        memories = await self.search_memories(content, user, chat_id, limit)
        formatted_edges = self._format_mem_edges(memories)
        return formatted_edges if formatted_edges else ""

    async def recent_messages(self, chat_id: Any, limit: int = 10) -> list[Any]:
        messages: list[Any] = await self.graphiti.retrieve_episodes(
            reference_time=datetime.now(),
            last_n=limit,
            group_ids=[str(chat_id)],
            source=EpisodeType.text,
        )
        return messages

    async def recent(self, chat_id: Any, limit: int = 10) -> str:
        messages = await self.recent_messages(chat_id, limit)
        if messages:
            return "\n".join([node.fact for node in messages])
        return ""
