from sensai.domain.protocols import EmbeddingProvider
from sensai.memory.rag.store import SQLiteVectorStore


class RAGRetriever:
    """Orchestrates embedding generation and vector search to retrieve context."""

    def __init__(self, provider: EmbeddingProvider, store: SQLiteVectorStore):
        self.provider = provider
        self.store = store

    async def retrieve_context(self, query: str, top_k: int = 5) -> str:
        """Embed a query, search the store, and format the top chunks as a context string."""
        embeddings = await self.provider.embed_texts([query])
        if not embeddings:
            return ""

        query_embedding = embeddings[0]
        scored_chunks = self.store.search(query_embedding, top_k=top_k)

        if not scored_chunks:
            return ""

        context_parts = []
        for chunk in scored_chunks:
            source = chunk.metadata.get("filename", "unknown")
            context_parts.append(f"--- Source: {source} ---\n{chunk.text}")

        return "\n\n".join(context_parts)
