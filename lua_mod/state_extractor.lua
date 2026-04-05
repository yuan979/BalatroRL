local StateExtractor = {}

-- ==========================================
-- 内部核心逻辑 (允许发生崩溃，会被外层接管)
-- ==========================================
local function get_game_state_unsafe(CardExtractor)
    -- 【关键修复】：填充默认键值对，防止 Lua 序列化出 JSON 数组 []
    -- 这样 Python 端的 old_stats.get("ante") 就永远不会报错
    local safe_skeleton = {
        current_screen = "MAIN_MENU",
        stats = { 
            money = 0, 
            ante = 1, 
            round = 1, 
            hands_left = 0, 
            discards_left = 0, 
            current_chips = 0, 
            blind_target = 0 
        },
        blinds = {}, 
        shop = {}, 
        jokers = {}, 
        consumables = {}, 
        hand = {}, 
        pack_choices = {}
    }

    if not G or type(G) ~= "table" then return safe_skeleton end

    local current_screen = "UNKNOWN"
    
    -- 1. 优先使用宏观阶段 (STAGE) 判断主菜单
    if G.STAGE == G.STAGES.MAIN_MENU then 
        current_screen = "MAIN_MENU"
    elseif G.STATE then
        -- 2. 微观状态 (STATE) 判断
        if G.STATE == G.STATES.GAME_OVER then 
            current_screen = "GAME_OVER"
        elseif G.STATE == G.STATES.SHOP then 
            current_screen = "SHOP"
        elseif G.STATE == G.STATES.BLIND_SELECT then 
            current_screen = "BLIND_SELECT"
        elseif G.STATE == G.STATES.ROUND_EVAL then 
            current_screen = "ROUND_EVAL"
        elseif G.STATE == G.STATES.TAROT_PACK or G.STATE == G.STATES.PLANET_PACK or G.STATE == G.STATES.STANDARD_PACK or G.STATE == G.STATES.BUFFOON_PACK or G.STATE == G.STATES.SPECTRAL_PACK then 
            current_screen = "PACK_CHOICE"
        elseif G.STATE == G.STATES.SELECTING_HAND or G.STATE == G.STATES.DRAW_TO_HAND or G.STATE == G.STATES.PLAY_TAROT or G.STATE == G.STATES.HAND_PLAYED or G.STATE == G.STATES.MAGIC_TEXT then 
            current_screen = "IN_GAME"
        end
    end

    -- 3. 终极防线：如果没有对局，强制设为主菜单
    if not G.GAME then
        current_screen = "MAIN_MENU"
    end

    -- 主菜单或死亡界面直接退回加固后的安全空壳
    if current_screen == "MAIN_MENU" or current_screen == "GAME_OVER" then
        safe_skeleton.current_screen = current_screen
        return safe_skeleton
    end

    -- ================= 深度数据提取逻辑 =================
    
    local stats = {
        money = G.GAME.dollars or 0,
        ante = G.GAME.round_resets and G.GAME.round_resets.ante or 1,
        round = G.GAME.round_resets and G.GAME.round_resets.round or 1,
        hands_left = G.GAME.current_round and G.GAME.current_round.hands_left or 0,
        discards_left = G.GAME.current_round and G.GAME.current_round.discards_left or 0,
        current_chips = G.GAME.chips or 0, -- 这里的 key 必须与 reward.py 对应
        blind_target = G.GAME.blind and G.GAME.blind.chips or 0,
        joker_slots = G.jokers and G.jokers.config and G.jokers.config.card_limit or 5,
        consumable_slots = G.consumeables and G.consumeables.config and G.consumeables.config.card_limit or 2,
        deck_size = G.deck and G.deck.cards and #G.deck.cards or 52
    }

    local hand, jokers, consumables, blinds = {}, {}, {}, {}
    local shop = { cards = {}, vouchers = {}, booster_packs = {} }

    if G.hand and G.hand.cards then
        for _, c in ipairs(G.hand.cards) do table.insert(hand, CardExtractor.get_details(c)) end
    end
    if G.jokers and G.jokers.cards then
        for _, c in ipairs(G.jokers.cards) do table.insert(jokers, CardExtractor.get_details(c)) end
    end
    if G.consumeables and G.consumeables.cards then
        for _, c in ipairs(G.consumeables.cards) do table.insert(consumables, CardExtractor.get_details(c)) end
    end

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

    if current_screen == "BLIND_SELECT" and G.GAME.round_resets then
        local function get_tag_info(tag_key)
            if type(tag_key) ~= "string" then return nil end
            local loc_text, name = {}, tag_key
            if G.localization and G.localization.descriptions and G.localization.descriptions.Tag and G.localization.descriptions.Tag[tag_key] then
                loc_text = G.localization.descriptions.Tag[tag_key].text or {}
                name = G.localization.descriptions.Tag[tag_key].name or tag_key
            end
            local vars = {}
            if G.P_TAGS and G.P_TAGS[tag_key] and G.P_TAGS[tag_key].config then
                for k, v in pairs(G.P_TAGS[tag_key].config) do
                    if type(v) == "number" or type(v) == "string" or type(v) == "boolean" then vars[k] = v end
                end
            end
            return { id_key = tag_key, name = name, description = loc_text, config_vars = vars }
        end

        local small_tag_key = G.GAME.round_resets.blind_tags and G.GAME.round_resets.blind_tags.Small
        local big_tag_key = G.GAME.round_resets.blind_tags and G.GAME.round_resets.blind_tags.Big
        local boss_key = G.GAME.round_resets.blind_choices and G.GAME.round_resets.blind_choices.Boss
        local boss_desc, boss_name = {}, boss_key
        
        if type(boss_key) == "string" and G.localization and G.localization.descriptions and G.localization.descriptions.Blind and G.localization.descriptions.Blind[boss_key] then
            boss_desc = G.localization.descriptions.Blind[boss_key].text or {}
            boss_name = G.localization.descriptions.Blind[boss_key].name or boss_key
        end

        blinds = {
            small_blind = { state = G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Small or "Unknown", skip_tag = get_tag_info(small_tag_key) },
            big_blind = { state = G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Big or "Unknown", skip_tag = get_tag_info(big_tag_key) },
            boss_blind = { state = G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Boss or "Unknown", id_key = boss_key, name = boss_name, description = boss_desc }
        }
    end

    local pack_choices = {}
    if current_screen == "PACK_CHOICE" and G.pack_cards and G.pack_cards.cards then
        for i, card in ipairs(G.pack_cards.cards) do table.insert(pack_choices, CardExtractor.get_details(card)) end
    end

    return {
        current_screen = current_screen, stats = stats, blinds = blinds, shop = shop, jokers = jokers,
        consumables = consumables, hand = hand, pack_choices = pack_choices
    }
end

-- ==========================================
-- 对外接口 (带 pcall 防爆层)
-- ==========================================
function StateExtractor.get_game_state(CardExtractor)
    local success, result = pcall(get_game_state_unsafe, CardExtractor)
    
    if success then
        return result
    else
        print("INFO - [G] [RL_MOD] [ERROR] StateExtractor CRASHED: " .. tostring(result))
        -- 同样在错误回调中提供带有默认 stats 的空壳
        return {
            current_screen = "MAIN_MENU",
            stats = { money = 0, ante = 1, round = 1, hands_left = 0, discards_left = 0, current_chips = 0, blind_target = 0 },
            blinds = {}, shop = {}, jokers = {}, consumables = {}, hand = {}, pack_choices = {}
        }
    end
end

return StateExtractor