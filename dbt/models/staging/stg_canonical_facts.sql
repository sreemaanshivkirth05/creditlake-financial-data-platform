-- Grain: issuer x metric x annual period end. Prefer the most recently
-- filed evidence, then the documented taxonomy fallback order.
-- Value is not part of the partition: conflicting revisions compete here,
-- while all versions remain available in raw.facts.
with ranked as (
    select *,
      row_number() over (
        partition by cik, metric, period_end
        order by filed desc, alias_priority asc, accession desc,
                 first_observed desc, fact_id
      ) as version_rank
    from {{ ref('stg_annual_candidates') }}
)
select * exclude (version_rank)
from ranked
where version_rank = 1
