import numpy as np

# ==========================================
# 动作空间定义 (Action Space Dictionary)
# ==========================================
ACTION_MAPPING = {
    **{i: f"TOGGLE_CARD_{i+1}" for i in range(10)},
    10: "PLAY",
    11: "DISCARD",
    12: "CASH_OUT",
    13: "NEXT_ROUND",
    14: "SELECT_BLIND Small", 15: "SELECT_BLIND Big", 16: "SELECT_BLIND Boss",
    17: "SKIP_BLIND Small",   18: "SKIP_BLIND Big",   19: "SKIP_BLIND Boss",
    **{i + 20: f"BUY_CARD {i+1}" for i in range(10)},
    **{i + 30: f"BUY_VOUCHER {i+1}" for i in range(5)},
    **{i + 35: f"BUY_BOOSTER {i+1}" for i in range(5)},
    **{i + 40: f"USE_CONSUMABLE {i+1}" for i in range(10)},
    **{i + 50: f"SELL_JOKER {i+1}" for i in range(10)},
    **{i + 60: f"SELL_CONSUMABLE {i+1}" for i in range(10)},
    **{i + 70: f"SELECT_PACK_CARD {i+1}" for i in range(10)},
    80: "SKIP_PACK"
}

NUM_ACTIONS = len(ACTION_MAPPING)

def get_action_mask(raw_state, selected_hand_indices):
    """
    获取动作掩码：根据传入的游戏状态，计算当前合法的动作
    """
    mask = np.zeros(NUM_ACTIONS, dtype=np.bool_)
    screen = raw_state.get("current_screen", "UNKNOWN")
    
    if screen == "IN_GAME":
        hand_size = len(raw_state.get("hand", []))
        consumable_size = len(raw_state.get("consumables", []))
        stats = raw_state.get("stats", {})
        
        for i in range(hand_size): mask[i] = True
        
        if len(selected_hand_indices) > 0:
            if stats.get("hands_left", 0) > 0: mask[10] = True
            if stats.get("discards_left", 0) > 0: mask[11] = True
            
        for i in range(consumable_size): mask[40 + i] = True
        
    elif screen == "BLIND_SELECT":
        blinds = raw_state.get("blinds", {})
        if blinds.get("small_blind", {}).get("state") == "Select":
            mask[14] = True; mask[17] = True
        if blinds.get("big_blind", {}).get("state") == "Select":
            mask[15] = True; mask[18] = True
        if blinds.get("boss_blind", {}).get("state") == "Select":
            mask[16] = True; mask[19] = True
            
    elif screen == "ROUND_EVAL":
        mask[12] = True
        
    elif screen == "SHOP":
        mask[13] = True
        money = raw_state.get("stats", {}).get("money", 0)
        shop = raw_state.get("shop", {})
        
        for i, card in enumerate(shop.get("cards", [])):
            if money >= card.get("cost", 0): mask[20 + i] = True
        for i, card in enumerate(shop.get("vouchers", [])):
            if money >= card.get("cost", 0): mask[30 + i] = True
        for i, card in enumerate(shop.get("booster_packs", [])):
            if money >= card.get("cost", 0): mask[35 + i] = True
            
        for i in range(len(raw_state.get("jokers", []))): mask[50 + i] = True
        for i in range(len(raw_state.get("consumables", []))): mask[60 + i] = True

    elif screen == "PACK_CHOICE":
        mask[80] = True
        pack_choices = raw_state.get("pack_choices", [])
        for i in range(len(pack_choices)): mask[70 + i] = True
        
    return mask