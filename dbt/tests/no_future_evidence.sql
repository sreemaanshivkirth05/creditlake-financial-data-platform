select * from {{ ref('stg_canonical_facts') }}
where filed > cast('{{ var("as_of") }}' as date)
