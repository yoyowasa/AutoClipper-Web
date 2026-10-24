"""A resolved existing crop plan, shared by exact preview and final rendering."""

from pydantic import BaseModel, ConfigDict

from app.render.crop_strategy import CropLayout, CropPlan
from app.video.face_detect import FaceDetection


class ShortCropDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: float
    end: float
    width: int
    height: int
    target_height: int
    layout: CropLayout
    plan: CropPlan
    faces: list[FaceDetection]

    def matches(self, *, start, end, width, height, target_height, layout):
        return (self.start, self.end, self.width, self.height, self.target_height, self.layout) == (
            start, end, width, height, target_height, layout,
        )
