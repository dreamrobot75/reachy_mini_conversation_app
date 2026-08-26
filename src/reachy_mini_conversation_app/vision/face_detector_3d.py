"""3D spatial face detection and coordinate estimation.

Estimates 3D coordinates (X forward, Y left, Z up in meters) and head gaze angles
(azimuth, elevation) from 2D camera frames and facial landmarks using pinhole camera
geometry and nominal human anthropometric dimensions (IPD and face width).
"""

import math
import logging
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from reachy_mini.vision.face_detector import Face, FaceDetector


logger = logging.getLogger(__name__)

NOMINAL_IPD_METERS = 0.063
NOMINAL_FACE_WIDTH_METERS = 0.14
DEFAULT_HORIZONTAL_FOV_RAD = math.radians(60.0)
MIN_VALID_DEPTH_METERS = 0.20
MAX_VALID_DEPTH_METERS = 4.00


@dataclass(frozen=True)
class Face3DCoordinates:
    """3D spatial position and gaze angles of a detected face in the robot reference frame."""

    x: float
    y: float
    z: float
    distance: float
    azimuth_rad: float
    elevation_rad: float
    azimuth_deg: float
    elevation_deg: float
    bbox: tuple[float, float, float, float]
    landmarks: dict[str, tuple[float, float]]


class Face3DDetector:
    """Detects faces in BGR frames and computes their 3D spatial position."""

    def __init__(
        self,
        camera_matrix: NDArray[np.float64] | None = None,
        horizontal_fov_rad: float = DEFAULT_HORIZONTAL_FOV_RAD,
    ) -> None:
        """Initialize the 3D face detector with camera calibration or FOV."""
        self._detector = FaceDetector()
        self._camera_matrix = camera_matrix
        self._horizontal_fov_rad = horizontal_fov_rad

    def set_camera_matrix(self, camera_matrix: NDArray[np.float64] | None) -> None:
        """Update the intrinsic camera matrix."""
        self._camera_matrix = camera_matrix

    def detect(self, frame_bgr: NDArray[np.uint8]) -> list[Face3DCoordinates]:
        """Detect faces in a BGR frame and return their 3D spatial coordinates."""
        if frame_bgr is None or frame_bgr.size == 0:
            return []

        height, width = frame_bgr.shape[:2]
        if height == 0 or width == 0:
            return []

        try:
            detected_faces = self._detector.detect(frame_bgr)
        except Exception as e:
            logger.warning("Face detection inference failed: %s", e)
            return []

        results: list[Face3DCoordinates] = []
        for face in detected_faces:
            coords = self._estimate_3d_coordinates(face, width, height)
            if coords is not None:
                results.append(coords)

        return results

    def _estimate_3d_coordinates(self, face: Face, width: int, height: int) -> Face3DCoordinates | None:
        """Estimate 3D position and angles for a single detected face."""
        fx, fy, cx, cy = self._get_camera_intrinsics(width, height)
        if fx <= 0.0 or fy <= 0.0:
            return None

        bx, by, bw, bh = face.bbox
        re_x, re_y = face.right_eye
        le_x, le_y = face.left_eye
        n_x, n_y = face.nose

        eye_dx = le_x - re_x
        eye_dy = le_y - re_y
        eye_dist_px = math.hypot(eye_dx, eye_dy)

        if eye_dist_px > 10.0:
            depth_ipd = (fx * NOMINAL_IPD_METERS) / eye_dist_px
            depth_bbox = (fx * NOMINAL_FACE_WIDTH_METERS) / max(1.0, bw)
            depth_m = 0.7 * depth_ipd + 0.3 * depth_bbox
        else:
            depth_m = (fx * NOMINAL_FACE_WIDTH_METERS) / max(1.0, bw)

        depth_m = max(MIN_VALID_DEPTH_METERS, min(MAX_VALID_DEPTH_METERS, depth_m))

        center_u = 0.5 * (re_x + le_x) if eye_dist_px > 5.0 else bx + 0.5 * bw
        center_v = 0.5 * (re_y + le_y) if eye_dist_px > 5.0 else by + 0.5 * bh

        x_cam = (center_u - cx) * depth_m / fx
        y_cam = (center_v - cy) * depth_m / fy
        z_cam = depth_m

        x_robot = z_cam
        y_robot = -x_cam
        z_robot = -y_cam

        distance = math.hypot(x_robot, y_robot, z_robot)
        ground_distance = math.hypot(x_robot, y_robot)

        azimuth_rad = math.atan2(y_robot, x_robot)
        elevation_rad = math.atan2(z_robot, max(1e-6, ground_distance))

        return Face3DCoordinates(
            x=round(x_robot, 3),
            y=round(y_robot, 3),
            z=round(z_robot, 3),
            distance=round(distance, 3),
            azimuth_rad=round(azimuth_rad, 4),
            elevation_rad=round(elevation_rad, 4),
            azimuth_deg=round(math.degrees(azimuth_rad), 2),
            elevation_deg=round(math.degrees(elevation_rad), 2),
            bbox=(round(bx, 1), round(by, 1), round(bw, 1), round(bh, 1)),
            landmarks={
                "right_eye": (round(re_x, 1), round(re_y, 1)),
                "left_eye": (round(le_x, 1), round(le_y, 1)),
                "nose": (round(n_x, 1), round(n_y, 1)),
            },
        )

    def _get_camera_intrinsics(self, width: int, height: int) -> tuple[float, float, float, float]:
        """Compute or extract focal lengths and optical center (fx, fy, cx, cy)."""
        if self._camera_matrix is not None and self._camera_matrix.shape == (3, 3):
            fx = float(self._camera_matrix[0, 0])
            fy = float(self._camera_matrix[1, 1])
            cx = float(self._camera_matrix[0, 2])
            cy = float(self._camera_matrix[1, 2])
            return fx, fy, cx, cy

        half_fov = max(0.01, self._horizontal_fov_rad * 0.5)
        fx = (width * 0.5) / math.tan(half_fov)
        fy = fx
        cx = width * 0.5
        cy = height * 0.5
        return fx, fy, cx, cy
