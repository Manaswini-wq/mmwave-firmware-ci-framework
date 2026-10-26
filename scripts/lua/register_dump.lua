-- register_dump.lua
-- Register dump utility for mmWave radar subsystem
-- Reads and displays formatted register values, highlights non-default values
-- Usage: lua register_dump.lua [--port COM3] [--output dump.txt]

local serial = require("periphery.serial")

-- Configuration
local config = {
    port     = "COM3",
    baudrate = 921600,
    output   = nil,
}

for i = 1, #arg, 2 do
    if arg[i] == "--port" then config.port = arg[i+1]
    elseif arg[i] == "--baud" then config.baudrate = tonumber(arg[i+1])
    elseif arg[i] == "--output" then config.output = arg[i+1]
    end
end

-- Register map for AWR2944 radar subsystem
-- Format: { name, address, default_value, description }
local register_map = {
    -- System Control
    { name = "SYS_CTRL",       addr = 0x02000000, default = 0x00000001, desc = "System control register" },
    { name = "SYS_STATUS",     addr = 0x02000004, default = 0x00000000, desc = "System status register" },
    { name = "CLK_CTRL",       addr = 0x02000008, default = 0x00000003, desc = "Clock control" },
    { name = "RST_CTRL",       addr = 0x0200000C, default = 0x00000000, desc = "Reset control" },
    -- Chirp Configuration
    { name = "CHIRP_START",    addr = 0x02010000, default = 0x00000000, desc = "Chirp start frequency" },
    { name = "CHIRP_SLOPE",    addr = 0x02010004, default = 0x00000000, desc = "Chirp frequency slope" },
    { name = "CHIRP_DURATION", addr = 0x02010008, default = 0x00000064, desc = "Chirp duration (us)" },
    { name = "CHIRP_COUNT",    addr = 0x0201000C, default = 0x00000080, desc = "Number of chirps per frame" },
    -- ADC Configuration
    { name = "ADC_CTRL",       addr = 0x02020000, default = 0x00000002, desc = "ADC control register" },
    { name = "ADC_RATE",       addr = 0x02020004, default = 0x00002710, desc = "ADC sample rate" },
    { name = "ADC_BITS",       addr = 0x02020008, default = 0x00000010, desc = "ADC bit resolution" },
    { name = "ADC_CHANNELS",   addr = 0x0202000C, default = 0x0000000F, desc = "Active ADC channels bitmask" },
    -- Frame Configuration
    { name = "FRAME_CTRL",     addr = 0x02030000, default = 0x00000000, desc = "Frame control" },
    { name = "FRAME_PERIOD",   addr = 0x02030004, default = 0x00004E20, desc = "Frame period (us)" },
    { name = "FRAME_COUNT",    addr = 0x02030008, default = 0x00000000, desc = "Frame counter (read-only)" },
    -- Interrupt Status
    { name = "IRQ_STATUS",     addr = 0x02040000, default = 0x00000000, desc = "Interrupt status" },
    { name = "IRQ_ENABLE",     addr = 0x02040004, default = 0x00000000, desc = "Interrupt enable mask" },
    { name = "IRQ_CLEAR",      addr = 0x02040008, default = 0x00000000, desc = "Interrupt clear register" },
}

-- Read register via UART command
local function read_register(uart_handle, addr)
    local cmd = string.format("RR 0x%08X\r\n", addr)
    uart_handle:write(cmd)
    local resp = uart_handle:read(64)
    if resp then
        local val = resp:match("0x(%x+)")
        if val then return tonumber(val, 16) end
    end
    return nil
end

-- Format register value with non-default highlighting
local function format_register(reg, value)
    local marker = ""
    if value ~= reg.default then
        marker = " <-- MODIFIED"
    end
    return string.format("  %-18s [0x%08X] = 0x%08X  (default: 0x%08X)%s  -- %s",
        reg.name, reg.addr, value, reg.default, marker, reg.desc)
end

-- Main dump routine
print("=== mmWave Radar Register Dump ===")
print(string.format("Port: %s  Baud: %d\n", config.port, config.baudrate))

local uart = serial.Serial(config.port, config.baudrate)
uart:setTimeout(1.0)

local output_lines = {}
local modified_count = 0

table.insert(output_lines, string.format("Register Dump - %s", os.date("%Y-%m-%d %H:%M:%S")))
table.insert(output_lines, string.rep("=", 90))

for _, reg in ipairs(register_map) do
    local value = read_register(uart, reg.addr)
    if value then
        local line = format_register(reg, value)
        table.insert(output_lines, line)
        if value ~= reg.default then modified_count = modified_count + 1 end
    else
        local line = string.format("  %-18s [0x%08X] = READ ERROR", reg.name, reg.addr)
        table.insert(output_lines, line)
    end
end

table.insert(output_lines, string.rep("=", 90))
table.insert(output_lines, string.format("Total registers: %d  |  Modified from default: %d", #register_map, modified_count))

-- Print to stdout
for _, line in ipairs(output_lines) do
    print(line)
end

-- Save to file if requested
if config.output then
    local f = io.open(config.output, "w")
    if f then
        for _, line in ipairs(output_lines) do
            f:write(line .. "\n")
        end
        f:close()
        print(string.format("\n[INFO] Dump saved to %s", config.output))
    else
        print(string.format("\n[ERROR] Cannot write to %s", config.output))
    end
end

uart:close()
