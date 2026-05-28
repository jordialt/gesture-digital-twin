# Gesture-Based HRI Prototype

This project is a lightweight human-robot interaction prototype for a TFG. It
uses a webcam, MediaPipe gesture recognition, debounce logic, and mode-based
command routing to drive either a 2D Pygame validation arm or a 3D PyBullet
digital twin.

The implementation is intentionally small and CPU-oriented. It is designed to
run on constrained hardware with a consumer RGB webcam while still collecting
frame-level data for evaluation.

## What the System Does

The runtime loop performs these steps:

1. Capture a webcam frame with OpenCV.
2. Mirror the frame so the display matches the user's movement.
3. Run MediaPipe gesture recognition.
4. Debounce raw gesture labels into stable symbolic commands.
5. Route commands through the active control mode.
6. Update the optional 2D or 3D digital twin.
7. Draw live diagnostics and optionally write CSV evaluation logs.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `main.py` | Main OpenCV runtime loop, CLI options, overlays, simulation integration, and logging calls. |
| `gesture.py` | MediaPipe recognizer wrapper, gesture-to-command mapping, debounce logic, and control-mode routing. |
| `arm_2d.py` | Pygame 2D planar arm used for fast command validation. |
| `arm_pybullet.py` | PyBullet 3D digital twin based on the bundled Franka Panda model. |
| `logger.py` | Non-blocking CSV logger for frame-level runtime metrics. |
| `scripts/analyze_evaluation_logs.py` | Analysis script that converts runtime CSV logs into LaTeX tables. |
| `gesture_recognizer.task` | MediaPipe gesture recognizer model bundle used by the runtime. |
| `data/raw_logs/` | Default location for physical evaluation CSV logs. |
| `results/evaluation_tables.tex` | Generated LaTeX tables for the Results chapter. |
| `docs/COMMAND_REFERENCE.md` | Gesture mappings, runtime controls, CLI options, and terminal output reference. |
| `.gitignore` | Keeps local environments, caches, report drafts, and non-repository files out of Git. |

## Requirements

The project uses Python and these runtime libraries:

- `opencv-python`
- `mediapipe`
- `numpy`
- `pygame`
- `pybullet`
- `pandas` for evaluation analysis

The MediaPipe model bundle must be present as `gesture_recognizer.task` in the
project root. This repository currently includes that file.

If the model file is missing, download the official MediaPipe gesture recognizer
bundle:

```bash
wget -O gesture_recognizer.task \
  https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task
```

## Setup

Create and activate a virtual environment:

```bash
uv venv
source .venv/bin/activate
```

Install the dependencies:

```bash
uv pip install opencv-python mediapipe numpy pygame pybullet pandas
```

If you do not use `uv`, the same packages can be installed with `pip` inside a
normal Python virtual environment.

## Running the Prototype

Run only the camera and gesture-perception loop:

```bash
python main.py
```

Run with the 2D validation arm:

```bash
python main.py --arm
```

Run with the 3D PyBullet digital twin:

```bash
python main.py --bullet
```

Record a physical evaluation run:

```bash
python main.py --bullet --log
```

CSV logs are written to `data/raw_logs/` by default with filenames such as:

```text
run_20260525_185110.csv
```

Press `q` or `Esc` in the OpenCV window to stop the runtime loop.

## Common Runtime Options

```bash
python main.py --camera 1
python main.py --width 1280 --height 720
python main.py --min-confidence 0.7
python main.py --stable-frames 8
python main.py --log-dir data/raw_logs/session_01
```

Use either `--arm` or `--bullet`, not both at the same time.

## Gesture and Command Summary

| Gesture | Base command | Effect |
| --- | --- | --- |
| `Open_Palm` | `STEP_X_NEG` | Move negative X in mode 1, yaw negative in mode 2. |
| `Closed_Fist` | `HOME` | Return the robot to its home pose. |
| `Pointing_Up` | `STEP_X_POS` | Move along X in mode 1, yaw positive in mode 2. |
| `Thumb_Up` | `STEP_Z_POS` | Move up in mode 1, move positive Y in mode 2. |
| `Thumb_Down` | `STEP_Z_NEG` | Move down in mode 1, move negative Y in mode 2. |
| `Victory` | `TOGGLE_MODE` | Toggle between the two control modes. |

The full command behavior is documented in
`docs/COMMAND_REFERENCE.md`.

The robot holds its current pose when no mapped gesture is active, so there is
no dedicated stop gesture in the default mapping.

## Evaluation Analysis

Generate LaTeX tables from all CSV logs in `data/raw_logs/`:

```bash
uv run --with pandas python scripts/analyze_evaluation_logs.py data/raw_logs
```

Write the tables directly to the Results file:

```bash
uv run --with pandas python scripts/analyze_evaluation_logs.py \
  data/raw_logs \
  --output results/evaluation_tables.tex
```

The script reports:

- number of runs and frames per evaluation case
- average, minimum, and maximum FPS
- average, minimum, and maximum processing latency
- recognized command counts grouped by evaluation case and control mode

By default, command counts use `emitted_command`, which counts each stable
gesture recognition once. Use `--command-column routed_command` when the goal is
to count commands after mode routing.

The generated LaTeX uses `booktabs`, so the thesis document should include:

```latex
\usepackage{booktabs}
```

## Troubleshooting

If the camera does not open, try a different index:

```bash
python main.py --camera 1
```

If gesture recognition is unstable, improve lighting, keep one hand visible,
raise `--stable-frames`, or raise `--min-confidence`.

If PyBullet opens but runs slowly, lower the camera resolution:

```bash
python main.py --bullet --width 640 --height 480
```

If imports fail, confirm that the virtual environment is active and that the
required packages were installed into that environment.

## Documentation Map

- Use `README.md` for setup and day-to-day operation.
- Use `docs/COMMAND_REFERENCE.md` when checking gestures, modes, CLI flags, or
  terminal messages.
