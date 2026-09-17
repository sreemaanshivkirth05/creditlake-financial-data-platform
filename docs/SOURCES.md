# Primary references

| Reference | Used for |
|---|---|
| [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | Company Facts endpoint, CIK formatting, units, whole-entity taxonomy coverage |
| [SEC developer resources](https://www.sec.gov/about/developer-resources) | Request identity, fair access, rate limits |
| [DuckDB Parquet](https://duckdb.org/docs/current/data/parquet/overview) | Typed columnar read/write and ZSTD output |
| [DuckDB transactions](https://duckdb.org/docs/current/sql/statements/transactions) | Fact, dimension and checkpoint transaction boundaries |
| [Official dbt DuckDB adapter](https://github.com/duckdb/dbt-duckdb) | Profiles, warehouse paths, dbt SQL and test execution |
| [Airflow Docker 2.11](https://airflow.apache.org/docs/apache-airflow/2.11.0/howto/docker-compose/index.html) | Optional development orchestration environment |
| [FastAPI testing](https://fastapi.tiangolo.com/tutorial/testing/) | API integration tests |

Actual data-response URLs, unmodified source checksums, and capture timestamps
are in `fixtures/sec/manifest.json`. Code generates filing index URLs from the
issuer CIK and accession. There are no invented real-company financial values in
the bundled data; synthetic sources are explicitly confined to tests and benchmarks.
