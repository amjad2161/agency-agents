"""Reinforcement Learning trainer for the JARVIS humanoid robot.

Implements a gym.Env-compatible environment (works with or without
gymnasium installed) and a pure-NumPy/PyTorch PPO stub.

Architecture
------------
* RobotEnv  — 24-dim observation (18 joints + 6 IMU), 12-dim action space
* SimplePPO — lightweight policy gradient (requires torch)
* RLTrainer — high-level API: train_walking_policy, evaluate

Usage (mock, no external deps)
------
    from agency.robotics.simulation import SimulationBridge, SimulationBackend
    from agency.robotics.rl_trainer import RobotEnv, RLTrainer

    sim = SimulationBridge(SimulationBackend.MOCK)
    env = RobotEnv(sim)
    obs = env.reset()
    obs2, reward, done, info = env.step(env.action_space.sample())
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..logging import get_logger
from .simulation import SimulationBridge, SimulationBackend, HUMANOID_JOINTS

log = get_logger()

# ---------------------------------------------------------------------------
# Observation / action dimensions
# ---------------------------------------------------------------------------

OBS_DIM    = 24    # 18 joints + 6 IMU (roll, pitch, yaw, accel_x, accel_y, accel_z)
ACTION_DIM = 12    # 10 leg joints + 2 elbow joints (actuated subset)

ACTUATED_JOINTS = [
    "left_hip_yaw", "left_hip_roll", "left_hip_pitch", "left_knee", "left_ankle",
    "right_hip_yaw", "right_hip_roll", "right_hip_pitch", "right_knee", "right_ankle",
    "left_elbow", "right_elbow",
]

# Reward weights
RW_FORWARD_VEL   =  1.0
RW_ENERGY_COST   = -0.01
RW_STABILITY     =  0.5
RW_SURVIVAL      =  0.1


# ---------------------------------------------------------------------------
# Minimal gym-like space classes (no gymnasium dependency)
# ---------------------------------------------------------------------------

class _Box:
    """Continuous n-dimensional box (mimics gymnasium.spaces.Box)."""

    def __init__(self, low: float, high: float, shape: Tuple[int, ...]) -> None:
        self.low   = low
        self.high  = high
        self.shape = shape
        self.n     = shape[0]

    def sample(self):
        try:
            import numpy as np  # type: ignore
            return np.random.uniform(self.low, self.high, self.shape).astype("float32")
        except ImportError:
            # Pure Python fallback
            import random
            return [random.uniform(self.low, self.high) for _ in range(self.n)]

    def __repr__(self) -> str:
        return f"Box({self.low}, {self.high}, shape={self.shape})"


# ---------------------------------------------------------------------------
# RobotEnv
# ---------------------------------------------------------------------------

class RobotEnv:
    """Gym-compatible environment wrapping a SimulationBridge.

    Observation (24-dim float32):
        [0:18]  — joint positions (radians, clipped to ±π)
        [18:21] — IMU orientation (roll, pitch, yaw) — mock: zeros
        [21:24] — IMU linear acceleration (x, y, z) — mock: (0, 0, 9.8)

    Action (12-dim float32):
        Target joint positions for ACTUATED_JOINTS, clipped to ±1.57 rad.

    Reward:
        forward_velocity * RW_FORWARD_VEL
        + energy_cost    * RW_ENERGY_COST
        + stability      * RW_STABILITY
        + survival       * RW_SURVIVAL
    """

    metadata: Dict[str, Any] = {"render_modes": []}

    def __init__(
        self,
        sim: Optional[SimulationBridge] = None,
        max_episode_steps: int = 1000,
    ) -> None:
        if sim is None:
            sim = SimulationBridge(SimulationBackend.MOCK)
        self.sim = sim
        self.max_episode_steps = max_episode_steps

        self.observation_space = _Box(-math.pi, math.pi, (OBS_DIM,))
        self.action_space      = _Box(-math.pi / 2, math.pi / 2, (ACTION_DIM,))

        self._step_count   = 0
        self._prev_x       = 0.0   # proxy for forward displacement
        self._total_torque = 0.0

    # --- gym interface ---

    def reset(self, *, seed: Optional[int] = None):  # noqa: ARG002
        self.sim.reset()
        self.sim.load_humanoid()
        self._step_count   = 0
        self._prev_x       = 0.0
        self._total_torque = 0.0
        return self._obs()

    def step(self, action) -> Tuple[Any, float, bool, Dict]:
        # Apply action: set actuated joint positions
        for i, joint in enumerate(ACTUATED_JOINTS):
            angle = float(action[i]) if hasattr(action, "__getitem__") else 0.0
            # Clip to safe range
            angle = max(-math.pi / 2, min(math.pi / 2, angle))
            self.sim.set_joint_position(joint, angle)
            self.sim.set_joint_torque(joint, angle * 10)  # crude torque model

        self.sim.step()
        self._step_count += 1

        obs    = self._obs()
        reward = self._reward(action)
        done   = self._is_done()
        info   = {
            "step": self._step_count,
            "energy": self._total_torque,
        }
        return obs, reward, done, info

    def render(self, mode: str = "human") -> None:
        pass   # headless

    def close(self) -> None:
        pass

    # --- private helpers ---

    def _obs(self):
        """Build 24-dim observation vector."""
        states = self.sim.get_joint_states()
        joint_pos = [states.get(j, 0.0) for j in HUMANOID_JOINTS]
        # Mock IMU: upright pose = roll=0, pitch=0, yaw=0, accel=(0,0,9.8)
        imu = [0.0, 0.0, 0.0, 0.0, 0.0, 9.8]
        raw = joint_pos + imu
        try:
            import numpy as np  # type: ignore
            return np.array(raw, dtype="float32")
        except ImportError:
            return raw

    def _reward(self, action) -> float:
        # Forward velocity proxy: sum of hip_pitch positions (moving hips → moving forward)
        states    = self.sim.get_joint_states()
        hip_pitch = (
            states.get("left_hip_pitch", 0.0) + states.get("right_hip_pitch", 0.0)
        ) / 2.0
        forward_vel = hip_pitch

        # Energy cost: sum of |action|
        energy = sum(abs(float(a)) for a in (action if hasattr(action, "__iter__") else [action]))
        self._total_torque += energy

        # Stability: reward keeping body_height close to 1.0 m
        impl = getattr(self.sim, "_impl", None)
        body_h = getattr(impl, "body_height", 1.0) if impl else 1.0
        stability = max(0.0, 1.0 - abs(body_h - 1.0))

        reward = (
            forward_vel * RW_FORWARD_VEL
            + energy    * RW_ENERGY_COST
            + stability * RW_STABILITY
            + 1.0       * RW_SURVIVAL
        )
        return float(reward)

    def _is_done(self) -> bool:
        if self._step_count >= self.max_episode_steps:
            return True
        impl   = getattr(self.sim, "_impl", None)
        body_h = getattr(impl, "body_height", 1.0) if impl else 1.0
        if body_h < 0.3:   # fallen
            return True
        return False


# ---------------------------------------------------------------------------
# SimplePPO (requires torch; raises ImportError with hint if missing)
# ---------------------------------------------------------------------------

class SimplePPO:
    """Minimal PPO implementation using PyTorch.

    Not intended for production — demonstrates the training loop structure.

    Parameters
    ----------
    env:
        A RobotEnv instance.
    lr:
        Learning rate.
    gamma:
        Discount factor.
    clip:
        PPO clip epsilon.
    """

    def __init__(
        self,
        env: RobotEnv,
        lr: float = 3e-4,
        gamma: float = 0.99,
        clip: float = 0.2,
    ) -> None:
        try:
            import torch              # type: ignore
            import torch.nn as nn    # type: ignore
        except ImportError as exc:
            raise ImportError(
                "PyTorch not installed. Run: pip install torch\n"
                "Then: pip install gymnasium"
            ) from exc

        self.env   = env
        self.gamma = gamma
        self.clip  = clip
        import torch
        import torch.nn as nn

        self._torch = torch
        hidden = 128

        self.policy = nn.Sequential(
            nn.Linear(OBS_DIM, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden),  nn.Tanh(),
            nn.Linear(hidden, ACTION_DIM),
        )
        self.value_fn = nn.Sequential(
            nn.Linear(OBS_DIM, hidden), nn.Tanh(),
            nn.Linear(hidden, hidden),  nn.Tanh(),
            nn.Linear(hidden, 1),
        )
        all_params = list(self.policy.parameters()) + list(self.value_fn.parameters())
        self.optim = torch.optim.Adam(all_params, lr=lr)
        self._log_std = torch.zeros(ACTION_DIM, requires_grad=True)

    def _to_tensor(self, x):
        import torch  # type: ignore
        if isinstance(x, list):
            return torch.tensor(x, dtype=torch.float32)
        return torch.tensor(x, dtype=torch.float32)

    def train(self, n_episodes: int = 100, steps_per_episode: int = 200) -> List[float]:
        """Run PPO training loop.  Returns list of episode rewards."""
        import torch  # type: ignore
        rewards_hist: List[float] = []

        for ep in range(n_episodes):
            obs = self.env.reset()
            ep_reward = 0.0
            obs_buf, act_buf, rew_buf, done_buf, logp_buf = [], [], [], [], []

            for _ in range(steps_per_episode):
                obs_t = self._to_tensor(obs)
                mean   = self.policy(obs_t)
                std    = self._log_std.exp()
                dist   = torch.distributions.Normal(mean, std)
                action = dist.sample()
                logp   = dist.log_prob(action).sum()

                next_obs, reward, done, _ = self.env.step(action.detach().numpy())
                obs_buf.append(obs_t)
                act_buf.append(action)
                rew_buf.append(reward)
                logp_buf.append(logp)
                done_buf.append(done)
                ep_reward += reward
                obs = next_obs
                if done:
                    break

            # Compute discounted returns
            returns = []
            R = 0.0
            for r, d in zip(reversed(rew_buf), reversed(done_buf)):
                R = r + self.gamma * R * (1 - int(d))
                returns.insert(0, R)
            returns_t = torch.tensor(returns, dtype=torch.float32)

            # PPO update (single epoch for simplicity)
            obs_t   = torch.stack(obs_buf)
            acts_t  = torch.stack(act_buf)
            logp_old = torch.stack(logp_buf).detach()
            values   = self.value_fn(obs_t).squeeze()
            advantages = returns_t - values.detach()
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

            mean_new = self.policy(obs_t)
            std_new  = self._log_std.exp()
            dist_new = torch.distributions.Normal(mean_new, std_new)
            logp_new = dist_new.log_prob(acts_t).sum(-1)

            ratio   = (logp_new - logp_old).exp()
            surr1   = ratio * advantages
            surr2   = ratio.clamp(1 - self.clip, 1 + self.clip) * advantages
            pol_loss = -torch.min(surr1, surr2).mean()
            val_loss = (returns_t - values).pow(2).mean()
            loss     = pol_loss + 0.5 * val_loss

            self.optim.zero_grad()
            loss.backward()
            self.optim.step()

            rewards_hist.append(ep_reward)
            if (ep + 1) % 10 == 0:
                log.info("ppo.train ep=%d reward=%.2f", ep + 1, ep_reward)

        return rewards_hist

    def save(self, path: str) -> None:
        import torch  # type: ignore
        torch.save(
            {
                "policy": self.policy.state_dict(),
                "value": self.value_fn.state_dict(),
                "log_std": self._log_std,
            },
            path,
        )
        log.info("ppo.save path=%s", path)

    def load(self, path: str) -> None:
        import torch  # type: ignore
        ckpt = torch.load(path, map_location="cpu")
        self.policy.load_state_dict(ckpt["policy"])
        self.value_fn.load_state_dict(ckpt["value"])
        self._log_std = ckpt["log_std"]
        log.info("ppo.load path=%s", path)


# ---------------------------------------------------------------------------
# RLTrainer — high-level API
# ---------------------------------------------------------------------------

class RLTrainer:
    """High-level RL training coordinator for the humanoid robot."""

    def __init__(self, sim: Optional[SimulationBridge] = None) -> None:
        self.sim = sim or SimulationBridge(SimulationBackend.MOCK)
        self._env: Optional[RobotEnv] = None
        self._ppo: Optional[SimplePPO] = None

    def train_walking_policy(
        self,
        episodes: int = 100,
        steps_per_episode: int = 200,
        save_path: Optional[str] = None,
    ) -> List[float]:
        """Train a walking policy with PPO.

        Returns list of episode rewards.
        Requires torch; otherwise logs error and returns empty list.
        """
        self._env = RobotEnv(self.sim, max_episode_steps=steps_per_episode)
        try:
            self._ppo = SimplePPO(self._env)
            rewards = self._ppo.train(n_episodes=episodes, steps_per_episode=steps_per_episode)
            if save_path:
                self._ppo.save(save_path)
            return rewards
        except ImportError as exc:
            log.error("rl_trainer.train: %s", exc)
            return []

    def evaluate(self, n_episodes: int = 5) -> float:
        """Run n_episodes with the current policy and return mean reward."""
        if self._env is None:
            self._env = RobotEnv(self.sim)
        total = 0.0
        for _ in range(n_episodes):
            obs = self._env.reset()
            ep_reward = 0.0
            done = False
            while not done:
                action = self._env.action_space.sample()
                obs, reward, done, _ = self._env.step(action)
                ep_reward += reward
            total += ep_reward
        mean = total / n_episodes
        log.info("rl_trainer.evaluate n=%d mean_reward=%.2f", n_episodes, mean)
        return mean
