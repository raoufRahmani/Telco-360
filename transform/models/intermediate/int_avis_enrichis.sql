-- Avis + enrichissement LLM réunis.
-- INCRÉMENTAL : à chaque run, on n'ajoute que les avis enrichis depuis le dernier run
-- (au lieu de tout recalculer). `dbt build --full-refresh` reconstruit tout si besoin.
{{
    config(
        materialized='incremental',
        unique_key='avis_key',
        on_schema_change='fail'
    )
}}

select
    r.avis_key,
    r.source,
    r.operateur,
    r.note,
    r.texte,
    r.longueur_texte,
    r.date_avis,
    e.motif,
    e.sentiment,
    e.sentiment = 'negatif'  as est_negatif,
    e.llm_model,
    e.enriched_at
from {{ ref('stg_raw_avis') }} r
join {{ ref('stg_enriched_avis') }} e using (avis_key)

{% if is_incremental() %}
where e.enriched_at > (select coalesce(max(enriched_at), '1900-01-01') from {{ this }})
{% endif %}
