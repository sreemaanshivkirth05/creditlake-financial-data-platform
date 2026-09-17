select * from {{ ref('stg_canonical_facts') }}
where kind = 'duration'
  and date_diff('day', period_start, period_end) not between 329 and 399
