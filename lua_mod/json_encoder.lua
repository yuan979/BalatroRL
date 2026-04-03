local JSONEncoder = {}

function JSONEncoder.encode(val)
    local t = type(val)
    if t == "number" or t == "boolean" then 
        return tostring(val)
    elseif t == "string" then 
        return '"' .. val:gsub('"', '\\"') .. '"'
    elseif t == "table" then
        -- 智能判断是字典还是数组
        local is_array = true
        for k, _ in pairs(val) do
            if type(k) ~= "number" then
                is_array = false
                break
            end
        end
        local parts = {}
        if is_array then
            for _, v in ipairs(val) do table.insert(parts, JSONEncoder.encode(v)) end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            for k, v in pairs(val) do table.insert(parts, '"' .. tostring(k) .. '":' .. JSONEncoder.encode(v)) end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return '"null"'
end

return JSONEncoder