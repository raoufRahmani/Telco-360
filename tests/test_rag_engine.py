"""Tests du moteur RAG sans réseau : embeddings et LLM simulés, mini base DuckDB."""

from types import SimpleNamespace

import duckdb
import pytest

from rag.engine import NE_SAIS_PAS, MoteurRAG, citations

# Vecteurs jouets à 3 dimensions : [réseau, facturation, service client]
VECTEURS = {
    "reseau": [1.0, 0.0, 0.0],
    "facture": [0.0, 1.0, 0.0],
    "conseiller": [0.0, 0.0, 1.0],
}


class FakeVectoriseur:
    """Vecteur = celui du premier mot-clé trouvé dans le texte (sinon un vecteur "hors sujet")."""

    model = "fake-embed"

    def vectoriser(self, textes):
        return [
            next((v for mot, v in VECTEURS.items() if mot in t.lower()), [-1.0, -1.0, -1.0]) for t in textes
        ]


class FakeLLM:
    """Imite client.chat.completions.create() et garde les messages reçus pour les vérifier."""

    def __init__(self, reponse: str = "Réponse [1]."):
        self.reponse = reponse
        self.messages = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, model, messages, **kwargs):
        self.messages = messages
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reponse))])


@pytest.fixture
def db(tmp_path):
    chemin = tmp_path / "test.duckdb"
    avis = [  # avis_key, operateur, motif, texte, vecteur
        ("gp:1", "sfr", "reseau", "Plus de réseau depuis une semaine", VECTEURS["reseau"]),
        ("gp:2", "orange", "reseau", "Réseau coupé tous les soirs", [0.9, 0.1, 0.0]),
        ("as:3", "sfr", "facturation", "Facture doublée sans prévenir", VECTEURS["facture"]),
        ("as:4", "bouygues", "service_client", "Conseiller très aimable", VECTEURS["conseiller"]),
    ]
    with duckdb.connect(str(chemin)) as con:
        con.execute("""CREATE TABLE int_avis_enrichis (avis_key VARCHAR, operateur VARCHAR, source VARCHAR,
                       motif VARCHAR, sentiment VARCHAR, note INT, texte VARCHAR, date_avis TIMESTAMP)""")
        con.execute(
            "CREATE TABLE avis_embeddings (avis_key VARCHAR, model VARCHAR, embedding FLOAT[], embedded_at TIMESTAMPTZ)"
        )
        for cle, op, motif, texte, v in avis:
            con.execute(
                "INSERT INTO int_avis_enrichis VALUES (?, ?, 'google_play', ?, 'negatif', 1, ?, '2026-09-01')",
                [cle, op, motif, texte],
            )
            con.execute("INSERT INTO avis_embeddings VALUES (?, 'fake-embed', ?, now())", [cle, v])
    return chemin


def moteur(db, llm=None, **kwargs):
    return MoteurRAG(FakeVectoriseur(), llm or FakeLLM(), "fake-llm", db_path=db, **kwargs)


def test_rechercher_classe_par_similarite(db):
    avis = moteur(db).rechercher("Problème de reseau ?")
    assert list(avis["avis_key"]) == ["gp:1", "gp:2"]  # les 2 avis réseau, le plus proche d'abord
    assert avis["similarite"].is_monotonic_decreasing


def test_rechercher_filtres(db):
    assert list(moteur(db).rechercher("reseau", operateur="orange")["avis_key"]) == ["gp:2"]
    assert moteur(db).rechercher("reseau", motif="facturation").empty  # aucun avis réseau classé facturation


def test_repondre_cite_ses_sources(db):
    llm = FakeLLM()
    res = moteur(db, llm).repondre("Que disent les clients du reseau ?")
    assert res["reponse"] == "Réponse [1]."
    assert [s["numero"] for s in res["sources"]] == [1]  # 2 avis donnés au LLM, seul le [1] est cité
    # le contexte envoyé au LLM est numéroté
    assert "[1] (sfr, reseau, note 1/5) Plus de réseau" in llm.messages[1]["content"]


def test_repondre_je_ne_sais_pas_sans_appeler_le_llm(db):
    llm = FakeLLM()
    res = moteur(db, llm).repondre("Quelle est la météo demain ?")  # hors sujet : aucun avis assez proche
    assert res == {"reponse": NE_SAIS_PAS, "sources": []}
    assert llm.messages is None  # garde-fou : le LLM n'a pas été appelé


def test_k_limite_le_contexte(db):
    assert len(moteur(db, k=1).rechercher("reseau")) == 1


def test_repondre_llm_dit_je_ne_sais_pas_aucune_source(db):
    res = moteur(db, FakeLLM(NE_SAIS_PAS)).repondre("reseau")
    assert res == {"reponse": NE_SAIS_PAS, "sources": []}


def test_citations():
    assert citations("Coupures [2, 5] et lenteurs [7], [2].") == {2, 5, 7}
    assert citations("Pas de citation.") == set()
