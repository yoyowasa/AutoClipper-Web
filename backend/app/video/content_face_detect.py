"""Content-selected faces: reuse anime detection before the human-face fallback."""

from PIL import Image

from app.render.thumbnail_face import detect_thumbnail_face
from app.video.face_detect import FaceDetection, _sample_times, detect_faces_for_clip


CONTENT_FACE_SAMPLE_COUNT = 5


def detect_content_faces_for_clip(video_path, start, end, *, detector=detect_thumbnail_face,
                                   capture_factory=None, fallback=detect_faces_for_clip):
    import cv2
    capture = (capture_factory or cv2.VideoCapture)(str(video_path))
    faces = []
    try:
        if capture.isOpened():
            for second in _sample_times(start, max(start, end - .001), CONTENT_FACE_SAMPLE_COUNT):
                capture.set(cv2.CAP_PROP_POS_MSEC, second * 1000)
                ok, frame = capture.read()
                if not ok or frame is None:
                    continue
                face = detector(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
                if face is not None:
                    faces.append(FaceDetection(second, second, *face))
    finally:
        capture.release()
    # Never combine unrelated human-cascade background detections with anime faces.
    # One/two detections stay insufficient evidence in the unchanged quality gate.
    return faces if faces else fallback(video_path, start, end)
