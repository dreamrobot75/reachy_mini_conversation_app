"""Camera manager and multi-source video capture service.

Supports both Reachy Mini daemon camera (IPC/GStreamer) and USB webcams via OpenCV.
Enables real-time camera switching, MJPEG streaming, and frame retrieval for vision tools.
"""

import time
import logging
import threading
from typing import Any, Callable, Optional, cast

import cv2
import numpy as np


logger = logging.getLogger(__name__)


class CameraService:
    """Manages active camera source (robot daemon or USB webcam) and frame acquisition."""

    _instance: Optional["CameraService"] = None

    def __init__(self) -> None:
        """Initialize the camera service with thread safety."""
        self._lock = threading.Lock()
        self._active_device_id: str = "auto"
        self._cached_devices: list[dict[str, str]] = []
        self._last_device_scan_time: float = 0.0
        self._cap: Optional[cv2.VideoCapture] = None
        self._cap_device_index: Optional[int] = None
        self._deps_provider: Optional[Callable[[], Any]] = None

    @classmethod
    def get_instance(cls) -> "CameraService":
        """Return the singleton instance of CameraService."""
        if cls._instance is None:
            cls._instance = CameraService()
        return cls._instance

    def set_deps_provider(self, deps_provider: Callable[[], Any]) -> None:
        """Register provider for ToolDependencies or ReachyMini instance."""
        self._deps_provider = deps_provider

    def list_devices(self, force_refresh: bool = False) -> list[dict[str, str]]:
        """List all available camera devices (robot camera + USB webcams)."""
        now = time.time()
        if not force_refresh and self._cached_devices and (now - self._last_device_scan_time < 10.0):
            return list(self._cached_devices)

        devices: list[dict[str, str]] = [
            {"id": "auto", "name": "자동 선택 (Auto)"},
            {"id": "robot", "name": "Reachy Mini 로봇/시뮬레이터"},
        ]

        # Scan USB webcam indices 0..2
        for idx in range(3):
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap.isOpened():
                    devices.append({"id": str(idx), "name": f"USB 웹캠 {idx}"})
                    cap.release()
            except Exception as e:
                logger.debug("Failed probing camera index %d: %s", idx, e)

        with self._lock:
            self._cached_devices = devices
            self._last_device_scan_time = now
        return devices

    def get_active_device_id(self) -> str:
        """Return the current active device identifier."""
        return self._active_device_id

    def select_device(self, device_id: str) -> bool:
        """Select active camera source."""
        with self._lock:
            if self._active_device_id == device_id:
                return True
            logger.info("Switching active camera to: %s", device_id)
            self._active_device_id = device_id
            if self._cap is not None:
                self._cap.release()
                self._cap = None
                self._cap_device_index = None
        return True

    def get_frame_jpeg(self) -> Optional[bytes]:
        """Fetch current frame as JPEG bytes from the active source."""
        bgr = self.get_frame_bgr()
        if bgr is None:
            return None
        success, encoded = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not success:
            return None
        return encoded.tobytes()

    def get_frame_bgr(self) -> Optional[np.ndarray]:
        """Fetch current frame as BGR numpy array from active source."""
        active = self._active_device_id

        # 1. If explicit USB webcam index is selected
        if active.isdigit():
            idx = int(active)
            return self._read_opencv_device(idx)

        # 2. If robot camera is explicitly selected
        if active == "robot":
            return self._read_robot_frame()

        # 3. If auto: try USB webcam 0 first, then fall back to robot
        frame = self._read_opencv_device(0)
        if frame is not None:
            return frame
        return self._read_robot_frame()

    def _read_opencv_device(self, index: int) -> Optional[np.ndarray]:
        """Read frame from OpenCV VideoCapture with persistent stream."""
        with self._lock:
            if self._cap is None or self._cap_device_index != index:
                if self._cap is not None:
                    self._cap.release()
                self._cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
                self._cap_device_index = index

            if self._cap is not None and self._cap.isOpened():
                ret, frame = self._cap.read()
                if ret and frame is not None:
                    return cast(np.ndarray, frame)
        return None

    def _read_robot_frame(self) -> Optional[np.ndarray]:
        """Read frame from the Reachy Mini robot media interface."""
        try:
            if self._deps_provider:
                deps = self._deps_provider()
                reachy_mini = getattr(deps, "reachy_mini", None) or deps
                media = getattr(reachy_mini, "media", None)
                if media:
                    frame = media.get_frame()
                    if frame is not None:
                        return cast(np.ndarray, frame)
                    jpeg_bytes = media.get_frame_jpeg()
                    if jpeg_bytes:
                        arr = np.frombuffer(jpeg_bytes, dtype=np.uint8)
                        decoded = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                        if decoded is not None:
                            return cast(np.ndarray, decoded)
        except Exception as e:
            logger.debug("Failed reading robot frame: %s", e)
        return None

    def close(self) -> None:
        """Release any open camera resources."""
        with self._lock:
            if self._cap is not None:
                self._cap.release()
                self._cap = None
                self._cap_device_index = None
