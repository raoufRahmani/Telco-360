"""Modèle de churn (POO : encapsule entraînement, prédiction et explicabilité)."""


class ModeleChurn:
    """XGBoost + SHAP pour la prédiction et l'explication du churn."""

    def __init__(self):
        self.model = None
        self.explainer = None  # SHAP

    def train(self, X, y):
        """Entraîne le modèle (scale_pos_weight pour le déséquilibre)."""
        ...

    def predict(self, X):
        """Retourne la probabilité de churn."""
        ...

    def expliquer_client(self, X_client):
        """Retourne la proba + les 3 principaux facteurs de risque (SHAP)."""
        ...

    def save(self, path: str): ...
    def load(self, path: str): ...
