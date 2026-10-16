"""Permission failures must not invalidate an otherwise valid login."""
from fastapi.testclient import TestClient
from zhiyin_api.app import create_app
from zhiyin_kernel.errors import AccessDenied, Forbidden


def test_forbidden_and_expired_login_have_distinct_responses():
    app = create_app()

    @app.get('/permission-test')
    async def denied():
        raise Forbidden('需要开发者权限')

    @app.get('/authentication-test')
    async def expired():
        raise AccessDenied('登录令牌已撤销')

    client = TestClient(app)
    denied_response = client.get('/permission-test')
    assert denied_response.status_code == 403
    assert denied_response.json()['code'] == 1008
    expired_response = client.get('/authentication-test')
    assert expired_response.status_code == 401
    assert expired_response.json()['code'] == 1004
