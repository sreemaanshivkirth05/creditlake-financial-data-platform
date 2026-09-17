from datetime import UTC, datetime
from decimal import Decimal

from creditlake.normalize import normalize
from creditlake.warehouse import connect, literal, save_silver


def test_parquet_preserves_currency_beyond_float_precision(tmp_path):
    data = b'{"cik":1,"entityName":"Test","facts":{"us-gaap":{"Assets":{"units":{"USD":[{"val":12345678901234567890123.125,"end":"2023-12-31","filed":"2024-02-01","accn":"0000000001-24-000001","form":"10-K"}]}}}}}'
    _, facts, rejected, _ = normalize(data, 1, 2015)
    assert not rejected
    with connect(tmp_path / "precision.duckdb") as connection:
        path = tmp_path / "facts.parquet"
        save_silver(connection, facts, path, datetime.now(UTC), "source", "bronze", "snapshot")
        stored = connection.execute(f"SELECT value FROM read_parquet({literal(path)})").fetchone()[
            0
        ]
    assert stored == Decimal("12345678901234567890123.125")
