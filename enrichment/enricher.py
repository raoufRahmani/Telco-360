"""Enrichissement des avis par LLM (motif, sentiment, entités) — sortie JSON."""


class EnrichisseurLLM:
    """Encapsule le client LLM, le prompt et le parsing structuré (idempotent)."""

    MOTIFS = ["reseau", "facturation", "resiliation", "service_client", "autre"]

    def __init__(self, model: str):
        self.model = model

    def enrichir(self, texte: str) -> dict:
        """Retourne {motif, sentiment, entites} en JSON validé (retry si invalide)."""
        ...
