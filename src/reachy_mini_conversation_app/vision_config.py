"""Vision configuration and registered user identity persistence."""

import json
import logging
from typing import Any, ClassVar, Optional
from pathlib import Path
from dataclasses import asdict, dataclass


logger = logging.getLogger(__name__)

CONFIG_PATH = Path(".vision_settings.json")


@dataclass
class VisionConfig:
    """Vision, camera and registered person settings."""

    registered_person_name: str = "사용자"
    registered_person_desc: str = "주인님 / 사용자"
    face_detection_enabled: bool = True
    auto_gaze_enabled: bool = True
    min_face_confidence: float = 0.5
    yolo_detection_enabled: bool = True
    active_camera: str = "auto"

    _instance: ClassVar[Optional["VisionConfig"]] = None

    @classmethod
    def get_instance(cls) -> "VisionConfig":
        """Get or load singleton vision configuration."""
        if cls._instance is None:
            cls._instance = cls.load()
        return cls._instance

    @classmethod
    def load(cls) -> "VisionConfig":
        """Load vision settings from JSON file or default."""
        if CONFIG_PATH.exists():
            try:
                data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                fields = cls.__dataclass_fields__
                valid_data = {k: v for k, v in data.items() if k in fields}
                return cls(**valid_data)
            except Exception as e:
                logger.warning("Failed loading vision settings: %s", e)
        return cls()

    def save(self) -> None:
        """Persist current settings to JSON file."""
        try:
            CONFIG_PATH.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Failed saving vision settings: %s", e)

    def update(self, payload: dict[str, Any]) -> None:
        """Update settings from dictionary payload and persist."""
        if "registered_person_name" in payload:
            self.registered_person_name = str(payload["registered_person_name"]).strip()
        if "registered_person_desc" in payload:
            self.registered_person_desc = str(payload["registered_person_desc"]).strip()
        if "face_detection_enabled" in payload:
            self.face_detection_enabled = bool(payload["face_detection_enabled"])
        if "auto_gaze_enabled" in payload:
            self.auto_gaze_enabled = bool(payload["auto_gaze_enabled"])
        if "min_face_confidence" in payload:
            self.min_face_confidence = float(payload["min_face_confidence"])
        if "yolo_detection_enabled" in payload:
            self.yolo_detection_enabled = bool(payload["yolo_detection_enabled"])
        if "active_camera" in payload:
            self.active_camera = str(payload["active_camera"])
        self.save()
