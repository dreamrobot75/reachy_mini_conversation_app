import logging
from typing import Any

from reachy_mini.vision.look_at import look_at_world_pose
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.dance_emotion_moves import GotoQueueMove
from reachy_mini_conversation_app.vision.face_detector_3d import Face3DDetector


logger = logging.getLogger(__name__)


class DetectFace(Tool):
    """Detect the user's face in 3D space and optionally look at the user."""

    name = "detect_face"
    description = (
        "Detect the user's face using the camera or USB webcam, estimate 3D spatial "
        "coordinates (distance, azimuth, elevation), and optionally orient the robot head "
        "to look directly at the user's face. Use when checking user presence, finding the "
        "user, or looking at the user's face."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "look_at_face": {
                "type": "boolean",
                "description": "True to rotate and orient the robot head toward the detected face.",
            },
        },
    }

    def __init__(self) -> None:
        """Initialize the 3D face detector."""
        self._detector: Face3DDetector | None = None

    def _get_detector(self, deps: ToolDependencies) -> Face3DDetector:
        """Lazily initialize the 3D detector with camera calibration if available."""
        if self._detector is None:
            camera_matrix = None
            if hasattr(deps.reachy_mini, "media") and deps.reachy_mini.media is not None:
                camera = getattr(deps.reachy_mini.media, "camera", None)
                if camera is not None:
                    camera_matrix = getattr(camera, "K", None)
            self._detector = Face3DDetector(camera_matrix=camera_matrix)
        return self._detector

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Detect faces in the current camera frame and return 3D coordinates."""
        look_at_face = bool(kwargs.get("look_at_face", False))
        logger.info("Tool call: detect_face look_at_face=%s", look_at_face)

        if not deps.camera_enabled:
            logger.warning("detect_face: Camera is disabled")
            return {"detected": False, "error": "Camera is disabled"}

        if not hasattr(deps.reachy_mini, "media") or deps.reachy_mini.media is None:
            logger.warning("detect_face: Media manager is unavailable")
            return {"detected": False, "error": "Camera media is unavailable"}

        frame_bgr = deps.reachy_mini.media.get_frame()
        if frame_bgr is None:
            logger.warning("detect_face: No frame available from camera")
            return {"detected": False, "error": "No frame available from camera"}

        detector = self._get_detector(deps)
        faces = detector.detect(frame_bgr)

        if not faces:
            logger.info("detect_face: No face detected in frame")
            return {"detected": False, "message": "No face detected in camera frame"}

        # Select the face closest to the center / most prominent
        primary_face = min(faces, key=lambda f: abs(f.azimuth_rad))

        if look_at_face and deps.movement_manager is not None:
            try:
                target_pose = look_at_world_pose(primary_face.x, primary_face.y, primary_face.z)
                current_head_pose = deps.reachy_mini.get_current_head_pose()
                head_joints, antenna_joints = deps.reachy_mini.get_current_joint_positions()
                body_yaw = head_joints[0] if head_joints else 0.0
                antennas = (antenna_joints[0], antenna_joints[1]) if len(antenna_joints) >= 2 else (0.0, 0.0)

                deps.movement_manager.queue_move(
                    GotoQueueMove(
                        target_head_pose=target_pose,
                        start_head_pose=current_head_pose,
                        target_antennas=antennas,
                        start_antennas=antennas,
                        target_body_yaw=body_yaw,
                        start_body_yaw=body_yaw,
                        duration=deps.motion_duration_s,
                    )
                )
                deps.movement_manager.set_moving_state(deps.motion_duration_s)
                logger.info(
                    "Queued head look-at toward 3D face position (x=%.2f, y=%.2f, z=%.2f)",
                    primary_face.x,
                    primary_face.y,
                    primary_face.z,
                )
            except Exception as e:
                logger.warning("Failed to queue look-at move: %s", e)

        return {
            "detected": True,
            "face_count": len(faces),
            "primary_face": {
                "distance_meters": primary_face.distance,
                "x_meters": primary_face.x,
                "y_meters": primary_face.y,
                "z_meters": primary_face.z,
                "azimuth_deg": primary_face.azimuth_deg,
                "elevation_deg": primary_face.elevation_deg,
                "bbox": primary_face.bbox,
                "landmarks": primary_face.landmarks,
            },
        }
