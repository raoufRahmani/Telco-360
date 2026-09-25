"""Collecteur d'avis Google Play (source principale)."""

import logging
from datetime import UTC, datetime

import pandas as pd
from google_play_scraper import Sort, reviews
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import AvisCollector

logger = logging.getLogger(__name__)

# Opérateur -> app_id Google Play (l'id est dans l'URL de la fiche : ...details?id=<app_id>)
APP_IDS = {
    "orange": "com.orange.orangeetmoi",  # Orange et moi
    "sfr": "com.sfr.android.moncompte",  # SFR & Moi
    "bouygues": "fr.bouyguestelecom.ecm.android",  # Bouygues Telecom (espace client)
    "free": None,  # TODO: coller l'id de l'appli Free Mobile depuis sa fiche Play Store
}


class GooglePlayCollector(AvisCollector):
    """Récupère les avis des applis opérateurs via google-play-scraper."""

    def __init__(self, operateurs: list[str], nb_avis: int = 500, lang: str = "fr", country: str = "fr"):
        super().__init__(operateurs)
        self.nb_avis = nb_avis
        self.lang = lang
        self.country = country

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    def _fetch(self, app_id: str) -> list[dict]:
        """Un appel à Google Play (retenté 3 fois si ça plante)."""
        result, _ = reviews(
            app_id,
            lang=self.lang,
            country=self.country,
            sort=Sort.NEWEST,
            count=self.nb_avis,
        )
        return result

    def collect(self) -> pd.DataFrame:
        frames = []
        for op in self.operateurs:
            app_id = APP_IDS.get(op)
            if not app_id:
                logger.warning("Pas d'app_id pour '%s', ignoré", op)
                continue

            raw = self._fetch(app_id)
            logger.info("%s : %d avis récupérés", op, len(raw))
            if not raw:
                continue

            df = pd.DataFrame(raw).rename(
                columns={
                    "reviewId": "id",
                    "score": "note",
                    "content": "texte",
                    "at": "date",
                }
            )
            df["operateur"] = op
            frames.append(df)

        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
        df["source"] = "google_play"
        df["ingested_at"] = datetime.now(UTC)
        if "id" in df.columns:
            df = df.drop_duplicates(subset="id")
        return self.normaliser(df)
