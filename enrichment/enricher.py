"""Enrichissement des avis par LLM (motif, sentiment) — sortie JSON."""

import json

from openai import OpenAI, RateLimitError
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

PROMPT = """Tu analyses un avis client laissé sur l'application d'un opérateur télécom français.
Réponds UNIQUEMENT avec un JSON de la forme {{"motif": "...", "sentiment": "..."}}.

motif = un seul parmi {motifs} :
- reseau : couverture, débit, coupures, 4G/5G, fibre, box
- facturation : prix, facture, prélèvement, hausse de tarif, remboursement
- resiliation : résilier, partir, changer d'opérateur, portabilité
- service_client : conseillers, SAV, temps d'attente, réponses du support
- autre : l'appli elle-même (bug, connexion, ergonomie), avis vide ou hors sujet

sentiment = un seul parmi {sentiments}."""


class EnrichisseurLLM:
    """Encapsule le client LLM, le prompt et le contrôle de la réponse JSON.

    Utilise le client OpenAI, compatible avec Mistral, Groq, Azure OpenAI ou Ollama :
    on change de fournisseur juste avec base_url + model dans le .env.
    """

    MOTIFS = ["reseau", "facturation", "resiliation", "service_client", "autre"]
    SENTIMENTS = ["positif", "neutre", "negatif"]

    def __init__(self, model: str, api_key: str | None = None, base_url: str | None = None, client=None):
        self.model = model
        self.client = client or OpenAI(api_key=api_key, base_url=base_url)
        self.prompt = PROMPT.format(motifs=self.MOTIFS, sentiments=self.SENTIMENTS)

    # pas de retry sur 429 (limite de requêtes) : le client openai réessaie déjà, puis run.py s'arrête
    @retry(
        retry=retry_if_not_exception_type(RateLimitError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=2, max=30),
    )
    def enrichir(self, texte: str) -> dict:
        """Retourne {motif, sentiment}. Retenté 3 fois si l'appel ou le JSON plante."""
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": self.prompt},
                {"role": "user", "content": texte[:2000]},  # on coupe les pavés
            ],
            response_format={"type": "json_object"},
            temperature=0,  # même avis -> même réponse
        )
        data = json.loads(resp.choices[0].message.content)

        # le LLM peut inventer une valeur : on la ramène à une valeur autorisée
        motif, sentiment = data.get("motif"), data.get("sentiment")
        return {
            "motif": motif if motif in self.MOTIFS else "autre",
            "sentiment": sentiment if sentiment in self.SENTIMENTS else "neutre",
        }
