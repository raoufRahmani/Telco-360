# Image Telco 360 : le pipeline (par défaut) ET l'app Streamlit (même image, autre commande)
FROM python:3.13-slim

# uv, le même outil qu'en local (version épinglée), copié depuis son image officielle
COPY --from=ghcr.io/astral-sh/uv:0.12.19 /uv /uvx /bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PREFECT_SERVER_ANALYTICS_ENABLED=false \
    DO_NOT_TRACK=1 \
    PATH="/app/.venv/bin:$PATH"

# 1) Dépendances d'abord : cette couche reste en cache tant que uv.lock ne change pas
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

# 2) Le code (pas les tests, notebooks ni données : voir .dockerignore)
COPY ingestion/ ingestion/
COPY enrichment/ enrichment/
COPY flows/ flows/
COPY transform/ transform/
COPY rag/ rag/
COPY modeling/ modeling/
COPY cloud/ cloud/
COPY app.py ./

# 3) Paquets dbt (dbt_utils) installés une fois pour toutes dans l'image
RUN cd transform && dbt deps

# Les données (base DuckDB, CSV Kaggle) ne sont PAS dans l'image :
# elles arrivent de l'extérieur par un volume monté sur /app/data.
# Par défaut : un run du pipeline. Pour l'app :
#   docker run -p 8501:8501 ... telco360 streamlit run app.py --server.address 0.0.0.0
EXPOSE 8501
CMD ["python", "-m", "flows.pipeline"]
