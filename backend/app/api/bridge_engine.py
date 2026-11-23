"""Read and change the engine, model and effort the host bridge uses per lane."""
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.intelligence import PRIVATE_HEADERS, require_local_origin
from app.bridge_engine import (
    BridgeEngineRead, EngineSettings, bridge_status, current_catalog, read_bridge_engine, save_bridge_engine,
    unsupported_choice,
)
from app.config import Settings, get_settings
from app.storage.paths import StoragePaths, get_storage_paths

router = APIRouter(prefix="/api/bridge-engine", tags=["bridge-engine"])


@router.get("", response_model=BridgeEngineRead)
def get_bridge_engine(response: Response, paths: StoragePaths = Depends(get_storage_paths)) -> BridgeEngineRead:
    response.headers.update(PRIVATE_HEADERS)
    return read_bridge_engine(paths)


@router.put("", response_model=BridgeEngineRead)
def put_bridge_engine(body: EngineSettings, request: Request, response: Response,
                      config: Settings = Depends(get_settings),
                      paths: StoragePaths = Depends(get_storage_paths)) -> BridgeEngineRead:
    require_local_origin(request, config)
    response.headers.update(PRIVATE_HEADERS)
    problem = unsupported_choice(body, current_catalog(bridge_status(paths))[0])
    if problem:
        raise HTTPException(422, problem)
    save_bridge_engine(paths, body)
    return read_bridge_engine(paths)
