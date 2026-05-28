"""Gesture recognition and debounce utilities for the HRI prototype.

Model bundle:
    Download the official MediaPipe Gesture Recognizer task bundle into the
    project root before running:

    wget -O gesture_recognizer.task \
      https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import mediapipe as mp
import numpy as np
from mediapipe.tasks import python
from mediapipe.tasks.python import vision


GESTURE_TO_COMMAND = {
    "Open_Palm": "STEP_X_NEG",
    "Closed_Fist": "HOME",
    "Pointing_Up": "STEP_X_POS",
    "Thumb_Up": "STEP_Z_POS",
    "Thumb_Down": "STEP_Z_NEG",
    "Victory": "TOGGLE_MODE",
}


@dataclass(frozen=True)
class RawGesture:
    """Top gesture reported by MediaPipe for a single frame."""

    label: Optional[str]
    confidence: float


@dataclass(frozen=True)
class DebounceResult:
    """Debounced gesture state after processing one frame."""

    active_command: Optional[str]
    emitted_command: Optional[str]
    stable_label: Optional[str]
    candidate_label: Optional[str]
    candidate_count: int


class GestureRecognizer:
    """Thin wrapper around the MediaPipe Tasks GestureRecognizer."""

    def __init__(self, model_path: str | Path = "gesture_recognizer.task") -> None:
        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"MediaPipe gesture model not found: {model_path}\n"
                "Download it with:\n"
                "wget -O gesture_recognizer.task "
                "https://storage.googleapis.com/mediapipe-models/"
                "gesture_recognizer/gesture_recognizer/float16/1/"
                "gesture_recognizer.task"
            )

        base_options = python.BaseOptions(model_asset_path=str(model_path))
        options = vision.GestureRecognizerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_hands=1,
        )
        self._recognizer = vision.GestureRecognizer.create_from_options(options)
        self._last_timestamp_ms = -1

    def recognize(self, rgb_frame: np.ndarray, timestamp_ms: int) -> RawGesture:
        """Return the highest-confidence canned gesture for an RGB frame."""
        if timestamp_ms <= self._last_timestamp_ms:
            timestamp_ms = self._last_timestamp_ms + 1
        self._last_timestamp_ms = timestamp_ms

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=np.ascontiguousarray(rgb_frame),
        )
        result = self._recognizer.recognize_for_video(mp_image, timestamp_ms)

        if not result.gestures or not result.gestures[0]:
            return RawGesture(label=None, confidence=0.0)

        top_gesture = result.gestures[0][0]
        label = top_gesture.category_name
        confidence = float(top_gesture.score)

        return RawGesture(label=label, confidence=confidence)

    def close(self) -> None:
        self._recognizer.close()


class GestureDebouncer:
    """Consecutive-frame debounce for raw gesture labels."""

    def __init__(self, min_confidence: float = 0.6, required_frames: int = 5) -> None:
        self.min_confidence = min_confidence
        self.required_frames = required_frames
        self._candidate_label: Optional[str] = None
        self._candidate_count = 0
        self._stable_label: Optional[str] = None
        self._active_command: Optional[str] = None

    def update(self, label: Optional[str], confidence: float) -> DebounceResult:
        """Update debounce state and emit only when a new command becomes stable."""
        if (
            label is None
            or label not in GESTURE_TO_COMMAND
            or confidence < self.min_confidence
        ):
            self.reset()
            return DebounceResult(
                active_command=None,
                emitted_command=None,
                stable_label=None,
                candidate_label=None,
                candidate_count=0,
            )

        if label == self._candidate_label:
            self._candidate_count += 1
        else:
            self._candidate_label = label
            self._candidate_count = 1

        emitted_command: Optional[str] = None
        if self._candidate_count >= self.required_frames:
            command = GESTURE_TO_COMMAND[label]
            if label != self._stable_label:
                emitted_command = command
            self._stable_label = label
            self._active_command = command

        return DebounceResult(
            active_command=self._active_command,
            emitted_command=emitted_command,
            stable_label=self._stable_label,
            candidate_label=self._candidate_label,
            candidate_count=self._candidate_count,
        )

    def reset(self) -> None:
        self._candidate_label = None
        self._candidate_count = 0
        self._stable_label = None
        self._active_command = None


class ModeController:
    """Tracks the active command plane and routes debounced commands."""

    MODE_XZ = "Mode 1: X-Z Plane"
    MODE_Y_YAW = "Mode 2: Y-Yaw Plane"

    def __init__(self, cooldown_frames: int = 45) -> None:
        self.cooldown_frames = cooldown_frames
        self._cooldown_remaining = 0
        self._mode_index = 0

    @property
    def current_mode(self) -> str:
        return (self.MODE_XZ, self.MODE_Y_YAW)[self._mode_index]

    @property
    def cooldown_remaining(self) -> int:
        return self._cooldown_remaining

    def update(self, emitted_command: Optional[str]) -> None:
        """Toggle mode from one-shot commands, then count down cooldown."""
        if self._cooldown_remaining > 0:
            self._cooldown_remaining -= 1
            return

        if emitted_command == "TOGGLE_MODE":
            self._mode_index = 1 - self._mode_index
            self._cooldown_remaining = self.cooldown_frames

    def route(self, active_command: Optional[str]) -> Optional[str]:
        """Map the current gesture command into the active control plane."""
        if active_command in {None, "STOP", "HOME"}:
            return active_command
        if active_command == "TOGGLE_MODE":
            return None
        if self.current_mode == self.MODE_XZ:
            return active_command

        mode_2_mapping = {
            "STEP_X_POS": "STEP_YAW_POS",
            "STEP_X_NEG": "STEP_YAW_NEG",
            "STEP_Z_POS": "STEP_Y_POS",
            "STEP_Z_NEG": "STEP_Y_NEG",
        }
        return mode_2_mapping.get(active_command)
