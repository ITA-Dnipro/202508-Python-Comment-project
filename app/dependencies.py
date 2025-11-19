from fastapi import Request

def get_http_client(request: Request):
    return request.app.state.http_client
