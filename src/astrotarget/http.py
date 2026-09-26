import asyncio

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ERROR_BODY_CHARS = 1500


def _response_detail(response: httpx.Response) -> str:
    """Return a bounded upstream response body suitable for diagnostics/logs."""
    try:
        detail = response.text.strip()
    except Exception:
        detail = ""
    if not detail:
        return "<empty response body>"
    if len(detail) > MAX_ERROR_BODY_CHARS:
        return detail[:MAX_ERROR_BODY_CHARS] + "... [truncated]"
    return detail


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    params: dict,
    retries: int = 3,
):
    """GET JSON with backoff only for transient transport/server failures.

    Non-retryable HTTP errors such as a TAP/ADQL 400 are raised immediately and
    include a bounded copy of the upstream response body, which usually contains
    the actual schema or query error.
    """
    last_error: Exception | None = None

    for attempt in range(retries):
        try:
            response = await client.get(url, params=params)
        except httpx.TransportError as exc:
            last_error = exc
            if attempt < retries - 1:
                await asyncio.sleep(2**attempt)
                continue
            break

        if response.status_code in RETRY_STATUS:
            last_error = httpx.HTTPStatusError(
                f"{response.status_code}",
                request=response.request,
                response=response,
            )
            if attempt < retries - 1:
                await asyncio.sleep(2**attempt)
                continue
            break

        if response.is_error:
            raise RuntimeError(
                f"Upstream returned HTTP {response.status_code}: {url}: "
                f"{_response_detail(response)}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"Upstream returned invalid JSON: {url}: {_response_detail(response)}"
            ) from exc

    raise RuntimeError(f"Upstream failed after {retries} attempts: {url}: {last_error}")
