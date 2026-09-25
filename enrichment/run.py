"""Enrichit par LLM les avis de raw_avis pas encore traités -> table enriched_avis.

Usage : python -m enrichment.run --limit 20   (sans --limit : tous les avis restants)
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

from .enricher import EnrichisseurLLM

logger = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS enriched_avis (
    source      VARCHAR,
    id          VARCHAR,
    motif       VARCHAR,
    sentiment   VARCHAR,
    model       VARCHAR,
    enriched_at TIMESTAMPTZ,
    PRIMARY KEY (source, id)
)
"""

# Avis de raw_avis qui ne sont pas encore dans enriched_avis (les plus récents d'abord)
A_FAIRE = """
SELECT r.source, r.id, r.texte
FROM raw_avis r
WHERE NOT EXISTS (
    SELECT 1 FROM enriched_avis e WHERE e.source = r.source AND e.id = r.id
)
ORDER BY r.date DESC
"""


def run(
    db_path: Path = DB_PATH,
    enrichisseur: EnrichisseurLLM | None = None,
    limit: int | None = None,
    pause: float = 1.0,
) -> int:
    """Enrichit les avis restants, un par un. Retourne le nb d'avis enrichis."""
    if enrichisseur is None:
        load_dotenv()
        enrichisseur = EnrichisseurLLM(
            model=os.environ["LLM_MODEL"],
            api_key=os.environ["LLM_API_KEY"],
            base_url=os.getenv("LLM_BASE_URL"),
        )

    with duckdb.connect(str(db_path)) as con:
        con.execute(CREATE_TABLE)
        requete = A_FAIRE + (f" LIMIT {int(limit)}" if limit else "")
        a_faire = con.execute(requete).fetchall()
        logger.info("%d avis à enrichir", len(a_faire))

        n = 0
        for source, id_, texte in a_faire:
            try:
                res = enrichisseur.enrichir(texte or "")
            except RateLimitError as e:  # 429 : inutile d'insister sur les avis suivants
                logger.error("Limite de requêtes du LLM atteinte (429), arrêt : %s", e)
                break
            except Exception as e:  # un avis qui plante ne bloque pas les autres
                logger.warning("Avis %s/%s ignoré : %s", source, id_, e)
                continue
            # insertion au fil de l'eau : si on coupe le script, rien n'est perdu
            con.execute(
                "INSERT INTO enriched_avis VALUES (?, ?, ?, ?, ?, now())",
                [source, id_, res["motif"], res["sentiment"], enrichisseur.model],
            )
            n += 1
            if n % 50 == 0:
                logger.info("%d / %d", n, len(a_faire))
            time.sleep(pause)  # respecte la limite de requêtes du tier gratuit

    logger.info("%d avis enrichis", n)
    return n


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # masque le log de chaque requête HTTP
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="nb max d'avis à traiter")
    run(limit=parser.parse_args().limit)
