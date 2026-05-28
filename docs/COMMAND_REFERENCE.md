# Command Reference

This document describes the runtime controls, gesture mappings, routed commands,
CLI options, and terminal output used by the prototype.

## Runtime Windows

The main window is the OpenCV camera window named `HRI Gesture Perception`.
Depending on the selected runtime option, an additional simulator window may
open:

- `--arm`: opens the Pygame 2D arm twin.
- `--bullet`: opens the PyBullet 3D arm twin.

Only one simulator can be enabled at a time.

## Stopping the Program

With the OpenCV window focused, press either:

- `q`
- `Esc`

Closing the 2D arm window also stops the runtime loop when `--arm` is active.

## Camera Overlay

The OpenCV overlay displays:

| Overlay field | Meaning |
| --- | --- |
| `Raw gesture` | Current top MediaPipe gesture label before debounce filtering. |
| `Confidence` | MediaPipe confidence score for the raw gesture. |
| `Stable frames` | Number of consecutive frames for the current candidate gesture. |
| `Command` | Active debounced command. |
| `Routed` | Command after mode-based routing. |
| `FPS` | Smoothed runtime loop frame rate. |
| Mode label | Current control mode, displayed at the bottom of the frame. |

## Gesture Mapping

The recognizer uses MediaPipe's built-in gesture labels. The project maps a
small subset of those labels into symbolic commands.

| MediaPipe gesture | Debounced command | Description |
| --- | --- | --- |
| `Open_Palm` | `STEP_X_NEG` | Negative X command before mode routing. |
| `Closed_Fist` | `HOME` | Reset the simulated robot to its home pose. |
| `Pointing_Up` | `STEP_X_POS` | Positive X command before mode routing. |
| `Thumb_Up` | `STEP_Z_POS` | Positive Z command before mode routing. |
| `Thumb_Down` | `STEP_Z_NEG` | Negative Z command before mode routing. |
| `Victory` | `TOGGLE_MODE` | Toggle between command modes. |

Unmapped gestures are ignored by the debouncer. When no mapped gesture is
active, the routed command is `None` and the simulator holds the current pose.

## Debounce Behavior

Raw gesture output is not sent directly to the robot. A gesture becomes active
only when:

- its confidence is at least `--min-confidence`, which defaults to `0.6`
- the same label appears for `--stable-frames` consecutive frames, which defaults
  to `5`

The active command remains available while the gesture is held. The emitted
command is a one-shot event that appears only when a new stable gesture first
becomes active.

This distinction matters for commands such as `TOGGLE_MODE`: the mode should
change once per stable `Victory` gesture, not once per frame.

## Control Modes

The mode controller exposes two modes:

| Mode | Purpose |
| --- | --- |
| `Mode 1: X-Z Plane` | Direct X and Z movement. |
| `Mode 2: Y-Yaw Plane` | Reuses the same gestures for Y movement and wrist yaw. |

`Victory` emits `TOGGLE_MODE`. A cooldown prevents rapid repeated toggles while
the gesture is held.

## Routed Commands

Commands are routed differently depending on the active mode.

| Debounced command | Mode 1 routed command | Mode 2 routed command |
| --- | --- | --- |
| `HOME` | `HOME` | `HOME` |
| `STEP_X_POS` | `STEP_X_POS` | `STEP_YAW_POS` |
| `STEP_X_NEG` | `STEP_X_NEG` | `STEP_YAW_NEG` |
| `STEP_Z_POS` | `STEP_Z_POS` | `STEP_Y_POS` |
| `STEP_Z_NEG` | `STEP_Z_NEG` | `STEP_Y_NEG` |
| `TOGGLE_MODE` | `None` | `None` |
| No active command | `None` | `None` |

`TOGGLE_MODE` is consumed by the mode controller and is not routed to the robot
as a movement command.

## Simulator Behavior

### 2D Arm

The 2D arm is a fast validation tool. It renders a simple 3-degree-of-freedom
planar arm in an X/Z side view. It is useful for confirming that gestures,
debounce state, and command updates are working before running the heavier 3D
simulation.

### 3D PyBullet Arm

The 3D arm uses the Franka Panda model included with `pybullet_data`. Cartesian
movement commands adjust a bounded end-effector target and PyBullet inverse
kinematics converts the target into joint commands.

The PyBullet arm also contains an internal Cartesian/joint control toggle for
direct use of `arm_pybullet.py`, but the main runtime loop normally controls
plane selection through `ModeController` in `gesture.py`.

## CLI Options

| Option | Default | Meaning |
| --- | --- | --- |
| `--model` | `gesture_recognizer.task` | Path to the MediaPipe gesture model bundle. |
| `--camera` | `0` | OpenCV camera index. |
| `--width` | `640` | Requested capture width. |
| `--height` | `480` | Requested capture height. |
| `--min-confidence` | `0.6` | Minimum raw gesture confidence before debounce acceptance. |
| `--stable-frames` | `5` | Consecutive frames required before a command becomes active. |
| `--arm` | disabled | Open the 2D Pygame arm twin. |
| `--bullet` | disabled | Open the 3D PyBullet arm twin. |
| `--log` | disabled | Write frame-level CSV logs. |
| `--log-dir` | `data/raw_logs` | Directory for CSV logs when `--log` is enabled. |

## Terminal Output

The terminal prints state changes and shutdown information:

```text
Command emitted: STEP_X_POS
Command routed: STEP_X_POS
Active mode: Mode 2: Y-Yaw Plane
CSV log saved to: data/raw_logs/run_20260525_185110.csv
```

`Command emitted` appears when a new debounced command becomes stable.
`Command routed` appears only when the routed command changes.

## CSV Log Fields

When `--log` is enabled, each processed frame can produce one CSV row with:

| Field | Meaning |
| --- | --- |
| `timestamp_utc` | UTC timestamp for the row. |
| `fps` | Smoothed loop FPS. |
| `processing_latency_ms` | Time from frame capture to command handoff. |
| `raw_gesture` | Current raw MediaPipe gesture label. |
| `raw_confidence` | Confidence score for the raw gesture. |
| `debounced_command` | Active command after debounce filtering. |
| `emitted_command` | One-shot command emitted on a new stable gesture. |
| `routed_command` | Command after mode routing. |
| `current_mode` | Active control mode. |
