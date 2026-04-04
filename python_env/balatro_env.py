import logging
import gymnasium as gym
from gymnasium import spaces

from balatro_ipc import BalatroIPC
from balatro_actions import ACTION_MAPPING, NUM_ACTIONS, get_action_mask

logger = logging.getLogger("BalatroEnv")

class BalatroEnv(gym.Env):
    def __init__(self):
        super().__init__()
        
        self.ipc = BalatroIPC()
        self.action_space = spaces.Discrete(NUM_ACTIONS) 
        self.observation_space = spaces.Dict({}) 
        
        self.selected_hand_indices = set()
        self.current_raw_state = {}
        
        logger.debug("BalatroEnv initialized with TCP Socket IPC.")

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.selected_hand_indices.clear()
        
        # 连接到游戏并通过发送一个心跳或空指令来获取初始状态
        # 假设 GET_STATE 是我们在 Lua 端处理的心跳指令（不做任何物理操作，只返回状态）
        self.current_raw_state = self.ipc.send_action_and_get_state("GET_STATE")
        
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

        # 处理客户端缓存操作
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

        # 发送指令并立刻获取返回的最新状态 (毫秒级响应)
        self.current_raw_state = self.ipc.send_action_and_get_state(lua_cmd)

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
    
    def close(self): 
        self.ipc.disconnect()
        logger.info("Environment closed.")