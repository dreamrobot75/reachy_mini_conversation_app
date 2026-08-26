"""YOLOv8-powered object detection tool for Reachy Mini."""

import logging
from typing import Any
from collections import Counter

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.vision.yolo_detector import YOLODetector


logger = logging.getLogger(__name__)


class DetectObjects(Tool):
    """Detect and recognize objects, people, and desk items using YOLOv8."""

    name = "detect_objects"
    description = (
        "Detect and identify objects, items, electronics, and people in front of the camera using YOLOv8. "
        "Use when the user asks what is on the desk, what objects are in view, whether a specific item "
        "(phone, cup, book, laptop, person, etc.) is visible, or to count objects."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "target_object": {
                "type": "string",
                "description": (
                    "Optional target object or category to search for in Korean or English "
                    "(e.g. 'cup', 'phone', '스마트폰', '사람', 'all'). Defaults to 'all'."
                ),
            },
        },
    }

    def __init__(self) -> None:
        """Initialize the object detection tool."""
        self._detector = YOLODetector.get_instance()

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Run YOLOv8 object detection on the current active camera frame."""
        target = (kwargs.get("target_object") or "all").strip().lower()
        logger.info("Tool call: detect_objects target=%s", target)

        if not deps.camera_enabled:
            logger.warning("detect_objects: Camera is disabled")
            return {"detected": False, "error": "Camera is disabled"}

        frame_bgr = None
        try:
            from reachy_mini_conversation_app.camera_service import CameraService

            frame_bgr = CameraService.get_instance().get_frame_bgr()
        except Exception:
            frame_bgr = None

        if frame_bgr is None and hasattr(deps.reachy_mini, "media") and deps.reachy_mini.media is not None:
            frame_bgr = deps.reachy_mini.media.get_frame()

        if frame_bgr is None:
            logger.warning("detect_objects: No frame available from camera")
            return {"detected": False, "error": "No frame available from camera"}

        detections = self._detector.detect(frame_bgr)

        # Filter by target object if specified and not 'all'
        if target and target not in {"all", "모두", "전부", ""}:
            filtered = [d for d in detections if target in d.label.lower() or target in d.label_ko.lower()]
            if not filtered:
                visible_preview = [f"{d.label_ko}({d.label})" for d in detections[:5]]
                return {
                    "detected": False,
                    "target": target,
                    "message": f"'{target}'을(를) 카메라 시야에서 찾지 못했습니다.",
                    "all_visible_objects": visible_preview,
                }
            detections = filtered

        if not detections:
            return {
                "detected": False,
                "message": "카메라 시야에서 인식된 물체가 없습니다.",
                "objects": [],
            }

        # Build Korean summary
        counts = Counter(d.label_ko for d in detections)
        summary_parts = [
            f"{label} {count}개" if label != "사람" else f"사람 {count}명" for label, count in counts.items()
        ]
        summary_str = f"카메라 시야에서 {', '.join(summary_parts)}이(가) 감지되었습니다."

        objects_data = [
            {
                "label_ko": d.label_ko,
                "label_en": d.label,
                "confidence": d.confidence,
                "center": {"x": round(d.center_xy[0], 1), "y": round(d.center_xy[1], 1)},
            }
            for d in detections
        ]

        return {
            "detected": True,
            "count": len(detections),
            "summary": summary_str,
            "objects": objects_data,
        }
