-- Keep annual durations and instant facts; quarterly and YTD durations stay
-- in raw for audit, but cannot contaminate full-year analytics.
select *
from {{ source('sec', 'facts') }}
where form in ('10-K', '10-K/A')
  and filed <= cast('{{ var("as_of") }}' as date)
  and (kind = 'instant'
       or date_diff('day', period_start, period_end) between 329 and 399)
