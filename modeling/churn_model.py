"""Modèle de churn (POO : encapsule préparation, entraînement, évaluation et explicabilité).

Deux modèles comparables derrière la même interface :
- "logistique" : régression logistique, référence simple et interprétable ;
- "xgboost"    : gradient boosting, plus performant, expliqué avec SHAP.
"""

from pathlib import Path

import duckdb
import joblib
import numpy as np
import pandas as pd
import shap
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

CIBLE = "churn"
# customer_id : identifiant ; montant_total ≈ ancienneté × montant mensuel (redondant, vu dans l'EDA)
A_EXCLURE = ["customer_id", "montant_total", CIBLE]

# Rattachement des variables Kaggle aux 4 motifs des avis (le "pont" du projet)
MOTIFS_VARIABLES = {
    "resiliation": ["contrat"],
    "reseau": ["internet", "lignes_multiples"],
    "facturation": ["montant_mensuel", "paiement", "facture_dematerialisee"],
    "service_client": ["support_technique"],
}


def charger_donnees(db_path: Path | str = "data/telco360.duckdb") -> pd.DataFrame:
    """Lit la table dbt stg_churn (lecture seule : ne bloque pas les autres scripts)."""
    with duckdb.connect(str(db_path), read_only=True) as con:
        return con.sql("SELECT * FROM stg_churn").df()


def preparer_X_y(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Variables explicatives numériques (booléens en 0/1, catégories en indicatrices) et cible."""
    X = df.drop(columns=[c for c in A_EXCLURE if c in df.columns])
    X = X.astype({c: int for c in X.select_dtypes("bool").columns})
    # drop_first : une modalité de référence par variable, évite la colinéarité parfaite en logistique
    X = pd.get_dummies(X, drop_first=True, dtype=int)
    return X, df[CIBLE].astype(int)


def motif_de(variable: str) -> str:
    """Motif auquel appartient une variable (ex. 'contrat_mensuel' -> 'resiliation'), sinon 'autre'."""
    for motif, prefixes in MOTIFS_VARIABLES.items():
        if any(variable == p or variable.startswith(p + "_") for p in prefixes):
            return motif
    return "autre"


def importance_par_motif(shap_values: pd.DataFrame) -> pd.Series:
    """Part (en %) de l'importance SHAP totale (moyenne des |SHAP|) portée par chaque motif."""
    importance = shap_values.abs().mean()
    par_motif = importance.groupby(importance.index.map(motif_de)).sum()
    return (100 * par_motif / par_motif.sum()).round(1).sort_values(ascending=False)


class ModeleChurn:
    """Prédit la probabilité de churn d'un client et explique la prédiction."""

    TYPES = ("logistique", "xgboost")

    def __init__(self, type_modele: str = "xgboost", seuil: float = 0.5, random_state: int = 42):
        if type_modele not in self.TYPES:
            raise ValueError(f"type_modele doit être parmi {self.TYPES}")
        self.type_modele = type_modele
        self.seuil = seuil
        self.random_state = random_state
        self.model = None
        self.colonnes: list[str] = []
        self._fond: pd.DataFrame | None = (
            None  # échantillon d'entraînement = population de référence pour SHAP
        )
        self._explainer = None  # SHAP, créé à la première explication

    def _construire(self, y: pd.Series):
        if self.type_modele == "logistique":
            # class_weight="balanced" : compense le déséquilibre (≈ 26 % de churn)
            return make_pipeline(StandardScaler(), LogisticRegression(class_weight="balanced", max_iter=2000))
        # scale_pos_weight = nb non-churn / nb churn : même idée que class_weight pour XGBoost
        return XGBClassifier(
            n_estimators=300,
            max_depth=4,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            scale_pos_weight=(y == 0).sum() / max((y == 1).sum(), 1),
            eval_metric="logloss",
            random_state=self.random_state,
        )

    def _aligner(self, X: pd.DataFrame) -> pd.DataFrame:
        """Mêmes colonnes, dans le même ordre qu'à l'entraînement (modalité absente -> 0)."""
        return X.reindex(columns=self.colonnes, fill_value=0)

    def train(self, X: pd.DataFrame, y: pd.Series) -> "ModeleChurn":
        self.colonnes = list(X.columns)
        self._fond = X.sample(min(len(X), 200), random_state=self.random_state)
        self.model = self._construire(y)
        self.model.fit(X, y)
        self._explainer = None
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Probabilité de churn de chaque client."""
        return self.model.predict_proba(self._aligner(X))[:, 1]

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """1 = va partir (probabilité >= seuil), 0 sinon."""
        return (self.predict_proba(X) >= self.seuil).astype(int)

    def evaluer(self, X: pd.DataFrame, y: pd.Series) -> dict:
        """Métriques adaptées à des classes déséquilibrées (l'accuracy seule serait trompeuse)."""
        proba = self.predict_proba(X)
        pred = (proba >= self.seuil).astype(int)
        return {
            "roc_auc": round(roc_auc_score(y, proba), 3),
            "pr_auc": round(average_precision_score(y, proba), 3),
            "recall": round(recall_score(y, pred), 3),
            "precision": round(precision_score(y, pred, zero_division=0), 3),
            "f1": round(f1_score(y, pred), 3),
        }

    def expliquer(self, X: pd.DataFrame) -> pd.DataFrame:
        """Valeurs SHAP : contribution de chaque variable à la prédiction de chaque client.

        > 0 : pousse vers le départ ; < 0 : retient le client.
        """
        X = self._aligner(X)
        if self._explainer is None:
            if self.type_modele == "xgboost":
                self._explainer = shap.TreeExplainer(self.model)
            else:  # logistique : SHAP linéaire sur les données standardisées,
                # par rapport aux clients d'entraînement (et non aux clients à expliquer)
                scaler, logit = self.model[0], self.model[-1]
                fond = pd.DataFrame(scaler.transform(self._fond), columns=self.colonnes)
                self._explainer = (shap.LinearExplainer(logit, fond), scaler)
        if self.type_modele == "xgboost":
            valeurs = self._explainer.shap_values(X)
        else:
            explainer, scaler = self._explainer
            valeurs = explainer.shap_values(pd.DataFrame(scaler.transform(X), columns=self.colonnes))
        return pd.DataFrame(valeurs, columns=self.colonnes, index=X.index)

    def expliquer_client(self, X_client: pd.DataFrame, top: int = 3) -> dict:
        """Probabilité de churn d'UN client + les `top` facteurs qui augmentent le plus son risque."""
        contributions = self.expliquer(X_client.head(1)).iloc[0].sort_values(ascending=False)
        facteurs = contributions[contributions > 0].head(top)
        return {
            "proba_churn": round(float(self.predict_proba(X_client.head(1))[0]), 3),
            "facteurs": [(variable, round(float(valeur), 3)) for variable, valeur in facteurs.items()],
        }

    def save(self, path: Path | str) -> None:
        joblib.dump(
            {
                "type_modele": self.type_modele,
                "seuil": self.seuil,
                "model": self.model,
                "colonnes": self.colonnes,
                "fond": self._fond,
            },
            path,
        )

    @classmethod
    def load(cls, path: Path | str) -> "ModeleChurn":
        d = joblib.load(path)
        obj = cls(type_modele=d["type_modele"], seuil=d["seuil"])
        obj.model, obj.colonnes, obj._fond = d["model"], d["colonnes"], d["fond"]
        return obj
