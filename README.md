# hiokitool

A Python-based telnet client for remote control and automated data acquisition from HIOKI digital multimeters (DMMs) via SCPI commands.

## Overview

hiokitool provides a programmatic interface to HIOKI multimeters that support telnet/SCPI communication, enabling automated measurement collection, instrument configuration, and long-term data logging. It's designed for laboratory automation, production testing, and continuous monitoring applications.

## Features

- **Automated Data Collection**: Configurable sampling rates and duration for long-term measurements
- **SCPI Command Interface**: Full support for standard HIOKI SCPI command set
- **CSV Data Logging**: Timestamped measurements automatically saved to CSV files
- **Temperature Monitoring**: Simultaneous voltage and temperature measurements (if supported by device)
- **Flexible Configuration**: INI-based configuration for easy setup without code changes
- **Batch Command Execution**: Efficient command queuing to minimize network overhead
- **Panel Management**: Save and recall instrument panel configurations
- **Custom Display Labels**: Set custom labels with datetime formatting support
- **Digital I/O Control**: Control up to 11 digital outputs for relay switching and automation
- **IO Sequencing**: Automatically cycle through IO patterns during measurements
- **External Triggering**: Support for external, bus, or immediate triggering modes

## Requirements

- Python 3.6+
- Network connection to HIOKI DMM with telnet/SCPI support
- Compatible HIOKI models with Ethernet/LAN interface (e.g., DM7275, DM7276, etc.)

## Installation

```bash
git clone https://github.com/4x0/hiokitool.git
cd hiokitool
```

No additional dependencies required - uses Python standard library only.

## Configuration

Create a `config.ini` file with your instrument settings:

```ini
[Host]
host = 192.168.1.200  ; DMM IP address
port = 23             ; Telnet port (default: 23)
timeout = 10          ; Connection timeout in seconds

[System]
reset = True          ; Reset instrument on connection

[Display]
brightness = 50       ; Display brightness (0-100)
view = HIST          ; Display mode (NUMeric, TCHart, METer, STATistics, HISTogram)
state = ON           ; Display ON/OFF
type = 0             ; Display type

[Measure]
voltage_range = 10V          ; Measurement range (100mV, 1V, 10V, 100V, 1000V, AUTO)
voltage_range_auto = OFF     ; Auto-ranging ON/OFF
voltage_digits = 8           ; Display digits (4-8)
impedence_auto = ON          ; Auto input impedance
sample_count = 1             ; Samples per measurement (1-5000)
continuous = OFF             ; Continuous measurement mode
format = FIX                 ; Output format (FIX/FLOAT)
speed = SLOW                 ; Measurement speed (SLOW/MEDium/FAST)
temperature = ON             ; Include temperature measurements

[Panel]
; load = 5                   ; Load panel number (1-10)
; save = 5                   ; Save to panel number

[Label]
state = ON                   ; Enable custom label
text = %%H%%M TEST          ; Label text (supports strftime formatting)

[Trigger]
source = IMMediate           ; Trigger source (IMMediate/EXTernal/BUS)
delay = 0.0                  ; Delay after trigger in seconds (0-9.999)
delay_auto = OFF             ; Auto delay calculation (ON/OFF)

[IO]
; Digital I/O configuration for relay control and external triggers
; Choose ONE of the following output formats:

; Option 1: Binary representation (clearest for bit patterns)
; output_binary = 0b00000001101  ; Bits 0, 2, 3 active

; Option 2: Decimal value
; output_decimal = 13  ; Same as above (decimal equivalent)

; Option 3: Individual bit control (most readable)
; bit_0 = ON   ; Relay 1 - Input channel A
; bit_1 = OFF  ; Relay 2 - Input channel B  
; bit_2 = ON   ; Relay 3 - Range 10V
; bit_3 = ON   ; Relay 4 - Range 100V
; bit_4 = OFF  ; Relay 5 - Filter
; bit_5 = OFF  ; Relay 6 - Shunt resistor
; bit_6 = OFF  ; Trigger output
; bit_7 = OFF  ; Status LED 1
; bit_8 = OFF  ; Status LED 2
; bit_9 = OFF  ; Status LED 3
; bit_10 = OFF ; Interlock signal

[IO.Sequence]
; Automated IO pattern sequencing during measurements
enabled = false              ; Enable IO sequencing (true/false)
mode = range                 ; Sequence mode (range/list)

; For range mode:
start = 0                    ; Starting IO value
end = 7                      ; Ending IO value  
step = 1                     ; Step size
samples_per_step = 10        ; Measurements per IO state
loop = true                  ; Loop back to start when complete

; For list mode (alternative to range):
; patterns = 0, 1, 3, 7, 15, 31, 63, 127, 255  ; Comma-separated values
; patterns = 0b001, 0b010, 0b100, 0b111         ; Or binary notation

include_io_in_csv = true     ; Add IO state column to output file

[Run]
settings_dump = False        ; Dump current settings to CSV header
samples = 100                ; Number of samples to collect
polling_rate = 1.0          ; Seconds between samples
```

## Usage

### Basic Usage

Run with default config.ini:
```bash
python hiokitool.py config.ini
```

### Example: 24-Hour Voltage Monitoring

Create a configuration for 24-hour monitoring at 1-minute intervals:

```ini
[Host]
host = 192.168.1.100
port = 23

[Measure]
voltage_range = 10V
speed = SLOW
voltage_digits = 8

[Run]
samples = 1440        ; 24 hours * 60 minutes
polling_rate = 60     ; 1 minute intervals
```

Run:
```bash
python hiokitool.py monitoring_config.ini
```

Output will be saved as `YYYYMMDD_HHMMSS_HIOKI.csv`

### Example: High-Speed Data Acquisition

For rapid measurements:

```ini
[Measure]
speed = FAST
sample_count = 100    ; Average 100 samples per reading
continuous = ON

[Run]
samples = 10000
polling_rate = 0.1    ; 10Hz sampling
```

### Example: Temperature and Voltage Logging

For dual measurements:

```ini
[Measure]
temperature = ON
voltage_range = 100V

[Run]
samples = 8640        ; 24 hours at 10-second intervals
polling_rate = 10
```

### Example: External Triggering

Synchronize measurements with external events:

```ini
[Trigger]
source = EXTernal    ; Wait for external trigger
delay = 0.1          ; 100ms delay after trigger
delay_auto = OFF

[Run]
samples = 100
polling_rate = 1
```

### Example: IO Sequencing - Range Mode

Automatically cycle through test configurations:

```ini
[IO.Sequence]
enabled = true
mode = range
start = 0            ; Binary: 000
end = 7              ; Binary: 111
step = 1
samples_per_step = 5 ; 5 measurements per configuration
loop = true          ; Continuous cycling

[Run]
samples = 80         ; Total samples (8 states × 5 samples × 2 loops)
polling_rate = 1
```

### Example: IO Sequencing - List Mode

Test specific configurations in a custom order:

```ini
[IO.Sequence]
enabled = true
mode = list
patterns = 0b001, 0b010, 0b100, 0b111  ; Test specific bit combinations
samples_per_step = 10
loop = false         ; Single pass through list

[Run]
samples = 40         ; 4 patterns × 10 samples each
polling_rate = 0.5
```

### Example: Digital I/O for Relay Control

Control external relays for automated test switching:

```ini
[IO]
; Example 1: Binary pattern for test configuration
output_binary = 0b00010001  ; Activate relays on bits 0 and 4

; Example 2: Individual bit control for clear documentation
bit_0 = ON   ; Connect test probe to channel A
bit_1 = OFF  ; Disconnect channel B
bit_2 = ON   ; Select 10V range
bit_3 = OFF  ; Deselect 100V range
bit_4 = ON   ; Enable input filter

; Example 3: Simple decimal value
output_decimal = 7  ; Activate first three relays (bits 0,1,2)
```

Common use cases:
- **Automated multiplexing**: Switch between multiple test points
- **Range switching**: Control external attenuators or amplifiers
- **Safety interlocks**: Ensure safe conditions before measurement
- **Status indication**: Drive LEDs or alarms based on configuration

## Output Format

CSV files are generated with the following format:
```csv
2024-01-15 14:30:00.123456,+1.23456789E+00
2024-01-15 14:30:01.123456,+1.23456790E+00
```

With temperature enabled:
```csv
2024-01-15 14:30:00.123456,+1.23456789E+00,+2.35000000E+01
```

## Programmatic Usage

You can also use hiokitool as a library:

```python
from hiokitool import TelnetClient, System, Measure

# Connect to instrument
client = TelnetClient('192.168.1.200', 23)
client.connect()

# Initialize subsystems
system = System()
measure = Measure()

# Configure measurement
measure.voltage_range.set('10V')
measure.speed.set('SLOW')
client.send_query()

# Take a reading
measure.read.get()
result = client.send_query()
print(f"Voltage: {result}")

client.close()
```

## SCPI Command Structure

hiokitool implements standard SCPI commands:

- **System Commands**: `*IDN?`, `*RST`, `*TST?`, `*WAI`
- **Measurement Commands**: `:READ?`, `:FETCh?`, `:MEASure:VOLTage:DC`
- **Configuration Commands**: `:SENSe:VOLTage:DC:RANGe`, `:SENSe:VOLTage:DC:NPLCycles`
- **Display Commands**: `:DISPlay:STATe`, `:DISPlay:VIEW`
- **Trigger Commands**: `:TRIGger:SOURce`, `:TRIGger:DELay`

## Troubleshooting

### Connection Issues
- Verify DMM IP address and network connectivity: `ping 192.168.1.200`
- Check DMM network settings and ensure telnet/SCPI is enabled
- Confirm port 23 is not blocked by firewalls

### Measurement Issues
- Ensure proper measurement range for your signal
- Check input impedance settings for high-impedance sources
- Verify trigger settings if measurements seem delayed

### Data Format Issues
- Use `format = FIX` for fixed-point notation
- Use `format = FLOAT` for scientific notation
- Adjust `voltage_digits` for required precision

## Supported HIOKI Models

Compatible with HIOKI DMMs supporting LAN/telnet interface:
- DM7275 Precision DC Voltmeter
- DM7276 Precision DC Voltmeter
- Other HIOKI models with SCPI over telnet support

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Disclaimer

This is an unofficial tool and is not affiliated with, endorsed by, or supported by HIOKI E.E. Corporation. Use at your own risk.

## Author

4x0

## See Also

- [HIOKI Official Website](https://www.hioki.com)
- [SCPI Standard Documentation](https://www.ivifoundation.org/docs/scpi-99.pdf)
- [HIOKI DMM Programming Manuals](https://www.hioki.com/en/support/download/)