"""Pipeline complet orchestré avec Prefect : ingestion -> enrichissement LLM -> dbt build.

Usage :
    uv run python -m flows.pipeline              # une exécution complète
    uv run python -m flows.pipeline --limit 50   # enrichit au plus 50 nouveaux avis
    uv run python -m flows.pipeline --serve      # exécution planifiée chaque jour à 6h (laisser tourner)
"""

import argparse
import subprocess

from prefect import flow, get_run_logger, task

from enrichment.run import run as enrichir_avis
from flows.suivi import nouveau_run_id, suivre
from ingestion.run import run as ingerer_avis


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
        # check=True : si un modèle ou un test dbt échoue, l'étape (et le flow) échoue
        subprocess.run(["dbt", "build", "--profiles-dir", "."], cwd="transform", check=True)


@flow(name="telco360-pipeline")
def pipeline(limit: int | None = None) -> None:
    """Les étapes s'enchaînent dans l'ordre ; si l'une échoue, les suivantes ne tournent pas."""
    logger = get_run_logger()
    run_id = nouveau_run_id()
    logger.info("Run %s", run_id)

    nouveaux = ingestion(run_id)
    enrichis = enrichissement(run_id, limit)
    dbt_build(run_id)

    logger.info("Run %s terminé : %s nouveaux avis, %s enrichis", run_id, nouveaux, enrichis)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="nb max d'avis à enrichir")
    parser.add_argument("--serve", action="store_true", help="planifier chaque jour à 6h")
    args = parser.parse_args()

    if args.serve:
        pipeline.serve(name="quotidien", cron="0 6 * * *", parameters={"limit": args.limit})
    else:
        pipeline(limit=args.limit)
