-- Résultat de l'enrichissement LLM : 1 ligne par avis enrichi
select
    source || ':' || id    as avis_key,
    motif,
    sentiment,
    model                  as llm_model,
    enriched_at
from {{ source('raw', 'enriched_avis') }}
