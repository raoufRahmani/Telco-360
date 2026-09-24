-- 1 ligne par avis : texte brut + enrichissement LLM, nettoyé et prêt à analyser
select
    r.source || ':' || r.id           as avis_key,   -- clé unique lisible
    r.source,
    r.id                               as avis_id,
    r.operateur,
    r.note,
    trim(r.texte)                      as texte,
    length(trim(r.texte))              as longueur_texte,
    cast(r.date as date)               as date_avis,
    e.motif,
    e.sentiment,
    e.sentiment = 'negatif'            as est_negatif,
    e.model                            as llm_model
from {{ source('raw', 'raw_avis') }} r
join {{ source('raw', 'enriched_avis') }} e
    on e.source = r.source and e.id = r.id
