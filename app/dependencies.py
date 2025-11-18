import httpx

async_client = httpx.AsyncClient(timeout=5.0)

def get_http_client() -> httpx.AsyncClient:
    """
    Reusable HTTPX client injected via Depends().
    """
    return async_client
