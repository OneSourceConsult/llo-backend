import logging
import os
from typing import Dict
from uuid import UUID
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.schemas.Provider import Provider
from app.schemas.Task import Task
from app.controllers.providers.common import (
    loadProvidersFromConfig,
)
from app.routers import clusters, providers, tasks

# from .controllers.monitoring import init_prometheus

app = FastAPI()
router = APIRouter()

# init_prometheus()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


logging.basicConfig(level=os.environ["APP_LOG_LEVEL"])
log = logging.getLogger(__name__)

# TODO: Warning: Not persistent! use as stateless
app.state.tasks: Dict[UUID, Task] = {}
app.state.providers: Dict[UUID, Provider] = loadProvidersFromConfig()


version = os.environ["APP_API_VERSION"]
app.include_router(providers.router, prefix=version)
app.include_router(clusters.router, prefix=version)
app.include_router(tasks.router, prefix=version)
