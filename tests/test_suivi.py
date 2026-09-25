"""Tests du suivi des exécutions (pipeline_runs), sans Prefect ni réseau."""

import duckdb
import pytest

from flows.suivi import nouveau_run_id, suivre


def lire_runs(db):
    with duckdb.connect(str(db)) as con:
        return con.execute("SELECT etape, statut, lignes, erreur FROM pipeline_runs").fetchall()


def test_etape_reussie_enregistree(tmp_path):
    db = tmp_path / "test.duckdb"
    with suivre("run-1", "ingestion", db_path=db) as r:
        r["lignes"] = 42

    assert lire_runs(db) == [("ingestion", "succes", 42, None)]


def test_etape_en_echec_enregistree_et_erreur_remontee(tmp_path):
    db = tmp_path / "test.duckdb"
    with pytest.raises(ValueError), suivre("run-1", "dbt_build", db_path=db):
        raise ValueError("modèle cassé")

    [(etape, statut, lignes, erreur)] = lire_runs(db)
    assert (etape, statut, lignes) == ("dbt_build", "echec", None)
    assert "modèle cassé" in erreur


def test_run_ids_uniques():
    assert nouveau_run_id() != nouveau_run_id()
