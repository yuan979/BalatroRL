import logging
import time
import gymnasium as gym
from gymnasium import spaces

from balatro_ipc import BalatroIPC
from balatro_actions import ACTION_MAPPING, NUM_ACTIONS, get_action_mask
from balatro_features import build_observation_space, extract_features
from balatro_reward import calculate_reward

logger = logging.getLogger("BalatroEnv")
logging.basicConfig(level=logging.DEBUG)

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
        self.steps_without_progress = 0
        self.idle_threshold = 20        # 连续多少步无进展开始惩罚
        self.idle_penalty_per_step = 0.05  # 每步额外惩罚（超出阈值后）
        self.consecutive_invalid = 0
        self.max_consecutive_invalid = 30  # 连续无效动作超过此值直接截断

    def _get_obs(self):
        mask = get_action_mask(self.current_raw_state, self.selected_hand_indices)
        obs = extract_features(self.current_raw_state, self.selected_hand_indices, mask)
        return obs, mask

    def _invalid_action_response(self):
        obs, mask = self._get_obs()
        return obs, -0.1, False, False, {"raw_state": self.current_raw_state, "action_mask": mask}

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.selected_hand_indices.clear()
        
        self.current_step = 0
        self.steps_without_progress = 0
        self.consecutive_invalid = 0
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
                    
        obs, mask = self._get_obs()
        return obs, {"raw_state": self.current_raw_state, "action_mask": mask}

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
                    # Bug 4 fix: 6th card toggle counts as invalid like all other invalid actions
                    self.consecutive_invalid += 1
                    penalty = min(0.5 + self.consecutive_invalid * 0.05, 3.0)
                    obs, mask = self._get_obs()
                    truncated = self.consecutive_invalid >= self.max_consecutive_invalid
                    if truncated:
                        logger.warning(f"Episode truncated: {self.consecutive_invalid} consecutive invalid actions.")
                    return obs, -penalty, False, truncated, {"raw_state": self.current_raw_state, "action_mask": mask}

            # Bug 3 fix: valid toggle resets the invalid counter
            self.consecutive_invalid = 0
            obs, mask = self._get_obs()
            return obs, 0.0, False, False, {"raw_state": self.current_raw_state, "action_mask": mask}

        # Python 层 action mask 强制拦截：不合法动作直接拒，不发给 Lua
        current_mask = get_action_mask(self.current_raw_state, self.selected_hand_indices)
        if not current_mask[action]:
            self.consecutive_invalid += 1
            penalty = min(0.5 + self.consecutive_invalid * 0.05, 3.0)
            logger.debug(f"[Mask Blocked] ({self.consecutive_invalid}x) action={action_name}, penalty={penalty:.2f}")
            obs = extract_features(self.current_raw_state, self.selected_hand_indices, current_mask)
            truncated = self.consecutive_invalid >= self.max_consecutive_invalid
            if truncated:
                logger.warning(f"Episode truncated: {self.consecutive_invalid} consecutive invalid actions.")
            return obs, -penalty, False, truncated, {
                "raw_state": self.current_raw_state,
                "action_mask": current_mask,
            }

        lua_cmd = action_name
        if action_name in ["PLAY", "DISCARD"] or action_name.startswith("USE_CONSUMABLE"):
            if len(self.selected_hand_indices) > 0:
                sorted_idx = sorted(list(self.selected_hand_indices))
                idx_str = " ".join(map(str, sorted_idx))
                lua_cmd = f"{action_name} {idx_str}"
            self.selected_hand_indices.clear()

        old_raw_state = self.current_raw_state
        self.current_raw_state = self.ipc.send_action_and_get_state(lua_cmd)

        new_mask = get_action_mask(self.current_raw_state, self.selected_hand_indices)
        obs = extract_features(self.current_raw_state, self.selected_hand_indices, new_mask)
        is_lua_invalid = self.current_raw_state.get("last_action_invalid", False)

        if is_lua_invalid:
            self.consecutive_invalid += 1
            penalty = min(0.5 + self.consecutive_invalid * 0.05, 3.0)  # 递增，上限3.0
            reward = -penalty
            logger.debug(f"[Penalty] Lua rejected ({self.consecutive_invalid}x): {lua_cmd}, penalty={penalty:.2f}")
        else:
            self.consecutive_invalid = 0
            reward = calculate_reward(old_raw_state, self.current_raw_state)

        # 无进展惩罚：检测关键状态是否发生变化
        def _progress_key(s):
            stats = s.get("stats", {})
            if isinstance(stats, list): stats = {}
            return (
                s.get("current_screen"),
                stats.get("current_chips"),
                stats.get("money"),
                stats.get("ante"),
                len(s.get("jokers", [])),
            )

        if _progress_key(old_raw_state) == _progress_key(self.current_raw_state):
            self.steps_without_progress += 1
        else:
            self.steps_without_progress = 0

        if self.steps_without_progress > self.idle_threshold:
            idle_penalty = self.idle_penalty_per_step * (self.steps_without_progress - self.idle_threshold)
            reward -= idle_penalty
            logger.debug(f"[Idle Penalty] {self.steps_without_progress} steps stalled, penalty={idle_penalty:.3f}")
            
        truncated = False
        if self.current_step >= self.max_steps:
            truncated = True
            logger.info(f"Episode truncated: max_steps={self.max_steps} reached.")
        elif self.consecutive_invalid >= self.max_consecutive_invalid:
            truncated = True
            logger.warning(f"Episode truncated: {self.consecutive_invalid} consecutive invalid actions.")

        terminated = self.current_raw_state.get("current_screen") == "GAME_OVER"
        
        info = {
            "raw_state": self.current_raw_state,
            "action_mask": new_mask
        }

        return obs, reward, terminated, truncated, info

    def render(self): pass
    
    def close(self): 
        self.ipc.disconnect()