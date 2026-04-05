import numpy as np

# ==========================================
# 动作空间定义 (Action Space Dictionary)
# 进行了紧凑化处理，总计 74 维连续动作
# ==========================================
ACTION_MAPPING = {
    0: "PLAY",
    1: "DISCARD",
}

# 2 - 22: 手牌选择 (支持到最大 21 张)
for i in range(21): ACTION_MAPPING[2 + i] = f"TOGGLE_CARD_{i+1}"
# 23 - 32: 使用消耗品
for i in range(10): ACTION_MAPPING[23 + i] = f"USE_CONSUMABLE_{i+1}"
# 33 - 42: 卖出小丑
for i in range(10): ACTION_MAPPING[33 + i] = f"SELL_JOKER_{i+1}"
# 43 - 52: 买卡
for i in range(10): ACTION_MAPPING[43 + i] = f"BUY_CARD_{i+1}"
# 53 - 55: 买优惠券
for i in range(3): ACTION_MAPPING[53 + i] = f"BUY_VOUCHER_{i+1}"
# 56 - 58: 买补充包
for i in range(3): ACTION_MAPPING[56 + i] = f"BUY_BOOSTER_{i+1}"
# 59 - 63: 选包里的卡
for i in range(5): ACTION_MAPPING[59 + i] = f"SELECT_PACK_CARD_{i+1}"

ACTION_MAPPING[64] = "SKIP_PACK"
ACTION_MAPPING[65] = "START_NEW_RUN"
ACTION_MAPPING[66] = "SELECT_BLIND Small"
ACTION_MAPPING[67] = "SELECT_BLIND Big"
ACTION_MAPPING[68] = "SELECT_BLIND Boss"
ACTION_MAPPING[69] = "SKIP_BLIND Small"
ACTION_MAPPING[70] = "SKIP_BLIND Big"
ACTION_MAPPING[71] = "SKIP_BLIND Boss"
ACTION_MAPPING[72] = "CASH_OUT"
ACTION_MAPPING[73] = "NEXT_ROUND"

NUM_ACTIONS = len(ACTION_MAPPING) # 总维度: 74

# ==========================================
# 动作掩码 (Action Masking) 引擎
# ==========================================
def get_action_mask(raw_state: dict, selected_hand_indices: set) -> np.ndarray:
    mask = np.zeros(NUM_ACTIONS, dtype=np.bool_)
    screen = raw_state.get("current_screen", "UNKNOWN")
    
    if screen in ["MAIN_MENU", "GAME_OVER"]:
        mask[65] = True  # START_NEW_RUN
        return mask
        
    elif screen == "IN_GAME":
        hand_size = len(raw_state.get("hand", []))
        consumable_size = len(raw_state.get("consumables", []))
        stats = raw_state.get("stats", {})
        
        # 激活手牌选择
        for i in range(min(hand_size, 21)): mask[2 + i] = True
        
        num_selected = len(selected_hand_indices)
        if 1 <= num_selected <= 5:
            if stats.get("hands_left", 0) > 0: mask[0] = True   # PLAY
            if stats.get("discards_left", 0) > 0: mask[1] = True # DISCARD
            
        # 激活消耗品使用
        for i in range(min(consumable_size, 10)): mask[23 + i] = True
        
    elif screen == "BLIND_SELECT":
        blinds = raw_state.get("blinds", {})
        if blinds.get("small_blind", {}).get("state") == "Select":
            mask[66] = True; mask[69] = True
        if blinds.get("big_blind", {}).get("state") == "Select":
            mask[67] = True; mask[70] = True
        if blinds.get("boss_blind", {}).get("state") == "Select":
            mask[68] = True; mask[71] = True
            
    elif screen == "ROUND_EVAL":
        mask[72] = True # CASH_OUT
        
    elif screen == "SHOP":
        mask[73] = True # NEXT_ROUND
        money = raw_state.get("stats", {}).get("money", 0)
        shop = raw_state.get("shop", {})
        
        # 融合经济判断逻辑：钱够才能买
        for i, card in enumerate(shop.get("cards", [])[:10]):
            if money >= card.get("cost", 0): mask[43 + i] = True
            
        for i, card in enumerate(shop.get("vouchers", [])[:3]):
            if money >= card.get("cost", 0): mask[53 + i] = True
            
        for i, pack in enumerate(shop.get("booster_packs", [])[:3]):
            if money >= pack.get("cost", 0): mask[56 + i] = True
            
        # 允许出售物品
        for i in range(min(len(raw_state.get("jokers", [])), 10)): mask[33 + i] = True
        # 消耗品出售暂时复用上面的范围，实际如果需细分可添加

    elif screen == "PACK_CHOICE":
        mask[64] = True # SKIP_PACK
        pack_choices = raw_state.get("pack_choices", [])
        for i in range(min(len(pack_choices), 5)): mask[59 + i] = True
        
    return mask