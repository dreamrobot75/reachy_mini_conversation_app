"""YOLOv8 real-time object detection and scene understanding service.

Detects objects, people, electronics, desk items, and scene elements from camera frames
with bilingual Korean/English classification and spatial bounding boxes.
"""

import logging
import threading
from typing import Any, Optional
from dataclasses import dataclass

import numpy.typing as npt


logger = logging.getLogger(__name__)

# COCO 80 class labels Korean translation dictionary
COCO_KO_TRANSLATIONS: dict[str, str] = {
    "person": "사람",
    "bicycle": "자전거",
    "car": "자동차",
    "motorcycle": "오토바이",
    "airplane": "비행기",
    "bus": "버스",
    "train": "기차",
    "truck": "트럭",
    "boat": "보트",
    "traffic light": "신호등",
    "fire hydrant": "소화전",
    "stop sign": "정지 표지판",
    "parking meter": "주차요금기",
    "bench": "벤치",
    "bird": "새",
    "cat": "고양이",
    "dog": "강아지",
    "horse": "말",
    "sheep": "양",
    "cow": "소",
    "elephant": "코끼리",
    "bear": "곰",
    "zebra": "얼룩말",
    "giraffe": "기린",
    "backpack": "배낭",
    "umbrella": "우산",
    "handbag": "손가방",
    "tie": "넥타이",
    "suitcase": "여행가방",
    "frisbee": "프리즈비",
    "skis": "스키",
    "snowboard": "스노보드",
    "sports ball": "공",
    "kite": "연",
    "baseball bat": "야구 방망이",
    "baseball glove": "야구 글러브",
    "skateboard": "스케이트보드",
    "surfboard": "서핑보드",
    "tennis racket": "테니스 라켓",
    "bottle": "물병",
    "wine glass": "와인잔",
    "cup": "컵",
    "fork": "포크",
    "knife": "나이프",
    "spoon": "숟가락",
    "bowl": "그릇",
    "banana": "바나나",
    "apple": "사과",
    "sandwich": "샌드위치",
    "orange": "오렌지",
    "broccoli": "브로콜리",
    "carrot": "당근",
    "hot dog": "핫도그",
    "pizza": "피자",
    "donut": "도넛",
    "cake": "케이크",
    "chair": "의자",
    "couch": "소파",
    "potted plant": "화분",
    "bed": "침대",
    "dining table": "식탁",
    "toilet": "변기",
    "tv": "TV",
    "laptop": "노트북",
    "mouse": "마우스",
    "remote": "리모컨",
    "keyboard": "키보드",
    "cell phone": "스마트폰",
    "microwave": "전자레인지",
    "oven": "오븐",
    "toaster": "토스터",
    "sink": "싱크대",
    "refrigerator": "냉장고",
    "book": "책",
    "clock": "시계",
    "vase": "꽃병",
    "scissors": "가위",
    "teddy bear": "곰인형",
    "hair drier": "헤어드라이어",
    "toothbrush": "칫솔",
}


@dataclass(frozen=True)
class DetectedObject:
    """Represents an object detected by YOLOv8."""

    label: str
    label_ko: str
    confidence: float
    bbox: tuple[float, float, float, float]  # (x1, y1, x2, y2)
    center_xy: tuple[float, float]  # (cx, cy)


class YOLODetector:
    """YOLOv8 inference engine with thread-safe model management."""

    _instance: Optional["YOLODetector"] = None

    def __init__(self, model_name: str = "yolov8n.pt") -> None:
        """Initialize the YOLO detector with lazy loading."""
        self._model_name = model_name
        self._model: Any = None
        self._lock = threading.Lock()

    @classmethod
    def get_instance(cls, model_name: str = "yolov8n.pt") -> "YOLODetector":
        """Return the singleton instance."""
        if cls._instance is None:
            cls._instance = YOLODetector(model_name=model_name)
        return cls._instance

    def _ensure_model_loaded(self) -> Any:
        """Load YOLOv8 model lazily when first needed."""
        if self._model is None:
            with self._lock:
                if self._model is None:
                    try:
                        import importlib

                        logger.info("Loading YOLOv8 model: %s", self._model_name)
                        ultralytics_mod = importlib.import_module("ultralytics")
                        yolo_cls = getattr(ultralytics_mod, "YOLO")
                        self._model = yolo_cls(self._model_name)
                    except Exception as e:
                        logger.error("Failed to load YOLOv8 model: %s", e)
                        raise
        return self._model

    def detect(
        self,
        frame_bgr: npt.NDArray[Any],
        conf_threshold: float = 0.30,
    ) -> list[DetectedObject]:
        """Run YOLOv8 object detection on a BGR image frame."""
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        try:
            model = self._ensure_model_loaded()
            results = model(frame_bgr, conf=conf_threshold, verbose=False)
            if not results:
                return []

            detected_list: list[DetectedObject] = []
            for r in results:
                boxes = getattr(r, "boxes", None)
                if boxes is None:
                    continue

                for box in boxes:
                    cls_id = int(box.cls[0].item())
                    conf = float(box.conf[0].item())
                    xyxy = box.xyxy[0].tolist()  # [x1, y1, x2, y2]
                    label_en = str(model.names.get(cls_id, f"class_{cls_id}"))
                    label_ko = COCO_KO_TRANSLATIONS.get(label_en, label_en)

                    x1, y1, x2, y2 = float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])
                    center_x = (x1 + x2) / 2.0
                    center_y = (y1 + y2) / 2.0

                    detected_list.append(
                        DetectedObject(
                            label=label_en,
                            label_ko=label_ko,
                            confidence=round(conf, 3),
                            bbox=(x1, y1, x2, y2),
                            center_xy=(center_x, center_y),
                        )
                    )

            # Sort by confidence descending
            detected_list.sort(key=lambda o: o.confidence, reverse=True)
            return detected_list
        except Exception as e:
            logger.error("Error during YOLOv8 detection: %s", e)
            return []
