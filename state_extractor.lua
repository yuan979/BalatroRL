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
    if current_screen == "BLIND_SELECT" and G.GAME.round_resets then
        
        -- 辅助函数：通过字符串 ID (如 "tag_uncommon") 去字典里查文本
        local function get_tag_info(tag_key)
        if type(tag_key) ~= "string" then return nil end
            
            local loc_text = {}
            local name = tag_key
            
            -- 1. 获取本地化文本模板
            if G.localization and G.localization.descriptions and G.localization.descriptions.Tag and G.localization.descriptions.Tag[tag_key] then
                loc_text = G.localization.descriptions.Tag[tag_key].text or {}
                name = G.localization.descriptions.Tag[tag_key].name or tag_key
            end
            
            -- 2. 获取标签的核心数值配置 (提取给 RL 智能体直接使用)
            local vars = {}
            if G.P_TAGS and G.P_TAGS[tag_key] and G.P_TAGS[tag_key].config then
                -- 遍历并只提取数字和字符串等基础类型，防止互相引用导致 JSON 崩溃
                for k, v in pairs(G.P_TAGS[tag_key].config) do
                    if type(v) == "number" or type(v) == "string" or type(v) == "boolean" then
                        vars[k] = v
                    end
                end
            end
            
            return {
                id_key = tag_key,
                name = name,
                description = loc_text,
                config_vars = vars
            }
        end

        -- 1. 获取跳过标签的字符串 ID
        local small_tag_key = G.GAME.round_resets.blind_tags and G.GAME.round_resets.blind_tags.Small
        local big_tag_key = G.GAME.round_resets.blind_tags and G.GAME.round_resets.blind_tags.Big

        -- 2. 获取 Boss 盲注的字符串 ID (根据你的日志，在 blind_choices 里面)
        local boss_key = G.GAME.round_resets.blind_choices and G.GAME.round_resets.blind_choices.Boss
        local boss_desc = {}
        local boss_name = boss_key
        
        -- 查表获取 Boss 的描述和名字
        if type(boss_key) == "string" and G.localization and G.localization.descriptions and G.localization.descriptions.Blind and G.localization.descriptions.Blind[boss_key] then
            boss_desc = G.localization.descriptions.Blind[boss_key].text or {}
            boss_name = G.localization.descriptions.Blind[boss_key].name or boss_key
        end

        -- 3. 拼装盲注数据
        blinds = {
            small_blind = {
                state = G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Small or "Unknown",
                skip_tag = get_tag_info(small_tag_key)
            },
            big_blind = {
                state = G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Big or "Unknown",
                skip_tag = get_tag_info(big_tag_key)
            },
            boss_blind = {
                state = G.GAME.round_resets.blind_states and G.GAME.round_resets.blind_states.Boss or "Unknown",
                id_key = boss_key,
                name = boss_name,
                description = boss_desc
            }
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