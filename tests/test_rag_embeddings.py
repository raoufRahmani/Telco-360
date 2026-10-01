"""Tests de la vectorisation sans réseau : l'API d'embeddings est simulée."""

from types import SimpleNamespace

import duckdb
import pytest
from openai import RateLimitError

from rag.embeddings import Vectoriseur
from rag.run import run


class FakeClient:
    """Imite client.embeddings.create() : vecteur = [longueur du texte, 1.0, 0.0]."""

    def __init__(self, echec_au_appel: int | None = None):
        self.appels = 0
        self.echec_au_appel = echec_au_appel
        self.embeddings = SimpleNamespace(create=self._create)

    def _create(self, model, input, **kwargs):
        self.appels += 1
        if self.appels == self.echec_au_appel:
            raise RateLimitError.__new__(RateLimitError)  # 429 simulé, sans requête HTTP
        # renvoyé dans le désordre exprès : le Vectoriseur doit remettre les vecteurs dans l'ordre
        data = [SimpleNamespace(index=i, embedding=[float(len(t)), 1.0, 0.0]) for i, t in enumerate(input)]
        return SimpleNamespace(data=data[::-1])


@pytest.fixture
def db(tmp_path):
    """Mini int_avis_enrichis : 5 avis dont 1 vide."""
    chemin = tmp_path / "test.duckdb"
    with duckdb.connect(str(chemin)) as con:
        con.execute("CREATE TABLE int_avis_enrichis (avis_key VARCHAR, texte VARCHAR, date_avis TIMESTAMP)")
        con.execute("""INSERT INTO int_avis_enrichis VALUES
            ('gp:1', 'Réseau coupé', '2026-09-01'),
            ('gp:2', 'Conseiller top', '2026-09-02'),
            ('as:3', 'Trop cher', '2026-09-03'),
            ('as:4', 'Pas de 5G', '2026-09-04'),
            ('gp:5', '   ', '2026-09-05')""")
    return chemin


def test_vectoriser_garde_l_ordre():
    v = Vectoriseur(client=FakeClient())
    assert v.vectoriser(["ab", "abcd"]) == [[2.0, 1.0, 0.0], [4.0, 1.0, 0.0]]


def test_run_incremental(db):
    client = FakeClient()
    assert run(db, Vectoriseur(client=client), taille_lot=2, pause=0) == 4  # l'avis vide est ignoré
    assert client.appels == 2  # 4 avis par lots de 2
    assert run(db, Vectoriseur(client=client), pause=0) == 0  # relancer ne refait rien

    with duckdb.connect(str(db)) as con:
        vecteur = con.execute("SELECT embedding FROM avis_embeddings WHERE avis_key = 'as:3'").fetchone()[0]
    assert vecteur == [9.0, 1.0, 0.0]  # 'Trop cher' = 9 caractères


def test_run_limit(db):
    assert run(db, Vectoriseur(client=FakeClient()), limit=3, pause=0) == 3


def test_run_arret_sur_429_garde_les_lots_faits(db):
    # 1er lot OK, 2e lot -> 429 : on garde le 1er et on s'arrête sans planter
    assert run(db, Vectoriseur(client=FakeClient(echec_au_appel=2)), taille_lot=2, pause=0) == 2
    # au run suivant, seuls les avis restants sont traités
    assert run(db, Vectoriseur(client=FakeClient()), pause=0) == 2
