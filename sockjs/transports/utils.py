import asyncio
import http.cookies
from datetime import datetime, timedelta

import async_timeout
from aiohttp import hdrs


CACHE_CONTROL = "no-store, no-cache, no-transform, must-revalidate, max-age=0"


def session_cookie(request):
    cookie = request.cookies.get("JSESSIONID", "dummy")
    cookies = http.cookies.SimpleCookie()
    cookies["JSESSIONID"] = cookie
    cookies["JSESSIONID"]["path"] = "/"
    return ((hdrs.SET_COOKIE, cookies["JSESSIONID"].output(header="")[1:]),)


td365 = timedelta(days=365)
td365seconds = str(
    (td365.microseconds + (td365.seconds + td365.days * 24 * 3600) * 10**6) // 10**6
)


def cache_headers():
    d = datetime.now() + td365
    return (
        (hdrs.ACCESS_CONTROL_MAX_AGE, td365seconds),
        (hdrs.CACHE_CONTROL, "max-age=%s, public" % td365seconds),
        (hdrs.EXPIRES, d.strftime("%a, %d %b %Y %H:%M:%S")),
    )


async def cancel_tasks(*coros_or_futures, timeout=1):
    """Cancel all not stopped coroutine or feature before exit
    from this context manager.
    """
    futures = [asyncio.ensure_future(cf) for cf in coros_or_futures if cf]
    waiting_to_complete = []
    for fut in futures:
        if not fut.cancelled() and fut.done():
            continue
        fut.cancel()
        waiting_to_complete.append(fut)
    if waiting_to_complete:
        try:
            async with async_timeout.timeout(timeout):
                await asyncio.gather(*waiting_to_complete, return_exceptions=True)
        except asyncio.TimeoutError:
            pass
