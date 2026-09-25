"""Crée une petite base DuckDB + un faux CSV Kaggle pour faire tourner dbt en CI.

Pas de réseau, pas de clé API : des données fictives mais au bon format,
pour vérifier que les modèles dbt se construisent et que leurs tests passent.

Usage : uv run python -m scripts.seed_ci
"""

import csv
import random
from pathlib import Path

import duckdb

from enrichment.run import CREATE_TABLE as CREATE_ENRICHED
from ingestion.run import CREATE_TABLE as CREATE_RAW
from ingestion.run import DB_PATH

CSV_PATH = Path("data/WA_Fn-UseC_-Telco-Customer-Churn.csv")
COLONNES_KAGGLE = [
    "customerID", "gender", "SeniorCitizen", "Partner", "Dependents", "tenure",
    "PhoneService", "MultipleLines", "InternetService", "OnlineSecurity", "OnlineBackup",
    "DeviceProtection", "TechSupport", "StreamingTV", "StreamingMovies", "Contract",
    "PaperlessBilling", "PaymentMethod", "MonthlyCharges", "TotalCharges", "Churn",
]  # fmt: skip


def creer_avis(con: duckdb.DuckDBPyConnection, n: int = 60) -> None:
    """Remplit raw_avis et enriched_avis avec des avis fictifs."""
    con.execute(CREATE_RAW)
    con.execute(CREATE_ENRICHED)
    for i in range(n):
        source = random.choice(["google_play", "app_store"])
        operateur = random.choice(["orange", "sfr", "bouygues"])
        con.execute(
            "INSERT INTO raw_avis VALUES (?, ?, ?, ?, ?, '2026-09-20 10:00:00', now())",
            [f"ci-{i}", source, operateur, random.randint(1, 5), f"avis fictif {i}"],
        )
        con.execute(
            "INSERT INTO enriched_avis VALUES (?, ?, ?, ?, 'fake', now())",
            [
                source,
                f"ci-{i}",
                random.choice(["reseau", "facturation", "resiliation", "service_client", "autre"]),
                random.choice(["positif", "neutre", "negatif"]),
            ],
        )


def creer_csv_kaggle(n: int = 60) -> None:
    """Écrit un faux CSV au format Kaggle, avec ses pièges (TotalCharges vide, 'No internet service')."""
    with CSV_PATH.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(COLONNES_KAGGLE)
        for i in range(n):
            internet = random.choice(["DSL", "Fiber optic", "No"])
            telephone = random.choice(["Yes", "No"])
            anciennete = 0 if i < 3 else random.randint(1, 72)

            def service(internet=internet):
                return "No internet service" if internet == "No" else random.choice(["Yes", "No"])

            w.writerow([
                f"{i:04d}-CI", random.choice(["Male", "Female"]), random.choice(["0", "1"]),
                random.choice(["Yes", "No"]), random.choice(["Yes", "No"]), anciennete, telephone,
                "No phone service" if telephone == "No" else random.choice(["Yes", "No"]),
                internet, service(), service(), service(), service(), service(), service(),
                random.choice(["Month-to-month", "One year", "Two year"]), random.choice(["Yes", "No"]),
                random.choice(["Electronic check", "Mailed check",
                               "Bank transfer (automatic)", "Credit card (automatic)"]),
                f"{random.uniform(18, 118):.2f}",
                " " if anciennete == 0 else f"{random.uniform(18, 8000):.2f}",
                random.choice(["Yes", "No"]),
            ])  # fmt: skip


if __name__ == "__main__":
    # garde-fou : ne jamais écraser les vraies données (base réelle ou vrai CSV Kaggle)
    for chemin in (DB_PATH, CSV_PATH):
        if chemin.exists():
            raise SystemExit(f"{chemin} existe déjà : ce script est réservé à la CI (données fictives).")

    random.seed(42)  # données identiques à chaque exécution
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with duckdb.connect(str(DB_PATH)) as con:
        creer_avis(con)
    creer_csv_kaggle()
    print(f"Base CI créée : {DB_PATH} + {CSV_PATH}")
