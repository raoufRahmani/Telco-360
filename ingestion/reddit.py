"""Collecteur d'avis Reddit (source complémentaire, API officielle via praw)."""
from .base import AvisCollector
import pandas as pd


class RedditCollector(AvisCollector):
    """Récupère les mentions des opérateurs sur Reddit.

    À implémenter : client praw (OAuth), recherche par mots-clés,
    récupération posts + commentaires, normalisation.
    """

    def collect(self) -> pd.DataFrame:
        # TODO: import praw ; praw.Reddit(...) ; subreddit.search(...)
        df = pd.DataFrame()
        return self.normaliser(df)
