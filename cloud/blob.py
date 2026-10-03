"""Synchronisation de data/ avec Azure Blob Storage (déploiement cloud).

Dans Azure, les conteneurs n'ont pas de disque permanent : la base DuckDB et le modèle vivent dans un
conteneur Blob. Le pipeline les télécharge au début et renvoie la base à la fin ; l'app les télécharge
au démarrage. Sans AZURE_STORAGE_CONNECTION_STRING (en local, en CI), ces fonctions ne font rien.
Cette variable n'est définie que dans Azure (secret) : ne pas la mettre dans le .env local.
"""

import logging
import os
from pathlib import Path

from azure.storage.blob import BlobServiceClient, ContainerClient

logger = logging.getLogger(__name__)

DOSSIER = Path("data")
BASE = "telco360.duckdb"
MODELE = "modele_churn.joblib"
CSV = "WA_Fn-UseC_-Telco-Customer-Churn.csv"


def conteneur() -> ContainerClient | None:
    """Le conteneur Blob configuré, ou None si on n'est pas dans le cloud."""
    connexion = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    if not connexion:
        return None
    nom = os.getenv("AZURE_STORAGE_CONTAINER", "telco360")
    return BlobServiceClient.from_connection_string(connexion).get_container_client(nom)


def telecharger(noms: list[str], dossier: Path = DOSSIER, client: ContainerClient | None = None) -> list[str]:
    """Blob -> data/. Retourne les fichiers téléchargés (aucun hors cloud)."""
    client = client or conteneur()
    if client is None:
        return []
    dossier.mkdir(parents=True, exist_ok=True)
    faits = []
    for nom in noms:
        blob = client.get_blob_client(nom)
        if not blob.exists():  # 1er déploiement : la base n'existe pas encore, le pipeline la créera
            logger.warning("Blob %s absent, ignoré", nom)
            continue
        with open(dossier / nom, "wb") as f:
            blob.download_blob().readinto(f)
        faits.append(nom)
    logger.info("Téléchargés depuis Blob : %s", faits)
    return faits


def envoyer(noms: list[str], dossier: Path = DOSSIER, client: ContainerClient | None = None) -> list[str]:
    """data/ -> Blob (écrase la version précédente). Retourne les fichiers envoyés (aucun hors cloud)."""
    client = client or conteneur()
    if client is None:
        return []
    faits = []
    for nom in noms:
        with open(dossier / nom, "rb") as f:
            client.upload_blob(nom, f, overwrite=True)
        faits.append(nom)
    logger.info("Envoyés vers Blob : %s", faits)
    return faits
