import math
import logging

logger = logging.getLogger("RewardShaping")

def calculate_reward(old_state: dict, new_state: dict) -> float:
    """
    根据状态转移计算奖励。
    加入了类型防御逻辑，防止 Lua 空表序列化为 Python 列表导致的 get 报错。
    """
    reward = 0.0
    
    old_screen = old_state.get("current_screen", "UNKNOWN")
    new_screen = new_state.get("current_screen", "UNKNOWN")

    if new_screen == "GAME_OVER":
        return -20.0
        
    old_stats = old_state.get("stats", {})
    new_stats = new_state.get("stats", {})
    if isinstance(old_stats, list): old_stats = {}
    if isinstance(new_stats, list): new_stats = {}

    reward -= 0.01
    
    if old_screen == "IN_GAME" and new_screen == "IN_GAME":
        old_chips = float(old_stats.get("current_chips", 0))
        new_chips = float(new_stats.get("current_chips", 0))
        
        if new_chips > old_chips:
            # log1p 奖励公式: R = 0.2 * (ln(1 + new) - ln(1 + old))
            delta_log = math.log1p(new_chips) - math.log1p(old_chips)
            reward += delta_log * 0.2 
            
        old_hands = int(old_stats.get("hands_left", 0))
        new_hands = int(new_stats.get("hands_left", 0))
        if new_hands < old_hands:
            reward -= 0.1 
            
        old_discards = int(old_stats.get("discards_left", 0))
        new_discards = int(new_stats.get("discards_left", 0))
        if new_discards < old_discards:
            reward -= 0.05 

    old_money = float(old_stats.get("money", 0))
    new_money = float(new_stats.get("money", 0))
    if new_money > old_money:
        reward += 0.05 
        
    old_jokers = len(old_state.get("jokers", []))
    new_jokers = len(new_state.get("jokers", []))
    if new_jokers > old_jokers:
        reward += 1.0 

    if old_screen == "IN_GAME" and new_screen == "ROUND_EVAL":
        reward += 2.0 
        logger.debug("Blind Defeated! Reward +2")


    old_ante = int(old_stats.get("ante", 1))
    new_ante = int(new_stats.get("ante", 1))
    if new_ante > old_ante:
        reward += 10.0
        logger.info(f"Milestone! Ante {old_ante} -> {new_ante}. Reward +10")

    if new_state.get("invalid_action", False):
        reward -= 0.5 
        logger.debug("Penalty: AI attempted an invalid action.")

    return reward