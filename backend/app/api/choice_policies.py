"""Read version history and explicitly restore the immediately preceding version."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.api.intelligence import PRIVATE_HEADERS, require_local_origin
from app.config import Settings, get_settings
from app.db import get_db
from app.intelligence.common import now
from app.intelligence.models import Channel
from app.intelligence.choice_policy_models import ChoicePolicyHead, ChoicePolicyVersion, ChoicePolicyDecision
from app.intelligence.choice_policy_schema import ChoicePolicyValues
from app.intelligence.choice_policy_engine import decision
from app.intelligence.policy import statistical_expiry
from uuid import uuid4

router = APIRouter(prefix="/api/intelligence/channels", tags=["intelligence"])


class VersionRead(BaseModel):
    id: str
    previousId: str | None
    createdAt: datetime
    values: ChoicePolicyValues


class DecisionRead(BaseModel):
    id: str
    action: str
    reason: str
    fromId: str
    toId: str
    analysisId: str
    createdAt: datetime
    evidence: dict | None


class PolicyRead(BaseModel):
    id: str
    character: str
    format: str
    currentId: str
    versions: list[VersionRead]
    decisions: list[DecisionRead]


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectedVersion: str


@router.get("/{channel_id}/choice-policies", response_model=list[PolicyRead])
def read_policies(channel_id: int, response: Response, db: Session = Depends(get_db)):
    response.headers.update(PRIVATE_HEADERS)
    if db.get(Channel, channel_id) is None:
        raise HTTPException(404, "チャンネルがありません。")
    result = []
    for head in db.scalars(select(ChoicePolicyHead).where(ChoicePolicyHead.channel_id == channel_id)
                          .order_by(ChoicePolicyHead.character, ChoicePolicyHead.format)):
        versions = list(db.scalars(select(ChoicePolicyVersion).where(ChoicePolicyVersion.policy_id == head.id)
                                  .order_by(ChoicePolicyVersion.created_at.desc(), ChoicePolicyVersion.id.desc())))
        events = list(db.scalars(select(ChoicePolicyDecision).where(ChoicePolicyDecision.policy_id == head.id)
                                .order_by(ChoicePolicyDecision.created_at.desc(), ChoicePolicyDecision.id.desc())))
        result.append(PolicyRead(id=head.id, character=head.character, format=head.format, currentId=head.current_id,
            versions=[VersionRead(id=v.id, previousId=v.previous_id, createdAt=v.created_at, values=v.values) for v in versions],
            decisions=[DecisionRead(id=e.id, action=e.action, reason=e.reason, fromId=e.from_id, toId=e.to_id,
                analysisId=e.analysis_id, createdAt=e.created_at,
                evidence=e.evidence if e.evidence_expires_at > now() else None) for e in events]))
    return result


@router.post("/{channel_id}/choice-policies/{policy_id}/rollback", status_code=204)
def rollback_policy(channel_id: int, policy_id: str, body: RestoreRequest, request: Request,
                    db: Session = Depends(get_db), config: Settings = Depends(get_settings)):
    require_local_origin(request, config)
    db.execute(update(Channel).where(Channel.id == channel_id).values(id=Channel.id))
    head = db.get(ChoicePolicyHead, policy_id, populate_existing=True)
    if head is None or head.channel_id != channel_id:
        db.rollback()
        raise HTTPException(404, "このチャンネルの方針がありません。")
    current = db.get(ChoicePolicyVersion, head.current_id)
    if head.current_id != body.expectedVersion or not current.previous_id:
        db.rollback()
        raise HTTPException(409, "版が変わったか、戻せる直前の版がありません。読み直してください。")
    stamp = now()
    decision(db, head, "manual_" + uuid4().hex, stamp, statistical_expiry(stamp, config),
             "rollback", "MANUAL_ROLLBACK", current.previous_id)
    db.commit()
