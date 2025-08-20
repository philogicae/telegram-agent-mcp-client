from logging import ERROR, Formatter, StreamHandler, getLogger
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
from graphiti_core.utils.maintenance.graph_data_operations import clear_data

from .utils import Singleton

environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"
logger = getLogger()
logger.setLevel(ERROR)
console_handler = StreamHandler(stdout)
console_handler.setLevel(ERROR)
console_handler.setFormatter(Formatter("%(name)s - %(levelname)s - %(message)s"))
logger.addHandler(console_handler)

load_dotenv()
neo4j_uri = getenv("NEO4J_URI", "bolt://localhost:7687")
neo4j_user = getenv("NEO4J_USER", "neo4j")
neo4j_password = getenv("NEO4J_PASSWORD")
api_key = getenv("GEMINI_API_KEY")


class GraphRAG(Singleton):
    graphiti: Any
    api_key = api_key
    model = "gemini-2.5-flash-lite"
    thinking_budget = 512
    embedding_model = "gemini-embedding-001"
    embedding_dim = 3072

    @staticmethod
    async def init(clear: bool = False) -> "GraphRAG":
        obj = GraphRAG()
        if not hasattr(obj, "graphiti"):
            obj.graphiti = Graphiti(
                neo4j_uri,
                neo4j_user,
                neo4j_password,
                llm_client=GeminiClient(
                    config=LLMConfig(api_key=obj.api_key, model=obj.model),
                    thinking_config=ThinkingConfig(
                        thinking_budget=obj.thinking_budget,
                    ),
                ),
                embedder=GeminiEmbedder(
                    config=GeminiEmbedderConfig(
                        api_key=obj.api_key,
                        embedding_dim=obj.embedding_dim,
                        embedding_model=obj.embedding_model,
                    )
                ),
                cross_encoder=GeminiRerankerClient(
                    config=LLMConfig(api_key=obj.api_key, model=obj.model)
                ),
            )
            if clear:
                await obj.clear()
            else:
                await obj.init_graph()
        return obj

    async def init_graph(self) -> None:
        await self.graphiti.build_indices_and_constraints()

    async def clear(self) -> None:
        await clear_data(self.graphiti.driver)
        await self.init_graph()
