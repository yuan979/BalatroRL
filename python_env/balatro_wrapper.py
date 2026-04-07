import numpy as np
import gymnasium as gym
from gymnasium import spaces
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from balatro_env import BalatroEnv

class BalatroDreamerWrapper(gym.Wrapper):
    def __init__(self, env_id=0):
        env = BalatroEnv()
        super().__init__(env)
        self.id = env_id
        
        orig = env.observation_space.spaces
        dim = (
            orig["global_scalars"].shape[0] +
            np.prod(orig["hand_cards"].shape) +
            np.prod(orig["jokers"].shape)
        )
        
        self.observation_space = spaces.Dict({
            'state': spaces.Box(low=-10.0, high=100.0, shape=(dim,), dtype=np.float32),
            'is_first': spaces.Box(low=0, high=1, shape=(), dtype=bool),
            'is_terminal': spaces.Box(low=0, high=1, shape=(), dtype=bool),
            'image': spaces.Box(low=0, high=255, shape=(64, 64, 3), dtype=np.uint8)
        })
        
        self._num_actions = env.action_space.n
        self.action_space = spaces.Box(
            low=0.0, high=1.0, shape=(self._num_actions,), dtype=np.float32
        )
        self.action_space.discrete = True
        
    def _flatten(self, obs, is_first, is_terminal):
        flat_vec = np.concatenate([
            obs["global_scalars"],
            obs["hand_cards"].flatten(),
            obs["jokers"].flatten()
        ]).astype(np.float32)
        return {
            "state": flat_vec,
            "is_first": np.array(is_first, dtype=bool),
            "is_terminal": np.array(is_terminal, dtype=bool),
            "image": np.zeros((64, 64, 3), dtype=np.uint8)
        }

    def reset(self, **kwargs):
        obs, info = self.env.reset(**kwargs)
        return self._flatten(obs, is_first=True, is_terminal=False)
        
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
        return self._flatten(obs, is_first=False, is_terminal=done), float(reward), done, info