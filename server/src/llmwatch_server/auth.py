import secrets
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from .config import Settings, get_settings


def require_api_key(
    config: Annotated[Settings, Depends(get_settings)],
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing API Key")
    elif not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid API Key format")
    elif not secrets.compare_digest(
        authorization.removeprefix("Bearer "), config.api_key
    ):
        raise HTTPException(status_code=401, detail="Invalid API Key")
