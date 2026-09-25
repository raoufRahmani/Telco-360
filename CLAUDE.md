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
- Base fictive (CI / tests dbt) : `uv run python -m scripts.seed_ci`

## Fait
- `ingestion/` : `AvisCollector` (abstrait, schéma commun) → `GooglePlayCollector` (google-play-scraper) et `AppStoreCollector` (flux RSS public Apple, fallback de tri mostrecent → mosthelpful). `run.py` charge la table DuckDB `raw_avis` (`data/telco360.duckdb`), clé (source, id), `INSERT OR IGNORE` = incrémental et idempotent. 2 450 avis.
- `enrichment/` : `EnrichisseurLLM` (client openai compatible, Mistral `ministral-8b-latest`), JSON motif + sentiment, valeurs hors liste ramenées à autre/neutre, arrêt net sur 429. Table `enriched_avis`, incrémentale. 2 450 avis enrichis.
- `transform/` (dbt-duckdb) : `stg_avis` (vue), `stg_churn` (table, lit le CSV Kaggle dans `data/`), `mart_motifs_operateur` (table). 24 modèles + tests.
- `notebooks/01_eda_churn.ipynb` : EDA churn (7 043 clients, 26,5 % churn ; contrat mensuel 43 %, fibre 42 %, chèque électronique 45 %). Figure dans `docs/img/`.
- Qualité : 11 tests pytest sans réseau (monkeypatch), ruff (lint + format), pre-commit (ruff, garde-fous `.env` et gros fichiers).
- CI GitHub Actions (`.github/workflows/ci.yml`) : uv sync --locked → ruff → pytest → base fictive → dbt build.

## Décisions / limites connues
- Reddit abandonné (création d'app bloquée, Responsible Builder Policy) → App Store à la place.
- Free : app_id introuvable sur les deux stores → ignoré. Flux Apple d'Orange souvent vide → Orange surtout couvert par Google Play.
- Biais d'échantillonnage : notes très différentes selon source / tri (ex. SFR 4,36 App Store vs 2,89 Google Play) → ne pas classer les opérateurs sur ces chiffres.
- Résultat clé : parmi les avis négatifs, réseau domine chez Bouygues / SFR, service client chez Orange ; résiliation quasi absente (2-4 %) → le départ se lit dans le contrat (données churn), pas dans les avis.
- openai ≥ 3 n'embarque plus httpx : ne jamais importer une lib non déclarée dans `pyproject.toml`.

## Plan (orientation data engineer)
- ✅ A. Fondations : uv, nettoyage du repo, ruff, pre-commit
- ✅ B. CI GitHub Actions
- ⏭️ C. Orchestration (flow Prefect ingestion → enrichissement → dbt) + table `pipeline_runs` + logs ; option : couche bronze en Parquet partitionné
- D. dbt rigoureux : couche intermediate, modèles incrémentaux, source freshness, dbt_utils, dbt docs (lineage)
- E. Docker (Dockerfile + compose)
- F. README avec schéma d'architecture, installation (`uv sync`), modèle de données, limites
- Ensuite (plus léger) : modèle churn (baseline logistique vs XGBoost, SHAP), RAG, app Streamlit ; bonus : déploiement Azure.
