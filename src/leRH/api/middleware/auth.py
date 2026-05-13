from __future__ import annotations

import logging

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from leRH.config import settings

logger = logging.getLogger(__name__)

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=True)


async def verify_api_key(api_key: str = Security(API_KEY_HEADER)) -> str:
    """Vérifie la clé API fournie dans le header X-API-Key.

    Si la clé interne n'est pas configurée, l'accès est refusé par défaut.
    """
    internal_key = settings.internal_api_key.get_secret_value()

    if not internal_key:
        logger.error("INTERNAL_API_KEY is not set in settings")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="La configuration de sécurité du serveur est incomplète.",
        )

    if api_key != internal_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API invalide",
        )

    return api_key
