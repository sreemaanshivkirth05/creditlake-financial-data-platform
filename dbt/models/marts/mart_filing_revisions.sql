-- Compare distinct monetary versions for one concept and economic period.
-- Repeated unchanged comparative filings do not become revision alerts.
-- A changed value can reflect a reclassification; it is not automatically
-- a formal SEC restatement or evidence of an accounting problem.
with versions as (
    select *, lag(value) over (
        partition by cik, concept, unit, period_start, period_end
        order by filed, accession, first_observed, fact_id
    ) as previous_value
    from {{ ref('stg_annual_candidates') }}
)
select fact_id, cik, metric, concept, period_start, period_end,
       accession, filed, value, previous_value,
       value - previous_value as change_amount,
       (value - previous_value) / nullif(abs(previous_value), 0) as relative_change,
       source_sha, bronze_path
from versions
where previous_value is not null and value <> previous_value
