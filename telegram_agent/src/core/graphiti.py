from datetime import datetime
from logging import CRITICAL, Formatter, StreamHandler, getLogger
from os import environ, getenv
from sys import stdout
from typing import Any

from dotenv import load_dotenv
from google.genai.types import ThinkingConfig
from graphiti_core import Graphiti
from graphiti_core.cross_encoder.gemini_reranker_client import GeminiRerankerClient
from graphiti_core.embedder.gemini import GeminiEmbedder, GeminiEmbedderConfig
from graphiti_core.llm_client.gemini_client import (  # type: ignore
    GeminiClient,
    LLMConfig,
)
from graphiti_core.nodes import EpisodeType
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

from .utils import Singleton

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

    # Methods
    async def add(
        self,
        content: list[tuple[str, str]],  # [(user, message), ...]
        chat_id: Any,
        source: str = "Group Chat",
    ) -> Any:
        date = datetime.now()
        return await self.graphiti.add_episode(
            name=f"{source.lower().replace(' ', '_')}_{chat_id}_on_{date.strftime('%Y-%m-%d_%H-%M-%S')}",
            episode_body="\n".join([f"{user}: {message}" for user, message in content]),
            reference_time=date,
            group_id=str(chat_id),
            source=EpisodeType.message,
            source_description=source,
        )

    async def search_memories(
        self, content: str, user: str, chat_id: Any, limit: int = 10
    ) -> list[Any]:
        memories: list[Any] = await self.graphiti.search(
            query=f"{user}: {content}",
            group_ids=[str(chat_id)],
            num_results=limit,
        )
        return [mem for mem in memories if not mem.expired_at and not mem.invalid_at]

    async def search(
        self, content: str, user: str, chat_id: Any, limit: int = 10
    ) -> str:
        memories = await self.search_memories(content, user, chat_id, limit)
        if memories:
            return "# Episodic Memories:\n> " + "\n> ".join(
                [edge.fact for edge in memories]
            )
        return ""

    async def recent_memories(self, chat_id: Any, limit: int = 10) -> list[Any]:
        memories: list[Any] = await self.graphiti.retrieve_episodes(
            reference_time=datetime.now(),
            last_n=limit,
            group_ids=[str(chat_id)],
            source=EpisodeType.text,
        )
        return memories

    async def recent(self, chat_id: Any, limit: int = 10) -> str:
        memories = await self.recent_memories(chat_id, limit)
        if memories:
            return "# Recent Memories:\n> " + "\n> ".join(
                [edge.fact for edge in memories]
            )
        return ""
