from sensai.domain.protocols import EmbeddingProvider, VectorStore
from sensai.memory.rag.chunker import TextChunker


class RAGRetriever:
    """Index local documents and retrieve relevant context for a query."""

    def __init__(self, provider: EmbeddingProvider, store: VectorStore):
        self.provider = provider
        self.store = store

    async def index_directory(
        self, path: str, chunker: TextChunker | None = None
    ) -> int:
        """Embed and atomically replace the index with the directory contents."""
        chunker = chunker or TextChunker()
        chunks = chunker.chunk_documents(chunker.ingest_directory(path))
        dimension = None
        for start in range(0, len(chunks), 32):
            batch = chunks[start : start + 32]
            embeddings = await self.provider.embed_texts(
                [chunk.text for chunk in batch]
            )
            if len(embeddings) != len(batch):
                raise ValueError(
                    "Embedding provider returned the wrong number of vectors"
                )
            for chunk, embedding in zip(batch, embeddings):
                if not embedding or (
                    dimension is not None and len(embedding) != dimension
                ):
                    raise ValueError("Embedding provider returned incompatible vectors")
                dimension = len(embedding)
                chunk.embedding = embedding

        self.store.replace_chunks(chunks)
        return len(chunks)

    async def retrieve_context(self, query: str, top_k: int = 5) -> str:
        """Embed a query, search the index, and format matching chunks."""
        embeddings = await self.provider.embed_texts([query])
        if len(embeddings) != 1:
            raise ValueError("Embedding provider returned the wrong number of vectors")
        scored_chunks = self.store.search(embeddings[0], top_k=top_k)
        return "\n\n".join(
            f"--- Source: {chunk.metadata.get('path', chunk.metadata.get('filename', 'unknown'))} ---\n{chunk.text}"
            for chunk in scored_chunks
        )
