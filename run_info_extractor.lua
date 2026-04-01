local RunInfoExtractor = {}

-- 1. 提取所有牌型的等级、筹码、倍率和打出次数
function RunInfoExtractor.get_poker_hands()
    local hands_info = {}
    if G and G.GAME and G.GAME.hands then
        -- 遍历所有游戏内置的牌型 (如 'Flush', 'Straight' 等)
        for hand_name, hand_data in pairs(G.GAME.hands) do
            hands_info[hand_name] = {
                level = hand_data.level or 1,
                chips = hand_data.chips or 0,
                mult = hand_data.mult or 0,
                played = hand_data.played or 0
            }
        end
    end
    return hands_info
end

-- 2. 提取当前整局游戏的全部牌库 (复用之前的 CardExtractor 解析单张卡牌)
function RunInfoExtractor.get_full_deck(CardExtractor)
    local deck_info = {}
    -- G.playing_cards 包含玩家当前拥有的所有物理卡牌
    if G and G.playing_cards then
        for _, card in ipairs(G.playing_cards) do
            table.insert(deck_info, CardExtractor.get_details(card))
        end
    end
    return deck_info
end

return RunInfoExtractor