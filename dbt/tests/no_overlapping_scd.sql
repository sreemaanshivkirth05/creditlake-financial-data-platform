select a.issuer_key from {{ source('sec', 'issuer_history') }} a
join {{ source('sec', 'issuer_history') }} b on a.cik = b.cik and a.issuer_key <> b.issuer_key
where a.valid_from < coalesce(b.valid_to, cast('9999-12-31' as timestamptz))
  and b.valid_from < coalesce(a.valid_to, cast('9999-12-31' as timestamptz))
