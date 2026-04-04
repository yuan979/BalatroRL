local socket = require("socket")
local json = require("json") -- 确保你的 mod 环境中有 json 库

local IPCServer = {}
IPCServer.server = nil
IPCServer.client = nil
IPCServer.port = 12345

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
    if not IPCServer.client then
        local client = IPCServer.server:accept()
        if client then
            client:settimeout(0)
            IPCServer.client = client
            IPCServer.Log.info("Python RL Client connected.")
        end
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
            local current_state = state_extractor_func()
            local response_json = json.encode(current_state)
            
            -- 将状态发回 Python，并附带换行符作为结束标记
            local success, send_err = IPCServer.client:send(response_json .. "\n")
            if not success then
                IPCServer.Log.error("Failed to send state: " .. tostring(send_err))
            end
            
        elseif err == "closed" then
            IPCServer.Log.info("Python RL Client disconnected.")
            IPCServer.client = nil
        end
    end
end

return IPCServer