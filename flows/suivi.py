"""Suivi des exécutions du pipeline dans la table DuckDB `pipeline_runs` (observabilité).

Chaque étape d'un run écrit une ligne : quand, combien de temps, succès ou échec, nb de lignes.
Afficher les derniers runs : uv run python -m flows.suivi
"""

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from ingestion.run import DB_PATH

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id   VARCHAR,
    etape    VARCHAR,
    debut    TIMESTAMPTZ,
    fin      TIMESTAMPTZ,
    duree_s  DOUBLE,
    statut   VARCHAR,   -- 'succes' ou 'echec'
    lignes   INTEGER,   -- nb de lignes ajoutées par l'étape (si pertinent)
    erreur   VARCHAR
)
"""


def nouveau_run_id() -> str:
    """Identifiant lisible et unique : date-heure UTC + suffixe aléatoire."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]


@contextmanager
def suivre(run_id: str, etape: str, db_path: Path = DB_PATH) -> Iterator[dict]:
    """Enregistre une étape dans pipeline_runs, qu'elle réussisse ou échoue.

    Usage :
        with suivre(run_id, "ingestion") as r:
            r["lignes"] = ingerer()
    """
    resultat = {"lignes": None}
    debut, t0 = datetime.now(UTC), time.perf_counter()
    statut, erreur = "succes", None
    try:
        yield resultat
    except Exception as e:
        statut, erreur = "echec", f"{type(e).__name__}: {e}"[:500]
        raise  # l'erreur remonte quand même : le suivi ne la cache pas
    finally:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(db_path)) as con:
            con.execute(CREATE_TABLE)
            con.execute(
                "INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    run_id,
                    etape,
                    debut,
                    datetime.now(UTC),
                    round(time.perf_counter() - t0, 2),
                    statut,
                    resultat["lignes"],
                    erreur,
                ],
            )


if __name__ == "__main__":
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        print(
            con.sql(
                "SELECT run_id, etape, debut, duree_s, statut, lignes, erreur "
                "FROM pipeline_runs ORDER BY debut DESC LIMIT 20"
            )
        )
