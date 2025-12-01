# proctor_vision/openvino_vision.py

import time
from dataclasses import dataclass, field
from typing import Optional, Tuple, List

import cv2
import numpy as np
from openvino.runtime import Core


@dataclass
class ProctorState:
    session_id: str
    max_warnings: int = 3

    # baseline head pose
    baseline_yaw: Optional[float] = None
    baseline_pitch: Optional[float] = None
    baseline_roll: Optional[float] = None

    # for center tracking (optional)
    baseline_cx: Optional[float] = None
    baseline_cy: Optional[float] = None
    baseline_w: Optional[float] = None
    baseline_h: Optional[float] = None

    warning_count: int = 0
    last_face_time: float = field(default_factory=time.time)
    terminated: bool = False

    # fatigue-friendly behaviour
    deviation_start_time: Optional[float] = None
    last_warning_time: float = field(default_factory=lambda: 0.0)


class OpenVINOProctor:
    """
    Uses OpenVINO face detection + head pose estimation to:
    - calibrate baseline head pose
    - detect large deviations & issue warnings/termination
    - ignore brief / natural movements (fatigue-friendly)
    """

    def __init__(
        self,
        state: ProctorState,
        model_dir: str = "models",
        device: str = "CPU",
    ):
        self.state = state
        self.core = Core()

        # --- Load models ---
        fd_model_path = f"{model_dir}/face-detection-adas-0001.xml"
        hp_model_path = f"{model_dir}/head-pose-estimation-adas-0001.xml"

        # Face detection model
        fd_model = self.core.read_model(fd_model_path)
        self.fd_compiled = self.core.compile_model(fd_model, device)
        self.fd_input = self.fd_compiled.input(0)
        self.fd_output = self.fd_compiled.output(0)
        _, _, self.fd_h, self.fd_w = self.fd_input.shape  # 1,3,H,W

        # Head pose model
        hp_model = self.core.read_model(hp_model_path)
        self.hp_compiled = self.core.compile_model(hp_model, device)
        self.hp_input = self.hp_compiled.input(0)
        _, _, self.hp_h, self.hp_w = self.hp_input.shape

        # ---------- thresholds (tunable) ----------

        # Soft zone = normal small movements / slight fatigue
        # Hard zone = clear looking away / big deviation
        self.soft_yaw_threshold_deg = 15.0
        self.hard_yaw_threshold_deg = 30.0

        self.soft_pitch_threshold_deg = 15.0
        self.hard_pitch_threshold_deg = 30.0

        self.soft_roll_threshold_deg = 20.0
        self.hard_roll_threshold_deg = 35.0

        # seconds without *any* face before warning
        self.no_face_timeout = 2.0

        # Deviation must last this long to count (seconds)
        self.soft_deviation_min_duration = 2.0   # for soft zone
        self.hard_deviation_min_duration = 0.5   # for hard zone

        # After giving a warning, wait this long before another (seconds)
        self.warning_cooldown = 5.0

        # frames with good detection needed for calibration
        self.min_calibration_frames = 20

    # ---------- Helpers ----------

    def _preprocess_for_fd(self, frame_bgr: np.ndarray) -> np.ndarray:
        """Resize and transpose frame for face detection model."""
        img = cv2.resize(frame_bgr, (self.fd_w, self.fd_h))
        img = img.transpose(2, 0, 1)  # HWC -> CHW
        img = img[np.newaxis, :, :, :].astype(np.float32)
        return img

    def _detect_faces(
        self, frame_bgr: np.ndarray, conf_thresh: float = 0.6
    ) -> List[Tuple[int, int, int, int]]:
        """
        Detect all faces. Returns list of boxes (x1, y1, x2, y2).
        """
        h, w, _ = frame_bgr.shape
        input_tensor = self._preprocess_for_fd(frame_bgr)
        result = self.fd_compiled([input_tensor])[self.fd_output]

        # result shape: [1, 1, N, 7] => [image_id, label, conf, xmin, ymin, xmax, ymax]
        detections = result[0, 0, :, :]
        boxes: List[Tuple[int, int, int, int]] = []

        for det in detections:
            conf = float(det[2])
            if conf < conf_thresh:
                continue

            xmin = int(det[3] * w)
            ymin = int(det[4] * h)
            xmax = int(det[5] * w)
            ymax = int(det[6] * h)

            # clamp
            xmin = max(0, xmin)
            ymin = max(0, ymin)
            xmax = min(w - 1, xmax)
            ymax = min(h - 1, ymax)

            # Skip extremely small faces
            if (xmax - xmin) * (ymax - ymin) < 0.02 * w * h:
                continue

            boxes.append((xmin, ymin, xmax, ymax))

        return boxes

    def _detect_face(self, frame_bgr: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
        """
        Backwards-compatible helper: returns the largest face or None.
        """
        boxes = self._detect_faces(frame_bgr)
        if not boxes:
            return None
        return max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))

    def _preprocess_for_head_pose(self, face_bgr: np.ndarray) -> np.ndarray:
        img = cv2.resize(face_bgr, (self.hp_w, self.hp_h))
        img = img.transpose(2, 0, 1)
        img = img[np.newaxis, :, :, :].astype(np.float32)
        return img

    def _estimate_head_pose(self, face_bgr: np.ndarray) -> Tuple[float, float, float]:
        """
        Returns yaw, pitch, roll in degrees using head-pose-estimation-adas-0001.
        """
        input_tensor = self._preprocess_for_head_pose(face_bgr)
        outputs = self.hp_compiled([input_tensor])

        yaw = None
        pitch = None
        roll = None

        for out in self.hp_compiled.outputs:
            name = out.get_any_name()
            val = float(outputs[out].flatten()[0])
            if "angle_y" in name:
                yaw = val
            elif "angle_p" in name:
                pitch = val
            elif "angle_r" in name:
                roll = val

        # Fallback: if names not matched, just take first 3 outputs
        if yaw is None or pitch is None or roll is None:
            vals = [float(outputs[o].flatten()[0]) for o in self.hp_compiled.outputs]
            yaw, pitch, roll = vals[:3]

        return yaw, pitch, roll

    # ---------- Public API ----------

    def calibrate(self, frames: List[np.ndarray]):
        """
        Use multiple frames to compute baseline head pose + face position.
        """
        yaw_list = []
        pitch_list = []
        roll_list = []
        centers_x = []
        centers_y = []
        widths = []
        heights = []

        for frame in frames:
            box = self._detect_face(frame)
            if box is None:
                continue
            x1, y1, x2, y2 = box
            face = frame[y1:y2, x1:x2]
            if face.size == 0:
                continue

            yaw, pitch, roll = self._estimate_head_pose(face)
            yaw_list.append(yaw)
            pitch_list.append(pitch)
            roll_list.append(roll)

            cx = (x1 + x2) / 2.0
            cy = (y1 + y2) / 2.0
            w = x2 - x1
            h = y2 - y1

            centers_x.append(cx)
            centers_y.append(cy)
            widths.append(w)
            heights.append(h)

        if len(yaw_list) < self.min_calibration_frames:
            return (
                False,
                "Face not detected consistently during calibration. "
                "Please sit properly and look at the screen.",
            )

        self.state.baseline_yaw = float(np.mean(yaw_list))
        self.state.baseline_pitch = float(np.mean(pitch_list))
        self.state.baseline_roll = float(np.mean(roll_list))

        self.state.baseline_cx = float(np.mean(centers_x))
        self.state.baseline_cy = float(np.mean(centers_y))
        self.state.baseline_w = float(np.mean(widths))
        self.state.baseline_h = float(np.mean(heights))

        self.state.warning_count = 0
        self.state.terminated = False
        self.state.last_face_time = time.time()
        self.state.deviation_start_time = None
        self.state.last_warning_time = 0.0

        return True, "Calibration successful"

    def check_frame(self, frame: np.ndarray):
        """
        Check a single frame:
        - Returns (status, details)
        - status: NORMAL / WARNING / TERMINATE / NO_FACE / ERROR
        """
        now = time.time()
        if self.state.terminated:
            return "TERMINATE", {"message": "Exam already terminated."}

        if self.state.baseline_yaw is None:
            return "ERROR", {"message": "Not calibrated yet"}

        # --- multi-face detection ---
        boxes = self._detect_faces(frame)
        if not boxes:
            if now - self.state.last_face_time > self.no_face_timeout:
                status, details = self._issue_warning(
                    "No face detected for too long"
                )
                details.update({"faces_detected": 0})
                return status, details
            else:
                return "NO_FACE", {
                    "message": "Face temporarily not detected",
                    "faces_detected": 0,
                }

        self.state.last_face_time = now

        faces_detected = len(boxes)
        # choose main (largest) face for pose
        box = max(boxes, key=lambda b: (b[2] - b[0]) * (b[3] - b[1]))
        x1, y1, x2, y2 = box
        face = frame[y1:y2, x1:x2]
        if face.size == 0:
            return "NO_FACE", {
                "message": "Face region invalid",
                "faces_detected": faces_detected,
            }

        # If more than one face, immediate warning via same pipeline
        if faces_detected > 1:
            status, details = self._issue_warning(
                "Multiple faces detected in frame"
            )
            yaw, pitch, roll = self._estimate_head_pose(face)
            dyaw = abs(yaw - self.state.baseline_yaw)
            dpitch = abs(pitch - self.state.baseline_pitch)
            droll = abs(roll - self.state.baseline_roll)
            details.update(
                {
                    "yaw": yaw,
                    "pitch": pitch,
                    "roll": roll,
                    "dyaw": dyaw,
                    "dpitch": dpitch,
                    "droll": droll,
                    "box": box,
                    "faces_detected": faces_detected,
                }
            )
            return status, details

        # --- normal single-face path ---
        yaw, pitch, roll = self._estimate_head_pose(face)

        dyaw = abs(yaw - self.state.baseline_yaw)
        dpitch = abs(pitch - self.state.baseline_pitch)
        droll = abs(roll - self.state.baseline_roll)

        # optional: movement check (body shift)
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        dx_center = abs(cx - (self.state.baseline_cx or cx))
        max_center_shift = 0.5 * (self.state.baseline_w or (x2 - x1))

        # Decide if current frame is deviated or normal
        deviated = False
        hard_deviation = False

        # yaw
        if dyaw > self.soft_yaw_threshold_deg:
            deviated = True
            if dyaw > self.hard_yaw_threshold_deg:
                hard_deviation = True

        # pitch
        if dpitch > self.soft_pitch_threshold_deg:
            deviated = True
            if dpitch > self.hard_pitch_threshold_deg:
                hard_deviation = True

        # roll
        if droll > self.soft_roll_threshold_deg:
            deviated = True
            if droll > self.hard_roll_threshold_deg:
                hard_deviation = True

        # big body shift
        if dx_center > max_center_shift:
            deviated = True
            hard_deviation = True

        # --- Handle deviation with time + cooldown (fatigue friendly) ---
        if deviated:
            # If a warning was given recently, don't spam
            if now - self.state.last_warning_time < self.warning_cooldown:
                return "NORMAL", {
                    "message": "Minor movement detected (cooldown active).",
                    "yaw": yaw,
                    "pitch": pitch,
                    "roll": roll,
                    "dyaw": dyaw,
                    "dpitch": dpitch,
                    "droll": droll,
                    "box": box,
                    "faces_detected": faces_detected,
                }

            # First frame where deviation is seen
            if self.state.deviation_start_time is None:
                self.state.deviation_start_time = now
                return "NORMAL", {
                    "message": "Movement detected, monitoring...",
                    "yaw": yaw,
                    "pitch": pitch,
                    "roll": roll,
                    "dyaw": dyaw,
                    "dpitch": dpitch,
                    "droll": droll,
                    "box": box,
                    "faces_detected": faces_detected,
                }

            # How long has deviation been continuous?
            duration = now - self.state.deviation_start_time
            required = (
                self.hard_deviation_min_duration
                if hard_deviation
                else self.soft_deviation_min_duration
            )

            if duration >= required:
                # Reset timer and actually issue warning
                self.state.deviation_start_time = None
                status, details = self._issue_warning(
                    f"Head deviation maintained for {duration:.1f}s"
                )
                self.state.last_warning_time = now
                details.update(
                    {
                        "yaw": yaw,
                        "pitch": pitch,
                        "roll": roll,
                        "dyaw": dyaw,
                        "dpitch": dpitch,
                        "droll": droll,
                        "box": box,
                        "faces_detected": faces_detected,
                    }
                )
                return status, details

            # still within time window, treat as normal for now
            return "NORMAL", {
                "message": f"Movement detected ({duration:.1f}s)...",
                "yaw": yaw,
                "pitch": pitch,
                "roll": roll,
                "dyaw": dyaw,
                "dpitch": dpitch,
                "droll": droll,
                "box": box,
                "faces_detected": faces_detected,
            }

        # --- NO deviation: reset deviation timer & adapt baseline slowly ---
        self.state.deviation_start_time = None

        # slow baseline adaptation to allow natural posture shifts
        alpha = 0.02  # small step; tune (0.01–0.05)
        self.state.baseline_yaw = (
            (1 - alpha) * self.state.baseline_yaw + alpha * yaw
        )
        self.state.baseline_pitch = (
            (1 - alpha) * self.state.baseline_pitch + alpha * pitch
        )
        self.state.baseline_roll = (
            (1 - alpha) * self.state.baseline_roll + alpha * roll
        )

        return "NORMAL", {
            "message": "OK",
            "yaw": yaw,
            "pitch": pitch,
            "roll": roll,
            "dyaw": dyaw,
            "dpitch": dpitch,
            "droll": droll,
            "box": box,
            "faces_detected": faces_detected,
        }

    def _issue_warning(self, reason: str):
        self.state.warning_count += 1
        if self.state.warning_count >= self.state.max_warnings:
            self.state.terminated = True
            return "TERMINATE", {
                "message": f"Exam terminated. Reason: {reason}. "
                           f"Max warnings reached.",
            }
        else:
            return "WARNING", {
                "message": f"Warning {self.state.warning_count}/"
                           f"{self.state.max_warnings}: {reason}",
            }
