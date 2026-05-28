"""OpenCV webcam loop for CPU-only gesture perception."""

from __future__ import annotations

import argparse
import time

import cv2

from gesture import GestureDebouncer, GestureRecognizer, ModeController
from logger import RuntimeCsvLogger


WINDOW_NAME = "HRI Gesture Perception"


def draw_overlay(
    frame,
    raw_label: str | None,
    confidence: float,
    active_command: str | None,
    routed_command: str | None,
    current_mode: str,
    candidate_count: int,
    fps: float,
) -> None:
    """Draw compact perception state on the frame in-place."""
    raw_text = raw_label if raw_label is not None else "None"
    command_text = active_command if active_command is not None else "None"
    routed_text = routed_command if routed_command is not None else "None"

    lines = [
        f"Raw gesture: {raw_text}",
        f"Confidence: {confidence:.2f}",
        f"Stable frames: {candidate_count}",
        f"Command: {command_text}",
        f"Routed: {routed_text}",
        f"FPS: {fps:.1f}",
    ]

    x, y = 16, 28
    line_height = 28
    for i, line in enumerate(lines):
        pos = (x, y + i * line_height)
        cv2.putText(
            frame,
            line,
            pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            line,
            pos,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    mode_pos = (16, frame.shape[0] - 22)
    cv2.putText(
        frame,
        current_mode,
        mode_pos,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (0, 0, 0),
        4,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        current_mode,
        mode_pos,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.8,
        (255, 0, 255),
        2,
        cv2.LINE_AA,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gesture-based HRI perception loop")
    parser.add_argument(
        "--model",
        default="gesture_recognizer.task",
        help="Path to MediaPipe gesture_recognizer.task model bundle",
    )
    parser.add_argument("--camera", type=int, default=0, help="OpenCV camera index")
    parser.add_argument("--width", type=int, default=640, help="Capture width")
    parser.add_argument("--height", type=int, default=480, help="Capture height")
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=0.6,
        help="Minimum raw gesture confidence before debouncing",
    )
    parser.add_argument(
        "--stable-frames",
        type=int,
        default=5,
        help="Consecutive frames required before a command becomes active",
    )
    parser.add_argument(
        "--arm",
        action="store_true",
        help="Open the non-blocking Pygame 2D arm twin beside the camera view",
    )
    parser.add_argument(
        "--bullet",
        action="store_true",
        help="Open the non-blocking PyBullet 3D arm twin beside the camera view",
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="Record frame-level evaluation metrics to data/raw_logs/",
    )
    parser.add_argument(
        "--log-dir",
        default="data/raw_logs",
        help="Directory for CSV logs when --log is enabled",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.arm and args.bullet:
        raise ValueError("Use either --arm for the 2D twin or --bullet for the 3D twin")

    recognizer = GestureRecognizer(args.model)
    debouncer = GestureDebouncer(
        min_confidence=args.min_confidence,
        required_frames=args.stable_frames,
    )
    mode_controller = ModeController(cooldown_frames=45)
    arm = None
    if args.arm:
        from arm_2d import Arm2D

        arm = Arm2D()
    bullet = None
    bullet_p = None
    if args.bullet:
        import pybullet as bullet_p

        from arm_pybullet import PyBulletArm

        bullet = PyBulletArm()
    csv_logger = RuntimeCsvLogger(args.log_dir) if args.log else None

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    if not cap.isOpened():
        recognizer.close()
        if arm is not None:
            arm.close()
        if bullet is not None:
            bullet.close()
        if csv_logger is not None:
            csv_logger.close()
        raise RuntimeError(f"Could not open camera index {args.camera}")

    fps = 0.0
    previous_time = time.perf_counter()
    last_printed_routed_command: str | None = None

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("Camera frame read failed; exiting.")
                break
            frame_captured_time = time.perf_counter()

            # Mirror the image so on-screen left/right match the user's motion.
            frame = cv2.flip(frame, 1)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            timestamp_ms = int(time.perf_counter() * 1000)
            raw = recognizer.recognize(rgb_frame, timestamp_ms)
            debounced = debouncer.update(raw.label, raw.confidence)
            mode_controller.update(debounced.emitted_command)
            routed_command = mode_controller.route(debounced.active_command)
            pybullet_handoff_time = time.perf_counter()
            processing_latency_ms = (pybullet_handoff_time - frame_captured_time) * 1000.0

            now = time.perf_counter()
            instant_fps = 1.0 / max(now - previous_time, 1e-6)
            fps = instant_fps if fps == 0.0 else (0.9 * fps + 0.1 * instant_fps)
            previous_time = now

            draw_overlay(
                frame=frame,
                raw_label=raw.label,
                confidence=raw.confidence,
                active_command=debounced.active_command,
                routed_command=routed_command,
                current_mode=mode_controller.current_mode,
                candidate_count=debounced.candidate_count,
                fps=fps,
            )

            if debounced.emitted_command is not None:
                print(f"Command emitted: {debounced.emitted_command}")
            if routed_command != last_printed_routed_command:
                print(f"Command routed: {routed_command or 'None'}")
                last_printed_routed_command = routed_command
            if debounced.emitted_command == "TOGGLE_MODE":
                print(f"Active mode: {mode_controller.current_mode}")

            if arm is not None:
                arm.update(routed_command)
                arm.draw()
                if not arm.running:
                    break
            if bullet is not None and bullet_p is not None:
                bullet.update(routed_command)
                bullet_p.stepSimulation(physicsClientId=bullet.client_id)

            if csv_logger is not None:
                csv_logger.log_frame(
                    fps=fps,
                    processing_latency_ms=processing_latency_ms,
                    raw_gesture=raw.label,
                    raw_confidence=raw.confidence,
                    debounced_command=debounced.active_command,
                    emitted_command=debounced.emitted_command,
                    routed_command=routed_command,
                    current_mode=mode_controller.current_mode,
                )

            cv2.imshow(WINDOW_NAME, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        cap.release()
        recognizer.close()
        if arm is not None:
            arm.close()
        if bullet is not None:
            bullet.close()
        if csv_logger is not None:
            csv_logger.close()
            print(f"CSV log saved to: {csv_logger.path}")
            if csv_logger.dropped_rows:
                print(f"CSV logger dropped {csv_logger.dropped_rows} rows.")
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
