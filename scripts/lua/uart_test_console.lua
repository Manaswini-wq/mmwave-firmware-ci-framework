-- uart_test_console.lua
-- Interactive debug console for firmware testing via UART
-- Supports register read/write, memory dump, test execution
-- Usage: lua uart_test_console.lua [--port COM3] [--baud 921600]

local serial = require("periphery.serial")

-- Configuration defaults
local config = {
    port     = "COM3",
    baudrate = 921600,
    timeout  = 2.0,
    retries  = 3,
    prompt   = "mmwave> ",
}

-- Parse command-line arguments
for i = 1, #arg, 2 do
    if arg[i] == "--port" then config.port = arg[i+1]
    elseif arg[i] == "--baud" then config.baudrate = tonumber(arg[i+1])
    elseif arg[i] == "--timeout" then config.timeout = tonumber(arg[i+1])
    end
end

-- Command history
local history = {}
local MAX_HISTORY = 50

-- UART connection handle
local uart = nil

-- Connect to UART port with auto-reconnect
local function connect()
    if uart then pcall(function() uart:close() end) end
    print(string.format("[INFO] Connecting to %s @ %d baud...", config.port, config.baudrate))
    local ok, err = pcall(function()
        uart = serial.Serial(config.port, config.baudrate)
        uart:setTimeout(config.timeout)
    end)
    if not ok then
        print("[ERROR] Failed to open UART: " .. tostring(err))
        return false
    end
    print("[INFO] Connected successfully.")
    return true
end

-- Send command and read response with retry
local function send_command(cmd)
    for attempt = 1, config.retries do
        if not uart then
            if not connect() then return nil, "Connection failed" end
        end
        local ok, err = pcall(function()
            uart:write(cmd .. "\r\n")
        end)
        if not ok then
            print(string.format("[WARN] Send failed (attempt %d/%d): %s", attempt, config.retries, err))
            connect()
        else
            -- Read response lines until prompt or timeout
            local response = {}
            while true do
                local line = uart:read(256)
                if not line or #line == 0 then break end
                line = line:gsub("[\r\n]+$", "")
                if line ~= cmd then  -- skip echo
                    table.insert(response, line)
                end
            end
            return table.concat(response, "\n"), nil
        end
    end
    return nil, "Max retries exceeded"
end

-- Command handlers
local commands = {}

function commands.read_reg(addr)
    if not addr then print("Usage: read_reg <hex_addr>"); return end
    local resp, err = send_command(string.format("RR 0x%s", addr))
    if resp then print(string.format("  [0x%s] = %s", addr, resp))
    else print("[ERROR] " .. (err or "unknown")) end
end

function commands.write_reg(addr, value)
    if not addr or not value then print("Usage: write_reg <hex_addr> <hex_value>"); return end
    local resp, err = send_command(string.format("WR 0x%s 0x%s", addr, value))
    if resp then print(string.format("  [0x%s] <- 0x%s  OK", addr, value))
    else print("[ERROR] " .. (err or "unknown")) end
end

function commands.mem_dump(addr, length)
    addr = addr or "00000000"
    length = length or "64"
    local resp, err = send_command(string.format("MD 0x%s %s", addr, length))
    if resp then print(resp)
    else print("[ERROR] " .. (err or "unknown")) end
end

function commands.run_test(test_id)
    if not test_id then print("Usage: run_test <test_id>"); return end
    print(string.format("[INFO] Executing on-target test: %s", test_id))
    local resp, err = send_command(string.format("TEST %s", test_id))
    if resp then
        print(resp)
        if resp:find("PASS") then print("[RESULT] PASS")
        elseif resp:find("FAIL") then print("[RESULT] FAIL")
        else print("[RESULT] UNKNOWN") end
    else
        print("[ERROR] " .. (err or "unknown"))
    end
end

function commands.status()
    local resp, err = send_command("STATUS")
    if resp then print(resp)
    else print("[ERROR] " .. (err or "unknown")) end
end

function commands.help()
    print("Available commands:")
    print("  read_reg <addr>           - Read register at hex address")
    print("  write_reg <addr> <value>  - Write value to register")
    print("  mem_dump <addr> [length]  - Dump memory region")
    print("  run_test <test_id>        - Execute on-target test")
    print("  status                    - Query firmware status")
    print("  history                   - Show command history")
    print("  reconnect                 - Reconnect UART")
    print("  quit                      - Exit console")
end

function commands.history_cmd()
    for i, cmd in ipairs(history) do
        print(string.format("  %3d  %s", i, cmd))
    end
end

-- Main REPL loop
print("=== mmWave Firmware UART Test Console ===")
print("Type 'help' for available commands.\n")

if not connect() then
    print("[WARN] Starting in offline mode. Use 'reconnect' when device is available.")
end

while true do
    io.write(config.prompt)
    local input = io.read("*l")
    if not input then break end

    input = input:match("^%s*(.-)%s*$")  -- trim whitespace
    if #input == 0 then goto continue end

    -- Add to history
    table.insert(history, input)
    if #history > MAX_HISTORY then table.remove(history, 1) end

    -- Parse command and arguments
    local parts = {}
    for word in input:gmatch("%S+") do table.insert(parts, word) end
    local cmd = parts[1]:lower()

    if cmd == "quit" or cmd == "exit" then
        print("Goodbye.")
        break
    elseif cmd == "read_reg" then commands.read_reg(parts[2])
    elseif cmd == "write_reg" then commands.write_reg(parts[2], parts[3])
    elseif cmd == "mem_dump" then commands.mem_dump(parts[2], parts[3])
    elseif cmd == "run_test" then commands.run_test(parts[2])
    elseif cmd == "status" then commands.status()
    elseif cmd == "help" then commands.help()
    elseif cmd == "history" then commands.history_cmd()
    elseif cmd == "reconnect" then connect()
    else
        print(string.format("[ERROR] Unknown command: '%s'. Type 'help' for usage.", cmd))
    end

    ::continue::
end

-- Cleanup
if uart then pcall(function() uart:close() end) end
