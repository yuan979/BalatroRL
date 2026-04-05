import logging
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
        
        # 动作空间：81 维离散动作
        self.action_space = spaces.Discrete(NUM_ACTIONS) 
        
        # 状态空间：调用特征模块构建的复杂 Dict 空间
        self.observation_space = build_observation_space()
        
        self.selected_hand_indices = set()
        self.current_raw_state = {}
        
        logger.debug("BalatroEnv initialized with TCP Socket IPC and Semantic Features.")

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.selected_hand_indices.clear()
        
        # 获取初始裸状态
        self.current_raw_state = self.ipc.send_action_and_get_state("GET_STATE")
        
        # 将裸状态转化为神经网络所需的张量字典
        obs = extract_features(self.current_raw_state)
        
        info = {
            "raw_state": self.current_raw_state,
            "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices)
        }
        return obs, info

    def step(self, action):
        action_name = ACTION_MAPPING.get(action, None)
        if action_name is None:
            raise ValueError(f"Invalid action index: {action}")

        # 处理客户端内部缓存动作 (选择手牌)
        if action_name.startswith("TOGGLE_CARD_"):
            idx = int(action_name.split("_")[-1])
            if idx in self.selected_hand_indices:
                self.selected_hand_indices.remove(idx)
            else:
                self.selected_hand_indices.add(idx)
            
            # 不发送网络请求，直接基于当前缓存重新生成 obs
            obs = extract_features(self.current_raw_state)
            info = {
                "raw_state": self.current_raw_state,
                "action_mask": get_action_mask(self.current_raw_state, self.selected_hand_indices),
                "internal_selection": list(self.selected_hand_indices)
            }
            return obs, 0.0, False, False, info

        # 组合真实物理指令
        lua_cmd = action_name
        if action_name in ["PLAY", "DISCARD"] or action_name.startswith("USE_CONSUMABLE"):
            if len(self.selected_hand_indices) > 0:
                sorted_idx = sorted(list(self.selected_hand_indices))
                idx_str = " ".join(map(str, sorted_idx))
                lua_cmd = f"{action_name} {idx_str}"
            self.selected_hand_indices.clear()

        # 缓存旧状态用于计算奖励
        old_raw_state = self.current_raw_state

        # 发送物理指令并获取新一帧状态
        self.current_raw_state = self.ipc.send_action_and_get_state(lua_cmd)

        # 提取张量特征
        obs = extract_features(self.current_raw_state)
        
        # 计算奖励与终止状态
        reward = calculate_reward(old_raw_state, self.current_raw_state)
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