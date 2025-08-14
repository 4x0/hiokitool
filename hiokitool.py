# Copyright (c) 2024 4x0
# Licensed under the MIT License - see LICENSE file for details

import socket
import time
import configparser
from datetime import datetime, timedelta
from time import sleep
import argparse
import re
import os
import signal
import sys


class MessageQueue:
    def __init__(self):
        self.queue = {'wait': True, 'items': []}
    @property
    def size(self):
        return len(self.queue['items'])
    def put(self, item, wait=True):
        if wait or self.size == 0:
            self.set_wait(wait)
        self.queue['items'].append(item)
    def get(self):
        return ';'.join(self.queue['items'])
    def wait(self):
        return self.queue['wait']
    def set_wait(self, do_wait):
        self.queue['wait'] = do_wait
    def clear(self):
        self.queue['items'] = []
        self.queue['wait'] = True


Q = MessageQueue()
BUFSIZE = 4096


class TelnetClient:
    def __init__(self, host, port=23, timeout=10):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.sock = None

    def connect(self):
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.setsockopt(socket.SOL_TCP, socket.TCP_NODELAY, 1)
            self.sock.settimeout(self.timeout)
            self.sock.connect((self.host, self.port))
        except socket.timeout:
            raise ConnectionError(f"Connection timeout to {self.host}:{self.port} after {self.timeout} seconds")
        except socket.gaierror as e:
            raise ConnectionError(f"Failed to resolve host {self.host}: {e}")
        except ConnectionRefusedError:
            raise ConnectionError(f"Connection refused by {self.host}:{self.port}. Check if instrument is powered on and network settings are correct")
        except Exception as e:
            raise ConnectionError(f"Failed to connect to {self.host}:{self.port}. Error: {e}")

    def send_command(self, command):
        if self.sock is None:
            raise RuntimeError("Not connected to any server.")
        try:
            command = command + '\r\n'  # Add a terminator, CR+LF, to transmitted command
            self.sock.send(bytes(command, 'utf-8'))  # Convert to byte type and send
            response = self._receive_response(self.timeout)
            return response
        except socket.timeout:
            raise TimeoutError(f"Timeout waiting for response to command: {command.strip()}")
        except BrokenPipeError:
            raise ConnectionError("Connection lost while sending command")
        except Exception as e:
            raise RuntimeError(f"Failed to send command '{command.strip()}'. Error: {e}")

    def send_query(self):
        if self.sock is None:
            raise RuntimeError("Not connected to any server.")
        try:
            command = Q.get() + '\r\n'  # Add a terminator, CR+LF, to transmitted command
            print(command.strip())
            self.sock.send(bytes(command, 'utf-8'))  # Convert to byte type and send
            if Q.wait():
                response = self._receive_response(self.timeout)
            else:
                response = True
            Q.clear()
            return response
        except socket.timeout:
            raise TimeoutError(f"Timeout waiting for response to query: {command.strip()}")
        except BrokenPipeError:
            raise ConnectionError("Connection lost while sending query")
        except Exception as e:
            raise RuntimeError(f"Failed to send query. Error: {e}")

    def _receive_response(self, timeout):
        msgBuf = bytes()  # Received Data
        MAX_RESPONSE_SIZE = 1024 * 1024  # 1MB max response size
        try:
            start = time.time()  # Record time for timeout
            while True:
                rcv = self.sock.recv(BUFSIZE)
                rcv = rcv.strip(b"\r")  # Delete CR in received data
                if b"\n" in rcv:  # End the loop when LF is received
                    rcv = rcv.strip(b"\n")  # Ignore the terminator CR
                    msgBuf += rcv
                    msgBuf = msgBuf.decode('utf-8')
                    break
                else:
                    msgBuf += rcv
                    # Check for buffer overflow
                    if len(msgBuf) > MAX_RESPONSE_SIZE:
                        raise RuntimeError(f"Response exceeded maximum size of {MAX_RESPONSE_SIZE} bytes")
                # Timeout processing
                if time.time() - start > timeout:
                    msgBuf = "Timeout Error"
                    break
        except UnicodeDecodeError as e:
            raise RuntimeError(f"Failed to decode response. Invalid UTF-8 data: {e}")
        except Exception as e:
            if isinstance(e, RuntimeError):
                raise
            raise RuntimeError(f"Failed to receive response. Error: {e}")
        return msgBuf

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None


class ControlQuery:
    def __init__(self, stub):
        self.stub = stub
    def get(self, sub=None):
        m = f'{self.stub}? {sub}' if sub is not None else f'{self.stub}?'
        Q.put(m, True)
        return m
    def __repr__(self):
        return self.get()
    def __str__(self):
        return self.get()


class Control(ControlQuery):
    def set(self, value):
        m = f'{self.stub} {value}'
        Q.put(m, False)
        return m

    def __call__(self, value):
        print(value)
        self.set(value)


class ControlSetting(ControlQuery):
    def get(self):
        m = f'{self.stub}'
        Q.put(m, False)
        return m


class System:
    def __init__(self):
        self.device_id = ControlQuery('*IDN')
        self.installed_options = ControlQuery('*OPT')
        self.reset = ControlSetting('*RST')
        self.self_test = ControlQuery('*TST')
        self.date = Control(':SYSTem:DATE')  # <Year>,<Month>,<Day>
        self.time = Control(':SYSTem:TIME')  # <Hour 00 to 23>,<Minute>,<Second; 00 to 59>
        self.wait = ControlSetting('*WAI')


class Display:
    def __init__(self):
        self.state = Control(':DISPlay:STATe')  # (1/0/ON/OFF)
        self.brightness = Control(':DISPlay:BACKlight')  # (0 to 100 or MAX/MIN/DEFault)
        self.type = Control(':DISPlay:TYPe')  # (0 to 1 or MAX/MIN/DEFault)
        self.view = Control(':DISPlay:VIEW')  # (NUMeric, TCHart, METer, STATistics, HISTogram).

    def status(self):
        return ';'.join([self.state.get(), self.brightness.get(), self.type.get(), self.view.get()])


class Measure:
    def __init__(self, include_temperature=True):
        self.include_temperature = include_temperature
        self.format = Control(':SYSTem:COMMunicate:FORMat')  # FIX/FLOAT
        self.continuous = Control(':INITiate:CONTinuous')  # 0/1/OFF/ON

        self.read = ControlQuery(':READ')
        self.fetch = ControlQuery(':FETCh')
        self.sample_count = Control(':SAMPle:COUNt')  # <Number of measurements/MAX/MIN/DEFault>
                                                      # (MAX: 5000, MIN: 1, DEFault: 1)
        self.last = Control(':DATA:LAST')
        self.dc_voltage = Control(':MEASure:VOLTage:DC')  # 100 mV/1 V/10 V/100 V/1000 V/Voltage to be measured
                                                               # (MAX: 1000 V, MIN: 100 mV, DEFault: AUTO)
        self.speed = Control(':SENSe:VOLTage:DC:NPLCycles')  # (MAX: 100, MIN: 0.02, DEFault: 10) / SLOW, MEDium, FAST
        self.temperature = ControlQuery(':MEASure:TEMPerature')

        self.apeture_control = Control(':SENSe:VOLTage:DC:APERture:ENABled')  # < 1/0/ON/OFF >
        self.apeture_time = Control(':SENSe:VOLTage:DC:APERture')  # < Integral time(sec) /MAX/MIN/DEFault >

        self.voltage_range = Control(':SENSe:VOLTage:DC:RANGe')  # <Measurement range/MAX/MIN/DEFault>
        self.voltage_range_auto = Control(':SENSe:VOLTage:DC:RANGe:AUTO')  # < 1/0/ON/OFF >
        self.voltage_digits = Control(':SENSe:VOLTage:DIGits')  # <Number of digits/MAX/MIN/DEFault>
                                                                # (MAX: 8, MIN: 4, DEFault: 8)
        self.impedence_auto = Control('SENSe:VOLTage:DC:IMPedance:AUTO')  # <1/0/ON/OFF >

        self.trigger_source = Control(':TRIGGER:SOURCE')  # < IMMediate/ EXTernal/BUS >
        self.trigger_delay = Control(':TRIGger:DELay')  # <Delay time/MAX/MIN/DEFault>
                                                        # (MAX: 9.999, MIN: 0, DEFault: 0)
        self.trigger_delay_auto = Control(':TRIGger:DELay:AUTO')  # <1/0/ON/OFF >

        self.immediate = ControlSetting(':INITiate:IMMediate')
        self.abort = ControlSetting(':ABORt')


class ExternalIO:
    def __init__(self):
        self.mode = ControlQuery(':IO:MODE')
        self.input = ControlQuery(':IO:INPut')
        self.output = ControlSetting(':IO:OUTPut')  # <Output data 0 to 2047>


class IOSequencer:
    """Handles sequential IO output patterns during measurements"""
    def __init__(self, config):
        self.enabled = False
        self.mode = 'range'  # 'range' or 'list'
        self.patterns = []
        self.current_index = 0
        self.samples_per_step = 1
        self.samples_at_current = 0
        self.loop = False
        self.include_in_csv = False
        
        if 'IO.Sequence' not in config:
            return
            
        seq_config = config['IO.Sequence']
        self.enabled = seq_config.get('enabled', 'false').upper() == 'TRUE'
        
        if not self.enabled:
            return
            
        self.mode = seq_config.get('mode', 'range').lower()
        self.samples_per_step = int(seq_config.get('samples_per_step', '1'))
        self.loop = seq_config.get('loop', 'true').upper() == 'TRUE'
        self.include_in_csv = seq_config.get('include_io_in_csv', 'true').upper() == 'TRUE'
        
        if self.mode == 'range':
            start = int(seq_config.get('start', '0'))
            end = int(seq_config.get('end', '7'))
            step = int(seq_config.get('step', '1'))
            
            # Validate range
            if start < 0 or start > 2047:
                raise ValueError(f"IO sequence start value {start} out of range (0-2047)")
            if end < 0 or end > 2047:
                raise ValueError(f"IO sequence end value {end} out of range (0-2047)")
            
            # Generate pattern list from range
            if step > 0:
                self.patterns = list(range(start, end + 1, step))
            else:
                raise ValueError("IO sequence step must be positive")
                
        elif self.mode == 'list':
            # Parse comma-separated list of patterns
            pattern_str = seq_config.get('patterns', '0')
            self.patterns = []
            for p in pattern_str.split(','):
                p = p.strip()
                if p.startswith('0b'):
                    value = int(p, 2)
                else:
                    value = int(p)
                if 0 <= value <= 2047:
                    self.patterns.append(value)
                else:
                    raise ValueError(f"IO pattern value {value} out of range (0-2047)")
        
        if not self.patterns:
            self.patterns = [0]  # Default to single pattern
    
    def should_change(self):
        """Check if it's time to change IO output"""
        if not self.enabled or not self.patterns:
            return False
        return self.samples_at_current >= self.samples_per_step
    
    def next(self):
        """Move to next IO pattern"""
        if not self.enabled:
            return None
            
        self.samples_at_current = 0
        self.current_index += 1
        
        if self.current_index >= len(self.patterns):
            if self.loop:
                self.current_index = 0
            else:
                self.enabled = False  # Disable after one complete cycle
                return None
                
        return self.get_current()
    
    def get_current(self):
        """Get current IO output value"""
        if not self.enabled or not self.patterns:
            return None
        if self.current_index < len(self.patterns):
            return self.patterns[self.current_index]
        return None
    
    def increment_sample(self):
        """Increment sample counter for current IO state"""
        if self.enabled:
            self.samples_at_current += 1
    
    def is_complete(self):
        """Check if sequence is complete (for non-looping mode)"""
        if not self.enabled or self.loop:
            return False
        return self.current_index >= len(self.patterns)


class Panel:
    def __init__(self):
        self.save_panel = Control('*SAV')
        self.load_panel = Control('*RCL')
    def load(self, panel_no):
        return self.load_panel.set(panel_no)
    def save(self, panel_no):
        return self.save_panel.set(panel_no)


class RestrictedAPI:
    """Safe API for user scripts - prevents dangerous operations"""
    
    def __init__(self, connection, measure_obj, system_obj=None):
        self.conn = connection
        self.measure_obj = measure_obj
        self.system_obj = system_obj
        self.results = []
        self.current_io = None
        self.current_range = None
        self.metadata = {}
        
    def set_io(self, value):
        """Safely set IO output (0-2047)"""
        if not isinstance(value, int):
            try:
                if isinstance(value, str) and value.startswith('0b'):
                    value = int(value, 2)
                else:
                    value = int(value)
            except ValueError:
                raise ValueError(f"Invalid IO value: {value}")
        
        if not 0 <= value <= 2047:
            raise ValueError(f"IO value {value} out of range (0-2047)")
        
        Q.put(f':IO:OUTPut {value}', False)
        self.conn.send_query()
        self.current_io = value
        print(f"IO set to: {value} (0b{value:011b})")
        return True
    
    def measure(self, samples=1, delay_ms=0):
        """Take measurements and return results"""
        if samples < 1 or samples > 5000:
            raise ValueError(f"Sample count {samples} out of range (1-5000)")
        
        results = []
        for i in range(samples):
            self.measure_obj.read.get()
            result_str = self.conn.send_query()
            
            try:
                # Handle both single values and comma-separated (voltage,temperature)
                if ',' in result_str:
                    values = [float(v.strip()) for v in result_str.split(',')]
                    results.append(values[0])  # Primary measurement
                else:
                    results.append(float(result_str.strip()))
            except ValueError:
                print(f"Warning: Could not parse measurement: {result_str}")
                results.append(None)
            
            if delay_ms > 0 and i < samples - 1:
                sleep(delay_ms / 1000.0)
        
        self.results.extend([r for r in results if r is not None])
        return results
    
    def set_range(self, range_value):
        """Set voltage measurement range"""
        valid_ranges = ['100MV', '1V', '10V', '100V', '1000V', 'AUTO', 'MAX', 'MIN', 'DEFAULT']
        
        range_upper = str(range_value).upper()
        if range_upper not in valid_ranges:
            raise ValueError(f"Invalid range: {range_value}. Valid: {', '.join(valid_ranges)}")
        
        self.measure_obj.voltage_range.set(range_value)
        self.conn.send_query()
        self.current_range = range_value
        print(f"Range set to: {range_value}")
        return True
    
    def set_speed(self, speed):
        """Set measurement speed (SLOW/MEDium/FAST)"""
        valid_speeds = ['SLOW', 'MEDIUM', 'MED', 'FAST']
        
        speed_upper = str(speed).upper()
        if speed_upper not in valid_speeds:
            raise ValueError(f"Invalid speed: {speed}. Valid: SLOW, MEDium, FAST")
        
        # Normalize MEDium/MED
        if speed_upper == 'MEDIUM':
            speed_upper = 'MED'
        
        self.measure_obj.speed.set(speed_upper)
        self.conn.send_query()
        print(f"Speed set to: {speed_upper}")
        return True
    
    def wait(self, seconds):
        """Safe wait/delay function"""
        if not 0 <= seconds <= 60:
            raise ValueError(f"Wait time {seconds} out of range (0-60 seconds)")
        sleep(seconds)
        return True
    
    def get_statistics(self):
        """Get measurement statistics"""
        if not self.results:
            return {
                'mean': None,
                'max': None,
                'min': None,
                'std': None,
                'count': 0
            }
        
        import statistics
        return {
            'mean': statistics.mean(self.results),
            'max': max(self.results),
            'min': min(self.results),
            'std': statistics.stdev(self.results) if len(self.results) > 1 else 0,
            'count': len(self.results)
        }
    
    def log(self, message):
        """Safe logging function"""
        print(f"[Script] {message}")
        return True
    
    def set_metadata(self, key, value):
        """Store metadata about the test"""
        self.metadata[str(key)] = value
        return True
    
    def get_metadata(self, key=None):
        """Retrieve metadata"""
        if key is None:
            return self.metadata.copy()
        return self.metadata.get(str(key))
    
    def clear_results(self):
        """Clear stored results"""
        self.results = []
        return True
    
    def save_results(self, filename=None):
        """Save results to file"""
        if not filename:
            filename = f"script_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Ensure filename is safe (no path traversal)
        filename = os.path.basename(filename)
        if not filename.endswith('.csv'):
            filename += '.csv'
        
        with open(filename, 'w') as f:
            # Write metadata
            for key, value in self.metadata.items():
                f.write(f"# {key}: {value}\n")
            
            # Write results
            f.write("# index,value\n")
            for i, value in enumerate(self.results):
                f.write(f"{i},{value}\n")
        
        print(f"Results saved to: {filename}")
        return filename


class Label:
    def __init__(self):
        self.label = Control(':SYSTem:LABel')
        self.label_state = Control(':SYSTem:LABel:STATe')
    def turn_on(self):
        self.label_state.set('ON')
    def turn_off(self):
        self.label_state.set('OFF')
    def set_text(self, text):
        self.turn_on()
        date_re = re.compile(r'(?:\%.){0,4}')
        _text = text[:8].strip()
        try:
            dt_mask = [x for x in date_re.findall(_text) if x].pop()
            # print(dt_mask)
            dt_text = datetime.now().strftime(dt_mask)
            print(dt_text)
            _text = _text.replace(dt_mask, dt_text)
            print(_text)
        except IndexError:
            pass
        self.label.set('"%s"' % _text)


def collect_current_setup(conn):
    _system = System()
    _display = Display()
    _measure = Measure()
    _label = Label()

    data = {}

    c = _system.device_id.get()
    data[c] = conn.send_query().strip()
    c = _system.installed_options.get()
    data[c] = conn.send_query().strip()
    c = _display.brightness.get()
    data[c] = conn.send_query().strip()
    c = _display.type.get()
    data[c] = conn.send_query().strip()
    c = _display.state.get()
    data[c] = conn.send_query().strip()
    c = _display.view.get()
    data[c] = conn.send_query().strip()
    # c = _measure.speed.get()
    # data[c] = conn.send_query().strip()
    c = _measure.sample_count.get()
    data[c] = conn.send_query().strip()
    c = _measure.voltage_range.get()
    data[c] = conn.send_query().strip()
    c = _measure.voltage_range_auto.get()
    data[c] = conn.send_query().strip()
    c = _measure.dc_voltage.get()
    data[c] = conn.send_query().strip()
    c = _measure.format.get()
    data[c] = conn.send_query().strip()
    c = _measure.apeture_control.get()
    data[c] = conn.send_query().strip()
    c = _measure.apeture_time.get()
    data[c] = conn.send_query().strip()
    c = _measure.impedence_auto.get()
    data[c] = conn.send_query().strip()
    c = _measure.immediate.get()
    data[c] = conn.send_query()
    c = _measure.voltage_digits.get()
    data[c] = conn.send_query().strip()
    c = _measure.trigger_delay.get()
    data[c] = conn.send_query().strip()
    c = _measure.trigger_delay_auto.get()
    data[c] = conn.send_query().strip()

    return data

def validate_config_value(section, key, value, valid_values=None, value_type=None):
    """Validate configuration values"""
    if value_type:
        try:
            if value_type == int:
                return int(value)
            elif value_type == float:
                return float(value)
        except ValueError:
            raise ValueError(f"Invalid {value_type.__name__} value for [{section}] {key}: {value}")
    
    if valid_values and value.upper() not in [v.upper() for v in valid_values]:
        raise ValueError(f"Invalid value for [{section}] {key}: {value}. Valid values: {', '.join(valid_values)}")
    
    return value


def execute_script_with_timeout(script_file, api, timeout=300, mode='restricted'):
    """Execute a Python script with timeout and safety controls"""
    
    # Create safe namespace based on mode
    if mode == 'restricted':
        # Minimal safe builtins
        safe_builtins = {
            '__builtins__': {
                'len': len,
                'range': range,
                'enumerate': enumerate,
                'zip': zip,
                'max': max,
                'min': min,
                'sum': sum,
                'abs': abs,
                'round': round,
                'str': str,
                'int': int,
                'float': float,
                'bool': bool,
                'list': list,
                'dict': dict,
                'tuple': tuple,
                'set': set,
                'print': print,
                'True': True,
                'False': False,
                'None': None,
            }
        }
    elif mode == 'trusted':
        # Allow more builtins and some imports
        import math
        import statistics
        safe_builtins = {
            '__builtins__': __builtins__,
            'math': math,
            'statistics': statistics,
        }
    else:  # developer mode
        safe_builtins = {'__builtins__': __builtins__}
    
    # Create namespace with API
    namespace = safe_builtins.copy()
    namespace.update({
        'api': api,
        'set_io': api.set_io,
        'measure': api.measure,
        'set_range': api.set_range,
        'set_speed': api.set_speed,
        'wait': api.wait,
        'get_statistics': api.get_statistics,
        'log': api.log,
        'set_metadata': api.set_metadata,
        'get_metadata': api.get_metadata,
        'clear_results': api.clear_results,
        'save_results': api.save_results,
    })
    
    # Set up timeout handler (Unix/Linux/Mac only)
    def timeout_handler(signum, frame):
        raise TimeoutError(f"Script execution exceeded timeout of {timeout} seconds")
    
    # Read and compile script
    if not os.path.exists(script_file):
        raise FileNotFoundError(f"Script file not found: {script_file}")
    
    with open(script_file, 'r') as f:
        script_code = f.read()
    
    # Set timeout alarm if on Unix-like system
    if hasattr(signal, 'SIGALRM'):
        old_handler = signal.signal(signal.SIGALRM, timeout_handler)
        signal.alarm(timeout)
    
    try:
        # Compile and execute script
        compiled_code = compile(script_code, script_file, 'exec')
        exec(compiled_code, namespace)
        
        # Look for and execute main function
        if 'sequence' in namespace and callable(namespace['sequence']):
            result = namespace['sequence'](api)
            return result
        elif 'main' in namespace and callable(namespace['main']):
            result = namespace['main'](api)
            return result
        else:
            print("Warning: No 'sequence' or 'main' function found in script")
            return api.results
            
    except TimeoutError:
        print(f"Script execution timeout after {timeout} seconds")
        raise
    except Exception as e:
        print(f"Script execution error: {e}")
        raise
    finally:
        # Cancel timeout alarm
        if hasattr(signal, 'SIGALRM'):
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)

def load_config(config_file):
    config = configparser.ConfigParser()
    config.read(config_file)
    return config

def apply_config(config):
    if 'Host' not in config:
        print("Error: No [Host] section in config file")
        exit(1)
    
    host = config.get('Host', 'host', fallback='192.168.1.200')
    port = validate_config_value('Host', 'port', 
                                  config.get('Host', 'port', fallback='23'),
                                  value_type=int)
    timeout = validate_config_value('Host', 'timeout',
                                     config.get('Host', 'timeout', fallback='10'),
                                     value_type=int)
    
    if port < 1 or port > 65535:
        raise ValueError(f"Invalid port number: {port}. Must be between 1 and 65535")
    if timeout < 1 or timeout > 300:
        raise ValueError(f"Invalid timeout: {timeout}. Must be between 1 and 300 seconds")
    
    conn = TelnetClient(host, port, timeout)
    
    try:
        conn.connect()
    except Exception as e:
        print(f"Failed to connect: {e}")
        exit(1)
    
    try:
        system = System()
        if 'System' in config:
            if 'reset' in config['System']:
                if config['System']['reset'].upper() == 'TRUE':
                    system.wait.get()
                    system.reset.get()
                    system.wait.get()
                    conn.send_query()

        if 'Display' in config:
            display = Display()
            if 'brightness' in config['Display']:
                display.brightness.set(config['Display']['brightness'])
            if 'view' in config['Display']:
                display.view.set(config['Display']['view'])
            if 'state' in config['Display']:
                display.state.set(config['Display']['state'])
            if 'type' in config['Display']:
                display.type.set(config['Display']['type'])

        conn.send_query()

        measure = Measure()
        temperature = False

        # Configure trigger if specified
        if 'Trigger' in config:
            trigger_source = config['Trigger'].get('source', 'IMMediate').upper()
            if trigger_source in ['IMMEDIATE', 'EXTERNAL', 'BUS']:
                measure.trigger_source.set(trigger_source)
            
            if 'delay' in config['Trigger']:
                delay = float(config['Trigger']['delay'])
                if 0 <= delay <= 9.999:
                    measure.trigger_delay.set(delay)
                else:
                    raise ValueError(f"Trigger delay {delay} out of range (0-9.999 seconds)")
            
            if 'delay_auto' in config['Trigger']:
                auto = config['Trigger']['delay_auto'].upper()
                if auto in ['ON', 'OFF', '1', '0']:
                    measure.trigger_delay_auto.set(auto)
            
            conn.send_query()

        if 'Measure' in config:
            if 'voltage_range' in config['Measure']:
                measure.voltage_range.set(config['Measure']['voltage_range'])
            if 'voltage_range_auto' in config['Measure']:
                measure.voltage_range_auto.set(config['Measure']['voltage_range_auto'])
            if 'speed' in config['Measure']:
                measure.speed.set(config['Measure']['speed'])
            if 'sample_count' in config['Measure']:
                measure.sample_count.set(config['Measure']['sample_count'])
            if 'format' in config['Measure']:
                measure.format.set(config['Measure']['format'])
            if 'continuous' in config['Measure']:
                measure.continuous.set(config['Measure']['continuous'])
            if 'impedence_auto' in config['Measure']:
                measure.impedence_auto.set(config['Measure']['impedence_auto'])
            if 'temperature' in config['Measure']:
                if config['Measure']['temperature'].strip().upper() == 'ON':
                    temperature = True
            conn.send_query()

        if 'Panel' in config:
            panel = Panel()
            if 'load' in config['Panel']:
                panel.load(config['Panel']['load'])
                conn.send_query()
            elif 'save' in config['Panel']:
                panel.save(config['Panel']['save'])
                conn.send_query()

        if 'Label' in config:
            label = Label()
            if 'state' in config['Label']:
                label.label_state.set(config['Label']['state'])
            if 'text' in config['Label']:
                label.set_text(config['Label']['text'])
            conn.send_query()

        if 'IO' in config:
            io = ExternalIO()
            
            # Set mode if specified
            if 'mode' in config['IO']:
                mode_value = config['IO']['mode'].upper()
                if mode_value in ['INPUT', 'OUTPUT', 'TRIGGER']:
                    # Note: mode might be read-only on some models
                    pass  # io.mode query only, cannot set
            
            # Handle different output formats
            output_value = None
            
            # Option 1: Binary string
            if 'output_binary' in config['IO']:
                try:
                    output_value = int(config['IO']['output_binary'], 2)
                except ValueError:
                    raise ValueError(f"Invalid binary value for IO output: {config['IO']['output_binary']}")
            
            # Option 2: Decimal
            elif 'output_decimal' in config['IO']:
                try:
                    output_value = int(config['IO']['output_decimal'])
                except ValueError:
                    raise ValueError(f"Invalid decimal value for IO output: {config['IO']['output_decimal']}")
            
            # Option 3: Individual bits
            elif any(f'bit_{i}' in config['IO'] for i in range(11)):
                output_value = 0
                for i in range(11):
                    bit_key = f'bit_{i}'
                    if bit_key in config['IO']:
                        if config['IO'][bit_key].upper() in ['ON', '1', 'TRUE']:
                            output_value |= (1 << i)
            
            # Apply output value if specified
            if output_value is not None:
                if 0 <= output_value <= 2047:
                    Q.put(f':IO:OUTPut {output_value}', False)
                    conn.send_query()
                else:
                    raise ValueError(f"IO output value {output_value} out of range (0-2047)")

        # Check for script execution
        if 'Script' in config and config['Script'].get('enabled', 'false').upper() == 'TRUE':
            script_file = config['Script'].get('file')
            if script_file and os.path.exists(script_file):
                print(f"Executing script: {script_file}")
                
                # Get script parameters
                mode = config['Script'].get('mode', 'restricted').lower()
                timeout = int(config['Script'].get('timeout', '300'))
                
                # Create API instance
                api = RestrictedAPI(conn, measure, system)
                
                try:
                    # Execute script
                    results = execute_script_with_timeout(script_file, api, timeout, mode)
                    print(f"Script completed. {len(api.results)} measurements collected.")
                    
                    # Save results if requested
                    if config['Script'].get('save_results', 'true').upper() == 'TRUE':
                        output_file = api.save_results()
                        print(f"Script results saved to: {output_file}")
                    
                except TimeoutError as e:
                    print(f"Script timeout: {e}")
                except Exception as e:
                    print(f"Script error: {e}")
                
                # Script execution replaces normal Run mode
                return
            else:
                print(f"Warning: Script file not found: {script_file}")

        if 'Run' in config:
            samples = int(config['Run'].get('samples', 10))
            rate = float(config['Run'].get('polling_rate', 1))
            output_file = '%s_HIOKI.csv' % datetime.now().strftime('%Y%m%d_%H%M%S')
            collected_samples = 0
            next_timestamp = datetime.now()
            
            # Initialize IO sequencer
            io_sequencer = IOSequencer(config)
            
            # Set initial IO state if sequencer is enabled
            if io_sequencer.enabled and io_sequencer.get_current() is not None:
                Q.put(f':IO:OUTPut {io_sequencer.get_current()}', False)
                conn.send_query()
                print(f"IO sequence started, initial output: {io_sequencer.get_current()}")
            
            with open(output_file, 'a') as f:
                if 'settings_dump' in config['Run'] and config['Run'].get('settings_dump').upper() == 'TRUE':
                    current_settings = collect_current_setup(conn)
                    for k, v in current_settings.items():
                        f.write(f'{k}={v}\n')
                
                # Write CSV header if IO state is included
                if io_sequencer.enabled and io_sequencer.include_in_csv:
                    header = '# timestamp, measurement, io_state\n' if not temperature else '# timestamp, voltage, temperature, io_state\n'
                    f.write(header)
                
                system.wait.get()
                conn.send_query()
                
                while collected_samples < samples:
                    # Check if IO needs to change
                    if io_sequencer.enabled and io_sequencer.should_change():
                        next_io = io_sequencer.next()
                        if next_io is not None:
                            Q.put(f':IO:OUTPut {next_io}', False)
                            conn.send_query()
                            print(f"IO output changed to: {next_io}")
                        elif io_sequencer.is_complete():
                            print("IO sequence complete")
                            if not io_sequencer.loop:
                                break  # Stop if sequence is complete and not looping
                    
                    if collected_samples == 0:
                        _now = next_timestamp
                    else:
                        _now = datetime.now()
                    if _now >= next_timestamp:
                        next_timestamp += timedelta(seconds=rate)
                        measure.read.get(sub='TEMP') if temperature else measure.read.get()
                        result = conn.send_query()
                        
                        # Format output line with optional IO state
                        if io_sequencer.enabled and io_sequencer.include_in_csv:
                            current_io = io_sequencer.get_current()
                            line = '%s,%s,%s' % (_now, result, current_io if current_io is not None else 'N/A')
                        else:
                            line = '%s,%s' % (_now, result)
                        
                        f.write(line)
                        
                        # Print progress with IO state if enabled
                        if io_sequencer.enabled:
                            io_info = f" IO:{io_sequencer.get_current()}" if io_sequencer.get_current() is not None else ""
                            print(line.strip(), '(%s/%s)%s' % (collected_samples+1, samples, io_info))
                        else:
                            print(line.strip(), '(%s/%s)' % (collected_samples+1, samples))
                        
                        collected_samples += 1
                        io_sequencer.increment_sample()
                    sleep(0.005)
    finally:
        conn.close()


def diag(host='192.168.1.200', port=23, timeout=10):
    """Diagnostic function for testing connections"""
    conn = TelnetClient(host, port, timeout)
    try:
        conn.connect()
        print(collect_current_setup(conn))
    finally:
        conn.close()


if __name__ == '__main__':
    # diag()
    # exit(0)
    parser = argparse.ArgumentParser(description='Run Telnet Client with config file')
    parser.add_argument('config_file', type=str, help='Path to the configuration INI file', default='config.ini')
    args = parser.parse_args()
    config = load_config(args.config_file)
    # config = load_config('config.ini')
    apply_config(config)



