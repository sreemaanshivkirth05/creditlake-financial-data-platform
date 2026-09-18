"""Build a self-contained dashboard from the latest published release."""

import json
import re
from datetime import date
from decimal import Decimal

from creditlake.analytics import filing_revisions
from creditlake.config import Settings
from creditlake.pipeline import release_manifest
from creditlake.quality import quality_report
from creditlake.warehouse import connect, rows


def main():
    settings = Settings.load()
    manifest = release_manifest(settings.data_dir)
    if not manifest:
        raise SystemExit("Run creditlake run first")
    with connect(settings.data_dir / manifest["warehouse"], read_only=True) as connection:
        companies = rows(connection, "SELECT * FROM analytics.dim_issuer ORDER BY ticker")
        candidates, revisions = {}, {}
        for issuer in companies:
            all_facts = rows(
                connection,
                """
              SELECT fact_id,cik,metric,concept,kind,alias_priority,period_start,
                period_end,value,accession,form,filed,first_observed,source_sha
              FROM raw.facts WHERE cik=? AND form IN ('10-K','10-K/A')
                AND (kind='instant' OR date_diff('day',period_start,period_end) BETWEEN 329 AND 399)
            """,
                [issuer["cik"]],
            )
            for fact in all_facts:
                accession = fact["accession"]
                fact["filing_url"] = (
                    f"https://www.sec.gov/Archives/edgar/data/{issuer['cik']}/"
                    f"{accession.replace('-', '')}/{accession}-index.html"
                )
            candidates[issuer["ticker"]] = all_facts
            revisions[issuer["ticker"]] = filing_revisions(connection, issuer["cik"], date.max, 200)
        quality = quality_report(connection)
    payload = {
        "status": manifest,
        "companies": companies,
        "candidates": candidates,
        "revisions": revisions,
        "quality": quality,
    }
    encoded = json.dumps(
        payload,
        default=lambda value: str(value) if isinstance(value, Decimal) else value.isoformat(),
        separators=(",", ":"),
    ).replace("</", "<\\/")
    static = settings.root / "src" / "creditlake" / "static"
    html = (static / "index.html").read_text()
    html, css_count = re.subn(
        r'<link\s+rel="stylesheet"\s+href="/static/app.css"\s*/?>',
        lambda _: "<style>" + (static / "app.css").read_text() + "</style>",
        html,
    )
    html, js_count = re.subn(
        r'<script\s+src="/static/app.js"\s+defer\s*>\s*</script>',
        lambda _: "<script>" + (static / "app.js").read_text() + "</script>",
        html,
    )
    if (css_count, js_count) != (1, 1):
        raise RuntimeError("Expected exactly one stylesheet and one application script")
    html = html.replace(
        "<!-- DEMO_DATA -->", "<script>window.CREDITLAKE_DEMO=" + encoded + ";</script>"
    )
    output = settings.root / "demo" / "CreditLake_Demo.html"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html)
    print(f"Created {output} ({output.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
