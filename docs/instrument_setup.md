# Lab Instrument Setup Guide

This guide covers the setup and configuration of lab instruments used for RF validation testing with the mmWave Firmware CI Framework.

## Table of Contents

1. [VISA Configuration](#visa-configuration)
2. [Spectrum Analyzer Setup](#spectrum-analyzer-setup)
3. [Signal Generator Setup](#signal-generator-setup)
4. [Logic Analyzer Setup](#logic-analyzer-setup)
5. [Verifying Connections](#verifying-connections)

---

## VISA Configuration

### Installing VISA Drivers

The framework uses PyVISA to communicate with SCPI instruments. You need a VISA backend:

**Option 1: NI-VISA (Recommended)**
- Download from [ni.com/visa](https://www.ni.com/visa)
- Install NI-VISA runtime (not full NI package unless needed)
- Verify: `python -c "import pyvisa; rm = pyvisa.ResourceManager(); print(rm.list_resources())"`

**Option 2: Keysight IO Libraries Suite**
- Download from Keysight website
- Includes VISA and instrument discovery tools

### Network Configuration

For TCP/IP instruments:
1. Connect instrument and host PC to the same network or VLAN
2. Assign static IPs to instruments for reliability
3. Verify connectivity: `ping <instrument_ip>`
4. Default SCPI port: 5025 (raw socket) or use VXI-11

### VISA Resource Strings

| Instrument | Format | Example |
|------------|--------|---------|
| TCP/IP (VXI-11) | `TCPIP0::<ip>::inst0::INSTR` | `TCPIP0::192.168.1.100::inst0::INSTR` |
| TCP/IP (Socket) | `TCPIP0::<ip>::<port>::SOCKET` | `TCPIP0::192.168.1.100::5025::SOCKET` |
| USB | `USB0::<vid>::<pid>::<serial>::INSTR` | `USB0::0x2A8D::0x1A0B::MY12345::INSTR` |
| GPIB | `GPIB0::<addr>::INSTR` | `GPIB0::18::INSTR` |

---

## Spectrum Analyzer Setup

### Keysight N9010A EXA

**Physical Setup:**
1. Connect RF output of EVM to SA input via calibrated cable and attenuator
2. Use appropriate attenuator (10-20 dB) to protect SA input
3. Cable loss should be characterized and recorded

**Configuration File:**
Edit `config/instruments/keysight_n9010a.yaml`:
```yaml
connection:
  visa_resource: "TCPIP0::192.168.1.100::inst0::INSTR"
defaults:
  center_freq_ghz: 77.0
  span_mhz: 5000
  rbw_khz: 100
  ref_level_dbm: 10
```

**Calibration Notes:**
- Perform a full SA calibration before qualification tests
- Record cable loss at frequency of interest (77 GHz typical)
- Store calibration data with test evidence

---

## Signal Generator Setup

### Rohde & Schwarz SMW200A

**Physical Setup:**
1. Connect signal generator output to EVM RX input
2. Use calibrated cable with known loss
3. Verify output level with power meter if precision is required

**Configuration File:**
Edit `config/instruments/rohde_smw200a.yaml`:
```yaml
connection:
  visa_resource: "TCPIP0::192.168.1.101::inst0::INSTR"
defaults:
  frequency_ghz: 77.0
  power_dbm: -30.0
```

**Notes:**
- For RX sensitivity tests, ensure the signal generator can reach -120 dBm or lower
- Use external attenuators for very low power levels
- Verify modulation accuracy before running chirp simulation tests

---

## Logic Analyzer Setup

### Saleae Logic Pro 16

**Physical Setup:**
1. Connect digital probes to EVM test points (SPI, UART, GPIO)
2. Connect ground probe to EVM ground
3. Ensure probe wires are short to minimize signal integrity issues

**Software Setup:**
1. Install Saleae Logic 2 software
2. Enable the Automation API in Logic 2 preferences (Settings > Automation)
3. Default automation server runs on `localhost:10430`

**Configuration File:**
Edit `config/instruments/saleae_logic_pro.yaml`:
```yaml
connection:
  host: "127.0.0.1"
  port: 10430
defaults:
  sample_rate_mhz: 100
  digital_channels: [0, 1, 2, 3]
```

**Channel Assignments (example):**

| Channel | Signal | Purpose |
|---------|--------|---------|
| 0 | FRAME_START | Frame trigger pulse |
| 1 | SPI_CLK | SPI clock |
| 2 | SPI_MOSI | SPI data out |
| 3 | SPI_MISO | SPI data in |
| 4 | UART_TX | UART transmit |
| 5 | UART_RX | UART receive |
| 6 | GPIO_0 | General purpose / LED |
| 7 | CHIRP_ACTIVE | Chirp active indicator |

---

## Verifying Connections

Run the instrument verification script to confirm all instruments are reachable:

```bash
python -m framework.instruments.verify_connections \
    --config config/instruments/keysight_n9010a.yaml \
    --config config/instruments/rohde_smw200a.yaml
```

Or verify manually in Python:

```python
import pyvisa

rm = pyvisa.ResourceManager()
sa = rm.open_resource("TCPIP0::192.168.1.100::inst0::INSTR")
print(sa.query("*IDN?"))  # Should return instrument identification
sa.close()
```

If connections fail, check:
- Network connectivity and firewall rules
- VISA resource string accuracy
- Instrument is not in local lockout mode
- VISA driver is properly installed
