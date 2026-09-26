# Telco 360 — contexte projet

Projet portfolio, orienté **data engineer** (couvre aussi DS / ML / AI eng). Spec d'origine : `docs/enonce_telco_customer_360_fusion.ipynb`.
Communication : français, concis, informel. Modifs minimales, code simple et lisible. POO là où ça sert, fonctions ailleurs.

## Concept
- Couche avis (réelle) : avis clients Orange / SFR / Bouygues → enrichissement LLM (motif, sentiment) → analyses dbt → (plus tard) RAG.
- Couche churn : dataset Kaggle Telco Customer Churn → (plus tard) XGBoost + SHAP.
- Pont = 4 motifs : réseau, facturation, résiliation, service client. Avis et clients Kaggle ne sont PAS joignables (limite assumée).

## Environnement
- **uv** uniquement : `pyproject.toml` + `uv.lock`, Python 3.13 (`.python-version`). Pas de pip/pipenv/requirements.txt.
- Installer : `uv sync`. Lancer : `uv run ...` (pas besoin d'activer le venv).
- Ajouter une dépendance : `uv add x` (runtime) ou `uv add --dev x` (tests, lint, notebooks). N'ajouter que ce qui est réellement utilisé.
- Secrets dans `.env` (jamais commité, bloqué par pre-commit). Modèle dans `.env.example` : `LLM_API_KEY`, `LLM_MODEL`, `LLM_BASE_URL`.

## Commandes
- Ingestion : `uv run python -m ingestion.run`
- Enrichissement : `uv run python -m enrichment.run [--limit N]`
- dbt : `cd transform && uv run dbt build --profiles-dir .`
- Tests : `uv run pytest -q` · Lint : `uv run ruff check .` · Format : `uv run ruff format .`
- Base fictive (CI / tests dbt) : `uv run python -m scripts.seed_ci` (refuse de tourner si des données existent)
- Pipeline complet (Prefect) : `uv run python -m flows.pipeline [--limit N] [--serve]` · suivi : `uv run python -m flows.suivi`
- dbt : `uv run dbt deps` (1re fois), `dbt source freshness`, `dbt docs generate/serve`
- Docker : `docker compose build` puis `docker compose run --rm pipeline` (virtualisation désactivée sur le PC de Raouf : l'image est validée par la CI)

## Fait
- `ingestion/` : `AvisCollector` (abstrait, schéma commun) → `GooglePlayCollector` (google-play-scraper) et `AppStoreCollector` (flux RSS public Apple, fallback de tri mostrecent → mosthelpful). `run.py` charge la table DuckDB `raw_avis` (`data/telco360.duckdb`), clé (source, id), `INSERT OR IGNORE` = incrémental et idempotent. 2 450 avis.
- `enrichment/` : `EnrichisseurLLM` (client openai compatible, Mistral `ministral-8b-latest`), JSON motif + sentiment, valeurs hors liste ramenées à autre/neutre, arrêt net sur 429. Table `enriched_avis`, incrémentale. 2 450 avis enrichis.
- `transform/` (dbt-duckdb + dbt_utils) : staging (`stg_raw_avis`, `stg_enriched_avis`, `stg_churn` en table car lit le CSV Kaggle) → intermediate (`int_avis_enrichis`, incrémental) → marts (`mart_motifs_operateur`). Source freshness sur `ingested_at` / `enriched_at`. 31 tests de données dont un test métier SQL (`tests/`). 3 040 avis enrichis.
- `notebooks/01_eda_churn.ipynb` : EDA churn (7 043 clients, 26,5 % churn ; contrat mensuel 43 %, fibre 42 %, chèque électronique 45 %). Figure dans `docs/img/`.
- Qualité : 11 tests pytest sans réseau (monkeypatch), ruff (lint + format), pre-commit (ruff, garde-fous `.env` et gros fichiers).
- `flows/` : flow Prefect ingestion → enrichissement → dbt (retries sur l'ingestion) + table `pipeline_runs` (durée, statut, lignes, erreur).
- Docker : `Dockerfile` (python 3.13-slim + uv, deps de uv.lock sans dev, dbt deps), `.dockerignore` (pas de .env ni data), `docker-compose.yml` (data/ monté, .env au lancement).
- CI GitHub Actions : job qualite-et-tests (uv sync --locked → ruff → pytest → base fictive → dbt deps/build → freshness) + job docker (build de l'image).
- 14 tests pytest. README complet (architecture Mermaid, résultats, lancement, limites).

## Décisions / limites connues
- Reddit abandonné (création d'app bloquée, Responsible Builder Policy) → App Store à la place.
- Free : app_id introuvable sur les deux stores → ignoré. Flux Apple d'Orange souvent vide → Orange surtout couvert par Google Play.
- Biais d'échantillonnage : notes très différentes selon source / tri (ex. SFR 4,36 App Store vs 2,89 Google Play) → ne pas classer les opérateurs sur ces chiffres.
- Résultat clé : parmi les avis négatifs, réseau domine chez Bouygues / SFR, service client chez Orange ; résiliation quasi absente (2-4 %) → le départ se lit dans le contrat (données churn), pas dans les avis.
- openai ≥ 3 n'embarque plus httpx : ne jamais importer une lib non déclarée dans `pyproject.toml`.

## Plan (orientation data engineer)
- ✅ A. Fondations : uv, nettoyage du repo, ruff, pre-commit
- ✅ B. CI GitHub Actions
- ✅ C. Orchestration Prefect + `pipeline_runs`
- ✅ D. dbt rigoureux : couches, incrémental, freshness, dbt_utils, test métier, docs
- ✅ E. Docker (validé par la CI)
- ✅ F. README
- ⏭️ Ensuite : modèle churn (baseline logistique vs XGBoost, SHAP) dans `modeling/` (stub `ModeleChurn`), puis RAG, app Streamlit ; bonus : déploiement Azure ; option : couche bronze Parquet.
- À faire à la fin : guide HTML qui explique tout le projet simplement (préparation entretiens).
