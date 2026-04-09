import numpy as np
from gymnasium import spaces
import logging

logger = logging.getLogger("FeatureExtractor")

# ==========================================
# 常量与维度定义
# ==========================================
MAX_MONEY = 400.0
MAX_ANTE = 8.0

# 矩阵最大尺寸
MAX_HAND_SIZE = 21   # 手牌上限 (考虑到各种增加上限的 Buff)
MAX_JOKERS = 10      # 小丑牌上限

# 特征向量长度
PLAYING_CARD_DIM = 24  # 每张手牌的特征数
JOKER_DIM = 12         # 每张小丑的特征数

SCREEN_LIST = ["IN_GAME", "BLIND_SELECT", "SHOP", "ROUND_EVAL", "OPENING_PACK", "GAME_OVER", "MAIN_MENU"]
SCREEN_DIM = len(SCREEN_LIST)  # 7

# 计算总维度: 7(全局) + 7(屏幕one-hot) + 21*24(手牌) + 10*12(小丑) = 638
TOTAL_FEATURE_DIM = 7 + SCREEN_DIM + (MAX_HAND_SIZE * PLAYING_CARD_DIM) + (MAX_JOKERS * JOKER_DIM)

# ==========================================
# 辅助编码函数
# ==========================================
def get_rank_val(rank_str: str) -> float:
    """将牌面点数转化为数值 (2-14)，并归一化"""
    rank_map = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9, '10':10, 'J':11, 'Q':12, 'K':13, 'A':14}
    val = rank_map.get(str(rank_str).upper(), 0)
    return val / 14.0

def get_suit_one_hot(suit_str: str) -> list:
    """将花色转化为 4 维 One-Hot 向量"""
    suit = str(suit_str).capitalize()
    if suit == 'Spades': return [1, 0, 0, 0]
    if suit == 'Hearts': return [0, 1, 0, 0]
    if suit == 'Clubs': return [0, 0, 1, 0]
    if suit == 'Diamonds': return [0, 0, 0, 1]
    return [0, 0, 0, 0] # 未知花色 (如石头牌)

def get_edition_one_hot(edition_str: str) -> list:
    """版本编码: 闪箔(Foil), 全息(Holo), 多彩(Poly), 负片(Negative)"""
    edition = str(edition_str).lower() if edition_str else ""
    return [
        1 if "foil" in edition else 0,
        1 if "holo" in edition else 0,
        1 if "poly" in edition else 0,
        1 if "negative" in edition else 0
    ]

# ==========================================
# 核心解析逻辑
# ==========================================
def extract_screen_one_hot(raw_state: dict) -> np.ndarray:
    """将 current_screen 编码为 7 维 one-hot"""
    vec = np.zeros(SCREEN_DIM, dtype=np.float32)
    screen = raw_state.get("current_screen", "")
    if screen in SCREEN_LIST:
        vec[SCREEN_LIST.index(screen)] = 1.0
    return vec


def extract_global_scalars(raw_state: dict) -> np.ndarray:
    if raw_state.get("current_screen") not in ["IN_GAME", "BLIND_SELECT", "SHOP", "ROUND_EVAL"]:
        return np.zeros(7, dtype=np.float32)

    stats = raw_state.get("stats", {})
    
    if isinstance(stats, list):
        stats = {}

    money = min(float(stats.get("money", 0)), MAX_MONEY) / MAX_MONEY
    hands_left = float(stats.get("hands_left", 0)) / 10.0
    discards_left = float(stats.get("discards_left", 0)) / 10.0
    ante = float(stats.get("ante", 1)) / MAX_ANTE
    
    # 直接从 stats 获取筹码和目标
    raw_chips = float(stats.get("current_chips", 0))
    raw_target = float(stats.get("blind_target", 0))
    
    current_chips_log = np.log1p(max(0, raw_chips))
    target_chips_log = np.log1p(max(0, raw_target))
    
    # 计算当前得分比例，上限为 1.0
    score_ratio = 0.0
    if raw_chips > 0 and raw_target > 0:
        score_ratio = min(raw_chips / raw_target, 1.0)

    return np.array([
        money, 
        hands_left, 
        discards_left, 
        ante, 
        current_chips_log, 
        target_chips_log, 
        score_ratio
    ], dtype=np.float32)


def extract_hand_features(raw_state: dict) -> np.ndarray:
    """解析手牌，生成形状为 [MAX_HAND_SIZE, PLAYING_CARD_DIM] 的二维张量"""
    hand_matrix = np.zeros((MAX_HAND_SIZE, PLAYING_CARD_DIM), dtype=np.float32)
    hand_cards = raw_state.get("hand", [])
    
    for i, card in enumerate(hand_cards):
        if i >= MAX_HAND_SIZE: break
        
        rank_val = get_rank_val(card.get("base", {}).get("value", ""))
        suit_vec = get_suit_one_hot(card.get("base", {}).get("suit", ""))
        
        chips = np.log1p(card.get("ability", {}).get("bonus_chips", 0))
        mult = np.log1p(card.get("ability", {}).get("mult", 0))
        x_mult = card.get("ability", {}).get("x_mult", 1) / 10.0
        
        edition_vec = get_edition_one_hot(card.get("edition", ""))
        
        feature_list = [rank_val] + suit_vec + [chips, mult, x_mult] + edition_vec
        hand_matrix[i, :len(feature_list)] = feature_list
        
    return hand_matrix


def extract_joker_features(raw_state: dict) -> np.ndarray:
    """解析小丑牌，生成形状为 [MAX_JOKERS, JOKER_DIM] 的二维张量"""
    joker_matrix = np.zeros((MAX_JOKERS, JOKER_DIM), dtype=np.float32)
    jokers = raw_state.get("jokers", [])
    
    for i, joker in enumerate(jokers):
        if i >= MAX_JOKERS: break
        
        cost = joker.get("cost", 0) / 20.0
        sell_cost = joker.get("sell_cost", 0) / 20.0
        rarity = joker.get("config", {}).get("center", {}).get("rarity", 1) / 4.0 
        
        chips = np.log1p(joker.get("ability", {}).get("extra", {}).get("chips", 0) if isinstance(joker.get("ability", {}).get("extra"), dict) else 0)
        mult = np.log1p(joker.get("ability", {}).get("extra", {}).get("mult", 0) if isinstance(joker.get("ability", {}).get("extra"), dict) else 0)
        x_mult = (joker.get("ability", {}).get("extra", {}).get("Xmult", 1) if isinstance(joker.get("ability", {}).get("extra"), dict) else 1) / 5.0
        
        edition_vec = get_edition_one_hot(joker.get("edition", ""))
        
        feature_list = [cost, sell_cost, rarity, chips, mult, x_mult] + edition_vec
        joker_matrix[i, :len(feature_list)] = feature_list
        
    return joker_matrix


# ==========================================
# 适配 DreamerV3 的顶层接口 (核心修改区)
# ==========================================
def build_observation_space() -> spaces.Dict:
    """
    正式的 Gym Observation Space。
    [修改点]：统一为一个名为 'state' 的 638 维一维向量 (Box)。
    """
    obs_space = spaces.Dict({
        "state": spaces.Box(low=-1.0, high=100.0, shape=(TOTAL_FEATURE_DIM,), dtype=np.float32)
    })
    return obs_space


def extract_features(raw_state: dict) -> dict:
    """
    顶层接口：将 raw JSON dict 转化为符合 observation_space 的字典。
    [修改点]：将所有特征展平并拼接在一起。
    """
    global_feats = extract_global_scalars(raw_state)       # 7
    screen_feats = extract_screen_one_hot(raw_state)       # 7

    # 将二维矩阵展平为一维向量: (21, 24) -> (504,)
    hand_feats = extract_hand_features(raw_state).flatten()

    # 将二维矩阵展平为一维向量: (10, 12) -> (120,)
    joker_feats = extract_joker_features(raw_state).flatten()

    # 拼接: 7 + 7 + 504 + 120 = 638
    state_vector = np.concatenate([global_feats, screen_feats, hand_feats, joker_feats], axis=0)
    
    return {
        "state": state_vector
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    
    mock_state = {
        "current_screen": "IN_GAME",
        "stats": {"money": 25, "hands_left": 4, "ante": 2},
        "blinds": {"current_blind": {"target_score": 5000}},
        "hand": [
            {"base": {"value": "K", "suit": "Hearts"}, "edition": "Foil", "ability": {"bonus_chips": 50}},
            {"base": {"value": "8", "suit": "Spades"}, "edition": "None", "ability": {}}
        ],
        "jokers": [
            {"cost": 6, "sell_cost": 3, "config": {"center": {"rarity": 2}}, "edition": "Polychrome", "ability": {"extra": {"mult": 15}}}
        ]
    }
    
    features = extract_features(mock_state)
    
    logger.info("Final Observation Keys: %s", features.keys())
    logger.info("Final 'state' vector shape: %s", features['state'].shape)
    
    assert features['state'].shape == (TOTAL_FEATURE_DIM,), f"Expected shape ({TOTAL_FEATURE_DIM},), got {features['state'].shape}"
    logger.info("Successfully flattened! The vector is ready for DreamerV3.")