"""Test du GooglePlayCollector sans appel réseau (Google Play est simulé)."""

from datetime import datetime

from ingestion.base import AvisCollector
from ingestion.google_play import GooglePlayCollector

FAKE_REVIEWS = [
    {"reviewId": "a1", "score": 1, "content": "Réseau nul", "at": datetime(2026, 9, 1)},
    {"reviewId": "a1", "score": 1, "content": "Réseau nul", "at": datetime(2026, 9, 1)},  # doublon
    {"reviewId": "a2", "score": 4, "content": "Appli pratique", "at": datetime(2026, 9, 2)},
]


def test_collect_schema_et_dedup(monkeypatch):
    col = GooglePlayCollector(["orange"])
    monkeypatch.setattr(col, "_fetch", lambda app_id: FAKE_REVIEWS)

    df = col.collect()

    assert list(df.columns) == AvisCollector.SCHEMA
    assert len(df) == 2
    assert set(df["operateur"]) == {"orange"}
    assert set(df["source"]) == {"google_play"}


def test_operateur_sans_app_id_est_ignore():
    df = GooglePlayCollector(["free"]).collect()
    assert df.empty
    assert list(df.columns) == AvisCollector.SCHEMA
