# Profile and demonstration wording

## Project entry

**CreditLake — Auditable Financial Data Platform**

Python, SQL, Parquet, DuckDB, dbt, Airflow, FastAPI, Docker, GitHub Actions

Built a versioned financial data platform from actual SEC responses, preserving
10,738 financial fact versions across eight issuers and producing 89 annual
company-period records. Implemented historical cutoff queries, metric lineage,
SCD2 issuer history, financial coverage reporting, and safe warehouse publication.
Validated replay and failure recovery with a reproducible local demonstration.

## Resume bullets

- Built a Python/SQL financial pipeline using Parquet, DuckDB, and dbt, preserving 10,738 SEC fact versions and producing 89 annual records with 23 passing data quality checks.
- Implemented historical financial queries, metric lineage, SCD2 issuer history, and atomic release publication; demonstrated idempotent replay and failure recovery through a FastAPI research dashboard and Airflow integration.

Use the measured dataset counts as portfolio results. Describe configured CI
and containers according to their actual execution status. Cloud infrastructure,
distributed processing, and financial institution adoption are future scope.

## Three-minute demonstration

1. Show one company's annual financials and its actual fiscal period end.
2. Change the filing-date cutoff and explain why later evidence is excluded.
3. Retrieve a fact trace and download the checksum-verified original source.
4. Show `creditlake quality` and explain one concrete missing-concept finding.
5. Run `python scripts/verify_portfolio.py`, showing unchanged-source replay,
   the publication failure, preserved serving data, and successful recovery.

Be ready to explain why the raw grain includes filing and value versions,
why compact marts rebuild, and why the cloud scaling plan needs a new commit
protocol. Practice running and modifying the project so the presentation reflects
your understanding of the implemented behavior.
