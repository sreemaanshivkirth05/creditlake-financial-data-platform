select cik from {{ source('sec', 'issuer_history') }}
group by cik
having count(*) filter (where valid_to is null) <> 1
