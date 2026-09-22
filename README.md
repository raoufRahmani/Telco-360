# Telco Customer 360 — Churn, Voix du Client & Rétention

Plateforme télécom end-to-end : prédiction de churn (ML), analyse de vrais avis
clients (NLP + RAG) et moteur de rétention, avec une app Streamlit déployée.

## Architecture en deux couches (reliées par le *motif*)

- **Couche client (structuré)** : dataset Kaggle Telco Churn → XGBoost + SHAP.
- **Couche voix du client (réel)** : avis Google Play + Reddit → enrichissement LLM
  (motif, sentiment, entités) → embeddings + RAG sourcé.

> Les deux couches ne partagent pas les mêmes individus : le lien se fait par
> **motif** (réseau, facturation, résiliation, service client), pas par client.

## Structure du repo

| Dossier | Rôle |
|---|---|
| `ingestion/` | Récupération des données (Kaggle, Google Play, Reddit) |
| `transform/` | Nettoyage / dbt |
| `modeling/`  | Modèle de churn (XGBoost, SHAP) |
| `enrichment/`| Analyse LLM des avis |
| `rag/`       | Moteur RAG |
| `app/`       | Application Streamlit |
| `tests/`     | Tests pytest |
| `flows/`     | Orchestration (Prefect / Azure Function) |
| `docs/`      | Schéma d'archi, captures |

## Démarrage

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # puis renseigne tes clés
```

## Stack

Python · pandas · DuckDB · scikit-learn · XGBoost · SHAP · google-play-scraper ·
praw · sentence-transformers · chromadb · Streamlit. Backbone cloud optionnel : Azure.
