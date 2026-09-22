"""Classe de base pour les collecteurs d'avis (POO : abstraction commune)."""
from abc import ABC, abstractmethod
import pandas as pd


class AvisCollector(ABC):
    """Interface commune à toutes les sources d'avis.

    Chaque source concrète (Google Play, Reddit...) hérite de cette classe
    et implémente collect(). La sortie est normalisée dans un schéma commun.
    """

    SCHEMA = ["id", "source", "operateur", "note", "texte", "date", "ingested_at"]

    def __init__(self, operateurs: list[str]):
        self.operateurs = operateurs

    @abstractmethod
    def collect(self) -> pd.DataFrame:
        """Récupère les avis et retourne un DataFrame au schéma SCHEMA."""
        raise NotImplementedError

    def normaliser(self, df: pd.DataFrame) -> pd.DataFrame:
        """Force le schéma commun (colonnes manquantes = None)."""
        for col in self.SCHEMA:
            if col not in df.columns:
                df[col] = None
        return df[self.SCHEMA]
