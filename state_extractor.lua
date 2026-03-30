local StateExtractor = {}

-- 接收 CardExtractor 作为依赖注入
function StateExtractor.get_game_state(CardExtractor)
    if not G or not G.STAGE or G.STAGE ~= G.STAGES.RUN then return nil end

    -- A. 识别当前 UI 界面状态
    local current_screen = "UNKNOWN"
    if G.STATE == G.STATES.SHOP then current_screen = "SHOP"
    elseif G.STATE == G.STATES.BLIND_SELECT then current_screen = "BLIND_SELECT"
    elseif G.STATE == G.STATES.TAROT_PACK or G.STATE == G.STATES.PLANET_PACK or G.STATE == G.STATES.STANDARD_PACK or G.STATE == G.STATES.BUFFOON_PACK then current_screen = "OPENING_PACK"
    elseif G.STATE == G.STATES.SELECTING_HAND or G.STATE == G.STATES.DRAW_TO_HAND or G.STATE == G.STATES.PLAY_TAROT then current_screen = "IN_GAME"
    elseif G.STATE == G.STATES.GAME_OVER then current_screen = "GAME_OVER"
    end

    -- B. 基础面板数据
    local stats = {
        money = G.GAME.dollars or 0,
        ante = G.GAME.round_resets.ante or 1,
        round = G.GAME.round_resets.round or 1,
        hands_left = G.GAME.current_round and G.GAME.current_round.hands_left or 0,
        discards_left = G.GAME.current_round and G.GAME.current_round.discards_left or 0,
        current_chips = G.GAME.chips or 0,
        blind_target = G.GAME.blind and G.GAME.blind.chips or 0,
        joker_slots = G.jokers and G.jokers.config and G.jokers.config.card_limit or 5,
        consumable_slots = G.consumeables and G.consumeables.config and G.consumeables.config.card_limit or 2,
        deck_size = G.deck and G.deck.cards and #G.deck.cards or 52
    }

    -- C. 收集所有区域的实体
    local hand = {}
    local jokers = {}
    local consumables = {}
    local shop = { cards = {}, vouchers = {}, booster_packs = {} }
    local blinds = {}

    if G.hand and G.hand.cards then
        for _, c in ipairs(G.hand.cards) do table.insert(hand, CardExtractor.get_details(c)) end
    end
    if G.jokers and G.jokers.cards then
        for _, c in ipairs(G.jokers.cards) do table.insert(jokers, CardExtractor.get_details(c)) end
    end
    if G.consumeables and G.consumeables.cards then
        for _, c in ipairs(G.consumeables.cards) do table.insert(consumables, CardExtractor.get_details(c)) end
    end

    -- D. 商店界面特有数据
    if current_screen == "SHOP" then
        if G.shop_jokers and G.shop_jokers.cards then
            for _, c in ipairs(G.shop_jokers.cards) do table.insert(shop.cards, CardExtractor.get_details(c)) end
        end
        if G.shop_vouchers and G.shop_vouchers.cards then
            for _, c in ipairs(G.shop_vouchers.cards) do table.insert(shop.vouchers, CardExtractor.get_details(c)) end
        end
        if G.shop_booster and G.shop_booster.cards then
            for _, c in ipairs(G.shop_booster.cards) do table.insert(shop.booster_packs, CardExtractor.get_details(c)) end
        end
    end

    -- E. 盲注界面特有数据
    if current_screen == "BLIND_SELECT" and G.GAME.round_resets.blind_states then
        blinds = {
            small_blind_state = G.GAME.round_resets.blind_states.Small or "Unknown",
            big_blind_state = G.GAME.round_resets.blind_states.Big or "Unknown",
            boss_blind_state = G.GAME.round_resets.blind_states.Boss or "Unknown",
            current_boss_name = G.GAME.boss_blind and G.GAME.boss_blind.name or "Unknown"
        }
    end

    return {
        current_screen = current_screen,
        stats = stats,
        blinds = blinds,
        shop = shop,
        jokers = jokers,
        consumables = consumables,
        hand = hand
    }
end

return StateExtractor