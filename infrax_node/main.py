from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status

from . import crud, node
from .config import config
from .store import store
from .types import App, Job, NodeState

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logging.info("Node startup")

    if config.host.local_only:
        yield
        return

    crud.register(config)
    yield


app = FastAPI(lifespan=lifespan)


@app.get("/__health")
async def health() -> Response:
    return Response(status_code=status.HTTP_200_OK)


async def fail_on_busy():
    if store.state == NodeState.BUSY:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Node is busy",
        )


@app.post("/app", status_code=status.HTTP_200_OK, dependencies=[Depends(fail_on_busy)])
async def install_app(app: App, _: Request) -> None:
    """
    Set the app to be installed on the node
    """
    # check if the app is already installed
    # if so, return 409
    if app.id in store.app_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="App is already installed"
        )

    Thread(target=node.install_app, args=(app,), daemon=True).start()


@app.delete(
    "/app", status_code=status.HTTP_200_OK, dependencies=[Depends(fail_on_busy)]
)
async def uninstall_app(
    app: App,
    _: Request,
) -> None:
    """
    Delete the app from the node
    """
    # check if the app is installed
    # if not, return 404
    if app.id not in store.app_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App is not installed",
        )
    Thread(target=node.uninstall_app, args=(app,), daemon=True).start()


@app.post(
    "/job",
    response_model=Job,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(fail_on_busy)],
)
async def create_job(job: Job, _: Request):
    # check if the app is installed
    # if not, return 404
    if job.app_id not in store.app_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="App is not installed",
        )
    store.job = job
    Thread(target=node.run_job, args=(job,), daemon=True).start()
    return job.model_dump()


# @app.get("/job", response_model=Job)
# async def get_job(_: Request) -> Job:
#     if job := store.job_request:
#         return job
#     raise HTTPException(status_code=404, detail="No job found")


# @app.delete("/job", status_code=status.HTTP_204_NO_CONTENT)
# async def delete_job(_: Request):
#     store.job_request = None
