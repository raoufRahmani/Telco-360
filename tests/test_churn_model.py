"""Tests de ModeleChurn sur un petit jeu de clients fictif (pas besoin du CSV Kaggle)."""

import numpy as np
import pandas as pd
import pytest

from modeling.churn_model import ModeleChurn, importance_par_motif, motif_de, preparer_X_y


@pytest.fixture
def clients():
    """200 clients fictifs au format stg_churn, où le contrat mensuel fait vraiment partir."""
    rng = np.random.default_rng(0)
    n = 200
    contrat = rng.choice(["mensuel", "1_an", "2_ans"], n)
    df = pd.DataFrame(
        {
            "customer_id": [f"c{i}" for i in range(n)],
            "senior": rng.choice([True, False], n),
            "anciennete_mois": rng.integers(0, 72, n),
            "internet": rng.choice(["dsl", "fibre", "aucun"], n),
            "support_technique": rng.choice([True, False], n),
            "contrat": contrat,
            "paiement": rng.choice(["cheque_electronique", "carte_auto"], n),
            "montant_mensuel": rng.uniform(20, 110, n),
            "montant_total": rng.uniform(0, 8000, n),
        }
    )
    proba = np.where(contrat == "mensuel", 0.6, 0.1)
    df["churn"] = (rng.random(n) < proba).astype(int)
    return df


def test_preparer_X_y(clients):
    X, y = preparer_X_y(clients)
    assert "customer_id" not in X and "montant_total" not in X and "churn" not in X
    assert "contrat_mensuel" in X  # catégorie transformée en indicatrice
    assert X.dtypes.map(lambda t: t.kind in "if").all()  # tout est numérique
    assert set(y.unique()) <= {0, 1}


@pytest.mark.parametrize("type_modele", ["logistique", "xgboost"])
def test_train_predict_evaluer(clients, type_modele):
    X, y = preparer_X_y(clients)
    modele = ModeleChurn(type_modele).train(X, y)

    proba = modele.predict_proba(X)
    assert proba.shape == (len(X),) and ((proba >= 0) & (proba <= 1)).all()
    assert set(modele.evaluer(X, y)) == {"roc_auc", "pr_auc", "recall", "precision", "f1"}
    assert modele.evaluer(X, y)["roc_auc"] > 0.6  # le signal "contrat mensuel" est bien appris


@pytest.mark.parametrize("type_modele", ["logistique", "xgboost"])
def test_expliquer_client(clients, type_modele):
    X, y = preparer_X_y(clients)
    modele = ModeleChurn(type_modele).train(X, y)
    client_mensuel = X[X["contrat_mensuel"] == 1].head(1)

    res = modele.expliquer_client(client_mensuel, top=3)
    assert 0 <= res["proba_churn"] <= 1
    assert 1 <= len(res["facteurs"]) <= 3
    assert all(valeur > 0 for _, valeur in res["facteurs"])  # uniquement des facteurs de risque
    assert "contrat_mensuel" in [v for v, _ in res["facteurs"]]  # le vrai facteur est retrouvé


def test_colonnes_manquantes_alignees(clients):
    """Un client avec une modalité jamais vue ne doit pas faire planter la prédiction."""
    X, y = preparer_X_y(clients)
    modele = ModeleChurn("xgboost").train(X, y)
    assert modele.predict_proba(X.drop(columns=["contrat_mensuel"]).head(2)).shape == (2,)


@pytest.mark.parametrize("type_modele", ["logistique", "xgboost"])
def test_save_load(clients, tmp_path, type_modele):
    X, y = preparer_X_y(clients)
    modele = ModeleChurn(type_modele).train(X, y)
    modele.save(tmp_path / "m.joblib")
    recharge = ModeleChurn.load(tmp_path / "m.joblib")
    np.testing.assert_allclose(modele.predict_proba(X), recharge.predict_proba(X))
    # l'explication fonctionne aussi après rechargement
    assert (
        recharge.expliquer_client(X.head(1))["proba_churn"]
        == modele.expliquer_client(X.head(1))["proba_churn"]
    )


def test_importance_par_motif(clients):
    assert motif_de("contrat_mensuel") == "resiliation"
    assert motif_de("internet_fibre") == "reseau"
    assert motif_de("anciennete_mois") == "autre"

    X, y = preparer_X_y(clients)
    parts = importance_par_motif(ModeleChurn("xgboost").train(X, y).expliquer(X))
    assert abs(parts.sum() - 100) < 0.5
    assert parts.index[0] == "resiliation"  # le contrat porte le signal dans ces données fictives


def test_type_inconnu():
    with pytest.raises(ValueError):
        ModeleChurn("random_forest")
