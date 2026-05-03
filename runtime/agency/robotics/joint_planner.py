"""
joint_planner.py — Pass 22
JointPlanner: linear + cubic spline trajectory planning for humanoid joints.
execute_trajectory sends waypoints to SimulationBridge.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# ── numpy detection ────────────────────────────────────────────────────────────

_NUMPY_AVAILABLE = False
try:
    import numpy as _np
    _NUMPY_AVAILABLE = True
except ImportError:
    pass

# ── Standard humanoid joint names ─────────────────────────────────────────────

HUMANOID_JOINTS: List[str] = [
    "head_pan",
    "head_tilt",
    "left_shoulder_pitch",
    "left_shoulder_roll",
    "left_elbow",
    "right_shoulder_pitch",
    "right_shoulder_roll",
    "right_elbow",
    "left_hip_pitch",
    "left_hip_roll",
    "left_knee",
    "right_hip_pitch",
    "right_hip_roll",
    "right_knee",
    "left_ankle",
    "right_ankle",
]

# ── dataclasses ────────────────────────────────────────────────────────────────

@dataclass
class JointTrajectory:
    joints: List[str]
    waypoints: List[Dict[str, float]]   # each dict: joint_name → angle_radians
    duration_s: float
    steps: int = field(init=False)

    def __post_init__(self):
        self.steps = len(self.waypoints)


# ── Interpolation helpers ──────────────────────────────────────────────────────

def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation."""
    return a + (b - a) * t


def _cubic_ease(t: float) -> float:
    """Smooth-step cubic easing: 3t²-2t³"""
    return t * t * (3.0 - 2.0 * t)


def _interpolate_joint_positions(
    start: Dict[str, float],
    goal: Dict[str, float],
    steps: int,
    use_spline: bool = False,
) -> List[Dict[str, float]]:
    """
    Generate `steps` waypoints interpolating from start to goal.
    Uses cubic easing with numpy if available, else linear.
    """
    waypoints: List[Dict[str, float]] = []
    joints = list(start.keys() | goal.keys())

    for i in range(steps):
        t_raw = i / max(steps - 1, 1)
        t = _cubic_ease(t_raw) if use_spline else t_raw
        wp: Dict[str, float] = {}
        for j in joints:
            a = start.get(j, 0.0)
            b = goal.get(j, 0.0)
            wp[j] = _lerp(a, b, t)
        waypoints.append(wp)
    return waypoints


def _numpy_spline_interpolate(
    start: Dict[str, float],
    goal: Dict[str, float],
    steps: int,
) -> List[Dict[str, float]]:
    """
    Numpy-based interpolation using smooth-step.
    Produces identical results to cubic_ease but vectorised.
    """
    joints = sorted(set(list(start.keys()) + list(goal.keys())))
    t_raw = _np.linspace(0.0, 1.0, steps)
    t = t_raw * t_raw * (3.0 - 2.0 * t_raw)  # smooth-step

    start_arr = _np.array([start.get(j, 0.0) for j in joints])
    goal_arr  = _np.array([goal.get(j, 0.0)  for j in joints])

    # shape: (steps, n_joints)
    all_positions = start_arr[None, :] + (goal_arr - start_arr)[None, :] * t[:, None]

    waypoints: List[Dict[str, float]] = []
    for row in all_positions:
        waypoints.append({j: float(v) for j, v in zip(joints, row)})
    return waypoints


# ── Public class ───────────────────────────────────────────────────────────────

class JointPlanner:
    """
    Plans joint trajectories for humanoid robots.

    Usage
    -----
    planner = JointPlanner()
    traj = planner.plan_trajectory(start_pos, goal_pos, steps=50)
    planner.execute_trajectory(traj, sim_bridge)
    """

    def __init__(self, joints: Optional[List[str]] = None):
        self.joints = joints or HUMANOID_JOINTS[:]
        logger.info(
            "JointPlanner initialised with %d joints (numpy=%s)",
            len(self.joints), _NUMPY_AVAILABLE
        )

    def plan_trajectory(
        self,
        start: Dict[str, float],
        goal: Dict[str, float],
        steps: int = 50,
        duration_s: float = 2.0,
    ) -> JointTrajectory:
        """
        Plan a smooth trajectory from start to goal.

        Parameters
        ----------
        start : dict of joint_name → angle (radians). Missing joints default to 0.
        goal  : dict of joint_name → angle (radians). Missing joints default to 0.
        steps : number of waypoints (min 2).
        duration_s : total motion time in seconds.

        Returns
        -------
        JointTrajectory with `steps` waypoints.
        """
        steps = max(2, steps)

        # Fill missing joints with 0
        full_start = {j: start.get(j, 0.0) for j in self.joints}
        full_goal  = {j: goal.get(j, 0.0)  for j in self.joints}

        if _NUMPY_AVAILABLE:
            waypoints = _numpy_spline_interpolate(full_start, full_goal, steps)
        else:
            waypoints = _interpolate_joint_positions(
                full_start, full_goal, steps, use_spline=True
            )

        return JointTrajectory(
            joints=list(self.joints),
            waypoints=waypoints,
            duration_s=duration_s,
        )

    def execute_trajectory(
        self,
        traj: JointTrajectory,
        sim_bridge,
        blocking: bool = True,
    ) -> None:
        """
        Send each waypoint to sim_bridge with correct timing.

        Parameters
        ----------
        traj       : JointTrajectory to execute.
        sim_bridge : Object with method send_joint_command(dict).
        blocking   : If True, sleep between waypoints to match duration_s.
        """
        if not traj.waypoints:
            logger.warning("Empty trajectory — nothing to execute")
            return

        dt = traj.duration_s / max(len(traj.waypoints) - 1, 1)
        logger.info(
            "Executing trajectory: %d waypoints, %.2fs total, dt=%.4fs",
            len(traj.waypoints), traj.duration_s, dt
        )

        for i, waypoint in enumerate(traj.waypoints):
            try:
                sim_bridge.send_joint_command(waypoint)
            except Exception as exc:
                logger.error("sim_bridge error at waypoint %d: %s", i, exc)
                break
            if blocking and i < len(traj.waypoints) - 1:
                time.sleep(dt)

        logger.info("Trajectory execution complete")

    def zero_pose(self) -> Dict[str, float]:
        """Return a dict with all joints at 0 radians."""
        return {j: 0.0 for j in self.joints}

    def stand_pose(self) -> Dict[str, float]:
        """
        Approximate humanoid standing pose (radians).
        All joints at 0 except slight knee bend.
        """
        pose = self.zero_pose()
        pose["left_knee"]  = 0.05
        pose["right_knee"] = 0.05
        return pose
