"""Pipeline complet orchestré avec Prefect : ingestion -> enrichissement LLM -> dbt build -> vectorisation (RAG).

Usage :
    uv run python -m flows.pipeline              # une exécution complète
    uv run python -m flows.pipeline --limit 50   # enrichit au plus 50 nouveaux avis
    uv run python -m flows.pipeline --serve      # exécution planifiée chaque jour à 6h (laisser tourner)
"""

import argparse
import subprocess
from pathlib import Path

from prefect import flow, get_run_logger, task

from cloud import blob
from enrichment.run import run as enrichir_avis
from flows.suivi import nouveau_run_id, suivre
from ingestion.run import run as ingerer_avis
from rag.run import run as vectoriser_avis


@task(retries=2, retry_delay_seconds=30)
def recuperer_donnees() -> list[str]:
    """Dans Azure : base DuckDB + CSV Kaggle depuis Blob Storage (en local : ne fait rien)."""
    return blob.telecharger([blob.BASE, blob.CSV])


@task(retries=2, retry_delay_seconds=30)
def sauvegarder_donnees() -> list[str]:
    """Dans Azure : renvoie la base mise à jour vers Blob Storage (en local : ne fait rien)."""
    return blob.envoyer([blob.BASE])


@task(retries=2, retry_delay_seconds=60)  # Google Play / Apple peuvent échouer ponctuellement
def ingestion(run_id: str) -> int:
    with suivre(run_id, "ingestion") as r:
        r["lignes"] = ingerer_avis()
    return r["lignes"]


@task  # pas de retry : enrichment.run s'arrête déjà proprement sur limite de requêtes (429)
def enrichissement(run_id: str, limit: int | None) -> int:
    with suivre(run_id, "enrichissement") as r:
        r["lignes"] = enrichir_avis(limit=limit)
    return r["lignes"]


@task
def dbt_build(run_id: str) -> None:
    with suivre(run_id, "dbt_build"):
        if not Path("transform/dbt_packages").exists():  # 1er lancement : installe dbt_utils
            subprocess.run(["dbt", "deps"], cwd="transform", check=True)
        # check=True : si un modèle ou un test dbt échoue, l'étape (et le flow) échoue
        subprocess.run(["dbt", "build", "--profiles-dir", "."], cwd="transform", check=True)


@task  # pas de retry : rag.run s'arrête déjà proprement sur limite de requêtes (429)
def vectorisation(run_id: str) -> int:
    with suivre(run_id, "vectorisation") as r:
        r["lignes"] = vectoriser_avis()  # lit int_avis_enrichis : doit passer après dbt
    return r["lignes"]


@flow(name="telco360-pipeline")
def pipeline(limit: int | None = None) -> None:
    """Les étapes s'enchaînent dans l'ordre ; si l'une échoue, les suivantes ne tournent pas."""
    logger = get_run_logger()
    run_id = nouveau_run_id()
    logger.info("Run %s", run_id)

    recuperer_donnees()
    nouveaux = ingestion(run_id)
    enrichis = enrichissement(run_id, limit)
    dbt_build(run_id)
    vectorises = vectorisation(run_id)
    sauvegarder_donnees()  # seulement si tout a réussi : une étape en échec arrête le flow avant

    logger.info(
        "Run %s terminé : %s nouveaux avis, %s enrichis, %s vectorisés",
        run_id,
        nouveaux,
        enrichis,
        vectorises,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="nb max d'avis à enrichir")
    parser.add_argument("--serve", action="store_true", help="planifier chaque jour à 6h")
    args = parser.parse_args()

    if args.serve:
        pipeline.serve(name="quotidien", cron="0 6 * * *", parameters={"limit": args.limit})
    else:
        pipeline(limit=args.limit)
