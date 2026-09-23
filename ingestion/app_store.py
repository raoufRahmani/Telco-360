"""Collecteur d'avis App Store (source complémentaire, remplace Reddit dont l'API est fermée)."""
from datetime import datetime, timezone
import json
import logging
import urllib.request

import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import AvisCollector

logger = logging.getLogger(__name__)

# Opérateur -> id App Store (l'id est dans l'URL de la fiche : .../app/.../id<app_id>)
APP_IDS = {
    "orange": "367722531",    # Orange et moi France
    "sfr": "326161564",       # SFR & Moi
    "bouygues": "422590767",  # Bouygues Telecom (espace client)
    "free": None,  # TODO: coller l'id de l'appli Free depuis sa fiche App Store
}

# Flux RSS public d'Apple : 50 avis par page, 10 pages max
URL = "https://itunes.apple.com/{country}/rss/customerreviews/page={page}/id={app_id}/sortby={sort}/json"
MAX_PAGES = 10
# Le flux Apple renvoie parfois 0 avis selon le tri : on essaie dans cet ordre
SORTS = ["mostrecent", "mosthelpful"]


class AppStoreCollector(AvisCollector):
    """Récupère les avis App Store via le flux RSS public d'Apple (pas de clé API)."""

    def __init__(self, operateurs: list[str], nb_pages: int = MAX_PAGES, country: str = "fr"):
        super().__init__(operateurs)
        self.nb_pages = min(nb_pages, MAX_PAGES)
        self.country = country

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20))
    def _fetch_page(self, app_id: str, page: int, sort: str = "mostrecent") -> list[dict]:
        """Une page du flux (50 avis max), retentée 3 fois si ça plante."""
        url = URL.format(country=self.country, page=page, app_id=app_id, sort=sort)
        req = urllib.request.Request(url, headers={"User-Agent": "telco360"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            feed = json.load(resp).get("feed", {})
        entries = feed.get("entry", [])
        return [entries] if isinstance(entries, dict) else entries  # 1 seul avis = dict

    def collect(self) -> pd.DataFrame:
        rows = []
        for op in self.operateurs:
            app_id = APP_IDS.get(op)
            if not app_id:
                logger.warning("Pas d'app_id pour '%s', ignoré", op)
                continue

            # premier tri qui renvoie des avis
            sort = next((s for s in SORTS if self._fetch_page(app_id, 1, s)), None)
            if sort is None:
                logger.warning("Flux Apple vide pour '%s', ignoré", op)
                continue

            for page in range(1, self.nb_pages + 1):
                entries = self._fetch_page(app_id, page, sort)
                if not entries:
                    break  # plus d'avis
                for e in entries:
                    if "im:rating" not in e:
                        continue  # entrée "fiche appli", pas un avis
                    rows.append({
                        "id": e["id"]["label"],
                        "operateur": op,
                        "note": int(e["im:rating"]["label"]),
                        # titre + texte : sur l'App Store le titre porte souvent le motif
                        "texte": f'{e["title"]["label"]}. {e["content"]["label"]}',
                        "date": pd.to_datetime(e["updated"]["label"]),
                    })
            logger.info("%s : %d avis cumulés", op, len(rows))

        df = pd.DataFrame(rows)
        df["source"] = "app_store"
        df["ingested_at"] = datetime.now(timezone.utc)
        if "id" in df.columns:
            df = df.drop_duplicates(subset="id")
        return self.normaliser(df)
