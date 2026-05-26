# JARVIS Humanoid Robot Setup — Windows

Pass 19 integrates a humanoid robot brain with simulation, STT, YOLO vision,
and reinforcement learning.  All hardware dependencies are **optional** —
MOCK backends work out of the box for development and CI.

---

## Quick Start (zero dependencies)

```powershell
cd C:\Users\User\agency\runtime
agency robotics start --sim mock --stt mock
agency robotics exec "walk forward 2 meters"
agency robotics status
```

---

## Simulation Backends

### 1. PyBullet (EASIEST — recommended for Windows)

```powershell
pip install pybullet
agency robotics start --sim pybullet
```

PyBullet ships pre-built wheels for Windows x64.  No compiler needed.
Use the built-in `humanoid/humanoid.urdf` or supply your own URDF.

### 2. MuJoCo (licence-free since v2.1)

```powershell
pip install mujoco
agency robotics start --sim mujoco
```

MuJoCo uses MJCF XML models.  Pass `--urdf path/to/model.xml` to
`SimulationBridge.load_humanoid()` for custom robots.

### 3. Webots

Download the installer from https://cyberbotics.com and install.
Webots runs as a separate process; the controller connects via the
Webots Python API.  Set `sim_backend=WEBOTS` in `SimulationBridge`
and launch Webots with your world file.

### 4. MOCK (default — CI safe)

No physics.  Joint states stored in a dict, `step()` increments time.
Perfect for unit tests and dry-runs of NLP→motion pipelines.

---

## Speech-to-Text Backends

### 1. Whisper (offline, no API key)

```powershell
pip install openai-whisper
pip install sounddevice   # mic capture on Windows
```

Uses the `tiny` model by default (~75 MB).  Runs on CPU, ~1–3 s latency.

```python
from agency.robotics.stt import STTEngine, STTBackend
stt = STTEngine(backend=STTBackend.WHISPER, model_size="base")
```

### 2. Google Web Speech API

```powershell
pip install SpeechRecognition pyaudio
```

Requires internet access.  PyAudio on Windows may need:
```powershell
pip install pipwin && pipwin install pyaudio
```

### 3. MOCK (default)

Returns preset strings cyclically.  Useful for testing the
NLP → motion pipeline without a microphone.

---

## Vision (YOLO Object Detection)

```powershell
pip install ultralytics opencv-python
```

```python
from agency.robotics.vision_perception import RobotVision
vision = RobotVision(camera_id=0, model="yolov8n")
vision.start()
result = vision.detect()
for det in result.objects:
    print(det.label, det.confidence, det.estimated_distance_m)
vision.stop()
```

Fallback: if ultralytics is not installed, falls back to OpenCV DNN,
then to MockVision.

---

## Reinforcement Learning (PPO walking policy)

```powershell
pip install torch gymnasium
```

```powershell
agency robotics train --episodes 100 --sim mock --save walking_policy.pt
```

Or from Python:

```python
from agency.robotics.rl_trainer import RLTrainer
from agency.robotics.simulation import SimulationBridge, SimulationBackend

trainer = RLTrainer(sim=SimulationBridge(SimulationBackend.MOCK))
rewards = trainer.train_walking_policy(episodes=100)
print("Mean reward:", sum(rewards) / len(rewards))
```

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `agency robotics start [--sim X] [--stt Y] [--vision]` | Initialise brain |
| `agency robotics stop` | Shutdown signal |
| `agency robotics status [--sim X]` | Print joint states & mode |
| `agency robotics exec "COMMAND"` | Run a text motion command |
| `agency robotics listen [--stt Y] [--steps N]` | Voice control loop |
| `agency robotics train [--episodes N] [--save PATH]` | RL training |

---

## Supported Motion Commands (NLP)

| Phrase | Skill |
|--------|-------|
| `walk forward N meters` | `walk_forward` |
| `walk backward N meters` | `walk_backward` |
| `turn left / right [N degrees]` | `turn_left / turn_right` |
| `sit down` | `sit_down` |
| `stand up` | `stand_up` |
| `wave [right/left] hand` | `wave_hand` |
| `nod head [N times]` | `nod_head` |
| `reach forward [N meters]` | `reach_forward` |
| `pick up X / grab X` | `grasp_object` |
| `release / drop` | `release_object` |
| `stop / halt / freeze` | `stand_still` |

---

## Real Hardware Integration

To connect a **Unitree H1** or **Boston Dynamics Atlas**:

1. Replace `SimulationBridge` with a hardware-specific driver that
   implements the same `get_joint_states / set_joint_position / step`
   interface.
2. Load the robot's official URDF for collision-accurate simulation.
3. Use `STTBackend.WHISPER` with a USB microphone for on-robot inference.
4. Mount a USB webcam and set `use_vision=True` in `RobotBrain`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `ImportError: PyBullet` | `pip install pybullet` |
| `ImportError: whisper` | `pip install openai-whisper` |
| `ImportError: torch` | `pip install torch` |
| `No module named 'sounddevice'` | `pip install sounddevice` |
| PyAudio install fails on Windows | `pip install pipwin && pipwin install pyaudio` |
| Camera not found | Check `camera_id=0` matches your device index |
