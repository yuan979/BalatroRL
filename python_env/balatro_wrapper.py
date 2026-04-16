import datetime
import uuid
import json
import time
import numpy as np
import gymnasium as gym
from gymnasium import spaces
import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from balatro_env import BalatroEnv


class BalatroDreamerWrapper(gym.Wrapper):
    def __init__(self, env_id=0):
        env = BalatroEnv()
        super().__init__(env)
        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        self.id = f"{timestamp}-{uuid.uuid4().hex}"
        
        dim = env.observation_space.spaces["state"].shape[0]

        self.observation_space = spaces.Dict({
            'state': spaces.Box(low=-1.0, high=100.0, shape=(dim,), dtype=np.float32),
            'is_first': spaces.Box(low=0, high=1, shape=(), dtype=bool),
            'is_terminal': spaces.Box(low=0, high=1, shape=(), dtype=bool),
            # 'image': spaces.Box(low=0, high=255, shape=(64, 64, 3), dtype=np.uint8)
        })
        
        self._num_actions = env.action_space.n
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(self._num_actions,), dtype=np.float32
        )
        self.action_space.discrete = True
        
    def _format_obs(self, obs, is_first, is_terminal):
        return {
            "state": obs["state"],
            "is_first": np.array(is_first, dtype=bool),
            "is_terminal": np.array(is_terminal, dtype=bool),
            "image": np.zeros((64, 64, 3), dtype=np.uint8)
        }

    def reset(self, **kwargs):
        # New id every Gymnasium episode so dreamerv3-torch/tools.simulate keeps one
        # in-memory trajectory per key; a fixed id makes train_length/train_return sum
        # many episodes into one buffer (misleading metrics and bad sampling spans).
        timestamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        self.id = f"{timestamp}-{uuid.uuid4().hex}"
        # region agent log
        try:
            logp = Path(__file__).resolve().parent.parent / "debug-260fea.log"
            logp.parent.mkdir(parents=True, exist_ok=True)
            with open(logp, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "sessionId": "260fea",
                            "runId": "wrapper-reset",
                            "hypothesisId": "H7",
                            "location": "python_env/balatro_wrapper.py:reset",
                            "message": "wrapper reset new episode id",
                            "data": {"new_id": self.id},
                            "timestamp": int(time.time() * 1000),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        except Exception as e:
            sys.stderr.write(f"[BalatroRL] wrapper debug NDJSON failed: {e!r}\n")
        # endregion
        obs, info = self.env.reset(**kwargs)
        return self._format_obs(obs, is_first=True, is_terminal=False)
        
    def step(self, action):
        if isinstance(action, dict):
            action = action.get('action', action)
            
        if isinstance(action, np.ndarray):
            if action.size > 1:
                action_idx = int(np.argmax(action))
            else:
                action_idx = int(action.item())
        else:
            action_idx = int(action)
            
        obs, reward, terminated, truncated, info = self.env.step(action_idx)
        done = terminated or truncated

        safe_info = {}

        return self._format_obs(obs, is_first=False, is_terminal=terminated), float(reward), done, safe_info