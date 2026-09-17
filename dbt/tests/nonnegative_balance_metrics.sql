select * from {{ ref('fct_annual_financials') }}
where revenue < 0 or assets < 0 or liabilities < 0
   or current_assets < 0 or current_liabilities < 0 or cash < 0
