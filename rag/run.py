"""Vectorise les avis enrichis pas encore traités -> table avis_embeddings.

Usage : uv run python -m rag.run --limit 100   (sans --limit : tous les avis restants)
Prérequis : dbt build a tourné (la source est le modèle dbt int_avis_enrichis).
"""

import argparse
import logging
import os
import time
from pathlib import Path

import duckdb
from dotenv import load_dotenv
from openai import RateLimitError

from ingestion.run import DB_PATH

from .embeddings import Vectoriseur

logger = logging.getLogger(__name__)

# FLOAT[] = liste de nombres : le vecteur est stocké directement dans DuckDB, pas besoin de base vectorielle
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS avis_embeddings (
    avis_key    VARCHAR PRIMARY KEY,
    model       VARCHAR,
    embedding   FLOAT[],
    embedded_at TIMESTAMPTZ
)
"""

# Avis enrichis (non vides) qui n'ont pas encore de vecteur, les plus récents d'abord
A_FAIRE = """
SELECT a.avis_key, a.texte
FROM int_avis_enrichis a
WHERE coalesce(trim(a.texte), '') <> ''
  AND NOT EXISTS (SELECT 1 FROM avis_embeddings e WHERE e.avis_key = a.avis_key)
ORDER BY a.date_avis DESC
"""


def run(
    db_path: Path = DB_PATH,
    vectoriseur: Vectoriseur | None = None,
    limit: int | None = None,
    taille_lot: int = 32,
    pause: float = 1.0,
) -> int:
    """Vectorise les avis restants par lots. Retourne le nb d'avis vectorisés."""
    if vectoriseur is None:
        load_dotenv()
        vectoriseur = Vectoriseur(
            model=os.getenv("EMBED_MODEL", "mistral-embed"),
            api_key=os.environ["LLM_API_KEY"],
            base_url=os.getenv("LLM_BASE_URL"),
        )

    with duckdb.connect(str(db_path)) as con:
        con.execute(CREATE_TABLE)
        requete = A_FAIRE + (f" LIMIT {int(limit)}" if limit else "")
        a_faire = con.execute(requete).fetchall()
        logger.info("%d avis à vectoriser", len(a_faire))

        n = 0
        for i in range(0, len(a_faire), taille_lot):
            lot = a_faire[i : i + taille_lot]
            try:
                vecteurs = vectoriseur.vectoriser([texte for _, texte in lot])
            except RateLimitError as e:  # 429 : on garde ce qui est fait, on reprendra au prochain run
                logger.error("Limite de requêtes atteinte (429), arrêt : %s", e)
                break
            # insertion lot par lot : si on coupe le script, les lots déjà faits sont gardés
            con.executemany(
                "INSERT INTO avis_embeddings VALUES (?, ?, ?, now())",
                [[cle, vectoriseur.model, v] for (cle, _), v in zip(lot, vecteurs, strict=True)],
            )
            n += len(lot)
            logger.info("%d / %d", n, len(a_faire))
            time.sleep(pause)  # respecte la limite de requêtes du tier gratuit

    logger.info("%d avis vectorisés", n)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    for nom in ("httpx", "httpx2"):
        logging.getLogger(nom).setLevel(logging.WARNING)  # masque le log de chaque requête HTTP
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="nb max d'avis à vectoriser")
    run(limit=parser.parse_args().limit)
