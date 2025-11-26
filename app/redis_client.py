from fastapi import Request

def get_redis(request: Request):
    """
    Singleton Redis client.
    """
    return request.app.state.redis
