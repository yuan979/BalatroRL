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

-- ==========================================
-- 核心搜寻引擎：支持通过 ref_table (卡牌实体) 锁定按钮
-- ==========================================
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
                -- 如果传了卡牌实体，必须匹配它才是对应的购买按钮
                if target_ref_table then
                    if curr.config.ref_table == target_ref_table then
                        Log.debug("Match found (with ref_table) after visiting " .. tostring(nodes_visited) .. " nodes.")
                        return curr
                    end
                else
                    Log.debug("Match found after visiting " .. tostring(nodes_visited) .. " nodes.")
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
    Log.debug("BFS exhausted. Target not found.")
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
            return
        end
        last_macro_time = current_time
    end

    Log.info("Attempting to execute: " .. content)

    -- 2. 宏观特权指令：无视动画锁，强制执行
    -- 0. 开始新游戏
    if cmd == "START_NEW_RUN" then
        Log.info("====== [ACTION] Triggering START_NEW_RUN ======")
        
        -- 核心修复：彻底移除对 G.PROFILES[...].memory 的访问，防止 nil 崩溃
        G.SAVED_GAME = nil
        
        if G.FUNCS.start_run then
            -- 构造一个不仅能“防删”，还能提供基础 config 的模拟实体
            local mock_button = {
                config = { 
                    button = 'start_run', 
                    id = 'start_run_button',
                    save_text = false 
                },
                UIBox = {
                    disable_button = function() end,
                    get_UIE_by_ID = function() return nil end,
                    recalculate = function() end,
                    remove = function() end -- 关键：防止引擎尝试移除 UI 时崩溃
                }
            }
            
            -- 使用 pcall 再次包裹，即使 start_run 内部崩了，也不会带走整个游戏
            local success, err = pcall(function()
                G.FUNCS.start_run(mock_button)
            end)
            
            if success then
                Log.success("start_run logic dispatched successfully.")
            else
                Log.error("start_run ENGINE CRASH: " .. tostring(err))
            end
        else
            Log.error("G.FUNCS.start_run pointer is missing!")
        end
        
        return -- 必须 return，防止继续执行后续代码
    end

    -- 3. 常规局内指令动画锁
    if G.STATE_COMPLETE == false then 
        Log.warn("Animation in progress, ignoring command: " .. content)
        return 
    end

    if (cmd == "SELECT_BLIND" or cmd == "SKIP_BLIND") and G.STATE == G.STATES.BLIND_SELECT then
        local blind_type = clean_string(params[1])
        local target_btn = (cmd == "SELECT_BLIND") and "select_blind" or "skip_blind"
        
        -- 原版状态校验
        if not blind_type or not G.GAME.round_resets.blind_states[blind_type] then return end
        if G.GAME.round_resets.blind_states[blind_type] ~= 'Select' then 
            Log.warn("Blind state is not Select, it is: " .. tostring(G.GAME.round_resets.blind_states[blind_type]))
            return 
        end
        
        -- 核心搜寻
        local real_btn_node = aggressive_ui_search(target_btn)
        
        if real_btn_node then
            Log.success("Real UI node captured. Triggering physical execution.")
            local success, err = pcall(function() G.FUNCS[target_btn](real_btn_node) end)
            if not success then Log.error("Click failed: " .. tostring(err)) end
        else
            Log.warn("BFS didn't find button (UI probably still animating). Using mock.")
            -- 回归最简单的 Mock：传一个基础的 config 和 UIBox 防崩壳
            -- ref_table 传入 blind_type (即 "Small", "Big")，满足引擎底层的基础校验
            local mock_event = create_mock_e({
                button = target_btn,
                ref_table = blind_type
            })
            
            local success, err = pcall(function() G.FUNCS[target_btn](mock_event) end)
            if success then
                Log.success("Mock blind selection executed.")
            else
                Log.error("Mock crash: " .. tostring(err))
            end
        end
        
    -- 2. 离开商店
    elseif cmd == "NEXT_ROUND" and G.STATE == G.STATES.SHOP then
        local real_btn_node = aggressive_ui_search("toggle_shop")
        if real_btn_node then G.FUNCS.toggle_shop(real_btn_node)
        else G.FUNCS.toggle_shop(create_mock_e({button = "toggle_shop"})) end

    -- 3. 出牌/弃牌
    elseif (cmd == "PLAY" or cmd == "DISCARD") and G.STATE == G.STATES.SELECTING_HAND then
        highlight_cards(params)
        if cmd == "PLAY" and #G.hand.highlighted > 0 then
            G.FUNCS.play_cards_from_highlighted(create_mock_e({button = "play_cards_from_highlighted"}))
        elseif cmd == "DISCARD" and #G.hand.highlighted > 0 then
            G.FUNCS.discard_cards_from_highlighted(create_mock_e({button = "discard_cards_from_highlighted"}))
        end

    -- 4. 提现结算
    elseif cmd == "CASH_OUT" and G.STATE == G.STATES.ROUND_EVAL then
        local real_btn_node = aggressive_ui_search("cash_out")
        if real_btn_node then G.FUNCS.cash_out(real_btn_node)
        else G.FUNCS.cash_out(create_mock_e({button = "cash_out"})) end

    -- 5. 购买商店物品 (彻底修复：分类路由到底层机制)
    elseif (cmd == "BUY_CARD" or cmd == "BUY_VOUCHER" or cmd == "BUY_BOOSTER") and G.STATE == G.STATES.SHOP then
        local idx = tonumber(params[1]) or 1
        local target_card = nil
        local target_func = nil -- 核心：记录该物品对应的真实底层回调函数

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
                Log.success("Executing " .. cmd .. " via " .. target_func .. " on index " .. tostring(idx))

                G.FUNCS[target_func](create_mock_e({ref_table = target_card, button = target_func}))
            else
                Log.warn("Not enough money! Required: " .. tostring(target_card.cost) .. ", Have: " .. tostring(G.GAME.dollars))
            end
        else
            Log.error("Shop item not found for " .. cmd .. " at index " .. tostring(idx))
        end

    -- 6. 使用消耗品
    elseif cmd == "USE_CONSUMABLE" then
        local idx = tonumber(params[1]) or 1
        local target_indices = {}
        for i = 2, #params do table.insert(target_indices, params[i]) end
        
        if #target_indices > 0 then highlight_cards(target_indices) end
        
        if G.consumeables and G.consumeables.cards and G.consumeables.cards[idx] then
            local card = G.consumeables.cards[idx]
            -- 使用消耗品在游戏中同样是点击卡牌触发，这里也加上真实 UI 抓取
            local real_btn_node = aggressive_ui_search("use_card", card)
            if real_btn_node then
                Log.success("Executing USE_CONSUMABLE physically.")
                G.FUNCS.use_card(real_btn_node)
            else
                G.FUNCS.use_card(create_mock_e({ref_table = card, button = "use_card"}))
            end
        else
            Log.error("Consumable not found at index " .. tostring(idx))
        end

    -- 7. 出售卡牌
    elseif string.match(cmd, "^SELL_") then
        local idx = tonumber(params[1]) or 1
        local target_card = nil
        
        if cmd == "SELL_JOKER" and G.jokers and G.jokers.cards then target_card = G.jokers.cards[idx]
        elseif cmd == "SELL_CONSUMABLE" and G.consumeables and G.consumeables.cards then target_card = G.consumeables.cards[idx] end

        if target_card then
            local real_btn_node = aggressive_ui_search("sell_card", target_card)
            if real_btn_node then G.FUNCS.sell_card(real_btn_node)
            else G.FUNCS.sell_card(create_mock_e({ref_table = target_card, button = "sell_card"})) end
        end

    -- 8. 交换卡牌位置 (已修复 align 为 align_cards)
    elseif string.match(cmd, "^SWAP_") then
        local idx1 = tonumber(params[1])
        local idx2 = tonumber(params[2])
        if idx1 and idx2 and idx1 ~= idx2 then
            local card_area = (cmd == "SWAP_JOKER") and G.jokers or G.hand
            if card_area and card_area.cards and card_area.cards[idx1] and card_area.cards[idx2] then
                Log.success("Executing " .. cmd .. " between " .. idx1 .. " and " .. idx2)
                local temp = card_area.cards[idx1]
                card_area.cards[idx1] = card_area.cards[idx2]
                card_area.cards[idx2] = temp
                
                if card_area.set_ranks then card_area:set_ranks() end
                if card_area.align_cards then card_area:align_cards() end
            end
        end
    

    -- 9. 卡包操作：选牌 / 跳过
    elseif (cmd == "SELECT_PACK_CARD" or cmd == "SKIP_PACK") then
        -- 安全校验：只有当屏幕上有卡包时才能执行
        if not G.pack_cards then
            Log.error("Command " .. cmd .. " failed: No active pack on screen.")
            return
        end

        if cmd == "SELECT_PACK_CARD" then
            local idx = tonumber(params[1]) or 1
            if G.pack_cards.cards and G.pack_cards.cards[idx] then
                local target_card = G.pack_cards.cards[idx]
                
                -- 在底层，从卡包选牌同样是调用 use_card 函数
                local real_btn_node = aggressive_ui_search("use_card", target_card)
                if real_btn_node then
                    Log.success("Executing SELECT_PACK_CARD physically on index " .. tostring(idx))
                    G.FUNCS.use_card(real_btn_node)
                else
                    Log.debug("SELECT_PACK_CARD falls back to mock event safely.")
                    G.FUNCS.use_card(create_mock_e({ref_table = target_card, button = "use_card"}))
                end
            else
                Log.error("Pack card not found at index " .. tostring(idx))
            end

        elseif cmd == "SKIP_PACK" then
            local real_btn_node = aggressive_ui_search("skip_booster")
            if real_btn_node then
                Log.success("Executing SKIP_PACK physically.")
                G.FUNCS.skip_booster(real_btn_node)
            else
                Log.debug("SELECT_PACK_CARD falls back to mock event safely.")
                G.FUNCS.skip_booster(create_mock_e({button = "skip_booster"}))
            end
        end

    -- ==========================================
    -- 调试专用：修改金钱 (SET_MONEY)
    -- ==========================================
    elseif cmd == "SET_MONEY" then
        local amount = tonumber(params[1])
        if amount then
            -- 直接修改底层金钱变量
            G.GAME.dollars = amount
            
            -- 可选：强制刷新 UI 显示，让屏幕上的数字立即更新
            if G.HUD and G.HUD.recalculate then
                G.HUD:recalculate()
            end
            
            Log.success("Debug Action: Money set to $" .. amount)
        else
            Log.error("SET_MONEY failed: Invalid amount.")
        end
    
    elseif cmd == "SET_HANDS_LEFT" then
        -- 修改剩余出牌次数
        local amount = tonumber(params[1])
        if amount and G.GAME and G.GAME.current_round then
            G.GAME.current_round.hands_left = amount
            Log.info("[SUCCESS] Debug Action: Hands left set to " .. amount)
        end
        
    elseif cmd == "SET_DISCARDS_LEFT" then
        -- 修改剩余弃牌次数
        local amount = tonumber(params[1])
        if amount and G.GAME and G.GAME.current_round then
            G.GAME.current_round.discards_left = amount
            Log.info("[SUCCESS] Debug Action: Discards left set to " .. amount)
        end
        
    elseif cmd == "SET_HAND_SIZE" then
        -- 修改手牌上限 (这会立刻改变你能抽到的卡牌最大数量)
        local amount = tonumber(params[1])
        if amount and G.hand and G.hand.config then
            -- Balatro 引擎需要计算差值来增减手牌槽位
            local delta = amount - G.hand.config.card_limit
            G.hand:change_size(delta)
            Log.info("[SUCCESS] Debug Action: Hand size set to " .. amount)
        end
    end
end

return ActionExecutor