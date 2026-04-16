import logging
import time
import json
import gymnasium as gym
from gymnasium import spaces
from pathlib import Path

from balatro_ipc import BalatroIPC
from balatro_actions import ACTION_MAPPING, NUM_ACTIONS, get_action_mask
from balatro_features import build_observation_space, extract_features
from balatro_reward import calculate_reward

logger = logging.getLogger("BalatroEnv")
# logging.basicConfig(level=logging.DEBUG)

# region agent log
_DEBUG_LOG_PATH = Path(__file__).resolve().parent.parent / "debug-260fea.log"
_DEBUG_SESSION_ID = "260fea"


def _env_dbglog(hypothesis_id: str, location: str, message: str, data: dict) -> None:
    try:
        _DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sessionId": _DEBUG_SESSION_ID,
            "runId": "episode-trace",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        if not getattr(_env_dbglog, "_warned", False):
            _env_dbglog._warned = True
            try:
                import sys

                sys.stderr.write(
                    f"[BalatroRL] debug NDJSON write failed: {e!r} path={_DEBUG_LOG_PATH}\n"
                )
            except Exception:
                pass


# endregion

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
        # IN_GAME local-only toggle streak (separate from _progress_key idle)
        self._toggle_only_streak = 0
        self.toggle_only_idle_threshold = 12
        self.toggle_idle_extra_per_step = 0.08
        self.max_toggle_only_streak = 120
        self.consecutive_invalid = 0
        self.max_consecutive_invalid = 30  # 杩炵画鏃犳晥鍔ㄤ綔瓒呰繃姝ゅ€肩洿鎺ユ埅锟?
        self._play_discard_cooldown = 0    # Lua鎷掔粷PLAY/DISCARD鍚庣煭鏆傚睆钄斤紝闃叉鍦ㄩ潪SELECTING_HAND鐘舵€佸弽澶嶅彂锟?
        self._blind_action_cooldown = 0    # 鐩叉敞瀹忓姩浣滃喎鍗达紝闄嶄綆SELECT/SKIP椋庢毚
        self._episode_return = 0.0
        self._episode_steps = 0

    def _accumulate_episode_return(self, reward: float) -> None:
        self._episode_return += float(reward)

    def _hard_horizon(self) -> tuple[bool, bool]:
        """Episode ends: GAME_OVER, max env steps, or consecutive invalid cap."""
        terminated = self.current_raw_state.get("current_screen") == "GAME_OVER"
        truncated = (
            self.current_step >= self.max_steps
            or self.consecutive_invalid >= self.max_consecutive_invalid
            or self._toggle_only_streak >= self.max_toggle_only_streak
        )
        return truncated, terminated

    def _dbg_episode_end(
        self,
        *,
        hypothesis_id: str,
        location: str,
        step_reward: float,
        truncated: bool,
        terminated: bool,
        lua_cmd: str | None,
        is_lua_invalid: bool | None,
        is_lua_throttled: bool | None,
        extra: dict | None = None,
    ) -> None:
        if not (truncated or terminated):
            return
        if terminated:
            reason = "game_over"
        elif self.current_step >= self.max_steps:
            reason = "max_steps"
        elif self._toggle_only_streak >= self.max_toggle_only_streak:
            reason = "toggle_only_streak"
        else:
            reason = "consecutive_invalid"
        data = {
            "reason": reason,
            "terminated": bool(terminated),
            "truncated": bool(truncated),
            "current_step": int(self.current_step),
            "episode_steps": int(self._episode_steps),
            "episode_return": float(self._episode_return),
            "step_reward": float(step_reward),
            "consecutive_invalid": int(self.consecutive_invalid),
            "steps_without_progress": int(self.steps_without_progress),
            "screen": self.current_raw_state.get("current_screen"),
            "last_lua_cmd": lua_cmd,
            "last_action_invalid": None if is_lua_invalid is None else bool(is_lua_invalid),
            "last_action_throttled": None if is_lua_throttled is None else bool(is_lua_throttled),
        }
        if extra:
            data.update(extra)
        _env_dbglog(hypothesis_id, location, "episode end", data)

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
        self._toggle_only_streak = 0
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
        # region agent log
        _env_dbglog(
            "H1",
            "python_env/balatro_env.py:reset",
            "env reset",
            {
                "screen": self.current_raw_state.get("current_screen"),
                "episode_return": float(self._episode_return),
                "episode_steps": int(self._episode_steps),
            },
        )
        # endregion
        self._episode_return = 0.0
        self._episode_steps = 0
        return obs, {"raw_state": self.current_raw_state, "action_mask": mask}

    def step(self, action):

        self.current_step += 1
        self._episode_steps += 1
        action_name = ACTION_MAPPING.get(action, None)
        if action_name is None:
            raise ValueError(f"Invalid action index: {action}")
        current_screen = self.current_raw_state.get("current_screen")

        if not (
            action_name.startswith("TOGGLE_CARD_") and current_screen == "IN_GAME"
        ):
            self._toggle_only_streak = 0

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
                    self._toggle_only_streak = 0
                    self.consecutive_invalid += 1
                    penalty = min(0.5 + self.consecutive_invalid * 0.05, 3.0)
                    obs, mask = self._get_obs()
                    truncated, terminated = self._hard_horizon()
                    if truncated and self.current_step >= self.max_steps:
                        logger.info(f"Episode truncated: max_steps={self.max_steps} reached.")
                    elif truncated:
                        logger.warning(f"Episode truncated: {self.consecutive_invalid} consecutive invalid actions.")
                    reward = -penalty
                    # region agent log
                    self._accumulate_episode_return(reward)
                    self._dbg_episode_end(
                        hypothesis_id="H3",
                        location="python_env/balatro_env.py:toggle_sixth_card",
                        step_reward=reward,
                        truncated=truncated,
                        terminated=False,
                        lua_cmd=None,
                        is_lua_invalid=None,
                        is_lua_throttled=None,
                        extra={"path": "toggle_sixth_card", "action_name": action_name},
                    )
                    # endregion
                    return obs, reward, terminated, truncated, {"raw_state": self.current_raw_state, "action_mask": mask}

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
                self._toggle_only_streak = 0
                old_action_name = action_name
                action = auto_commit_action
                action_name = ACTION_MAPPING[action]
            else:
                # Local-only toggles do not advance game state; count them as stalled steps.
                self._toggle_only_streak += 1
                self.steps_without_progress += 1
                reward = 0.0
                if self.steps_without_progress > self.idle_threshold:
                    idle_penalty = self.idle_penalty_per_step * (self.steps_without_progress - self.idle_threshold)
                    reward -= idle_penalty
                if self._toggle_only_streak > self.toggle_only_idle_threshold:
                    reward -= self.toggle_idle_extra_per_step * (
                        self._toggle_only_streak - self.toggle_only_idle_threshold
                    )
                obs, mask = self._get_obs()
                truncated, terminated = self._hard_horizon()
                if truncated and self.current_step >= self.max_steps:
                    logger.info(f"Episode truncated: max_steps={self.max_steps} reached.")
                elif truncated and self._toggle_only_streak >= self.max_toggle_only_streak:
                    logger.warning(
                        "Episode truncated: toggle_only_streak=%s (max=%s)",
                        self._toggle_only_streak,
                        self.max_toggle_only_streak,
                    )
                elif truncated:
                    logger.warning(f"Episode truncated: {self.consecutive_invalid} consecutive invalid actions.")
                # region agent log
                self._accumulate_episode_return(float(reward))
                self._dbg_episode_end(
                    hypothesis_id="H5",
                    location="python_env/balatro_env.py:toggle_local_idle",
                    step_reward=float(reward),
                    truncated=truncated,
                    terminated=terminated,
                    lua_cmd=None,
                    is_lua_invalid=None,
                    is_lua_throttled=None,
                    extra={
                        "path": "toggle_local_idle",
                        "steps_without_progress": int(self.steps_without_progress),
                        "toggle_only_streak": int(self._toggle_only_streak),
                    },
                )
                # endregion
                return obs, reward, terminated, truncated, {"raw_state": self.current_raw_state, "action_mask": mask}

        # Python 锟?action mask 寮哄埗鎷︽埅锛氫笉鍚堟硶鍔ㄤ綔鐩存帴鎷掞紝涓嶅彂锟?Lua
        current_mask = self._build_action_mask()
        if not current_mask[action]:
            is_blind_macro = action_name.startswith("SELECT_BLIND") or action_name.startswith("SKIP_BLIND")
            is_blind_screen_non_macro = (
                current_screen == "BLIND_SELECT" and not is_blind_macro
            )
            if is_blind_macro:
                # Blind macro blocked by dynamic mask/cooldown should not count as invalid streak.
                self.consecutive_invalid = 0
                penalty = 0.02
            elif is_blind_screen_non_macro:
                # Wrong action family on blind screen (e.g. TOGGLE): do not explode consecutive_invalid.
                self.consecutive_invalid = 0
                penalty = 0.05
            else:
                self.consecutive_invalid += 1
                penalty = min(0.5 + self.consecutive_invalid * 0.05, 3.0)
            logger.debug(f"[Mask Blocked] ({self.consecutive_invalid}x) action={action_name}, penalty={penalty:.2f}")
            obs = extract_features(self.current_raw_state, self.selected_hand_indices, current_mask)
            truncated, terminated = self._hard_horizon()
            if truncated and self.current_step >= self.max_steps:
                logger.info(f"Episode truncated: max_steps={self.max_steps} reached.")
            elif truncated:
                logger.warning(f"Episode truncated: {self.consecutive_invalid} consecutive invalid actions.")
            reward = -penalty
            # region agent log
            self._accumulate_episode_return(reward)
            self._dbg_episode_end(
                hypothesis_id="H4",
                location="python_env/balatro_env.py:mask_blocked",
                step_reward=reward,
                truncated=truncated,
                terminated=False,
                lua_cmd=None,
                is_lua_invalid=None,
                is_lua_throttled=None,
                extra={
                    "path": "mask_blocked",
                    "action_name": action_name,
                    "is_blind_macro": is_blind_macro,
                    "is_blind_screen_non_macro": is_blind_screen_non_macro,
                },
            )
            # endregion
            return obs, reward, terminated, truncated, {
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
            
        truncated, terminated = self._hard_horizon()
        if truncated and self.current_step >= self.max_steps:
            logger.info(f"Episode truncated: max_steps={self.max_steps} reached.")
        elif truncated:
            logger.warning(f"Episode truncated: {self.consecutive_invalid} consecutive invalid actions.")

        info = {
            "raw_state": self.current_raw_state,
            "action_mask": new_mask
        }

        # region agent log
        self._accumulate_episode_return(float(reward))
        self._dbg_episode_end(
            hypothesis_id="H2",
            location="python_env/balatro_env.py:step_main_path",
            step_reward=float(reward),
            truncated=bool(truncated),
            terminated=bool(terminated),
            lua_cmd=str(lua_cmd),
            is_lua_invalid=bool(is_lua_invalid),
            is_lua_throttled=bool(is_lua_throttled),
            extra={"path": "ipc_step"},
        )
        # endregion

        return obs, reward, terminated, truncated, info

    def render(self): pass
    
    def close(self): 
        self.ipc.disconnect()

