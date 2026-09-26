-- Par opérateur et par motif : volume, part des plaintes, note moyenne
with base as (
    select * from {{ ref('int_avis_enrichis') }}
)

select
    operateur,
    motif,
    count(*)                                        as n_avis,
    count(*) filter (where est_negatif)             as n_negatifs,
    -- part de ce motif dans les avis négatifs de l'opérateur (en %)
    round(100.0 * count(*) filter (where est_negatif)
          / sum(count(*) filter (where est_negatif)) over (partition by operateur), 1)
                                                    as pct_des_negatifs,
    round(avg(note), 2)                             as note_moyenne
from base
group by operateur, motif
order by operateur, n_negatifs desc
