"""Tool template."""

from json import dumps
from os import getenv

from httpx import AsyncClient
from langchain.tools import tool

DESCRIPTION = "Wiki search and article retrieval, enabling discovery and fetching of encyclopedic information from Wiki articles."

OWNED_API = getenv("GROKIPEDIA_API_URL", "https://grokipedia-api.rphi.xyz").rstrip("/")


@tool
async def wiki_search(
    query: str, action: str = "smart", slug: str | None = None, max_results: int = 2
) -> str:
    """Search wiki and retrieve articles. Actions: 'smart' (search+fetch top N results), 'search' (slugs only), 'page' (citations/metadata by slug), 'content' (full text by slug). Args: query (topic/term), action (default: smart), slug (for page/content), max_results (default: 2)."""
    try:
        # ACTION: Get specific page by slug
        if action == "page" and slug:
            url = f"https://grokipedia.com/api/page?slug={slug}&includeContent=false&validateLinks=true"
            async with AsyncClient() as client:
                response = await client.get(url, timeout=30.0)

                if response.status_code == 429:
                    return dumps({"error": "Rate limit exceeded", "slug": slug})

                response.raise_for_status()
                data = response.json()

            if not data.get("found", False):
                return dumps({"error": "Page not found", "slug": slug})

            page_data = data.get("page", {})
            citations = [
                {
                    "id": c.get("id", ""),
                    "title": c.get("title", ""),
                    "url": c.get("url", ""),
                }
                for c in page_data.get("citations", [])[:10]
            ]

            return dumps(
                {
                    "action": "page",
                    "slug": slug,
                    "citations": citations,
                    "categories": page_data.get("metadata", {}).get("categories", []),
                    "stats": page_data.get("stats", {}),
                }
            )

        # ACTION: Get full content by slug
        if action == "content" and slug:
            url = f"{OWNED_API}/page/{slug}"
            async with AsyncClient() as client:
                response = await client.get(url, timeout=30.0)

                if response.status_code == 429:
                    return dumps({"error": "Rate limit exceeded", "slug": slug})

                response.raise_for_status()
                data = response.json()

            return dumps(
                {
                    "action": "content",
                    "title": data.get("title", ""),
                    "slug": data.get("slug", ""),
                    "url": data.get("url", ""),
                    "content_text": data.get("content_text", ""),
                    "word_count": data.get("word_count", 0),
                    "char_count": data.get("char_count", 0),
                }
            )

        # ACTION: Search (either just search, or smart search with details)
        # Step 1: Search
        search_url = f"https://grokipedia.com/api/full-text-search?query={query}&limit=11&offset=0"
        async with AsyncClient() as client:
            response = await client.get(search_url, timeout=30.0)

            if response.status_code == 429:
                return dumps({"error": "Rate limit exceeded", "query": query})

            response.raise_for_status()
            search_data = response.json()

        search_results = [
            {
                "slug": item.get("slug", ""),
                "title": item.get("title", ""),
                "snippet": item.get("snippet", "")
                .replace("<em>", "")
                .replace("</em>", ""),
                "relevanceScore": item.get("relevanceScore", 0),
            }
            for item in search_data.get("results", [])
        ]

        if action == "search":
            return dumps(
                {
                    "action": "search",
                    "query": query,
                    "results": search_results,
                    "totalCount": search_data.get("totalCount", 0),
                }
            )

        # Smart mode - fetch full content for top results
        if not search_results:
            return dumps(
                {"action": "smart", "query": query, "message": "No results found"}
            )

        # Fetch full content for top N results
        detailed_results = []
        async with AsyncClient() as client:
            for result in search_results[:max_results]:
                try:
                    content_response = await client.get(
                        f"{OWNED_API}/page/{result['slug']}",
                        timeout=30.0,
                    )
                    if content_response.status_code == 200:
                        content_data = content_response.json()
                        detailed_results.append(
                            {
                                "slug": result["slug"],
                                "title": content_data.get("title", result["title"]),
                                "snippet": result["snippet"],
                                "relevanceScore": result["relevanceScore"],
                                "content_preview": content_data.get("content_text", "")[
                                    :500
                                ]
                                + "...",
                                "word_count": content_data.get("word_count", 0),
                                "url": content_data.get("url", ""),
                            }
                        )
                    elif content_response.status_code == 429:
                        result["error"] = "Rate limit exceeded"
                        detailed_results.append(result)
                    else:
                        detailed_results.append(result)
                except Exception as e:
                    result["error"] = str(e)
                    detailed_results.append(result)

        return dumps(
            {
                "action": "smart",
                "query": query,
                "results": detailed_results,
                "totalFound": search_data.get("totalCount", 0),
                "showing": len(detailed_results),
            }
        )

    except Exception as e:
        return dumps({"error": str(e), "query": query, "action": action})
