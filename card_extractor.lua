local CardExtractor = {}

function CardExtractor.get_details(card)
    -- 安全检查，防止遇到空槽位报错
    if not card or not card.config or not card.config.center then return {} end

    local center = card.config.center
    local key = center.key
    local set = center.set or "unknown" -- 例如 "Joker", "Tarot", "Booster"

    -- 1. 提取本地化文本描述 (查字典)
    local loc_text = {}
    if G.localization and G.localization.descriptions and G.localization.descriptions[set] and G.localization.descriptions[set][key] then
        -- 游戏的描述通常是一个字符串数组，每行对应一句描述
        loc_text = G.localization.descriptions[set][key].text or {}
    end

    -- 2. 提取动态能力数值 (强化学习极度依赖这些精确的数字)
    local ability = card.ability or {}

    return {
        name = center.name or "unknown",
        id_key = key,
        set = set, 
        suit = (card.base and card.base.suit) or "none",
        value = (card.base and card.base.value) or "none",
        edition = (card.edition and card.edition.type) or "standard",
        enhancement = (center.name ~= (card.base and card.base.name) and center.name) or "none",
        cost = card.cost or 0,
        sell_cost = card.sell_cost or 0,
        
        -- 新增：纯文本描述 (中/英文取决于你游戏的语言设置)
        description = loc_text,
        
        -- 新增：精确数值变量 (方便 RL 直接作为 Observation 特征)
        ability_vars = {
            mult = ability.mult,           -- 加法倍率
            h_mult = ability.h_mult,       -- 牌面基础倍率
            x_mult = ability.x_mult,       -- 乘法倍率
            chips = ability.chips,         -- 筹码
            extra = ability.extra,         -- 额外变量 (如 DNA 的触发次数等)
            max = ability.max              -- 上限变量 (如吸血鬼的上限)
        }
    }
end

return CardExtractor