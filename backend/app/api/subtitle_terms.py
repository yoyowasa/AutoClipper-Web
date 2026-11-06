"""List the exact subtitle terms learned per character, and switch single rules off or on again."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.intelligence import PRIVATE_HEADERS, require_local_origin
from app.config import Settings, get_settings
from app.storage.paths import StoragePaths, get_storage_paths
from app.subtitle_terms import MAX_SOURCE_CHARS, derive_rules, read_store, set_disabled

router = APIRouter(prefix="/api/subtitle-terms", tags=["subtitle-terms"])


class TermRead(BaseModel):
    src: str
    dst: str
    count: int
    jobs: int
    kept: int
    reversed: int
    active: bool
    disabled: bool


class CharacterTermsRead(BaseModel):
    id: str
    character: str
    terms: list[TermRead]


class TermSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    src: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    dst: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)


def _characters(paths: StoragePaths) -> dict[str, str]:
    result = {}
    for file in sorted(paths.subtitle_terms.glob("*.json")):
        try:
            result[file.stem] = json.loads(file.read_text(encoding="utf-8"))["character"]
        except (OSError, ValueError, KeyError):
            continue
    return result


@router.get("", response_model=list[CharacterTermsRead])
def list_terms(response: Response, paths: StoragePaths = Depends(get_storage_paths)):
    response.headers.update(PRIVATE_HEADERS)
    result = []
    for id, character in _characters(paths).items():
        rules = [r for r in derive_rules(read_store(paths.root, character)) if r["active"] or r["disabled"] or r["count"] >= 2]
        result.append(CharacterTermsRead(id=id, character=character, terms=[
            TermRead(**{k: r[k] for k in TermRead.model_fields}) for r in rules]))
    return result


def _switch(character_id: str, body: TermSwitch, request: Request, config: Settings, paths: StoragePaths, disabled: bool):
    require_local_origin(request, config)
    character = _characters(paths).get(character_id)
    if character is None:
        raise HTTPException(404, "このキャラの学習済みの語がありません。")
    if not any((r["src"], r["dst"]) == (body.src, body.dst) for r in derive_rules(read_store(paths.root, character))):
        raise HTTPException(404, "その語の組み合わせはありません。")
    set_disabled(paths.root, character, body.src, body.dst, disabled)
    return Response(status_code=204)


@router.post("/{character_id}/disable", status_code=204)
def disable_term(character_id: str, body: TermSwitch, request: Request, config: Settings = Depends(get_settings),
                 paths: StoragePaths = Depends(get_storage_paths)):
    return _switch(character_id, body, request, config, paths, True)


@router.post("/{character_id}/enable", status_code=204)
def enable_term(character_id: str, body: TermSwitch, request: Request, config: Settings = Depends(get_settings),
                paths: StoragePaths = Depends(get_storage_paths)):
    return _switch(character_id, body, request, config, paths, False)
