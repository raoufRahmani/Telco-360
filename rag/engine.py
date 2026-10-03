"""Moteur RAG : retrouve les avis proches d'une question, puis fait répondre le LLM en citant ses sources.

Usage :
    uv run python -m rag.engine "Pourquoi les clients se plaignent du réseau ?"
    uv run python -m rag.engine "Que disent les clients des conseillers ?" --operateur sfr --motif service_client
"""

import argparse
import os
import re
from pathlib import Path

import duckdb
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from ingestion.run import DB_PATH

from .embeddings import Vectoriseur

NE_SAIS_PAS = "Je ne sais pas : les avis disponibles ne permettent pas de répondre à cette question."

PROMPT = f"""Tu es analyste de la relation client chez un opérateur télécom français.
Réponds à la question en français, en 3 à 6 phrases, en t'appuyant UNIQUEMENT sur les avis clients fournis.
Chaque avis est numéroté [1], [2]... : cite entre crochets les numéros des avis qui appuient chaque idée.
N'invente rien. Si les avis ne permettent pas de répondre, réponds exactement : "{NE_SAIS_PAS}" """

# Similarité cosinus calculée directement en SQL par DuckDB (pas de base vectorielle à part).
# Les filtres opérateur / motif viennent de l'enrichissement LLM (modèle dbt int_avis_enrichis).
RECHERCHE = """
SELECT a.avis_key, a.operateur, a.source, a.motif, a.sentiment, a.note, a.texte, a.date_avis,
       list_cosine_similarity(e.embedding, $vecteur::FLOAT[]) AS similarite
FROM avis_embeddings e
JOIN int_avis_enrichis a USING (avis_key)
WHERE ($operateur IS NULL OR a.operateur = $operateur)
  AND ($motif IS NULL OR a.motif = $motif)
ORDER BY similarite DESC
LIMIT $k
"""


def citations(reponse: str) -> set[int]:
    """Numéros cités entre crochets : "[2]", "[2, 5]" ou "[2], [5]" -> {2, 5}."""
    return {int(n) for groupe in re.findall(r"\[([\d,\s]+)\]", reponse) for n in re.findall(r"\d+", groupe)}


class MoteurRAG:
    """Répond aux questions sur les avis en citant ses sources.

    Garde-fous :
    (1) aucun avis au-dessus du seuil de similarité -> "je ne sais pas" sans appeler le LLM ;
    (2) le prompt interdit d'inventer : c'est lui qui filtre vraiment le hors-sujet (voir `seuil`) ;
    (3) on ne renvoie que les avis réellement cités, et aucun si le LLM répond "je ne sais pas".
    """

    def __init__(
        self,
        vectoriseur: Vectoriseur,
        llm_client,
        llm_model: str,
        db_path: Path | str = DB_PATH,
        k: int = 8,
        seuil: float = 0.75,
    ):
        self.vectoriseur = vectoriseur
        self.llm_client = llm_client
        self.llm_model = llm_model
        self.db_path = db_path
        self.k = k  # nb d'avis donnés au LLM
        # Avec mistral-embed, les scores sont tassés : mesuré sur nos avis, ~0,80-0,83 pour une question
        # pertinente et encore ~0,77-0,79 pour une question hors sujet. Le seuil n'écarte donc que
        # l'évident ; le tri fin du hors-sujet est fait par le LLM (garde-fou 2).
        self.seuil = seuil

    def rechercher(
        self, question: str, operateur: str | None = None, motif: str | None = None
    ) -> pd.DataFrame:
        """Les k avis les plus proches de la question (filtrés), du plus au moins similaire."""
        vecteur = self.vectoriseur.vectoriser([question])[0]
        params = {"vecteur": vecteur, "operateur": operateur, "motif": motif, "k": self.k}
        with duckdb.connect(str(self.db_path), read_only=True) as con:  # lecture seule : ne bloque personne
            avis = con.execute(RECHERCHE, params).df()
        return avis[avis["similarite"] >= self.seuil].reset_index(drop=True)

    def repondre(self, question: str, operateur: str | None = None, motif: str | None = None) -> dict:
        """Retourne {"reponse": texte avec citations [n], "sources": avis numérotés utilisés comme contexte}."""
        avis = self.rechercher(question, operateur, motif)
        if avis.empty:  # garde-fou 1 : rien de pertinent -> pas d'appel au LLM, pas d'invention possible
            return {"reponse": NE_SAIS_PAS, "sources": []}

        contexte = "\n".join(
            f"[{i}] ({a.operateur}, {a.motif}, note {a.note}/5) {a.texte}"
            for i, a in enumerate(avis.itertuples(), start=1)
        )
        resp = self.llm_client.chat.completions.create(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": f"Avis clients :\n{contexte}\n\nQuestion : {question}"},
            ],
            temperature=0,
        )
        reponse = resp.choices[0].message.content.strip()
        sources = avis.assign(numero=range(1, len(avis) + 1))
        if NE_SAIS_PAS in reponse:  # le LLM a jugé les avis hors sujet : on n'affiche pas de sources
            sources = sources.iloc[0:0]
        elif cites := citations(reponse):  # garde-fou 3 : seulement les avis cités dans la réponse
            sources = sources[sources["numero"].isin(cites)]
        return {
            "reponse": reponse,
            "sources": sources[
                ["numero", "operateur", "source", "motif", "note", "texte", "similarite"]
            ].to_dict("records"),
        }

    @classmethod
    def depuis_env(cls, **kwargs) -> "MoteurRAG":
        """Construit le moteur à partir du .env (même clé Mistral pour les embeddings et le LLM)."""
        load_dotenv()
        api_key, base_url = os.environ["LLM_API_KEY"], os.getenv("LLM_BASE_URL")
        return cls(
            vectoriseur=Vectoriseur(os.getenv("EMBED_MODEL", "mistral-embed"), api_key, base_url),
            llm_client=OpenAI(api_key=api_key, base_url=base_url),
            llm_model=os.environ["LLM_MODEL"],
            **kwargs,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--operateur", choices=["orange", "sfr", "bouygues"])
    parser.add_argument(
        "--motif", choices=["reseau", "facturation", "resiliation", "service_client", "autre"]
    )
    args = parser.parse_args()

    res = MoteurRAG.depuis_env().repondre(args.question, args.operateur, args.motif)
    print("\n" + res["reponse"] + "\n")
    for s in res["sources"]:
        print(f"[{s['numero']}] {s['operateur']} · {s['motif']} · {s['note']}/5 · sim {s['similarite']:.2f}")
        print(f"    {s['texte'][:200]}")
