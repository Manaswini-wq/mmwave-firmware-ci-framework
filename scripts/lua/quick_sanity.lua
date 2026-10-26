-- quick_sanity.lua
-- Quick sanity check for mmWave firmware after flash
-- Performs: POST verification, register access, UART comms, GPIO toggle
-- Usage: lua quick_sanity.lua [--port COM3] [--baud 921600]

local serial = require("periphery.serial")

-- Configuration
local config = {
    port     = "COM3",
    baudrate = 921600,
    timeout  = 2.0,
}

for i = 1, #arg, 2 do
    if arg[i] == "--port" then config.port = arg[i+1]
    elseif arg[i] == "--baud" then config.baudrate = tonumber(arg[i+1])
    end
end

-- Test result tracking
local results = {}
local function record(name, passed, detail)
    table.insert(results, { name = name, passed = passed, detail = detail or "" })
    local status = passed and "PASS" or "FAIL"
    print(string.format("  [%s] %s %s", status, name, detail or ""))
end

-- Send command and get response
local function send_cmd(uart, cmd)
    uart:write(cmd .. "\r\n")
    local resp = uart:read(512)
    if resp then return resp:gsub("[\r\n]+$", "") end
    return nil
end

print("=== mmWave Quick Sanity Check ===")
print(string.format("Target: %s @ %d baud\n", config.port, config.baudrate))

-- Open UART connection
local ok, uart = pcall(serial.Serial, config.port, config.baudrate)
if not ok then
    print("[FATAL] Cannot open UART port: " .. tostring(uart))
    os.exit(1)
end
uart:setTimeout(config.timeout)

-- Test 1: Power-On Self-Test verification
print("[TEST] Power-On Self-Test (POST)...")
local post_resp = send_cmd(uart, "POST_STATUS")
if post_resp and post_resp:find("POST_OK") then
    record("POST Verification", true, "Self-test passed")
elseif post_resp then
    record("POST Verification", false, "Unexpected response: " .. post_resp)
else
    record("POST Verification", false, "No response from device")
end

-- Test 2: Basic register accessibility
print("[TEST] Register Accessibility...")
local reg_ok = true
local test_addr = "0x02000000"  -- SYS_CTRL register
local read_resp = send_cmd(uart, "RR " .. test_addr)
if read_resp and read_resp:match("0x%x+") then
    record("Register Read", true, string.format("SYS_CTRL = %s", read_resp:match("0x%x+")))
else
    record("Register Read", false, "Cannot read SYS_CTRL register")
    reg_ok = false
end

-- Write and read-back test on scratch register
local scratch_addr = "0x020000FC"
local test_val = "0xDEADBEEF"
send_cmd(uart, string.format("WR %s %s", scratch_addr, test_val))
local readback = send_cmd(uart, "RR " .. scratch_addr)
if readback and readback:upper():find("DEADBEEF") then
    record("Register Write/Readback", true, "Scratch register verified")
else
    record("Register Write/Readback", false, "Readback mismatch")
end

-- Test 3: UART communication test (echo)
print("[TEST] UART Communication...")
local echo_payload = "SANITY_CHECK_12345"
local echo_resp = send_cmd(uart, "ECHO " .. echo_payload)
if echo_resp and echo_resp:find(echo_payload) then
    record("UART Echo", true, "Round-trip communication OK")
else
    record("UART Echo", false, "Echo payload mismatch")
end

-- Test 4: LED/GPIO toggle test
print("[TEST] GPIO/LED Toggle...")
local gpio_resp = send_cmd(uart, "GPIO_TOGGLE 0")  -- Toggle GPIO 0 (typically LED)
if gpio_resp and (gpio_resp:find("OK") or gpio_resp:find("TOGGLED")) then
    record("GPIO Toggle", true, "GPIO 0 toggled successfully")
else
    record("GPIO Toggle", false, "GPIO toggle failed or no response")
end

-- Summary
print("\n" .. string.rep("=", 50))
local total = #results
local passed = 0
for _, r in ipairs(results) do
    if r.passed then passed = passed + 1 end
end
local failed = total - passed

print(string.format("RESULTS: %d/%d passed, %d failed", passed, total, failed))

if failed == 0 then
    print("OVERALL: PASS - All sanity checks passed")
else
    print("OVERALL: FAIL - Sanity check failures detected")
end
print(string.rep("=", 50))

uart:close()
os.exit(failed == 0 and 0 or 1)
