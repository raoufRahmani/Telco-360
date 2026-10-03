"""Application Streamlit Telco 360 : questions sur les avis (RAG), motifs par opérateur, risque de churn.

Lancement (depuis la racine du projet) : uv run streamlit run app.py
Prérequis : pipeline lancé (avis enrichis, dbt build, rag.run) et modèle sauvegardé par le notebook 02.
"""

import duckdb
import pandas as pd
import streamlit as st

from ingestion.run import DB_PATH
from modeling.churn_model import ModeleChurn, motif_de, preparer_X_y
from rag.engine import MoteurRAG

MODELE_PATH = "data/modele_churn.joblib"
OPERATEURS = ["orange", "sfr", "bouygues"]
MOTIFS = ["reseau", "facturation", "resiliation", "service_client", "autre"]

st.set_page_config(page_title="Telco 360", page_icon="📡", layout="wide")


# --- Chargements mis en cache : faits une seule fois, pas à chaque clic -------------------------------
def lire(sql: str) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:  # lecture seule : ne bloque pas le pipeline
        return con.sql(sql).df()


@st.cache_resource
def moteur_rag() -> MoteurRAG:
    return MoteurRAG.depuis_env()


@st.cache_data
def motifs_operateur() -> pd.DataFrame:
    return lire("SELECT * FROM mart_motifs_operateur")


@st.cache_resource
def modele_churn() -> ModeleChurn:
    return ModeleChurn.load(MODELE_PATH)


@st.cache_data
def clients_scores() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Clients Kaggle + probabilité de churn prédite (X sert ensuite à expliquer un client)."""
    clients = lire("SELECT * FROM stg_churn")
    X, _ = preparer_X_y(clients)
    clients["proba_churn"] = modele_churn().predict_proba(X)
    return clients, X


# --- Interface --------------------------------------------------------------------------------------
st.title("📡 Telco 360")
st.caption("Avis clients réels (Orange, SFR, Bouygues) enrichis par LLM · modèle de churn expliqué par SHAP")

onglet_rag, onglet_motifs, onglet_churn = st.tabs(
    ["💬 Interroger les avis", "📊 Motifs par opérateur", "⚠️ Risque de churn"]
)

with onglet_rag:
    st.write(
        "Posez une question : la réponse s'appuie **uniquement** sur les avis clients, cités entre crochets."
    )
    question = st.text_input("Question", placeholder="Pourquoi les clients se plaignent-ils du réseau ?")
    col1, col2 = st.columns(2)
    operateur = col1.selectbox("Opérateur", [None, *OPERATEURS], format_func=lambda v: v or "tous")
    motif = col2.selectbox("Motif", [None, *MOTIFS], format_func=lambda v: v or "tous")

    if st.button("Répondre", type="primary", disabled=not question):
        with st.spinner("Recherche des avis et rédaction de la réponse…"):
            res = moteur_rag().repondre(question, operateur, motif)
        st.markdown(res["reponse"])
        if res["sources"]:
            st.subheader(f"Sources ({len(res['sources'])} avis cités)")
        for s in res["sources"]:
            with st.expander(f"[{s['numero']}] {s['operateur']} · {s['motif']} · {s['note']}/5"):
                st.write(s["texte"])
                st.caption(f"{s['source']} · similarité {s['similarite']:.2f}")

with onglet_motifs:
    df = motifs_operateur()
    st.write("Part de chaque motif parmi les avis **négatifs** de chaque opérateur (en %).")
    pivot = df.pivot(index="motif", columns="operateur", values="pct_des_negatifs").fillna(0)
    st.bar_chart(pivot, stack=False)
    st.dataframe(df, hide_index=True, width="stretch")
    st.caption(
        "Instantané d'avis récents (Google Play, App Store) : décrit les irritants, pas un classement des opérateurs."
    )

with onglet_churn:
    clients, X = clients_scores()
    st.write(
        "Score de churn prédit par le modèle (XGBoost) sur le dataset Kaggle, "
        "avec les facteurs qui augmentent le risque de chaque client (SHAP)."
    )
    c1, c2, c3 = st.columns(3)
    c1.metric("Clients", f"{len(clients):,}".replace(",", " "))
    c2.metric("Churn réel", f"{clients['churn'].mean():.1%}")
    c3.metric("Clients à risque (proba ≥ 0,5)", f"{(clients['proba_churn'] >= 0.5).mean():.1%}")

    st.subheader("Clients les plus à risque")
    a_risque = clients.sort_values("proba_churn", ascending=False).head(50)
    colonnes = [
        "customer_id",
        "proba_churn",
        "contrat",
        "anciennete_mois",
        "internet",
        "paiement",
        "montant_mensuel",
    ]
    st.dataframe(a_risque[colonnes].round({"proba_churn": 3}), hide_index=True, width="stretch")

    client_id = st.selectbox("Expliquer un client", a_risque["customer_id"])
    position = clients.index[clients["customer_id"] == client_id][0]
    explication = modele_churn().expliquer_client(X.loc[[position]], top=5)

    st.metric("Probabilité de churn", f"{explication['proba_churn']:.0%}")
    facteurs = pd.DataFrame(explication["facteurs"], columns=["variable", "contribution SHAP"])
    facteurs["motif"] = facteurs["variable"].map(motif_de)  # le pont vers les motifs des avis
    st.dataframe(facteurs, hide_index=True, width="stretch")
