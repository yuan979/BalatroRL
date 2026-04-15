import logging
import time
import gymnasium as gym
from gymnasium import spaces

from balatro_ipc import BalatroIPC
from balatro_actions import ACTION_MAPPING, NUM_ACTIONS, get_action_mask
from balatro_features import build_observation_space, extract_features
from balatro_reward import calculate_reward

logger = logging.getLogger("BalatroEnv")
# logging.basicConfig(level=logging.DEBUG)

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
        self.idle_threshold = 20        # 杩炵画澶氬皯姝ユ棤杩涘睍寮€濮嬫儵锟?
        self.idle_penalty_per_step = 0.05  # 姣忔棰濆鎯╃綒锛堣秴鍑洪槇鍊煎悗锟?
        self.consecutive_invalid = 0
        self.max_consecutive_invalid = 30  # 杩炵画鏃犳晥鍔ㄤ綔瓒呰繃姝ゅ€肩洿鎺ユ埅锟?
        self._play_discard_cooldown = 0    # Lua鎷掔粷PLAY/DISCARD鍚庣煭鏆傚睆钄斤紝闃叉鍦ㄩ潪SELECTING_HAND鐘舵€佸弽澶嶅彂锟?
        self._blind_action_cooldown = 0    # 鐩叉敞瀹忓姩浣滃喎鍗达紝闄嶄綆SELECT/SKIP椋庢毚

    def _build_action_mask(self):
        mask = get_action_mask(self.current_raw_state, self.selected_hand_indices)
        if self._play_discard_cooldown > 0:
            mask[0] = False  # PLAY
            mask[1] = False  # DISCARD
        # Do NOT blanket-mask 66-71 during blind cooldown: in BLIND_SELECT the only
        # legal actions are 66-71, so zeroing them makes every step mask-blocked and
        # nothing is ever sent to Lua (only GET_STATE from reset remains visible).
        return mask

    def _get_obs(self):
        mask = self._build_action_mask()
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
        self._play_discard_cooldown = 0
        self._blind_action_cooldown = 0
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
        current_screen = self.current_raw_state.get("current_screen")

        if self._play_discard_cooldown > 0:
            self._play_discard_cooldown -= 1
        if self._blind_action_cooldown > 0:
            self._blind_action_cooldown -= 1

        # In BLIND_SELECT, force action into legal blind macro set as early as possible
        # so we do not get trapped in local-only toggle returns.
        if current_screen == "BLIND_SELECT" and not (
            action_name.startswith("SELECT_BLIND") or action_name.startswith("SKIP_BLIND")
        ):
            current_mask = self._build_action_mask()
            preferred = [66, 69, 67, 70, 68, 71]
            chosen = None
            for idx in preferred:
                if current_mask[idx]:
                    chosen = idx
                    break
            if chosen is not None:
                old_action_name = action_name
                action = chosen
                action_name = ACTION_MAPPING[chosen]

        # Toggle cards should only be local in IN_GAME.
        if action_name.startswith("TOGGLE_CARD_") and current_screen == "IN_GAME":
            prev_steps_wo_progress = self.steps_without_progress
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
            current_mask = self._build_action_mask()
            selected_count = len(self.selected_hand_indices)
            auto_commit_action = None
            if selected_count >= 2:
                if current_mask[1]:
                    auto_commit_action = 1  # DISCARD
                elif current_mask[0]:
                    auto_commit_action = 0  # PLAY

            if auto_commit_action is not None:
                old_action_name = action_name
                action = auto_commit_action
                action_name = ACTION_MAPPING[action]
            else:
                # Local-only toggles do not advance game state; count them as stalled steps.
                self.steps_without_progress += 1
                reward = 0.0
                if self.steps_without_progress > self.idle_threshold:
                    idle_penalty = self.idle_penalty_per_step * (self.steps_without_progress - self.idle_threshold)
                    reward -= idle_penalty
                obs, mask = self._get_obs()
                return obs, reward, False, False, {"raw_state": self.current_raw_state, "action_mask": mask}

        # Python 锟?action mask 寮哄埗鎷︽埅锛氫笉鍚堟硶鍔ㄤ綔鐩存帴鎷掞紝涓嶅彂锟?Lua
        current_mask = self._build_action_mask()
        if not current_mask[action]:
            is_blind_macro = action_name.startswith("SELECT_BLIND") or action_name.startswith("SKIP_BLIND")
            if is_blind_macro:
                # Blind macro blocked by dynamic mask/cooldown should not count as invalid streak.
                self.consecutive_invalid = 0
                penalty = 0.02
            else:
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

        # Convert Python action name (CMD_TYPE_N) to Lua command format (CMD_TYPE N [targets])
        _SLOT_CMDS = {
            "BUY_CARD_": "BUY_CARD", "BUY_VOUCHER_": "BUY_VOUCHER",
            "BUY_BOOSTER_": "BUY_BOOSTER", "USE_CONSUMABLE_": "USE_CONSUMABLE",
            "SELL_JOKER_": "SELL_JOKER", "SELL_CONSUMABLE_": "SELL_CONSUMABLE",
            "SELECT_PACK_CARD_": "SELECT_PACK_CARD",
        }
        lua_cmd = action_name
        for prefix, lua_base in _SLOT_CMDS.items():
            if action_name.startswith(prefix):
                slot = action_name[len(prefix):]
                if lua_base == "USE_CONSUMABLE" and self.selected_hand_indices:
                    targets = " ".join(map(str, sorted(self.selected_hand_indices)))
                    lua_cmd = f"{lua_base} {slot} {targets}"
                    self.selected_hand_indices.clear()
                else:
                    lua_cmd = f"{lua_base} {slot}"
                break
        else:
            if action_name in ["PLAY", "DISCARD"]:
                if self.selected_hand_indices:
                    idx_str = " ".join(map(str, sorted(self.selected_hand_indices)))
                    lua_cmd = f"{action_name} {idx_str}"
                self.selected_hand_indices.clear()

        old_raw_state = self.current_raw_state
        self.current_raw_state = self.ipc.send_action_and_get_state(lua_cmd)

        new_mask = get_action_mask(self.current_raw_state, self.selected_hand_indices)
        obs = extract_features(self.current_raw_state, self.selected_hand_indices, new_mask)
        is_lua_invalid = self.current_raw_state.get("last_action_invalid", False)
        is_lua_throttled = self.current_raw_state.get("last_action_throttled", False)

        if is_lua_throttled:
            # Lua瀹忛槻鎶栦涪寮冿細涓嶈鍏nvalid杩炲嚮锛岄伩鍏嶈鎴柇
            self.consecutive_invalid = 0
            reward = -0.02
            if lua_cmd.startswith(("SELECT_BLIND", "SKIP_BLIND")):
                self._blind_action_cooldown = max(self._blind_action_cooldown, 6)
        elif is_lua_invalid:
            is_blind_macro_cmd = lua_cmd.startswith(("SELECT_BLIND", "SKIP_BLIND"))
            if is_blind_macro_cmd:
                # Blind macro rejection is often transient (UI state/animation), avoid invalid streak explosion.
                self.consecutive_invalid = 0
                reward = -0.05
                self._blind_action_cooldown = max(self._blind_action_cooldown, 6)
                logger.debug(f"[Penalty] Lua rejected blind macro: {lua_cmd}")
            else:
                self.consecutive_invalid += 1
                penalty = min(0.5 + self.consecutive_invalid * 0.05, 3.0)  # 閫掑锛屼笂锟?.0
                reward = -penalty
                logger.debug(f"[Penalty] Lua rejected ({self.consecutive_invalid}x): {lua_cmd}, penalty={penalty:.2f}")
            if lua_cmd.startswith(("PLAY", "DISCARD")):
                self._play_discard_cooldown = 4  # 灞忚斀4姝ワ紝绛夊緟娓告垙鍥炲埌SELECTING_HAND
        else:
            self.consecutive_invalid = 0
            reward = calculate_reward(old_raw_state, self.current_raw_state)

        # 鏃犺繘灞曟儵缃氾細妫€娴嬪叧閿姸鎬佹槸鍚﹀彂鐢熷彉锟?
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

