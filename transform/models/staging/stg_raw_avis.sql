-- Avis bruts nettoyés : 1 ligne par avis, sans logique métier
select
    source || ':' || id    as avis_key,   -- clé unique lisible
    source,
    id                     as avis_id,
    operateur,
    note,
    trim(texte)            as texte,
    length(trim(texte))    as longueur_texte,
    cast(date as date)     as date_avis,
    ingested_at
from {{ source('raw', 'raw_avis') }}
