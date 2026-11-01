from typing import Any

import httpx

from .base import SensitiveTool


class WebSearch(SensitiveTool):
    name = "web_search"
    description = (
        "Search the web for information or pages requested by the user, especially "
        "when a current fact or source URL is needed. Start with concise, neutral "
        "keywords; narrow the search only when the user provides a constraint or "
        "the results justify one. Returns page titles, URLs, and excerpts. Use the "
        "results as evidence and include relevant source links in the answer."
    )

    def __init__(self, base_url: str) -> None:
        if not base_url.strip():
            raise ValueError("base_url must not be empty")

        self.base_url = base_url.strip().rstrip("/")
        self.parameters_schema = {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Concise search keywords, without unverified assumptions",
                }
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> str:
        query = kwargs.get("query")
        if not isinstance(query, str) or not query.strip():
            return "Error: query must be a non-empty string"
        query = query.strip()

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=10.0
            ) as client:
                response = await client.get(
                    "/search", params={"q": query, "format": "json"}
                )
                response.raise_for_status()
                data = response.json()
        except httpx.RequestError:
            return "Error: search service is unavailable."
        except httpx.HTTPStatusError as exc:
            return f"Error: search service returned HTTP {exc.response.status_code}."
        except ValueError:
            return "Error: search service returned invalid JSON."
        if not isinstance(data, dict) or not isinstance(data.get("results"), list):
            return "Error: search service returned invalid results."

        lines = []
        for item in data["results"][:5]:
            if not isinstance(item, dict):
                return "Error: search service returned invalid results."

            title = item.get("title", "")
            url = item.get("url", "")
            excerpt = item.get("content", "")

            if not isinstance(title, str) or not isinstance(url, str):
                return "Error: search service returned invalid results."
            if not title or not url:
                continue
            if not isinstance(excerpt, str):
                excerpt = ""

            lines.append(f"{title}\nURL: {url}\nExtrait: {excerpt}")

        return "\n\n".join(lines) if lines else "Aucun résultat trouvé."
