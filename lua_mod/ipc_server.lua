local socket = require("socket")
local json = require("json") -- 确保你的 mod 环境中有 json 库

local IPCServer = {}
IPCServer.server = nil
IPCServer.client = nil
IPCServer.port = 12345

local function close_client_safely(client)
    if client then
        pcall(function() client:close() end)
    end
end

function IPCServer.init(logger_instance)
    IPCServer.Log = logger_instance or { info = print, error = print, debug = print }
    
    -- 创建 TCP Server，绑定本地回环地址
    IPCServer.server = socket.bind("127.0.0.1", IPCServer.port)
    if IPCServer.server then
        IPCServer.server:settimeout(0) -- 设置为非阻塞模式
        IPCServer.Log.info("TCP Server started on port " .. tostring(IPCServer.port))
    else
        IPCServer.Log.error("Failed to start TCP Server on port " .. tostring(IPCServer.port))
    end
end

function IPCServer.poll_and_respond(state_extractor_func, action_executor_func)
    if not IPCServer.server then return end

    -- 1. 尝试接受新的客户端连接
    -- 允许新连接覆盖旧连接，避免旧 socket 假死导致永远无法恢复
    local pending_client = IPCServer.server:accept()
    if pending_client then
        pending_client:settimeout(0)
        if IPCServer.client then
            IPCServer.Log.info("Replacing stale Python RL Client connection.")
            close_client_safely(IPCServer.client)
        else
            IPCServer.Log.info("Python RL Client connected.")
        end
        IPCServer.client = pending_client
    end

    -- 2. 如果有客户端，处理通信
    if IPCServer.client then
        -- 读取来自 Python 的单行指令（以 \n 结尾）
        local request, err = IPCServer.client:receive("*l")
        
        if request then
            IPCServer.Log.debug("Received action: " .. request)
            
            -- 执行动作
            action_executor_func(request)
            
            -- 获取最新状态并序列化为单行 JSON
            local current_state = state_extractor_func(request)
            local response_json = json.encode(current_state)
            
            -- 将状态发回 Python，并附带换行符作为结束标记
            local success, send_err = IPCServer.client:send(response_json .. "\n")
            if not success then
                IPCServer.Log.error("Failed to send state: " .. tostring(send_err))
                close_client_safely(IPCServer.client)
                IPCServer.client = nil
            end
            
        elseif err == "closed" then
            IPCServer.Log.info("Python RL Client disconnected.")
            close_client_safely(IPCServer.client)
            IPCServer.client = nil
        elseif err and err ~= "timeout" then
            IPCServer.Log.warn("Socket receive error: " .. tostring(err))
            close_client_safely(IPCServer.client)
            IPCServer.client = nil
        end
    end
end

return IPCServer