"""Moteur RAG (POO : vector store + LLM encapsulés) avec citations et garde-fous."""


class MoteurRAG:
    """Répond aux questions sur les avis en citant ses sources."""

    def __init__(self, vector_store, llm):
        self.vector_store = vector_store
        self.llm = llm

    def repondre(self, question: str, operateur: str | None = None,
                 motif: str | None = None) -> dict:
        """Retrieve (filtré) -> génère -> retourne réponse + avis sources.

        Garde-fou : si aucun contexte pertinent, le dire au lieu d'inventer.
        """
        ...
