import io
from email.message import Message
from urllib.error import HTTPError

import pytest

from creditlake.sources import SECClient


def test_live_requires_contact():
    with pytest.raises(ValueError):
        SECClient("anonymous-bot")


def test_429_retries_and_uses_contact_header():
    requests, times = [], []
    current = [0.0]

    def sleep(duration):
        current[0] += duration

    def opener(request, timeout):
        requests.append(request)
        times.append(current[0])
        if len(requests) == 1:
            headers = Message()
            headers["Retry-After"] = "2"
            raise HTTPError(request.full_url, 429, "rate limited", headers, None)
        return io.BytesIO(b'{"cik":1}')

    client = SECClient(
        "Test owner@example.com", opener=opener, sleep=sleep, clock=lambda: current[0]
    )
    data, url = client.fetch(1)
    client.fetch(1)
    assert data == b'{"cik":1}'
    assert url.endswith("CIK0000000001.json")
    assert requests[0].get_header("User-agent") == "Test owner@example.com"
    assert times[1] - times[0] >= 2
    assert times[2] - times[1] == pytest.approx(0.55)


def test_403_does_not_retry():
    calls = []

    def opener(request, timeout):
        calls.append(request)
        raise HTTPError(request.full_url, 403, "forbidden", Message(), None)

    client = SECClient("Test owner@example.com", opener=opener, sleep=lambda _: None)
    with pytest.raises(HTTPError):
        client.fetch(1)
    assert len(calls) == 1
