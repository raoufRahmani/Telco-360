# Telco 360 — contexte projet

Projet portfolio (data science / ML / data eng / AI eng). Spec complète : `docs/enonce_telco_customer_360_fusion.ipynb`.
Communication : français, concis, informel. Préférer des modifs minimales et du code simple et lisible.

## Concept
- Couche 1 (structurée) : dataset Kaggle Telco Customer Churn → XGBoost + SHAP.
- Couche 2 (non structurée) : vrais avis clients Orange / SFR / Bouygues (/ Free) → enrichissement LLM (motif, sentiment) → embeddings + RAG.
- Pont entre les couches = 4 motifs : réseau, facturation, résiliation, service client. Les avis ne peuvent PAS être joints aux customerID Kaggle (limite assumée).
- Stack : Azure en colonne vertébrale, alternatives locales gratuites (DuckDB, Ollama/API gratuite, Prefect, Streamlit).
- POO là où ça sert (collecteurs, enricher, moteur RAG, modèle churn) ; fonctions simples ailleurs.

## Fait
- `ingestion/base.py` : `AvisCollector` abstrait, schéma commun `id, source, operateur, note, texte, date, ingested_at`.
- `ingestion/google_play.py` : `GooglePlayCollector` (google-play-scraper, 500 avis les plus récents / appli, retry tenacity).
- `ingestion/app_store.py` : `AppStoreCollector` (flux RSS public Apple, 10 pages × 50 max). Fallback de tri `mostrecent` → `mosthelpful` car le flux est parfois vide.
- `ingestion/run.py` : lance les 2 collecteurs → table DuckDB `raw_avis` dans `data/telco360.duckdb`, clé (source, id), `INSERT OR IGNORE` (incrémental, idempotent). Lancer : `python -m ingestion.run`.
- Tests pytest sans réseau (monkeypatch) dans `tests/` : `python -m pytest -q tests/`.
- Premier run : 2 450 avis en base.

## Décisions / limites connues
- Reddit abandonné : création d'app bloquée par la Responsible Builder Policy (2025). Remplacé par l'App Store.
- Free : app_id non trouvé sur les deux stores → `None`, ignoré avec warning.
- App Store Orange : flux Apple instable (parfois vide, parfois 400 avis).
- Biais d'échantillonnage : notes très différentes selon source/tri (ex. SFR 4,36 App Store vs 2,89 Google Play) → ne pas classer les opérateurs sur ces chiffres ; à documenter.

## Prochaine étape
- Enrichissement LLM (`enrichment/enricher.py`) : motif (4 classes + autre) et sentiment par avis, depuis `raw_avis`. Clé API à choisir (Groq / Mistral gratuits, ou Azure OpenAI).
- Ensuite : transform (dbt), churn, RAG, app Streamlit.
