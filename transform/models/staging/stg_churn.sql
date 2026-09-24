-- Matérialisé en TABLE (pas en vue) : le chemin du CSV est relatif à transform/,
-- une vue ne marcherait donc pas quand on lit la base depuis la racine du projet.
{{ config(materialized='table') }}

-- 1 ligne par client Kaggle, typée et en français. Tout est lu en texte puis converti.
select
    customerID                                          as customer_id,
    lower(gender)                                       as genre,
    SeniorCitizen = '1'                                 as senior,
    Partner = 'Yes'                                     as en_couple,
    Dependents = 'Yes'                                  as personnes_a_charge,
    cast(tenure as integer)                             as anciennete_mois,

    -- services : 'No internet service' / 'No phone service' -> false
    PhoneService = 'Yes'                                as telephone,
    MultipleLines = 'Yes'                               as lignes_multiples,
    case InternetService
        when 'DSL' then 'dsl'
        when 'Fiber optic' then 'fibre'
        else 'aucun'
    end                                                 as internet,
    OnlineSecurity = 'Yes'                              as securite_en_ligne,
    OnlineBackup = 'Yes'                                as sauvegarde_en_ligne,
    DeviceProtection = 'Yes'                            as protection_appareil,
    TechSupport = 'Yes'                                 as support_technique,
    StreamingTV = 'Yes'                                 as streaming_tv,
    StreamingMovies = 'Yes'                             as streaming_films,

    -- contrat et facturation
    case Contract
        when 'Month-to-month' then 'mensuel'
        when 'One year' then '1_an'
        when 'Two year' then '2_ans'
    end                                                 as contrat,
    PaperlessBilling = 'Yes'                            as facture_dematerialisee,
    case PaymentMethod
        when 'Electronic check' then 'cheque_electronique'
        when 'Mailed check' then 'cheque_postal'
        when 'Bank transfer (automatic)' then 'virement_auto'
        when 'Credit card (automatic)' then 'carte_auto'
    end                                                 as paiement,
    cast(MonthlyCharges as double)                      as montant_mensuel,
    -- piège connu : TotalCharges est vide pour les clients à 0 mois d'ancienneté
    coalesce(try_cast(nullif(trim(TotalCharges), '') as double), 0)
                                                        as montant_total,

    -- cible
    cast(Churn = 'Yes' as integer)                      as churn
from {{ source('kaggle', 'telco_churn') }}
