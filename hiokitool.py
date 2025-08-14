# Copyright (c) 2024 4x0
# Licensed under the MIT License - see LICENSE file for details

import socket
import time
import configparser
from datetime import datetime, timedelta
from time import sleep
import argparse
import re


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
        except Exception as e:
            raise Exception(f"Failed to connect to {self.host}:{self.port}. Error: {e}")

    def send_command(self, command):
        if self.sock is None:
            raise Exception("Not connected to any server.")
        try:
            command = command + '\r\n'  # Add a terminator, CR+LF, to transmitted command
            self.sock.send(bytes(command, 'utf-8'))  # Convert to byte type and send
            response = self._receive_response(self.timeout)
            return response
        except Exception as e:
            raise Exception(f"Failed to send command. Error: {e}")

    def send_query(self):
        if self.sock is None:
            raise Exception("Not connected to any server.")
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
        except Exception as e:
            raise Exception(f"Failed to send command. Error: {e}")

    def _receive_response(self, timeout):
        msgBuf = bytes()  # Received Data
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
                # Timeout processing
                if time.time() - start > timeout:
                    msgBuf = "Timeout Error"
                    break
        except Exception as e:
            raise Exception(f"Failed to receive response. Error: {e}")
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


class Panel:
    def __init__(self):
        self.save_panel = Control('*SAV')
        self.load_panel = Control('*RCL')
    def load(self, panel_no):
        return self.load_panel.set(panel_no)
    def save(self, panel_no):
        return self.save_panel.set(panel_no)


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

def load_config(config_file):
    config = configparser.ConfigParser()
    config.read(config_file)
    return config

def apply_config(config):
    if 'Host' in config:
        conn = TelnetClient(
            config.get('Host', 'host', fallback='192.168.1.200'),
            int(config.get('Host', 'port', fallback=23)),
            int(config.get('Host', 'timeout', fallback=10)),
        )
        conn.connect()
    else:
        exit(1)

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

    if 'Run' in config:
        samples = int(config['Run'].get('samples', 10))
        rate = float(config['Run'].get('polling_rate', 1))
        output_file = '%s_HIOKI.csv' % datetime.now().strftime('%Y%m%d_%H%M%S')
        collected_samples = 0
        next_timestamp = datetime.now()
        with open(output_file, 'a') as f:
            if 'settings_dump' in config['Run'] and config['Run'].get('settings_dump').upper() == 'TRUE':
                current_settings = collect_current_setup(conn)
                for k, v in current_settings.items():
                    f.write(f'{k}={v}\n')
            system.wait.get()
            conn.send_query()
            while collected_samples < samples:
                if collected_samples == 0:
                    _now = next_timestamp
                else:
                    _now = datetime.now()
                if _now >= next_timestamp:
                    next_timestamp += timedelta(seconds=rate)
                    measure.read.get(sub='TEMP') if temperature else measure.read.get()
                    result = conn.send_query()
                    line = '%s,%s' % (_now, result)
                    f.write(line)
                    print(line.strip(), '(%s/%s)' % (collected_samples+1, samples))
                    collected_samples += 1
                sleep(0.005)
    conn.close()


def diag():
    conn = TelnetClient('192.168.1.200')
    conn.connect()
    print(collect_current_setup(conn))
    #
    # system = System()
    # system.reset.get()
    # measure = Measure()
    # measure.voltage_range.get()
    # print(conn.send_query())
    # measure.voltage_range.set('100V')
    # measure.speed.set('FAST')
    # print(conn.send_query())
    # # measure.voltage_range.get()
    # # measure.read.get()
    # measure.continuous.set('ON')
    # measure.voltage_range_auto.set('ON')
    # measure.voltage_digits.set('8')
    # measure.speed.get()
    # print(conn.send_query())
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



