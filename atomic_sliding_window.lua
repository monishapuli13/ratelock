local current_key = KEYS[1]
local prev_key = KEYS[2]

local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])
local now = tonumber(ARGV[4])

local window_start = math.floor(now / window) * window
local elapsed = now - window_start
local fraction = elapsed / window
local prev_weight = 1 - fraction

local current = tonumber(redis.call("GET", current_key) or "0")
local prev = tonumber(redis.call("GET", prev_key) or "0")

local weighted = math.floor(prev * prev_weight) + current

-- Reject if limit exceeded
if (weighted + cost) > limit then
    return {0, weighted, prev_weight, current, prev}
end

-- Allow request
local new_current = redis.call("INCRBY", current_key, cost)
redis.call("EXPIRE", current_key, window * 2)
redis.call("EXPIRE", prev_key, window * 2)

local new_weighted = math.floor(prev * prev_weight) + new_current

return {1, new_weighted, prev_weight, new_current, prev}