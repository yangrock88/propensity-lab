-- Staging: one certified row per customer per monthly snapshot.
-- This model is the single place where source columns are renamed,
-- typed and cleaned. Nothing downstream touches the raw schema.

with source as (

    select * from {{ source('raw', 'customer_snapshots') }}

),

renamed as (

    select
        cast(fecha_dato as date)                      as snapshot_date,
        cast(ncodpers as bigint)                      as customer_id,
        cast(fecha_dato as varchar) || '|' || cast(ncodpers as varchar)
                                                      as snapshot_customer_key,
        nullif(trim(sexo), '')                        as gender,
        cast(age as integer)                          as age,
        cast(fecha_alta as date)                      as customer_since,
        greatest(cast(antiguedad as integer), 0)      as tenure_months,
        nullif(trim(canal_entrada), '')               as join_channel,
        nullif(trim(nomprov), '')                     as province,
        coalesce(cast(ind_actividad_cliente as integer), 0) = 1
                                                      as is_active,
        cast(renta as double)                         as gross_income,
        nullif(trim(segmento), '')                    as segment,

        -- product ownership flags, renamed to business terms
        cast(ind_ahor_fin_ult1 as tinyint)            as savings_account,
        cast(ind_aval_fin_ult1 as tinyint)            as guarantee,
        cast(ind_cco_fin_ult1 as tinyint)             as checking_account,
        cast(ind_cder_fin_ult1 as tinyint)            as derivatives,
        cast(ind_cno_fin_ult1 as tinyint)             as payroll_account,
        cast(ind_ctju_fin_ult1 as tinyint)            as junior_account,
        cast(ind_ctma_fin_ult1 as tinyint)            as particular_plus_account,
        cast(ind_ctop_fin_ult1 as tinyint)            as particular_account,
        cast(ind_ctpp_fin_ult1 as tinyint)            as premium_account,
        cast(ind_deco_fin_ult1 as tinyint)            as short_term_deposit,
        cast(ind_deme_fin_ult1 as tinyint)            as medium_term_deposit,
        cast(ind_dela_fin_ult1 as tinyint)            as long_term_deposit,
        cast(ind_ecue_fin_ult1 as tinyint)            as e_account,
        cast(ind_fond_fin_ult1 as tinyint)            as investment_fund,
        cast(ind_hip_fin_ult1 as tinyint)             as mortgage,
        cast(ind_plan_fin_ult1 as tinyint)            as pension_plan,
        cast(ind_pres_fin_ult1 as tinyint)            as personal_loan,
        cast(ind_reca_fin_ult1 as tinyint)            as tax_payment_service,
        cast(ind_tjcr_fin_ult1 as tinyint)            as credit_card,
        cast(ind_valo_fin_ult1 as tinyint)            as securities,
        cast(ind_viv_fin_ult1 as tinyint)             as home_account,
        cast(ind_nomina_ult1 as tinyint)              as payroll_deposit,
        cast(ind_nom_pens_ult1 as tinyint)            as pension_deposit,
        cast(ind_recibo_ult1 as tinyint)              as direct_debit

    from source
    where ncodpers is not null

)

select
    *,
    {% for p in var('product_names') %}{{ p }}{% if not loop.last %} + {% endif %}{% endfor %}
        as held_product_count
from renamed
