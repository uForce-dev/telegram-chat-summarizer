import base64
import binascii
import secrets

from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    SimpleUser,
    AuthenticationError,
)
from starlette.requests import HTTPConnection
from starlette.responses import PlainTextResponse

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
            decoded = base64.b64decode(credentials).decode("ascii")
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise AuthenticationError("Invalid basic auth credentials")

        username, _, password = decoded.partition(":")
        correct_username = secrets.compare_digest(
            username.encode("utf8"), settings.admin_username.encode("utf8")
        )
        correct_password = secrets.compare_digest(
            password.encode("utf8"), settings.admin_password.encode("utf8")
        )
        if correct_username and correct_password:
            return AuthCredentials(["authenticated"]), SimpleUser(
                settings.admin_username
            )


def on_auth_error(request, exc: Exception):
    return PlainTextResponse(
        str(exc), status_code=401, headers={"WWW-Authenticate": "Basic"}
    )
