local ActionExecutor = {}

local Log = { info = print, warn = print, error = print, success = print, debug = print }

local last_macro_time = 0
local MACRO_COOLDOWN = 3.0

function ActionExecutor.init(logger_instance)
    if logger_instance then Log = logger_instance end
end

local function clean_string(str)
    if not str then return nil end
    str = str:gsub("%s+", "")
    local low = str:lower()
    if low == "small" then return "Small" end
    if low == "big" then return "Big" end
    if low == "boss" then return "Boss" end
    return str
end

local function create_mock_e(config_data)
    local mock_uibox = {
        config = config_data or {},
        get_UIE_by_ID = function() return nil end,
        recalculate = function() end,
        disable_button = function() end,
        remove = function() end,
        children = {}, states = {}
    }
    return { config = config_data or {}, UIBox = mock_uibox }
end

local function aggressive_ui_search(target_button, target_ref_table)
    Log.debug("Starting BFS search for button: " .. tostring(target_button))
    local visited = {}
    local queue = {}
    
    for k, v in pairs(G) do
        if type(v) == "table" and type(k) == "string" then
            if k:match("UI") or k:match("ROOM") or k:match("HUD") or k:match("overlay") or k:match("blind") or k:match("menu") or k:match("shop") or k == "jiggle" then
                table.insert(queue, v)
            end
        end
    end

    local head = 1
    local nodes_visited = 0

    while head <= #queue and head < 50000 do
        local curr = queue[head]
        head = head + 1
        
        if type(curr) == "table" and not visited[curr] then
            visited[curr] = true
            nodes_visited = nodes_visited + 1
            
            if curr.config and type(curr.config) == "table" and curr.config.button == target_button then
                if target_ref_table then
                    if curr.config.ref_table == target_ref_table then
                        return curr
                    end
                else
                    return curr
                end
            end
            
            for k, v in pairs(curr) do
                if type(v) == "table" and k ~= "parent" and k ~= "cards" and k ~= "playing_cards" then
                    queue[#queue + 1] = v
                end
            end
        end
    end
    return nil
end

local function highlight_cards(indices)
    if not G.hand or not G.hand.cards then return end
    if G.hand.unhighlight_all then G.hand:unhighlight_all()
    else
        for i = #G.hand.highlighted, 1, -1 do G.hand:remove_from_highlighted(G.hand.highlighted[i]) end
    end
    for _, idx_str in ipairs(indices) do
        local idx = tonumber(idx_str)
        if idx and G.hand.cards[idx] then G.hand:add_to_highlighted(G.hand.cards[idx], true) end
    end
end

-- ==========================================
-- 核心执行逻辑
-- ==========================================
function ActionExecutor.execute_command(content)
    if not content or content == "" then return end

    -- [新增] 重置非法动作标记。Python端读取状态时可提取此标记用于计算惩罚
    if G then G.last_action_invalid = false end

    -- 1. 优先解析指令
    local args = {}
    for word in string.gmatch(content, "%S+") do table.insert(args, word) end
    if #args == 0 then return end
    
    local cmd = args[1]:upper()
    local params = {unpack(args, 2)}

    local is_macro_action = (cmd == "START_NEW_RUN" or cmd == "SELECT_BLIND" or cmd == "SKIP_BLIND" or cmd == "NEXT_ROUND" or cmd == "CASH_OUT" or cmd == "SKIP_PACK" or cmd == "SELECT_PACK_CARD")
    
    if is_macro_action then
        local current_time = os.clock()
        if current_time - last_macro_time < MACRO_COOLDOWN then
            Log.warn("Machine-gun prevention! Dropping spammed macro action: " .. cmd)
            if G then G.last_action_invalid = true end
            return
        end
        last_macro_time = current_time
    end

    Log.info("Attempting to execute: " .. content)

    -- 2. 开始新游戏
    if cmd == "START_NEW_RUN" then
        Log.info("====== [ACTION] Triggering START_NEW_RUN ======")
        G.SAVED_GAME = nil
        if G.FUNCS.start_run then
            local mock_button = {
                config = { button = 'start_run', id = 'start_run_button', save_text = false },
                UIBox = { disable_button = function() end, get_UIE_by_ID = function() return nil end, recalculate = function() end, remove = function() end }
            }
            local success, err = pcall(function() G.FUNCS.start_run(mock_button) end)
            if success then Log.success("start_run logic dispatched successfully.") else Log.error("start_run ENGINE CRASH: " .. tostring(err)) end
        else
            Log.error("G.FUNCS.start_run pointer is missing!")
        end
        return
    end

    -- 3. 动画锁检查
    if G.STATE_COMPLETE == false then 
        Log.warn("Animation in progress, ignoring command: " .. content)
        if G then G.last_action_invalid = true end
        return 
    end

    -- 选择盲注
    if (cmd == "SELECT_BLIND" or cmd == "SKIP_BLIND") and G.STATE == G.STATES.BLIND_SELECT then
        local blind_type = clean_string(params[1])
        local target_btn = (cmd == "SELECT_BLIND") and "select_blind" or "skip_blind"
        
        if not blind_type or not G.GAME.round_resets.blind_states[blind_type] or G.GAME.round_resets.blind_states[blind_type] ~= 'Select' then 
            if G then G.last_action_invalid = true end
            Log.warn("Invalid Blind Selection: " .. tostring(blind_type))
            return 
        end
        
        local real_btn_node = aggressive_ui_search(target_btn)
        if real_btn_node then
            pcall(function() G.FUNCS[target_btn](real_btn_node) end)
        else
            pcall(function() G.FUNCS[target_btn](create_mock_e({button = target_btn, ref_table = blind_type})) end)
        end
        
    -- 离开商店
    elseif cmd == "NEXT_ROUND" and G.STATE == G.STATES.SHOP then
        local real_btn_node = aggressive_ui_search("toggle_shop")
        if real_btn_node then G.FUNCS.toggle_shop(real_btn_node) else G.FUNCS.toggle_shop(create_mock_e({button = "toggle_shop"})) end

    -- 出牌/弃牌
    elseif (cmd == "PLAY" or cmd == "DISCARD") and G.STATE == G.STATES.SELECTING_HAND then
        highlight_cards(params)
        if cmd == "PLAY" then
            if #G.hand.highlighted > 0 then
                G.FUNCS.play_cards_from_highlighted(create_mock_e({button = "play_cards_from_highlighted"}))
            else
                if G then G.last_action_invalid = true end
                Log.warn("Invalid PLAY: No cards selected.")
            end
        elseif cmd == "DISCARD" then
            if #G.hand.highlighted > 0 and G.GAME.current_round.discards_left > 0 then
                G.FUNCS.discard_cards_from_highlighted(create_mock_e({button = "discard_cards_from_highlighted"}))
            else
                if G then G.last_action_invalid = true end
                Log.warn("Invalid DISCARD: No cards selected or 0 discards left.")
            end
        end

    -- 提现结算
    elseif cmd == "CASH_OUT" and G.STATE == G.STATES.ROUND_EVAL then
        local real_btn_node = aggressive_ui_search("cash_out")
        if real_btn_node then G.FUNCS.cash_out(real_btn_node) else G.FUNCS.cash_out(create_mock_e({button = "cash_out"})) end

    -- 购买商店物品
    elseif (cmd == "BUY_CARD" or cmd == "BUY_VOUCHER" or cmd == "BUY_BOOSTER") and G.STATE == G.STATES.SHOP then
        local idx = tonumber(params[1]) or 1
        local target_card = nil
        local target_func = nil 

        if cmd == "BUY_CARD" and G.shop_jokers and G.shop_jokers.cards then
            target_card = G.shop_jokers.cards[idx]
            target_func = "buy_from_shop" 
        elseif cmd == "BUY_VOUCHER" and G.shop_vouchers and G.shop_vouchers.cards then
            target_card = G.shop_vouchers.cards[idx]
            target_func = "use_card" 
        elseif cmd == "BUY_BOOSTER" and G.shop_booster and G.shop_booster.cards then
            target_card = G.shop_booster.cards[idx]
            target_func = "use_card" 
        end

        if target_card and target_func then
            if G.GAME.dollars >= (target_card.cost or 0) then
                G.FUNCS[target_func](create_mock_e({ref_table = target_card, button = target_func}))
            else
                if G then G.last_action_invalid = true end
                Log.warn("Invalid BUY: Not enough money! Have: " .. tostring(G.GAME.dollars))
            end
        else
            if G then G.last_action_invalid = true end
            Log.warn("Invalid BUY: Item not found for " .. cmd .. " at index " .. tostring(idx))
        end

    -- 使用消耗品
    elseif cmd == "USE_CONSUMABLE" then
        local idx = tonumber(params[1]) or 1
        if G.consumeables and G.consumeables.cards and G.consumeables.cards[idx] then
            local card = G.consumeables.cards[idx]
            local real_btn_node = aggressive_ui_search("use_card", card)
            if real_btn_node then G.FUNCS.use_card(real_btn_node) else G.FUNCS.use_card(create_mock_e({ref_table = card, button = "use_card"})) end
        else
            if G then G.last_action_invalid = true end
            Log.warn("Invalid USE: Consumable not found at index " .. tostring(idx))
        end

    -- 出售卡牌
    elseif string.match(cmd, "^SELL_") then
        local idx = tonumber(params[1]) or 1
        local target_card = nil
        
        if cmd == "SELL_JOKER" and G.jokers and G.jokers.cards then target_card = G.jokers.cards[idx]
        elseif cmd == "SELL_CONSUMABLE" and G.consumeables and G.consumeables.cards then target_card = G.consumeables.cards[idx] end

        if target_card then
            local real_btn_node = aggressive_ui_search("sell_card", target_card)
            if real_btn_node then G.FUNCS.sell_card(real_btn_node) else G.FUNCS.sell_card(create_mock_e({ref_table = target_card, button = "sell_card"})) end
        else
            -- [新增] 拦截无效出售
            if G then G.last_action_invalid = true end
            Log.warn("Invalid SELL: Card not found for " .. cmd .. " at index " .. tostring(idx))
        end

    -- 交换卡牌位置
    elseif string.match(cmd, "^SWAP_") then
        local idx1 = tonumber(params[1])
        local idx2 = tonumber(params[2])
        if idx1 and idx2 and idx1 ~= idx2 then
            local card_area = (cmd == "SWAP_JOKER") and G.jokers or G.hand
            if card_area and card_area.cards and card_area.cards[idx1] and card_area.cards[idx2] then
                local temp = card_area.cards[idx1]
                card_area.cards[idx1] = card_area.cards[idx2]
                card_area.cards[idx2] = temp
                if card_area.set_ranks then card_area:set_ranks() end
                if card_area.align_cards then card_area:align_cards() end
            else
                if G then G.last_action_invalid = true end
                Log.warn("Invalid SWAP: Cards not found at indices " .. tostring(idx1) .. " and " .. tostring(idx2))
            end
        else
            if G then G.last_action_invalid = true end
            Log.warn("Invalid SWAP: Missing or identical indices.")
        end
    
    -- 卡包操作
    elseif (cmd == "SELECT_PACK_CARD" or cmd == "SKIP_PACK") then
        if not G.pack_cards then
            if G then G.last_action_invalid = true end
            Log.warn("Invalid Pack Action: No active pack on screen.")
            return
        end

        if cmd == "SELECT_PACK_CARD" then
            local idx = tonumber(params[1]) or 1
            if G.pack_cards.cards and G.pack_cards.cards[idx] then
                local target_card = G.pack_cards.cards[idx]
                local real_btn_node = aggressive_ui_search("use_card", target_card)
                if real_btn_node then G.FUNCS.use_card(real_btn_node) else G.FUNCS.use_card(create_mock_e({ref_table = target_card, button = "use_card"})) end
            else
                if G then G.last_action_invalid = true end
                Log.warn("Invalid Pack Selection: Card not found at index " .. tostring(idx))
            end
        elseif cmd == "SKIP_PACK" then
            local real_btn_node = aggressive_ui_search("skip_booster")
            if real_btn_node then G.FUNCS.skip_booster(real_btn_node) else G.FUNCS.skip_booster(create_mock_e({button = "skip_booster"})) end
        end
        
    -- 状态不匹配的其他指令，统统标记为非法
    else
        if G then G.last_action_invalid = true end
        Log.warn("Invalid Action: " .. cmd .. " cannot be executed in current STATE.")
    end
end

return ActionExecutor