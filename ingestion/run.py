"""Lance toutes les sources d'avis et les enregistre dans DuckDB (couche raw).

Usage : python -m ingestion.run
"""

import logging
from pathlib import Path

import duckdb
import pandas as pd

from .app_store import AppStoreCollector
from .google_play import GooglePlayCollector

logger = logging.getLogger(__name__)

DB_PATH = Path("data/telco360.duckdb")
OPERATEURS = ["orange", "sfr", "bouygues", "free"]

# Table brute : une ligne par avis, clé unique = (source, id)
CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS raw_avis (
    id          VARCHAR,
    source      VARCHAR,
    operateur   VARCHAR,
    note        INTEGER,
    texte       VARCHAR,
    date        TIMESTAMP,
    ingested_at TIMESTAMPTZ,
    PRIMARY KEY (source, id)
)
"""


def run(db_path: Path = DB_PATH, collectors: list | None = None) -> int:
    """Collecte les avis et ajoute les nouveaux dans raw_avis. Retourne le nb d'avis ajoutés."""
    if collectors is None:
        collectors = [GooglePlayCollector(OPERATEURS), AppStoreCollector(OPERATEURS)]

    df = pd.concat([c.collect() for c in collectors], ignore_index=True)
    # dates en UTC sans fuseau (Apple donne un fuseau, Google non)
    df["date"] = pd.to_datetime(df["date"], utc=True).dt.tz_localize(None)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(db_path)) as con:
        con.execute(CREATE_TABLE)
        avant = con.execute("SELECT count(*) FROM raw_avis").fetchone()[0]
        con.register("nouveaux", df)
        # OR IGNORE : un avis déjà en base (même source + id) n'est pas réinséré
        con.execute("INSERT OR IGNORE INTO raw_avis SELECT * FROM nouveaux")
        apres = con.execute("SELECT count(*) FROM raw_avis").fetchone()[0]

    ajoutes = apres - avant
    logger.info("%d avis collectés, %d nouveaux, %d en base", len(df), ajoutes, apres)
    return ajoutes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    run()
