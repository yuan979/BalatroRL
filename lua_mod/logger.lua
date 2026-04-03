local Logger = {}

-- 日志开关：在正式训练 RL 模型时，可以将其设为 false 来关闭所有 DEBUG 级别的日志，提升性能
Logger.DEBUG_MODE = true 
Logger.PREFIX = "[RL_MOD]"

function Logger.info(msg)
    print(Logger.PREFIX .. " [INFO] " .. tostring(msg))
end

function Logger.warn(msg)
    print(Logger.PREFIX .. " [WARN] " .. tostring(msg))
end

function Logger.error(msg)
    print(Logger.PREFIX .. " [ERROR] " .. tostring(msg))
end

function Logger.success(msg)
    print(Logger.PREFIX .. " [SUCCESS] " .. tostring(msg))
end

function Logger.debug(msg)
    if Logger.DEBUG_MODE then
        print(Logger.PREFIX .. " [DEBUG] " .. tostring(msg))
    end
end

return Logger