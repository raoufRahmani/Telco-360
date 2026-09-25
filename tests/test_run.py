"""Test de run() sans réseau : faux collecteurs + base DuckDB temporaire."""

from datetime import UTC, datetime

import duckdb
import pandas as pd

from ingestion.base import AvisCollector
from ingestion.run import run


class FakeCollector(AvisCollector):
    """Collecteur bidon qui renvoie des avis écrits à la main."""

    def __init__(self, rows):
        super().__init__([])
        self.rows = rows

    def collect(self) -> pd.DataFrame:
        return self.normaliser(pd.DataFrame(self.rows))


NOW = datetime.now(UTC)
GP = [
    {
        "id": "g1",
        "source": "google_play",
        "operateur": "orange",
        "note": 1,
        "texte": "Réseau nul",
        "date": datetime(2026, 9, 1),
        "ingested_at": NOW,
    }
]
AS = [
    {
        "id": "a1",
        "source": "app_store",
        "operateur": "sfr",
        "note": 5,
        "texte": "Top. Rapide",
        "date": pd.Timestamp("2026-09-02T10:00:00-07:00"),
        "ingested_at": NOW,
    }
]


def test_run_insere_puis_ignore_les_doublons(tmp_path):
    db = tmp_path / "test.duckdb"
    collectors = [FakeCollector(GP), FakeCollector(AS)]

    assert run(db, collectors) == 2  # 1er passage : 2 avis ajoutés
    assert run(db, collectors) == 0  # 2e passage : rien de nouveau

    with duckdb.connect(str(db)) as con:
        rows = con.execute("SELECT source, operateur FROM raw_avis ORDER BY source").fetchall()
    assert rows == [("app_store", "sfr"), ("google_play", "orange")]
