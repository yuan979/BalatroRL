local ActionExecutor = {}

-- ==========================================
-- 辅助函数：深度清洗字符串
-- ==========================================
local function clean_string(str)
    if not str then return nil end
    str = str:gsub("%s+", "")
    local low = str:lower()
    if low == "small" then return "Small" end
    if low == "big" then return "Big" end
    if low == "boss" then return "Boss" end
    return str
end

-- ==========================================
-- 辅助函数：创建用于出牌的轻量 Mock
-- ==========================================
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
-- 终极武器：内存 UI 树广度优先搜索 (BFS)
-- ==========================================
local function find_real_ui_node(root_node, target_button, target_blind_type, target_blind_id)
    if type(root_node) ~= "table" then return nil end
    
    local visited = {}
    local queue = {root_node}
    local head = 1
    
    while head <= #queue do
        local curr = queue[head]
        head = head + 1
        
        if type(curr) == "table" and not visited[curr] then
            visited[curr] = true
            
            -- 检查当前节点是否是目标按钮
            if curr.config and type(curr.config) == "table" and curr.config.button == target_button then
                -- 如果是盲注按钮，额外校验它的盲注类型
                if target_blind_type or target_blind_id then
                    if curr.config.blind == target_blind_type or curr.config.blind == target_blind_id then
                        return curr
                    end
                else
                    return curr
                end
            end
            
            -- 将所有可能的子节点推入队列
            if type(curr.children) == "table" then
                for _, child in pairs(curr.children) do queue[#queue + 1] = child end
            end
            if type(curr.nodes) == "table" then
                for _, child in ipairs(curr.nodes) do queue[#queue + 1] = child end
            end
            if type(curr.UIElement) == "table" then
                queue[#queue + 1] = curr.UIElement
            end
        end
    end
    return nil
end

-- ==========================================
-- 辅助函数：高亮手牌
-- ==========================================
local function highlight_cards(indices)
    if not G.hand or not G.hand.cards then return end
    if G.hand.unhighlight_all then
        G.hand:unhighlight_all()
    else
        for i = #G.hand.highlighted, 1, -1 do
            G.hand:remove_from_highlighted(G.hand.highlighted[i])
        end
    end
    for _, idx_str in ipairs(indices) do
        local idx = tonumber(idx_str)
        if idx and G.hand.cards[idx] then
            G.hand:add_to_highlighted(G.hand.cards[idx], true)
        end
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
        print("[RL_ACTION]  正在播放动画，指令忽略: " .. content)
        return 
    end

    local args = {}
    for word in string.gmatch(content, "%S+") do table.insert(args, word) end
    if #args == 0 then return end
    
    local cmd = args[1]:upper()
    local params = {unpack(args, 2)}

    print("[RL_ACTION] 尝试执行指令: " .. content)

    -- 1. 盲注操作 (完美解决软锁死)
    if (cmd == "SELECT_BLIND" or cmd == "SKIP_BLIND") and G.STATE == G.STATES.BLIND_SELECT then
        local blind_type = clean_string(params[1])
        local blind_id = G.GAME.round_resets.blind_choices[blind_type]
        local target_btn = (cmd == "SELECT_BLIND") and "select_blind" or "skip_blind"
        
        -- 核心修复：直接从游戏的盲注专属 UI 根节点进行搜索！
        local roots_to_search = {G.blind_select, G.OVERLAY_MENU, G.UI_ROOT}
        local real_btn_node = nil
        
        for _, root in ipairs(roots_to_search) do
            if root then
                real_btn_node = find_real_ui_node(root, target_btn, blind_type, blind_id)
                if real_btn_node then break end
            end
        end

        if real_btn_node then
            print("[RL_ACTION]  成功抓取真实按钮内存节点，物理触发！")
            -- 传入拥有所有真实物理属性和动画状态的 UIBox，完美绕开所有崩溃
            G.FUNCS[target_btn]({UIBox = real_btn_node, config = real_btn_node.config})
        else
            print("[RL_ACTION]  失败：在内存中没有找到该盲注按钮，可能界面尚未完全加载。")
        end

    -- 2. 离开商店
    elseif cmd == "NEXT_ROUND" and G.STATE == G.STATES.SHOP then
        local real_btn_node = find_real_ui_node(G.shop, "toggle_shop")
        if real_btn_node then
            print("[RL_ACTION]  找到真实下一回合按钮，物理触发！")
            G.FUNCS.toggle_shop({UIBox = real_btn_node, config = real_btn_node.config})
        else
            -- 备用强制退出
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