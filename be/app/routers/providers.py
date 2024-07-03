import logging
from typing import List

from fastapi import APIRouter, Request
from app.schemas.Provider import Provider

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/providers", tags=["providers"],
            response_model=List[Provider])
def list_providers(req: Request):
    """
    This endpoint is designed to get a list of providers.

    Input

    - None

    Output

    - A list of Provider objects.

    

    """
    providers = req.app.state.providers
    return [provider for uuid, provider in providers.items()]
