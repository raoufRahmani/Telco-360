"""Collecteur d'avis Google Play (source principale)."""
from .base import AvisCollector
import pandas as pd


class GooglePlayCollector(AvisCollector):
    """Récupère les avis des applis opérateurs via google-play-scraper.

    À implémenter : mapping operateur -> app_id, appel de reviews(),
    gestion des retries et du déduplication.
    """

    def collect(self) -> pd.DataFrame:
        # TODO: from google_play_scraper import reviews_all ; boucle sur self.operateurs
        df = pd.DataFrame()
        return self.normaliser(df)
