import secrets

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
)
from starlette.requests import HTTPConnection
from starlette.responses import Response

from app.loader import settings


class BasicAuthBackend(AuthenticationBackend):
    async def authenticate(self, conn: HTTPConnection):
        if "Authorization" not in conn.headers:
            return

        auth = conn.headers["Authorization"]
        try:
            scheme, credentials = auth.split()
            if scheme.lower() != "basic":
                return
            decoded = credentials.encode("ascii")
            username, password = decoded.split(b":")
            correct_username = secrets.compare_digest(
                username, settings.admin_username.encode("utf8")
            )
            correct_password = secrets.compare_digest(
                password, settings.admin_password.encode("utf8")
            )
            if correct_username and correct_password:
                return AuthCredentials(["authenticated"]), SimpleUser(
                    settings.admin_username
                )
        except Exception:
            pass


def on_auth_error(request, exc: Exception):
    return Response(
        "Unauthorized",
        status_code=401,
        headers={"WWW-Authenticate": "Basic realm='Private Area'"},
    )
