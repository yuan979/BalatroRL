import logging
import time
import gymnasium as gym
from gymnasium import spaces

from balatro_ipc import BalatroIPC
from balatro_actions import ACTION_MAPPING, NUM_ACTIONS, get_action_mask
from balatro_features import build_observation_space, extract_features
from balatro_reward import calculate_reward

logger = logging.getLogger("BalatroEnv")

class BalatroEnv(gym.Env):
    def __init__(self):
        super().__init__()
        self.ipc = BalatroIPC()
        self.action_space = spaces.Discrete(NUM_ACTIONS) 
        self.observation_space = build_observation_space()
        self.selected_hand_indices = set()
        self.current_raw_state = {}
        self.current_step = 0
        self.max_steps = 500

    def _invalid_action_response(self):
        obs = extract_features(self.current_raw_state)
        info = {
            "raw_state": self.current_raw_state,
            "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices)
        }
        return obs, -0.1, False, False, info

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.selected_hand_indices.clear()
        
        self.current_step = 0
        self.current_raw_state = self.ipc.send_action_and_get_state("GET_STATE")
        current_screen = self.current_raw_state.get("current_screen")
        
        if current_screen in ["MAIN_MENU", "GAME_OVER", None, ""]:
            logger.info("Starting new run")
            self.ipc.send_action_and_get_state("START_NEW_RUN")
            
            for _ in range(15):
                time.sleep(1.0)
                self.current_raw_state = self.ipc.send_action_and_get_state("GET_STATE")
                if self.current_raw_state.get("current_screen") in ["IN_GAME", "BLIND_SELECT", "SHOP"]:
                    break
                    
        obs = extract_features(self.current_raw_state)
        info = {
            "raw_state": self.current_raw_state,
            "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices)
        }
        return obs, info

    def step(self, action):
        self.current_step += 1
        action_name = ACTION_MAPPING.get(action, None)
        if action_name is None:
            raise ValueError(f"Invalid action index: {action}")

        if action_name.startswith("TOGGLE_CARD_"):
            idx = int(action_name.split("_")[-1])
            if idx in self.selected_hand_indices:
                self.selected_hand_indices.remove(idx)
            else:
                if len(self.selected_hand_indices) < 5:
                    self.selected_hand_indices.add(idx)
                else:
                    return self._invalid_action_response()
            
            obs = extract_features(self.current_raw_state)        
            info = {
                "raw_state": self.current_raw_state,
                "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices),
                "internal_selection": list(self.selected_hand_indices)
            }
            return obs, 0.0, False, False, info

        stats = self.current_raw_state.get("stats", {})
        
        if action_name == "PLAY":
            if stats.get("hands_left", 0) <= 0 or len(self.selected_hand_indices) == 0:
                return self._invalid_action_response()
        elif action_name == "DISCARD":
            if stats.get("discards_left", 0) <= 0 or len(self.selected_hand_indices) == 0:
                return self._invalid_action_response()

        lua_cmd = action_name
        if action_name in ["PLAY", "DISCARD"] or action_name.startswith("USE_CONSUMABLE"):
            if len(self.selected_hand_indices) > 0:
                sorted_idx = sorted(list(self.selected_hand_indices))
                idx_str = " ".join(map(str, sorted_idx))
                lua_cmd = f"{action_name} {idx_str}"
            self.selected_hand_indices.clear()

        old_raw_state = self.current_raw_state
        self.current_raw_state = self.ipc.send_action_and_get_state(lua_cmd)

        obs = extract_features(self.current_raw_state)
        is_lua_invalid = self.current_raw_state.get("last_action_invalid", False)

        if is_lua_invalid:
            reward = -0.5  
            logger.debug(f"[Penalty] Lua rejected action: {lua_cmd}")
        else:
            reward = calculate_reward(old_raw_state, self.current_raw_state)
            
        truncated = False
        if self.current_step >= self.max_steps:
            truncated = True
            logger.info(f"Episode forcibly truncated after {self.max_steps} steps to prevent locking.")

        terminated = self.current_raw_state.get("current_screen") == "GAME_OVER"
        truncated = False
        
        info = {
            "raw_state": self.current_raw_state,
            "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices)
        }

        return obs, reward, terminated, truncated, info

    def render(self): pass
    
    def close(self): 
        self.ipc.disconnect()