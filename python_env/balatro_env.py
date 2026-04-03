import os
import logging
import gymnasium as gym
from gymnasium import spaces

from balatro_ipc import read_json_safe, send_action
from balatro_actions import ACTION_MAPPING, NUM_ACTIONS, get_action_mask

logger = logging.getLogger("BalatroEnv")

class BalatroEnv(gym.Env):
    def __init__(self, game_dir=None):
        super().__init__()
        
        if game_dir is None:
            appdata = os.getenv('APPDATA')
            if not appdata:
                raise ValueError("未找到 APPDATA 环境变量，请手动指定 game_dir")
            self.game_dir = os.path.join(appdata, "Balatro")
        else:
            self.game_dir = game_dir
            
        self.obs_file = os.path.join(self.game_dir, "rl_observation.json")
        self.info_file = os.path.join(self.game_dir, "rl_run_info.json")
        self.action_file = os.path.join(self.game_dir, "rl_action.txt")
        
        self.action_space = spaces.Discrete(NUM_ACTIONS) 
        self.observation_space = spaces.Dict({}) 
        
        self.selected_hand_indices = set()
        self.current_raw_state = {}
        
        logger.debug("BalatroEnv initialized.")

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.selected_hand_indices.clear()
        
        if os.path.exists(self.obs_file):
            try: os.remove(self.obs_file)
            except PermissionError: pass
                
        self.current_raw_state = read_json_safe(self.obs_file)
        
        obs = {} 
        info = {
            "raw_state": self.current_raw_state,
            "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices)
        }
        return obs, info

    def step(self, action):
        action_name = ACTION_MAPPING.get(action, None)
        if action_name is None:
            raise ValueError(f"Invalid action index: {action}")

        # 处理客户端缓存操作 (选中手牌)
        if action_name.startswith("TOGGLE_CARD_"):
            idx = int(action_name.split("_")[-1])
            if idx in self.selected_hand_indices:
                self.selected_hand_indices.remove(idx)
            else:
                self.selected_hand_indices.add(idx)
            
            info = {
                "raw_state": self.current_raw_state,
                "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices),
                "internal_selection": list(self.selected_hand_indices)
            }
            return {}, 0.0, False, False, info

        # 组合物理指令
        lua_cmd = action_name
        if action_name in ["PLAY", "DISCARD"] or action_name.startswith("USE_CONSUMABLE"):
            if len(self.selected_hand_indices) > 0:
                sorted_idx = sorted(list(self.selected_hand_indices))
                idx_str = " ".join(map(str, sorted_idx))
                lua_cmd = f"{action_name} {idx_str}"
            self.selected_hand_indices.clear()

        # 真实的动作下发与观测刷新
        if os.path.exists(self.obs_file):
            try: os.remove(self.obs_file)
            except PermissionError: pass

        send_action(lua_cmd, self.action_file)
        self.current_raw_state = read_json_safe(self.obs_file)

        obs = {} 
        reward = 0.0
        terminated = self.current_raw_state.get("current_screen") == "GAME_OVER"
        truncated = False
        info = {
            "raw_state": self.current_raw_state,
            "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices)
        }

        return obs, reward, terminated, truncated, info

    def render(self): pass
    def close(self): pass