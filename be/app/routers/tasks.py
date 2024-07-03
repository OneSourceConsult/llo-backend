import logging
import traceback
from typing import Dict
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from app.schemas.Task import Task

router = APIRouter()
log = logging.getLogger(__name__)


@router.get("/task", tags=["tasks"])
def get_task(uuid: UUID, req: Request):
    tasks = req.app.state.tasks
       
    try:
        task = tasks.get(uuid)
        if task is None:
            raise ValueError("Task Not Found")
        return task

    except ValueError as e:
        log.error("A value error exception occurred: {}".format(e))
        raise HTTPException(status_code=500, detail="{}".format(e))
    except Exception as e:
        tb = traceback.format_exc()
        log.error("An exception occurred: {}".format(tb))
        raise HTTPException(status_code=500, detail="{}".format(e))
