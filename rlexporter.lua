--- STEAMODDED HEADER
--- MOD_NAME: RL State Exporter
--- MOD_ID: rlexporter
--- MOD_AUTHOR: [YUAN_Dev]
--- MOD_DESCRIPTION: Modular Exporter for Reinforcement Learning.
--rlexporter/
-- ├── rlexporter.lua     (主调度文件：负责挂载钩子和定时任务)
-- ├── json_encoder.lua   (功能模块：专门负责 JSON 序列化)
-- ├── card_extractor.lua (功能模块：专门负责卡牌属性解析)
-- └── state_extractor.lua(功能模块：负责遍历游戏状态树)
-- =========================================
-- 1. 模块动态加载器 (绕过 require 的路径限制)
-- =========================================
local mod_path = "Mods/rlexporter/"

local function load_module(filename)
    -- 使用 LÖVE 引擎底层的方法加载文件，确保路径绝对准确
    local chunk, err = love.filesystem.load(mod_path .. filename)
    if chunk then
        return chunk()
    else
        print("[RL_EXPORTER] ERROR: Could not load " .. filename .. " - " .. tostring(err))
        return nil
    end
end

-- 加载所有子模块
local JSONEncoder = load_module("json_encoder.lua")
local CardExtractor = load_module("card_extractor.lua")
local StateExtractor = load_module("state_extractor.lua")
local RunInfoExtractor = load_module("run_info_extractor.lua")

-- 防崩溃安全检查
if not JSONEncoder or not CardExtractor or not StateExtractor then
    print("[RL_EXPORTER] INIT FAILED! Please check if all 4 files are in the rlexporter folder.")
    return
end

-- =========================================
-- 2. 导出任务分发
-- =========================================
local function run_export_task()
-- 安全检查：确保游戏在运行中
    if not G or not G.STAGE or G.STAGE ~= G.STAGES.RUN then return end

    -- 任务 A: 导出高频变动的环境状态 -> rl_observation.json
    local state = StateExtractor.get_game_state(CardExtractor)
    if state then
        love.filesystem.write("rl_observation.json", JSONEncoder.encode(state))
    end

    -- 任务 B: 导出低频变动的比赛与牌库信息 -> rl_run_info.json
    local run_info = {
        poker_hands = RunInfoExtractor.get_poker_hands(),
        full_deck = RunInfoExtractor.get_full_deck(CardExtractor)
    }
    love.filesystem.write("rl_run_info.json", JSONEncoder.encode(run_info))
end

-- =========================================
-- 3. 游戏引擎挂载钩子
-- =========================================
local last_export_time = 0
local export_interval = 0.5
local has_printed_init = false

local original_love_update = love.update
function love.update(dt)
    if original_love_update then original_love_update(dt) end
    
    -- 启动成功提示
    if not has_printed_init and G and G.STAGE then
        print("========================================")
        print("[RL_EXPORTER] Modular Engine Hooked Successfully!")
        print("========================================")
        has_printed_init = true
    end

    -- 计时器
    last_export_time = last_export_time + dt
    if last_export_time >= export_interval then
        run_export_task()
        last_export_time = 0
    end
end