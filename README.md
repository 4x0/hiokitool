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