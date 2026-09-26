-- Test métier : pour chaque opérateur, les parts des motifs parmi les avis négatifs
-- doivent faire 100 % (à l'arrondi près). Le test échoue s'il renvoie des lignes.
select
    operateur,
    sum(pct_des_negatifs) as total_pct
from {{ ref('mart_motifs_operateur') }}
group by operateur
having sum(pct_des_negatifs) is not null
   and abs(sum(pct_des_negatifs) - 100) > 1
