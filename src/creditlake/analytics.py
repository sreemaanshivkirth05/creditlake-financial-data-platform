from __future__ import annotations

from datetime import date, datetime

from creditlake.warehouse import rows

# Dynamic filing-date analytics mirror dbt's selection contract. Parity is
# checked against every bundled issuer in the integration suite.
CANONICAL = """
WITH eligible AS (
  SELECT * FROM raw.facts
  WHERE cik=? AND filed<=? AND (? IS NULL OR first_observed<=?)
    AND form IN ('10-K','10-K/A')
    AND (kind='instant' OR date_diff('day',period_start,period_end) BETWEEN 329 AND 399)
), ranked AS (
  SELECT *, row_number() OVER (
    PARTITION BY cik,metric,period_end
    ORDER BY filed DESC,alias_priority,accession DESC,first_observed DESC,fact_id
  ) AS version_rank FROM eligible
)
SELECT * EXCLUDE (version_rank) FROM ranked WHERE version_rank=1
"""


def canonical_facts(
    connection,
    cik: int,
    as_of: date,
    period_end: date | None = None,
    observed_before: datetime | None = None,
) -> list[dict]:
    query = (
        "SELECT * FROM ("
        + CANONICAL
        + ") WHERE (? IS NULL OR period_end=?) ORDER BY period_end,metric"
    )
    facts = rows(
        connection, query, [cik, as_of, observed_before, observed_before, period_end, period_end]
    )
    for fact in facts:
        accession = fact["accession"]
        fact["filing_url"] = (
            f"https://www.sec.gov/Archives/edgar/data/{cik}/"
            f"{accession.replace('-', '')}/{accession}-index.html"
        )
    return facts


def annual_history(
    connection, cik: int, as_of: date, observed_before: datetime | None = None
) -> list[dict]:
    query = (
        """
WITH canonical AS ("""
        + CANONICAL
        + """), pivoted AS (
  SELECT cik,period_end,
    max(value) FILTER (WHERE metric='revenue') AS revenue,
    max(value) FILTER (WHERE metric='net_income') AS net_income,
    max(value) FILTER (WHERE metric='operating_income') AS operating_income,
    max(value) FILTER (WHERE metric='operating_cash_flow') AS operating_cash_flow,
    max(value) FILTER (WHERE metric='assets') AS assets,
    max(value) FILTER (WHERE metric='liabilities') AS liabilities,
    max(value) FILTER (WHERE metric='equity') AS equity,
    max(value) FILTER (WHERE metric='current_assets') AS current_assets,
    max(value) FILTER (WHERE metric='current_liabilities') AS current_liabilities,
    max(value) FILTER (WHERE metric='cash') AS cash,
    max(filed) AS latest_evidence_filed,
    count(*) AS available_metrics
  FROM canonical GROUP BY cik,period_end
  HAVING max(value) FILTER (WHERE metric='revenue') IS NOT NULL
), compared AS (
  SELECT *, lag(revenue) OVER (ORDER BY period_end) AS previous_revenue,
    lag(period_end) OVER (ORDER BY period_end) AS previous_period_end FROM pivoted
)
SELECT *, net_income/nullif(revenue,0) AS net_margin,
  current_assets/nullif(current_liabilities,0) AS current_ratio,
  liabilities/nullif(assets,0) AS liabilities_to_assets,
  CASE WHEN date_diff('day',previous_period_end,period_end) BETWEEN 330 AND 400
    THEN revenue/nullif(previous_revenue,0)-1 END AS revenue_growth_yoy
FROM compared ORDER BY period_end
"""
    )
    return rows(connection, query, [cik, as_of, observed_before, observed_before])


def filing_revisions(
    connection, cik: int, as_of: date, limit: int = 200, observed_before: datetime | None = None
) -> list[dict]:
    return rows(
        connection,
        """
      WITH eligible AS (
        SELECT * FROM raw.facts
        WHERE cik=? AND filed<=? AND (? IS NULL OR first_observed<=?)
          AND form IN ('10-K','10-K/A')
          AND (kind='instant' OR date_diff('day',period_start,period_end) BETWEEN 329 AND 399)
      ), versions AS (
        SELECT *, lag(value) OVER (
          PARTITION BY cik,concept,unit,period_start,period_end
          ORDER BY filed,accession,first_observed,fact_id
        ) AS previous_value FROM eligible
      )
      SELECT fact_id,cik,metric,concept,period_start,period_end,accession,filed,
        value,previous_value,value-previous_value AS change_amount,
        (value-previous_value)/nullif(abs(previous_value),0) AS relative_change,
        source_sha,bronze_path
      FROM versions WHERE previous_value IS NOT NULL AND value<>previous_value
      ORDER BY filed DESC,period_end DESC LIMIT ?
    """,
        [cik, as_of, observed_before, observed_before, limit],
    )
