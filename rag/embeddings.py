"""Vectorisation des avis : chaque texte devient un vecteur (embedding).

Deux textes au sens proche ont des vecteurs proches : c'est ce qui permettra au RAG
de retrouver les avis qui parlent de la même chose qu'une question, même avec d'autres mots.
"""

from openai import OpenAI, RateLimitError
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential


class Vectoriseur:
    """Encapsule le client d'embeddings (Mistral via le client openai compatible, comme l'enrichissement)."""

    def __init__(
        self,
        model: str = "mistral-embed",
        api_key: str | None = None,
        base_url: str | None = None,
        client=None,
    ):
        self.model = model
        self.client = client or OpenAI(api_key=api_key, base_url=base_url)

    # pas de retry sur 429 : run.py s'arrête proprement (même logique que l'enrichissement)
    @retry(
        retry=retry_if_not_exception_type(RateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=30),
    )
    def vectoriser(self, textes: list[str]) -> list[list[float]]:
        """Un vecteur par texte, dans le même ordre. Un seul appel API pour tout le lot."""
        resp = self.client.embeddings.create(
            model=self.model,
            input=[t[:1000] for t in textes],  # on coupe les pavés (limite de tokens par requête)
            encoding_format="float",  # le client openai demande du base64 par défaut, Mistral veut des floats
        )
        return [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
