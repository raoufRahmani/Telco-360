"""Test de l'AppStoreCollector sans appel réseau (le flux Apple est simulé)."""

from ingestion.app_store import AppStoreCollector
from ingestion.base import AvisCollector


def _avis(id_, note, titre, texte):
    return {
        "id": {"label": id_},
        "im:rating": {"label": str(note)},
        "title": {"label": titre},
        "content": {"label": texte},
        "updated": {"label": "2026-09-20T10:00:00-07:00"},
    }


FAKE_PAGE = [
    {"id": {"label": "app"}, "title": {"label": "Fiche appli"}},  # pas un avis -> ignoré
    _avis("r1", 1, "Facturation", "Prélevé deux fois"),
    _avis("r1", 1, "Facturation", "Prélevé deux fois"),  # doublon
    _avis("r2", 5, "Top", "Appli rapide"),
]


def test_collect_schema_dedup_et_pagination(monkeypatch):
    col = AppStoreCollector(["sfr"], nb_pages=3)
    # page 1 = avis, page 2 = vide -> la boucle doit s'arrêter
    monkeypatch.setattr(
        col, "_fetch_page", lambda app_id, page, sort="mostrecent": FAKE_PAGE if page == 1 else []
    )

    df = col.collect()

    assert list(df.columns) == AvisCollector.SCHEMA
    assert len(df) == 2
    assert set(df["source"]) == {"app_store"}
    assert df.loc[df["id"] == "r1", "texte"].item() == "Facturation. Prélevé deux fois"


def test_operateur_sans_app_id_est_ignore():
    df = AppStoreCollector(["free"]).collect()
    assert df.empty
    assert list(df.columns) == AvisCollector.SCHEMA


def test_bascule_sur_mosthelpful_si_mostrecent_vide(monkeypatch):
    col = AppStoreCollector(["sfr"], nb_pages=1)
    # comme SFR en vrai : mostrecent vide, mosthelpful rempli
    monkeypatch.setattr(
        col, "_fetch_page", lambda app_id, page, sort="mostrecent": FAKE_PAGE if sort == "mosthelpful" else []
    )
    assert len(col.collect()) == 2


def test_flux_vide_partout_est_ignore(monkeypatch):
    col = AppStoreCollector(["orange"])
    monkeypatch.setattr(col, "_fetch_page", lambda app_id, page, sort="mostrecent": [])
    df = col.collect()
    assert df.empty
    assert list(df.columns) == AvisCollector.SCHEMA
