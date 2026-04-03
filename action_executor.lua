local ActionExecutor = {}

local Log = { info = print, warn = print, error = print, success = print, debug = print }

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
-- 核心搜寻引擎：只匹配 button 名称
-- ==========================================
local function aggressive_ui_search(target_button)
    Log.debug("Starting BFS search for button: " .. tostring(target_button))
    local visited = {}
    local queue = {}
    
    for k, v in pairs(G) do
        if type(v) == "table" and type(k) == "string" then
            if k:match("UI") or k:match("ROOM") or k:match("HUD") or k:match("overlay") or k:match("blind") or k:match("menu") or k == "jiggle" then
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
            
            -- 核心修复：因为原版游戏的 config.blind 是 nil，所以我们只需校验 config.button！
            if curr.config and type(curr.config) == "table" and curr.config.button == target_button then
                Log.debug("Match found after visiting " .. tostring(nodes_visited) .. " nodes.")
                return curr
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
function ActionExecutor.poll_and_execute()
    local info = love.filesystem.getInfo("rl_action.txt")
    if not info then return end

    local content, _ = love.filesystem.read("rl_action.txt")
    love.filesystem.remove("rl_action.txt")
    if not content or content == "" then return end

    if G.STATE_COMPLETE == false then 
        Log.warn("Animation in progress, ignoring command: " .. content)
        return 
    end

    local args = {}
    for word in string.gmatch(content, "%S+") do table.insert(args, word) end
    if #args == 0 then return end
    
    local cmd = args[1]:upper()
    local params = {unpack(args, 2)}

    Log.info("Attempting to execute: " .. content)

    -- 1. 盲注操作
    if (cmd == "SELECT_BLIND" or cmd == "SKIP_BLIND") and G.STATE == G.STATES.BLIND_SELECT then
        local blind_type = clean_string(params[1])
        local target_btn = (cmd == "SELECT_BLIND") and "select_blind" or "skip_blind"
        
        -- 安全校验：防止你的 RL 在不可选状态下发指令
        if not blind_type or not G.GAME.round_resets.blind_states[blind_type] then
            Log.error("Invalid blind type: " .. tostring(blind_type))
            return
        end
        if G.GAME.round_resets.blind_states[blind_type] ~= 'Select' then
            Log.error("Blind [" .. blind_type .. "] is not in 'Select' state. Ignored.")
            return
        end
        
        -- 搜索真实按钮
        local real_btn_node = aggressive_ui_search(target_btn)

        if real_btn_node then
            Log.success("Real UI node captured. Triggering physical execution.")
            -- 将真实按钮扔给底层，底层会根据真实树状结构去找标签奖励，完美执行！
            G.FUNCS[target_btn](real_btn_node)
        else
            Log.error("Target button not found in memory.")
        end

    -- 2. 离开商店
    elseif cmd == "NEXT_ROUND" and G.STATE == G.STATES.SHOP then
        local real_btn_node = aggressive_ui_search("toggle_shop")
        if real_btn_node then
            G.FUNCS.toggle_shop(real_btn_node)
        else
            G.FUNCS.toggle_shop(create_mock_e({button = "toggle_shop"}))
        end

    -- 3. 出牌/弃牌
    elseif (cmd == "PLAY" or cmd == "DISCARD") and G.STATE == G.STATES.SELECTING_HAND then
        highlight_cards(params)
        if cmd == "PLAY" and #G.hand.highlighted > 0 then
            G.FUNCS.play_cards_from_highlighted(create_mock_e({button = "play_cards_from_highlighted"}))
        elseif cmd == "DISCARD" and #G.hand.highlighted > 0 then
            G.FUNCS.discard_cards_from_highlighted(create_mock_e({button = "discard_cards_from_highlighted"}))
        end
    end
end

return ActionExecutor