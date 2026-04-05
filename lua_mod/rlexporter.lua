--- STEAMODDED HEADER
--- MOD_NAME: RL State Exporter
--- MOD_ID: rlexporter
--- MOD_AUTHOR: [YUAN_Dev]
--- MOD_DESCRIPTION: Modular Exporter for Reinforcement Learning (TCP Socket Version).

-- =========================================
-- 1. 模块动态加载器
-- =========================================
local mod_path = "Mods/rlexporter/"

local function load_module(filename)
    local chunk, err = love.filesystem.load(mod_path .. filename)
    if chunk then
        return chunk()
    else
        print("[RL_EXPORTER] ERROR: Could not load " .. filename .. " - " .. tostring(err))
        return nil
    end
end

-- 加载日志模块
local Logger = load_module("logger.lua")
if not Logger then return end

-- 加载所有子模块
local JSONEncoder = load_module("json_encoder.lua")
local CardExtractor = load_module("card_extractor.lua")
local StateExtractor = load_module("state_extractor.lua")
local RunInfoExtractor = load_module("run_info_extractor.lua")
local ActionExecutor = load_module("action_executor.lua")
local IPCServer = load_module("ipc_server.lua")

-- 防崩溃安全检查
if not JSONEncoder or not CardExtractor or not StateExtractor or not IPCServer then
    Logger.error("[RL_EXPORTER] INIT FAILED! Please check if all modules are present.")
    return
end

-- 模块初始化与依赖注入
ActionExecutor.init(Logger)
IPCServer.init(Logger)

-- =========================================
-- 2. 游戏引擎挂载钩子 (Socket 高频轮询)
-- =========================================
local has_printed_init = false

local original_love_update = love.update
function love.update(dt)
    if original_love_update then original_love_update(dt) end
    
    -- 启动成功提示
    if not has_printed_init and G and G.STAGE then
        Logger.info("========================================")
        Logger.info("[RL_EXPORTER] TCP Socket Engine Hooked Successfully!")
        Logger.info("========================================")
        has_printed_init = true
    end

    -- 【核心修复】：移除 G.STAGE == G.STAGES.RUN 的限制
    -- 只要引擎核心 (G) 存在，允许在所有阶段（含主菜单）进行网络轮询
    if G then
        -- 核心：每帧调用 Socket 的无阻塞轮询
        IPCServer.poll_and_respond(
            -- 闭包 1: 状态获取器 (根据指令决定返回的内容)
            function(cmd)
                -- 如果 Python 端需要静态牌库信息
                if cmd == "GET_RUN_INFO" then
                    return {
                        poker_hands = RunInfoExtractor.get_poker_hands(),
                        full_deck = RunInfoExtractor.get_full_deck(CardExtractor)
                    }
                end
                
                -- 默认返回高频变动的环境状态
                local state = StateExtractor.get_game_state(CardExtractor)
                return state or {}
            end,
            
            -- 闭包 2: 动作执行器
            function(cmd)
                -- 过滤掉纯粹的心跳/状态获取指令
                if cmd ~= "GET_STATE" and cmd ~= "GET_RUN_INFO" then
                    ActionExecutor.execute_command(cmd)
                end
            end
        )
    end
end