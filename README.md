# Telco 360 — pipeline de données sur la voix du client télécom

![CI](https://github.com/raoufRahmani/Telco-360/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.13-blue)
![dbt](https://img.shields.io/badge/dbt-duckdb-orange)

Pipeline de données **de bout en bout** : collecte de vrais avis clients d'opérateurs télécom français
(Orange, SFR, Bouygues), enrichissement par **LLM** (motif + sentiment), modélisation **dbt**,
orchestration **Prefect**, le tout testé, conteneurisé et vérifié en **CI**.
Par-dessus : un **RAG** qui répond aux questions en citant les avis, un **modèle de churn** expliqué par SHAP
(dataset Kaggle) et une **application Streamlit** qui réunit le tout.

> **La question métier :** de quoi se plaignent vraiment les clients télécom, et est-ce que ces plaintes
> rejoignent les facteurs qui font partir les clients ?

---

## Architecture

```mermaid
flowchart LR
    GP[Google Play] --> ING
    AS[App Store<br/>flux RSS Apple] --> ING
    ING[ingestion/<br/>collecteurs POO<br/>incrémental + retry] --> RAW[(raw_avis)]
    RAW --> ENR[enrichment/<br/>LLM Mistral<br/>motif + sentiment]
    ENR --> ENRT[(enriched_avis)]
    RAW --> STG
    ENRT --> STG
    CSV[CSV Kaggle<br/>Telco Churn] --> STGC

    subgraph DBT[dbt · DuckDB]
        STG[staging<br/>stg_raw_avis · stg_enriched_avis] --> INT[intermediate<br/>int_avis_enrichis<br/>incrémental]
        INT --> MART[marts<br/>mart_motifs_operateur]
        STGC[staging<br/>stg_churn]
    end

    INT --> EMB[rag/<br/>mistral-embed]
    EMB --> VEC[(avis_embeddings)]
    VEC --> RAG[MoteurRAG<br/>cosinus SQL + LLM]
    STGC --> ML[modeling/<br/>logistique vs XGBoost<br/>SHAP]
    RAG --> APP[[app Streamlit]]
    MART --> APP
    ML --> APP

    PREFECT{{Prefect<br/>flows/pipeline.py}} -.orchestre.-> ING
    PREFECT -.-> ENR
    PREFECT -.-> DBT
    PREFECT -.-> EMB
    PREFECT -.trace.-> RUNS[(pipeline_runs)]
```

Toutes les tables vivent dans un seul fichier **DuckDB** (`data/telco360.duckdb`).

---

## Stack

| Besoin | Outil | Pourquoi |
|---|---|---|
| Environnement | **uv** (`pyproject.toml` + `uv.lock`) | installation reproductible, versions verrouillées |
| Stockage | **DuckDB** | base analytique en un fichier, SQL rapide, zéro serveur |
| Ingestion | Python (POO), `google-play-scraper`, flux RSS Apple, `tenacity` | sources hétérogènes derrière une interface commune |
| Enrichissement | LLM **Mistral** via client `openai` compatible | changer de fournisseur (Mistral, Azure OpenAI, Groq…) = changer le `.env` |
| Transformation | **dbt** (dbt-duckdb, dbt_utils) | SQL versionné, testé, documenté |
| RAG | **mistral-embed** + similarité cosinus dans **DuckDB** | pas de base vectorielle en plus : vecteurs et filtres au même endroit |
| Application | **Streamlit** | démonstration interactive en un fichier Python |
| Machine learning | **scikit-learn**, **XGBoost**, **SHAP** | baseline interprétable vs boosting, explications par client |
| Orchestration | **Prefect** | pipeline en une commande, retries, planification |
| Qualité | **pytest**, **ruff**, **pre-commit** | tests sans réseau, lint + format automatiques |
| CI | **GitHub Actions** | chaque push : lint, tests, dbt build, build Docker |
| Conteneur | **Docker** + Compose | le pipeline tourne partout de la même façon |

---

## Ce que fait le pipeline

1. **Ingestion** (`ingestion/`) — une classe abstraite `AvisCollector` impose un schéma commun ;
   `GooglePlayCollector` et `AppStoreCollector` en héritent. Chargement **incrémental et idempotent**
   dans `raw_avis` (clé `source + id`, `INSERT OR IGNORE`) : relancer n'ajoute que les nouveaux avis.
2. **Enrichissement LLM** (`enrichment/`) — chaque avis reçoit un **motif** (réseau, facturation,
   résiliation, service client, autre) et un **sentiment**, en JSON contrôlé (valeurs hors liste ramenées
   à `autre` / `neutre`). Incrémental, arrêt propre en cas de limite de requêtes (429).
3. **Transformation dbt** (`transform/`) — trois couches :
   - **staging** : nettoyage, un modèle par source ;
   - **intermediate** : `int_avis_enrichis`, jointure avis + LLM, **modèle incrémental** ;
   - **marts** : `mart_motifs_operateur`, table d'analyse finale.
4. **Orchestration** (`flows/`) — un flow Prefect enchaîne les trois étapes ; chaque étape écrit une ligne
   dans **`pipeline_runs`** (durée, statut, lignes ajoutées, erreur) : on sait toujours ce qui a tourné.
5. **Vectorisation** (`rag/run.py`) — chaque avis enrichi devient un vecteur de 1 024 dimensions
   (`mistral-embed`), stocké dans la table DuckDB `avis_embeddings`. Incrémental, par lots, arrêt propre sur 429.

![Lignage dbt](docs/img/dbt_lineage.png)

---

## Résultats clés

**Avis clients** — part de chaque motif parmi les avis **négatifs** (échantillon de 2 450 avis, sept. 2026) :

| Opérateur | Réseau | Service client | Facturation | Résiliation | Autre (appli…) |
|---|---|---|---|---|---|
| Bouygues | **31,7 %** | 15,1 % | 17,7 % | 1,6 % | 33,9 % |
| Orange | 20,0 % | **21,9 %** | 15,7 % | 2,6 % | 39,9 % |
| SFR | **27,1 %** | 17,2 % | 18,0 % | 3,9 % | 33,8 % |

- Le **réseau** domine les plaintes chez Bouygues et SFR, le **service client** chez Orange.
- Réseau et facturation ont les **pires notes** (≈ 1,9 à 2,4 / 5).
- La **résiliation** n'apparaît presque jamais (2 à 4 %) : les clients qui partent ne laissent pas d'avis.

**Churn** (dataset Kaggle, 7 043 clients, 26,5 % de churn) — `notebooks/01_eda_churn.ipynb` :

| Facteur | Plus risqué | Moins risqué |
|---|---|---|
| Contrat | mensuel **43 %** | 2 ans **3 %** |
| Ancienneté | 0-6 mois **53 %** | 49-72 mois **10 %** |
| Internet | fibre **42 %** | sans internet **7 %** |
| Paiement | chèque électronique **45 %** | carte auto **15 %** |

**Le lien entre les deux :** les 4 motifs des avis se retrouvent dans les facteurs de churn
(contrat → résiliation, fibre → réseau, paiement → facturation, support technique → service client).
L'intention de partir ne se lit pas dans les avis mais dans le **contrat** : les deux sources sont complémentaires.

![Churn par variable](docs/img/churn_par_variable.png)

### Modèle de churn — `modeling/churn_model.py`, `notebooks/02_modele_churn.ipynb`

Classe `ModeleChurn` : même interface pour une **régression logistique** (baseline) et **XGBoost**,
déséquilibre des classes compensé (`class_weight` / `scale_pos_weight`), explications **SHAP** par client.

| Modèle | ROC-AUC (CV 5 plis) | ROC-AUC test | PR-AUC | Rappel | Précision |
|---|---|---|---|---|---|
| Régression logistique | 0,845 ± 0,012 | 0,838 | 0,628 | 0,773 | 0,506 |
| XGBoost | 0,842 ± 0,011 | 0,839 | 0,651 | 0,775 | 0,519 |

- **XGBoost ≈ logistique** : sur ce dataset, le signal est surtout linéaire. XGBoost gagne un peu en PR-AUC,
  la logistique reste plus simple à expliquer. On garde les deux, comparés honnêtement.
- On détecte **~3 partants sur 4** (rappel 0,77), au prix d'une fausse alerte sur deux : acceptable
  pour une campagne de rétention peu coûteuse.
- Facteurs SHAP principaux : contrat mensuel, faible ancienneté, montant mensuel élevé, fibre.

![Courbes ROC et PR](docs/img/modele_courbes.png)
![Importance SHAP](docs/img/shap_importance.png)

### Le pont : ce qui fait partir vs ce dont on se plaint

Part de chaque motif dans le **signal de churn** (importance SHAP, XGBoost) et dans les **plaintes** (avis négatifs) :

| Motif | Poids dans le churn | Part des plaintes |
|---|---|---|
| Résiliation (contrat) | **40,9 %** | 4,3 % |
| Facturation | 33,9 % | 26,1 % |
| Réseau | 20,3 % | **40,2 %** |
| Service client | 4,9 % | 29,5 % |

**Lecture :** ce qui fait partir les clients (engagement contractuel, prix) n'est **pas** ce dont ils se
plaignent le plus (réseau, service client). La **facturation** est le seul motif fort des deux côtés :
c'est le levier prioritaire. Les avis mesurent l'irritation, le contrat mesure le risque de départ —
deux sources complémentaires, pas redondantes.

![Pont motifs](docs/img/pont_motifs.png)

### RAG — interroger les avis en langage naturel (`rag/engine.py`)

`MoteurRAG` vectorise la question, retrouve les 8 avis les plus proches (similarité cosinus calculée en SQL
par DuckDB, filtrable par opérateur et par motif), puis fait répondre le LLM **uniquement** à partir de ces avis,
en les citant `[n]`.

```text
$ uv run python -m rag.engine "Pourquoi les clients se plaignent du réseau ?"
Les clients se plaignent principalement de la qualité instable du réseau [2, 3, 4, 5, 6, 7] :
coupures fréquentes [4], connexions défaillantes [3], zones inaccessibles depuis des mois [7]...
[2] orange · reseau · 1/5 · sim 0.83   réseau toujours aussi pourri, par contre les factures augmentent
...
$ uv run python -m rag.engine "Quelle est la recette de la tarte aux pommes ?"
Je ne sais pas : les avis disponibles ne permettent pas de répondre à cette question.
```

**Garde-fous :** (1) aucun avis assez proche → « je ne sais pas » sans appeler le LLM ; (2) le prompt interdit
d'inventer et impose les citations ; (3) seuls les avis **réellement cités** sont renvoyés comme sources.
**Constat mesuré :** avec `mistral-embed`, les similarités sont tassées (≈ 0,80-0,83 pour une question pertinente,
encore ≈ 0,77-0,79 hors sujet) : un seuil seul ne suffit pas, c'est le garde-fou du prompt qui tranche.

### Application Streamlit (`app.py`)

Trois onglets : **interroger les avis** (RAG avec sources dépliables), **motifs par opérateur** (mart dbt),
**risque de churn** (clients les plus à risque, facteurs SHAP rattachés aux motifs).

![App — RAG](docs/img/app_rag.png)
![App — churn](docs/img/app_churn.png)

---

## Qualité et fiabilité

- **35 tests pytest**, sans réseau ni clé API (sources, LLM et embeddings simulés, modèle entraîné sur des clients fictifs).
- **31 tests de données dbt** : unicité, valeurs autorisées, intégrité référentielle, bornes (`dbt_utils`)
  et un **test métier** SQL (les parts de motifs somment à 100 % par opérateur).
- **Fraîcheur des sources** : alerte si l'ingestion n'a pas tourné depuis 2 jours, erreur au-delà de 7.
- **CI GitHub Actions** à chaque push : `uv sync --locked` → ruff → pytest → dbt build sur une base fictive
  → fraîcheur → build de l'image Docker.
- **pre-commit** : ruff à chaque commit + garde-fous (interdiction de commiter `.env`, blocage des gros fichiers).
- **Secrets** hors du code et hors de l'image Docker (`.env`, passé au lancement).

---

## Lancer le projet

### Prérequis
- [uv](https://docs.astral.sh/uv/) (installe aussi Python 3.13)
- une clé API LLM (ex. Mistral, offre gratuite) pour l'enrichissement
- le CSV [Telco Customer Churn](https://www.kaggle.com/datasets/blastchar/telco-customer-churn)
  (`WA_Fn-UseC_-Telco-Customer-Churn.csv`) à placer dans `data/`

### Installation
```bash
git clone https://github.com/raoufRahmani/Telco-360.git
cd Telco-360
uv sync
cp .env.example .env        # puis renseigner LLM_API_KEY
```

### Pipeline complet (ingestion → LLM → dbt → vectorisation)
```bash
uv run python -m flows.pipeline              # une exécution
uv run python -m flows.pipeline --limit 50   # enrichit au plus 50 nouveaux avis
uv run python -m flows.pipeline --serve      # planifié tous les jours à 6h
uv run python -m flows.suivi                 # derniers runs (pipeline_runs)
```

### Étape par étape
```bash
uv run python -m ingestion.run
uv run python -m enrichment.run
cd transform && uv run dbt deps && uv run dbt build --profiles-dir .
uv run dbt source freshness --profiles-dir .
uv run dbt docs generate --profiles-dir . && uv run dbt docs serve --profiles-dir .
cd ..
uv run python -m rag.run                     # vectorise les avis (mistral-embed)
```

### RAG et application
```bash
uv run python -m rag.engine "Que disent les clients des conseillers ?" --operateur sfr
uv run streamlit run app.py                  # http://localhost:8501
```
Le modèle de churn utilisé par l'app est sauvegardé par `notebooks/02_modele_churn.ipynb` (`data/modele_churn.joblib`).

### Avec Docker
```bash
docker compose build
docker compose run --rm pipeline                       # un run complet
docker compose run --rm pipeline python -m flows.suivi
```
Les données restent sur la machine (`./data` monté dans le conteneur) et la clé API vient du `.env`.

### Tests et qualité
```bash
uv run pytest -q
uv run ruff check . && uv run ruff format --check .
```

---

## Structure

```
ingestion/     collecteurs d'avis (Google Play, App Store) + chargement DuckDB
enrichment/    enrichissement LLM (motif, sentiment)
transform/     projet dbt : staging → intermediate → marts, tests, sources
flows/         orchestration Prefect + suivi des runs (pipeline_runs)
modeling/      modèle de churn (logistique vs XGBoost, SHAP)
rag/           vectorisation des avis + MoteurRAG (réponses sourcées)
app.py         application Streamlit
notebooks/     EDA churn, modèle de churn
scripts/       base fictive pour la CI
tests/         tests pytest (sans réseau)
docs/          énoncé du projet, figures
```

---

## Choix techniques et limites

- **Reddit abandonné** : la création d'app pour l'API officielle est fermée aux projets personnels
  (Responsible Builder Policy) → remplacé par les avis App Store.
- **Free** absent : application introuvable de façon fiable sur les stores.
- **Biais d'échantillonnage** : Google Play ne donne que les avis les plus récents, et le flux Apple varie
  selon le tri (parfois vide pour Orange). Les chiffres décrivent un **instantané**, pas un classement
  des opérateurs.
- **Classification LLM** par un petit modèle gratuit : quelques erreurs sur les avis ambigus ou ironiques.
- **Pas de jointure client** entre avis et dataset Kaggle (clients américains, anonymes) : le lien se fait
  par **motif**, au niveau des tendances.
- **RAG** : la recherche est purement sémantique (pas de mots-clés) et les scores `mistral-embed` sont peu
  discriminants ; une recherche hybride (BM25 + vecteurs) ou un reranker améliorerait la précision.
- **DuckDB** = un seul processus écrivain à la fois : adapté à ce volume, à remplacer par un entrepôt
  (ex. Azure, BigQuery) pour un usage multi-utilisateurs.

---

## Suite du projet

- [x] Modèle de churn : baseline régression logistique vs **XGBoost**, explicabilité **SHAP**
- [x] **RAG** sur les avis : questions en langage naturel, réponses sourcées
- [x] Application **Streamlit**
- [ ] Déploiement **Azure** (stockage Blob pour la couche brute, job planifié)

---

**Auteur :** Abderraouf Rahmani — M2 MoSEF, Université Paris 1 Panthéon-Sorbonne
