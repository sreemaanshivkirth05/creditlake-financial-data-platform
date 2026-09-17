select issuer_key, cik, name, ticker, sector, headquarters, valid_from
from {{ source('sec', 'issuer_history') }}
where valid_to is null
