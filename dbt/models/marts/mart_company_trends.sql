with previous as (
    select f.*, d.ticker, d.name, d.sector,
      lag(revenue) over (partition by cik order by period_end) as previous_revenue,
      lag(period_end) over (partition by cik order by period_end) as previous_period_end
    from {{ ref('fct_annual_financials') }} f
    inner join {{ ref('dim_issuer') }} d using (issuer_key, cik)
)
select *,
       -- Do not call a comparison YoY when an intervening year is missing.
       case when date_diff('day', previous_period_end, period_end) between 330 and 400
            then revenue / nullif(previous_revenue, 0) - 1 end as revenue_growth_yoy,
       case when current_ratio < 1 then true else false end as liquidity_review,
       case when net_income < 0 then true else false end as loss_review,
       case when operating_cash_flow < 0 then true else false end as cash_flow_review,
       available_metrics < 10 as incomplete_metrics
from previous
