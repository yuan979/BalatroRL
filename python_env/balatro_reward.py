import math
import logging

logger = logging.getLogger("RewardShaping")

def calculate_reward(old_state: dict, new_state: dict) -> float:
    """
    根据状态转移计算奖励。
    加入了类型防御逻辑，防止 Lua 空表序列化为 Python 列表导致的 get 报错。
    """
    reward = 0.0
    
    # 1. 提取并校验 Screen 状态
    old_screen = old_state.get("current_screen", "UNKNOWN")
    new_screen = new_state.get("current_screen", "UNKNOWN")
    
    # 终局惩罚 (大幅度负反馈)
    if new_screen == "GAME_OVER":
        return -20.0
        
    # 2. 提取并校验 Stats (防御性编程：如果是 list 则转为 dict)
    old_stats = old_state.get("stats", {})
    new_stats = new_state.get("stats", {})
    
    if isinstance(old_stats, list): old_stats = {}
    if isinstance(new_stats, list): new_stats = {}

    # 3. 步时惩罚 (Time Penalty)
    # 鼓励 AI 尽快出牌，而不是做无效的卡牌切换动作
    reward -= 0.01
    
    # 4. 筹码增量奖励 (仅在 IN_GAME 状态下)
    if old_screen == "IN_GAME" and new_screen == "IN_GAME":
        # Balatro 中 current_chips 是累计的，通过对数差分给予奖励
        old_chips = float(old_stats.get("current_chips", 0))
        new_chips = float(new_stats.get("current_chips", 0))
        
        if new_chips > old_chips:
            # log1p 防止 chips 为 0 时 log 报错
            delta_log = math.log1p(new_chips) - math.log1p(old_chips)
            reward += delta_log * 0.2  # 增加权重，让 AI 更渴望筹码
            
    # 5. 经济奖励 (引导 AI 关注金钱)
    old_money = float(old_stats.get("money", 0))
    new_money = float(new_stats.get("money", 0))
    if new_money > old_money:
        reward += 0.05  # 赚小钱给小奖励
        
    # 6. 核心里程碑奖励 (底注 Ante 增加)
    # 这通常发生在 ROUND_EVAL 之后或 SHOP 结束进入新关卡
    old_ante = int(old_stats.get("ante", 1))
    new_ante = int(new_stats.get("ante", 1))
    
    if new_ante > old_ante:
        reward += 10.0  # 大额奖励
        logger.info(f"Milestone! Ante {old_ante} -> {new_ante}. Reward +10")

    return reward