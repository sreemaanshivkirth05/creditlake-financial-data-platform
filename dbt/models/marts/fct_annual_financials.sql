-- Revenue anchors the annual period: this avoids treating comparative
-- balance-sheet instants, or the filing's fy hint, as separate fiscal years.
with anchors as (
    select cik, period_end from {{ ref('stg_canonical_facts') }} where metric = 'revenue'
), pivoted as (
    select f.cik, f.period_end,
      max(case when metric = 'revenue' then value end) as revenue,
      max(case when metric = 'net_income' then value end) as net_income,
      max(case when metric = 'operating_income' then value end) as operating_income,
      max(case when metric = 'operating_cash_flow' then value end) as operating_cash_flow,
      max(case when metric = 'assets' then value end) as assets,
      max(case when metric = 'liabilities' then value end) as liabilities,
      max(case when metric = 'equity' then value end) as equity,
      max(case when metric = 'current_assets' then value end) as current_assets,
      max(case when metric = 'current_liabilities' then value end) as current_liabilities,
      max(case when metric = 'cash' then value end) as cash,
      max(filed) as latest_evidence_filed,
      count(*) as available_metrics
    from {{ ref('stg_canonical_facts') }} f
    inner join anchors a using (cik, period_end)
    group by f.cik, f.period_end
)
select md5(cast(cik as varchar) || ':' || cast(period_end as varchar)) as annual_key,
       d.issuer_key, p.*,
       net_income / nullif(revenue, 0) as net_margin,
       operating_income / nullif(revenue, 0) as operating_margin,
       current_assets / nullif(current_liabilities, 0) as current_ratio,
       liabilities / nullif(assets, 0) as liabilities_to_assets,
       operating_cash_flow / nullif(revenue, 0) as cash_flow_margin,
       cast('{{ var("as_of") }}' as date) as filing_date_cutoff
from pivoted p
inner join {{ ref('dim_issuer') }} d using (cik)
