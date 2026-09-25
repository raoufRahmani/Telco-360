"""Tests de l'enrichissement sans réseau : le LLM est simulé."""
import json
from types import SimpleNamespace

import duckdb

from enrichment.enricher import EnrichisseurLLM
from enrichment.run import run


class FakeClient:
    """Imite client.chat.completions.create() et renvoie une réponse fixe."""

    def __init__(self, reponse: dict):
        contenu = json.dumps(reponse)
        message = SimpleNamespace(content=contenu)
        self.chat = SimpleNamespace(completions=SimpleNamespace(
            create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(message=message)])
        ))


def test_enrichir_reponse_valide():
    e = EnrichisseurLLM("fake", client=FakeClient({"motif": "facturation", "sentiment": "negatif"}))
    assert e.enrichir("Prélevé deux fois !") == {"motif": "facturation", "sentiment": "negatif"}


def test_enrichir_valeurs_inventees_ramenees_aux_valeurs_autorisees():
    e = EnrichisseurLLM("fake", client=FakeClient({"motif": "prix", "sentiment": "furieux"}))
    assert e.enrichir("...") == {"motif": "autre", "sentiment": "neutre"}


def test_run_incremental(tmp_path):
    db = tmp_path / "test.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE raw_avis (id VARCHAR, source VARCHAR, texte VARCHAR, date TIMESTAMP)")
        con.execute("""INSERT INTO raw_avis VALUES
            ('1', 'google_play', 'Réseau coupé', '2026-09-01'),
            ('2', 'google_play', 'Conseiller top', '2026-09-02'),
            ('3', 'app_store',  'Trop cher',    '2026-09-03')""")

    e = EnrichisseurLLM("fake", client=FakeClient({"motif": "reseau", "sentiment": "negatif"}))
    assert run(db, e, limit=2, pause=0) == 2  # limite respectée
    assert run(db, e, pause=0) == 1           # seulement celui qui restait
    assert run(db, e, pause=0) == 0           # tout est déjà fait

    with duckdb.connect(str(db)) as con:
        assert con.execute("SELECT count(*) FROM enriched_avis").fetchone()[0] == 3


def test_run_s_arrete_sur_limite_429(tmp_path):
    from openai import RateLimitError

    class Client429:
        def __init__(self):
            def create(**kwargs):
                # erreur 429 créée sans objet HTTP : le test ne dépend pas de la lib HTTP interne d'openai
                raise RateLimitError.__new__(RateLimitError)
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))

    db = tmp_path / "test.duckdb"
    with duckdb.connect(str(db)) as con:
        con.execute("CREATE TABLE raw_avis (id VARCHAR, source VARCHAR, texte VARCHAR, date TIMESTAMP)")
        con.execute("INSERT INTO raw_avis VALUES ('1','gp','a','2026-09-01'), ('2','gp','b','2026-09-02')")

    assert run(db, EnrichisseurLLM("fake", client=Client429()), pause=0) == 0  # arrêt net, pas de boucle
