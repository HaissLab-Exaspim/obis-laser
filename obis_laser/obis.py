#!/usr/bin/env python3
"""Serial device driver for OBIS LS/LX/LG lasers."""

import sys
from serial import Serial
from enum import Enum, IntFlag
from time import sleep

try:
    from enum import StrEnum
except ImportError:
    class StrEnum(str, Enum):
        pass


# Collect various sets of commands into enums.
# Commands are SCPI-based
# https://en.wikipedia.org/wiki/Standard_Commands_for_Programmable_Instruments


class IEEESCPI(StrEnum):
    WARM_BOOT = "*RST"

class SessionControlCmd(StrEnum):
    SYSTEM_COMMUNICATE_HANDSHAKING = "SYST:COMM:HAND"
    SYSTEM_COMMUNICATE_PROMPT = "SYST:COMM:PROM"
    SYSTEM_AUTOSTART = "SYST:AUT"
    SYSTEM_INFO_AMODULATION_TYPE = "SYST:INF:AMOD:TYP"

    SYSTEM_INDICATOR_LASER = "SYST:IND:LAS"
    SYSTEM_AKEY = "SYST:AKEY"

    SYSTEM_ERROR_CLEAR = "SYST:ERR:CLE"


class SessionControlQuery(StrEnum):
    SYSTEM_COMMUNICATE_HANDSHAKING = "SYST:COMM:HAND?"
    SYSTEM_COMMUNICATE_PROMPT = "SYST:COMM:PROM?"
    SYSTEM_AUTOSTART = "SYST:AUT?"
    SYSTEM_INFO_AMODULATION_TYPE = "SYST:INF:AMOD:TYP?"

    SYSTEM_STATUS = "SYST:STAT?"
    SYSTEM_FAULT = "SYST:FAUL?"
    SYSTEM_INDICATOR_LASER = "SYST:IND:LAS?"
    SYSTEM_AKEY = "SYST:AKEY?"
    SYSTEM_ERROR_COUNT = "SYST:ERR:COUN?"
    SYSTEM_ERROR_NEXT = "SYST:ERR:NEX?"


class SysInfoCmd(StrEnum):
    USER = "SYST:INF:USER"
    FIELD_CALIBRATION_DATE = "SYST:INF:FCD"
    POWER = "SYST:INF:POW"


class SysInfoQuery(StrEnum):
    MODEL = "SYST:INF:MOD?"
    MANUFACTURING_DATE = "SYST:INF:MDAT?"
    CALIBRATION_DATE = "SYST:INF:CDAT?"
    SERIAL_NUMBER = "SYST:INF:SNUM?"
    MANUFACTURING_PART_NUMBER = "SYST:INF:PNUM?"
    FIRMWARE_VERSION = "SYST:INF:FVER?"
    PROTOCOL_VERSION = "SYST:INF:PVER?"
    WAVELENGTH = "SYST:INF:WAV?"
    POWER = "SYST:INF:POW?"
    TYPE = "SYST:INF:TYP?"
    SOURCE_POWER_NOMINAL = "SOUR:POW:NOM?"
    SOURCE_POWER_LOW = "SOUR:POW:LIM:LOW?"
    SOURCE_POWER_HIGH = "SOUR:POW:LIM:HIGH?"
    USER = "SYST:INF:USER?"
    FIELD_CALIBRATION_DATE = "SYST:INF:FCD?"


class SystemStateQuery(StrEnum):
    # All of these are read only.
    SYSTEM_CYCLES = "SYST:CYCL?"
    SYSTEM_HOURS = "SYST:HOUR?"
    SYSTEM_DIODE_HOURS = "SYST:DIOD:HOUR?"
    SOURCE_POWER_LEVEL = "SOUR:POW:LEV?"
    SOURCE_POWER_CURRENT = "SOUR:POW:CURR?"
    SOURCE_TEMPERATURE_BASEPLATE = "SOUR:TEMP:BAS?"
    SYSTEM_LOCK = "SYST:LOCK"


class OperationalCmd(StrEnum):
    MODE_INTERNAL_CW = "SOUR:AM:INT"
    MODE_EXTERNAL = "SOUR:AM:EXT"
    POWER_LEVEL_AMPLITUDE = "SOUR:POW:LEV:IMM:AMPL"
    POWER_LEVEL_MEMORY = "SOUR:POW:LEV:MEM:AMPL"  # Start-up power setpoint (nonvolatile)
    LASER_OUTPUT_STATE = "SOUR:AM:STATe"
    EMISSION_DELAY = "SYST:CDRH"


class OperationalQuery(StrEnum):
    OPERATING_MODE = "SOUR:AM:SOUR?"
    LASER_OUTPUT_STATE = "SOUR:AM:STATe?"
    EMISSION_DELAY = "SYST:CDRH?"
    POWER_LEVEL_AMPLITUDE = "SOUR:POW:LEV:IMM:AMPL?"
    POWER_LEVEL_MEMORY = "SOUR:POW:LEV:MEM:AMPL?"  # Start-up power setpoint


class OptionalCmd(StrEnum):
    DIODE_TEMPERATURE_CTRL = "SOUR:TEMP:APR"


class OptionalQuery(StrEnum):
    DIODE_TEMPERATURE_CTRL = "SOUR:TEMP:APR?"


class LGTemperatureQuery(StrEnum):
    """LG-specific temperature queries (Section 7.4.3 in manual)."""
    RESONATOR = "SOUR:TEMP:RES?"
    BRF = "SOUR:TEMP:BRF?"
    SHG = "SOUR:TEMP:SHG?"
    THG = "SOUR:TEMP:THG?"  # UV models only
    RESONATOR_SETPOINT = "SOUR:TEMP:RES:SERV:SETP?"
    BRF_SETPOINT = "SOUR:TEMP:BRF:SERV:SETP?"
    SHG_SETPOINT = "SOUR:TEMP:SHG:SERV:SETP?"
    THG_SETPOINT = "SOUR:TEMP:THG:SERV:SETP?"  # UV models only
    RESONATOR_TEC_OUTPUT = "SOUR:TEMP:RES:DRIV:OUTP?"
    BRF_HEATER_OUTPUT = "SOUR:TEMP:BRF:DRIV:OUTP?"
    SHG_HEATER_OUTPUT = "SOUR:TEMP:SHG:DRIV:OUTP?"
    THG_HEATER_OUTPUT = "SOUR:TEMP:THG:DRIV:OUTP?"  # UV models only


class LGQuery(StrEnum):
    """LG-specific queries (Section 7.4.3 and 7.4.4 in manual)."""
    AUTOMATIC_KEY = "SYST:AKEY?"
    HEAD_FAULT_LATCHED = "?HFL"  # HOPS compatibility: latched faults
    HEAD_FAULT_CURRENT = "?HFF"  # HOPS compatibility: current faults
    INTERLOCK_STATE = "?INT"  # 1=closed, 0=open
    COMPOSITE_KEYSWITCH = "?KSW"  # 1=both keys closed
    CURRENT_LIMIT = "?CLIM"
    CURRENT_MODE = "?CMODE"  # 0=power mode, 1=current mode
    CURRENT_MODE_CMD = "?CMODECMD"


class LGCmd(StrEnum):
    """LG-specific commands (Section 7.4.3 in manual)."""
    AUTOMATIC_KEY = "SYST:AKEY"  # Store start-up value of laser enable


class BoolStrEnum(StrEnum):
    # For bool-like settings the device takes "ON" and "OFF", not 0 and 1.
    ON = "ON"
    OFF = "OFF"


class SystemStatus(StrEnum):

    KEY_OUT_INT_WARMUP = 'CE000100'
    KEY_OUT_INT_STANDBY = 'CE000008'
    KEY_OUT_EXT_WARMUP = 'CE000500'
    KEY_OUT_LASER_READY_INT_MODE = 'CE000008'
    KEY_OUT_LASER_READY_EXT_MODE = 'CE000408'
    KEY_OUT_FAULT = 'CE000001'  # Laser RED, Fault RED, KEY OFF

    KEY_ON_INT_WARMUP = 'C8001100'
    KEY_ON_EXT_WARMUP = 'C8001500'
    KEY_ON_LASER_READY_INT_MODE = 'C8001002'
    KEY_ON_LASER_READY_EXT_MODE = 'C8001402'
    # Open Interlock cannot be detected with the Key out.
    KEY_ON_LASER_READY_INT_MODE_INTERLOCK_OPEN = 'CC000008' # Status RED
    KEY_ON_LASER_READY_EXT_MODE_INTERLOCK_OPEN = 'CC000408'
    KEY_ON_FAULT = 'C8001001'  # Laser RED, Fault RED

    # if AUTOSTART was not set, then powering up the device with the key armed
    # will put the device in these special states. Status LED will blink blue.
    KEY_ARMED_EARLY_INT_WARMUP = 'C8000100'
    KEY_ARMED_EARLY_EXT_WARMUP = 'C8000500' # 'CE000500'
    KEY_ARMED_EARLY_LASER_READY_INT_MODE = 'C8000008'
    KEY_ARMED_EARLY_LASER_READY_EXT_MODE = 'C8000408'

# Analog input impedance setting is model-agnostic.
class AnalogInputImpedanceType(StrEnum):
    FIFTY_OHM = "1"
    TWO_THOUSAND_OHM = "2"

# Modulation Setting (Operating Mode) depends on Model.
# See pg 143 in datasheet Part 1.
class LSModulationType(StrEnum):
    CW_POWER = "CWP"
    DIGITAL = "DIGITAL"
    ANALOG = "ANALOG"
    MIXED = "MIXED"


class LXModulationType(StrEnum):
    CW_POWER = "CWP"
    CW_CURRENT = "CWC"
    DIGITAL = "DIGITAL"
    DIGITAL_POWER = "DIGSO"
    ANALOG = "ANALOG"
    MIXED_POWER = "MIXSO"
    MIXED = "MIXED"

class LGModulationType(StrEnum):
    CW_POWER = "CWP"
    CW_CURRENT = "CWC"


class LGStatusBits(IntFlag):
    """Status bits returned by SYST:STAT? for LG lasers (Table 7-5 in manual)."""
    LASER_FAULT = 0x00000001
    LASER_EMISSION = 0x00000002
    LASER_READY = 0x00000004
    LASER_STANDBY = 0x00000008
    CDRH_DELAY = 0x00000010
    LASER_HARDWARE_FAULT = 0x00000020
    LASER_ERROR = 0x00000040
    LASER_POWER_CALIBRATION = 0x00000080  # Always 1 for LG
    LASER_WARM_UP = 0x00000100
    LASER_HEAD_NOISE = 0x00000200  # Always 0 for LG
    EXTERNAL_OPERATING_MODE = 0x00000400
    FIELD_CALIBRATION = 0x00000800  # Always 0 for LG
    LASER_POWER_VOLTAGE = 0x00001000


class LGFaultBits(IntFlag):
    """Fault bits returned by SYST:FAUL? for LG lasers (Table 7-6 in manual)."""
    BASE_PLATE_TEMP_FAULT = 0x00000001
    DIODE_TEMP_FAULT = 0x00000002  # Not applicable to LG
    INTERNAL_TEMP_FAULT = 0x00000004  # Not applicable to LG
    LASER_POWER_SUPPLY_FAULT = 0x00000008
    I2C_ERROR = 0x00000010  # Not implemented in LG
    DIODE_OVERCURRENT = 0x00000020  # Not applicable (LG has current limit)
    MEMORY_CHECKSUM_ERROR = 0x00000040
    CHECKSUM_RECOVERY = 0x00000080  # Not applicable to LG
    BUFFER_OVERFLOW = 0x00000100
    WARMUP_TIME_LIMIT = 0x00000200
    TEC_DRIVER_ERROR = 0x00000400  # Not applicable to LG
    BUS_ERROR = 0x00000800  # Not applicable to LG
    DIODE_TEMP_LIMIT_ERROR = 0x00001000  # Not applicable to LG
    LASER_READY_FAULT = 0x00002000
    PHOTODIODE_FAULT = 0x00004000  # Not applicable to LG
    FATAL_FAULT = 0x00008000  # Not implemented in LG
    STARTUP_FAULT = 0x00010000  # Not implemented in LG
    WATCHDOG_TIMER_RESET = 0x00020000
    FIELD_CALIBRATION_ERROR = 0x00040000  # Not applicable to LG
    LASER_OVERPOWER_FAULT = 0x00100000  # Not applicable (LG has power limit)


class LGHeadFaultBits(IntFlag):
    """Head fault bits returned by ?HFL and ?HFF for LG lasers (Table 8-1 in manual)."""
    BRF_TEMP_FAULT = 0x00000001
    SHG_TEMP_FAULT = 0x00000002
    THG_TEMP_FAULT = 0x00000004
    ETALON_TEMP_FAULT = 0x00000008
    RESONATOR_TEMP_FAULT = 0x00000010
    HEATSINK_TEMP_FAULT = 0x00000100
    INTERNAL_TEMP_FAULT = 0x00000200
    LDD_FAULT = 0x00010000
    SHUTTER_FAULT = 0x00020000
    HEAD_MEMORY_FAULT = 0x01000000
    BOARD_MEMORY_FAULT = 0x02000000
    WARMUP_TIMEOUT = 0x20000000


OBIS_COM_SETUP = {"baudrate": 9600}
OBIS_LG_COM_SETUP = {"baudrate": 115200}

class Obis:

    def __init__(self, port, prefix=None, com_setup=None):
        """Constructor. Connect to the device."""

        self.prefix = f'{prefix} ' if prefix is not None else ''
        com_setup = OBIS_COM_SETUP if com_setup is None else com_setup
        self.ser = Serial(port, **com_setup) if type(port) != Serial else port
        # Flush OS buffers.
        self.ser.reset_output_buffer()
        self.ser.reset_input_buffer()

    @property  # TODO: make a @cached_property
    def wavelength(self):
        return self.get_sys_info_setting(SysInfoQuery.WAVELENGTH)

    @property
    def temperature(self):
        """Return the temperature of the baseplate in degrees C."""
        reply = self.get_state_setting(SystemStateQuery.SOURCE_TEMPERATURE_BASEPLATE)
        return float(reply.strip('C'))

    def enable(self):
        """Enable the laser once it is ready (i.e: not warming up or faulted).

        Note: this command does not provide any feedback. If enabled while
              the laser is warming up, the setting will take effect after
              warmup is complete.
        """
        if self.is_enabled():
            return
        return self.set_operational_setting(OperationalCmd.LASER_OUTPUT_STATE,
                                            BoolStrEnum.ON.value)

    def disable(self):
        """Disable the laser.

        Note: this command does not provide any feeback.
        """
        if not self.is_enabled():
            return
        return self.set_operational_setting(OperationalCmd.LASER_OUTPUT_STATE,
                                            BoolStrEnum.OFF.value)

    def is_enabled(self):
        reply = self.get_operational_setting(OperationalQuery.LASER_OUTPUT_STATE)
        return reply == BoolStrEnum.ON.value

    def get_system_status(self) -> SystemStatus:
        """Return the status of the laser as an enum."""
        stat_str = \
            self.get_session_ctrl_setting(SessionControlQuery.SYSTEM_STATUS)
        try:
            return SystemStatus(stat_str)
        except ValueError:
            print(f"'{stat_str}' is an unrecognized state.")
            raise

    def wait_until_ready(self):
        """Block until the laser is enabled."""
        state = self.get_system_status()
        while True:
            if state.value[-1] == '0':  # Check for warmup states.
                sleep(0.05)
            elif state.value[-1] == '1':  # Check for fault states.
                raise RuntimeError("Error: device is in a fault state.")
            state = self.get_system_status()
    @property
    def cdrh(self):
        status = self.get_operational_setting(OperationalQuery.EMISSION_DELAY)
        return status

    @cdrh.setter
    def cdrh(self, status: BoolStrEnum or str):
        value = status.value if type(status) == BoolStrEnum else status
        self.set_operational_setting(OperationalCmd.EMISSION_DELAY,
                                     value)

    @property
    def power_setpoint(self):
        """Returns current power of laser in mW"""
        power_W = self.get_operational_setting(OperationalQuery.POWER_LEVEL_AMPLITUDE)
        return float(power_W)*1000

    @power_setpoint.setter
    def power_setpoint(self, power_mW):
        """set to setpoint of laser power in mW"""
        self.set_operational_setting(OperationalCmd.POWER_LEVEL_AMPLITUDE, str(power_mW/1000))

    @property
    def max_power(self):
        """Returns maximum power of laser in mW"""
        return float(self.get_sys_info_setting(SysInfoQuery.SOURCE_POWER_HIGH)) *1000

    @property
    def min_power(self):
        """Returns maximum power of laser in mW"""
        return float(self.get_sys_info_setting(SysInfoQuery.SOURCE_POWER_LOW)) * 1000


    def warm_boot(self):
        """Tell the laser to warm boot."""
        self._writecmd(IEEESCPI.WARM_BOOT, "")

    @property
    def analog_input_impedance(self):
        """get the input impedance of the SMB analog input."""
        return self.get_session_ctrl_setting(
            SessionControlCmd.SYSTEM_INFO_AMODULATION_TYPE)
    @analog_input_impedance.setter
    def analog_input_impedance(self, ohms: AnalogInputImpedanceType):
        """Set the input impedance of the SMB analog input."""
        self.set_session_ctrl_setting(
            SessionControlCmd.SYSTEM_INFO_AMODULATION_TYPE, ohms)

    @property
    def external_mode(self):
        mode = self.get_operational_setting(OperationalQuery.OPERATING_MODE)
        if mode == 'DIGITAL' or mode == 'ANALOG' or mode == 'MIXED':
            return 'ON'
        else:
            return 'OFF'


    # ---- Utility funcs ----

    def get_sys_info_setting(self, sys_info_query: SysInfoQuery):
        return self._readcmd(sys_info_query)

    def set_sys_info_setting(self, sys_info_cmd: SysInfoCmd, value):
        return self._writecmd(sys_info_cmd, value)

    def get_session_ctrl_setting(self, setting: SessionControlQuery):
        return self._readcmd(setting)

    def set_session_ctrl_setting(self, setting: SessionControlCmd, value: str):
        # String value depends on what setting we are writing.
        return self._writecmd(setting, value)

    def get_state_setting(self, setting: SystemStateQuery):
        return self._readcmd(setting)

    def get_operational_setting(self, setting:OperationalQuery):
        return self._readcmd(setting)

    def set_operational_setting(self, setting: OperationalCmd, value: str):
        return self._writecmd(setting, value)

    def get_optional_info(self, setting: OptionalQuery):
        return self._readcmd(setting)

    def _writecmd(self, cmd: StrEnum, cmd_arg_val: str) -> str:
        """Write a command. Confirm that the device responds with an OK."""
        cmd_str = f"{cmd.value} {cmd_arg_val}" if cmd_arg_val else f"{cmd.value}"
        cmd_bytes = f"{self.prefix}{cmd_str}\r\n".encode("ascii") if self.prefix \
            else f"{cmd_str}\r\n".encode("ascii")
        # print(f"Writing: {cmd_bytes}")
        self.ser.write(cmd_bytes)
        conf = self.ser.readline().decode('utf8').rstrip('\r\n')
        if conf.startswith("ERR"):
            err_detail = ""
            try:
                err_count = self.get_session_ctrl_setting(
                    SessionControlQuery.SYSTEM_ERROR_COUNT)
                if err_count and int(err_count) > 0:
                    err_detail = self.get_session_ctrl_setting(
                        SessionControlQuery.SYSTEM_ERROR_NEXT)
            except Exception:
                err_detail = ""
            detail_msg = f" Details: {err_detail}" if err_detail else ""
            raise RuntimeError(
                "Error: received error response when attempting to "
                f"write: {repr(cmd_bytes)}.\r\n"
                f"Response: {conf}.{detail_msg}"
            )
        assert conf == 'OK', \
            "Error: did not receive an OK when attempting to " \
            f"write: {repr(cmd_bytes)}\r\n" \
            f"Instead received: {conf}"

    def _readcmd(self, cmd: StrEnum) -> str:
        """Read a setting and return reply as string without \r\n."""
        if self.prefix:
            cmd_str = f"{self.prefix}{cmd.value}"
        else:
            cmd_str = f"{cmd.value}"
        cmd_bytes = f"{cmd_str}\r\n".encode("ascii")
        self.ser.write(cmd_bytes)
        val = self.ser.readline().decode("utf8").rstrip("\r\n")
        if cmd.value.startswith("?"):
            return val
        conf = self.ser.readline().decode("utf8").rstrip("\r\n")
        assert conf == "OK", \
            "Error: did not receive an OK when attempting to " \
            f"write: {repr(cmd_bytes)}.\r\n" \
            f"Instead received: {val}"
        return val

    def close(self):
        self.ser.close()

class ObisLS(Obis):

    @property
    def modulation_mode(self):
        return self._readcmd(OperationalQuery.OPERATING_MODE)
    @modulation_mode.setter
    def modulation_mode(self, mode: LSModulationType):
        # Modes fall into 2 categories: internal or external.
        # CW type modes (only one for LS type) are internal.
        if mode == LSModulationType.CW_POWER:
            self._writecmd(OperationalCmd.MODE_INTERNAL_CW, mode)
        else:
            self._writecmd(OperationalCmd.MODE_EXTERNAL, mode)


class ObisLX(Obis):

    @property
    def modulation_mode(self):
        return self._readcmd(OperationalQuery.OPERATING_MODE)

    @modulation_mode.setter
    def modulation_mode(self, mode: LSModulationType):
        # Modes fall into 2 categories: internal or external.
        # CW type modes (only one for LS type) are internal.
        # Modes fall into 2 categories: internal or external.
        # CW type modes (only one for LS type) are internal.
        if mode in {LXModulationType.CW_POWER, LXModulationType.CW_CURRENT}:
            self._writecmd(OperationalCmd.MODE_INTERNAL_CW, mode)
        else:
            self._writecmd(OperationalCmd.MODE_EXTERNAL, mode)

class ObisLG(Obis):
    """Driver for OBIS LG (including XT) series lasers.

    Key differences from LX/LS:
    - Baud rate is 115200 (vs 9600)
    - Only supports CWP (constant power) and CWC (constant current) modes
    - No external modulation modes (DIGITAL, ANALOG, MIXED)
    - Temperature values do NOT have 'C' suffix
    - Power level command is volatile (use MEMory command for persistent storage)
    - Baseplate fault is latching - requires cycling enable after fault clears
    """

    def __init__(self, port, prefix=None):
        super().__init__(port, prefix=prefix, com_setup=OBIS_LG_COM_SETUP)

    @property
    def temperature(self):
        """Return the temperature of the baseplate in degrees C."""
        reply = self.get_state_setting(SystemStateQuery.SOURCE_TEMPERATURE_BASEPLATE)
        return float(reply.strip('C'))

    @property
    def modulation_mode(self):
        return self._readcmd(OperationalQuery.OPERATING_MODE)

    @modulation_mode.setter
    def modulation_mode(self, mode: LGModulationType):
        if mode not in {LGModulationType.CW_POWER, LGModulationType.CW_CURRENT}:
            raise ValueError("LG modulation mode must be CWP or CWC.")
        self._writecmd(OperationalCmd.MODE_INTERNAL_CW, mode)

    def get_system_status(self) -> LGStatusBits:
        """Return the system status as LGStatusBits flags."""
        stat_str = self.get_session_ctrl_setting(SessionControlQuery.SYSTEM_STATUS)
        try:
            return LGStatusBits(int(stat_str, 16))
        except ValueError:
            print(f"'{stat_str}' is an unrecognized status value.")
            raise

    def get_system_fault(self) -> LGFaultBits:
        """Return the system fault code as LGFaultBits flags."""
        fault_str = self.get_session_ctrl_setting(SessionControlQuery.SYSTEM_FAULT)
        try:
            return LGFaultBits(int(fault_str, 16))
        except ValueError:
            print(f"'{fault_str}' is an unrecognized fault value.")
            raise

    def get_head_fault_latched(self) -> LGHeadFaultBits:
        """Return latched head faults (faults since warmup or last clear)."""
        fault_str = self._readcmd(LGQuery.HEAD_FAULT_LATCHED)
        return LGHeadFaultBits(int(fault_str, 16))

    def get_head_fault_current(self) -> LGHeadFaultBits:
        """Return current head faults (faults active right now)."""
        fault_str = self._readcmd(LGQuery.HEAD_FAULT_CURRENT)
        return LGHeadFaultBits(int(fault_str, 16))

    def wait_until_ready(self):
        """Block until the laser is ready for emission."""
        while True:
            status = self.get_system_status()
            if status & (LGStatusBits.LASER_FAULT | LGStatusBits.LASER_HARDWARE_FAULT):
                raise RuntimeError("Error: device is in a fault state.")
            if status & LGStatusBits.LASER_READY:
                return
            sleep(0.05)

    # LG-specific temperature queries
    @property
    def resonator_temperature(self):
        """Return the resonator (main/diode) temperature in degrees C."""
        return float(self._readcmd(LGTemperatureQuery.RESONATOR))

    @property
    def brf_temperature(self):
        """Return the BRF temperature in degrees C."""
        return float(self._readcmd(LGTemperatureQuery.BRF))

    @property
    def shg_temperature(self):
        """Return the SHG temperature in degrees C."""
        return float(self._readcmd(LGTemperatureQuery.SHG))

    @property
    def thg_temperature(self):
        """Return the THG temperature in degrees C (UV models only)."""
        return float(self._readcmd(LGTemperatureQuery.THG))

    @property
    def resonator_temperature_setpoint(self):
        """Return the resonator setpoint temperature in degrees C."""
        return float(self._readcmd(LGTemperatureQuery.RESONATOR_SETPOINT))

    @property
    def brf_temperature_setpoint(self):
        """Return the BRF setpoint temperature in degrees C."""
        return float(self._readcmd(LGTemperatureQuery.BRF_SETPOINT))

    @property
    def shg_temperature_setpoint(self):
        """Return the SHG setpoint temperature in degrees C."""
        return float(self._readcmd(LGTemperatureQuery.SHG_SETPOINT))

    @property
    def thg_temperature_setpoint(self):
        """Return the THG setpoint temperature in degrees C (UV models only)."""
        return float(self._readcmd(LGTemperatureQuery.THG_SETPOINT))

    @property
    def interlock_state(self):
        """Return True if interlock is closed (OK), False if open."""
        return self._readcmd(LGQuery.INTERLOCK_STATE) == "1"

    @property
    def keyswitch_state(self):
        """Return True if both physical and virtual keyswitches are closed."""
        return self._readcmd(LGQuery.COMPOSITE_KEYSWITCH) == "1"

    @property
    def current_limit(self):
        """Return the current command limit in amps."""
        return float(self._readcmd(LGQuery.CURRENT_LIMIT))

    @property
    def automatic_key(self):
        """Return the automatic key (start-up laser enable) setting."""
        return self._readcmd(LGQuery.AUTOMATIC_KEY)

    @automatic_key.setter
    def automatic_key(self, value: BoolStrEnum or str):
        """Set the automatic key (stored start-up value of laser enable).

        Note: If SYST:AUT (autostart) is ON, this setting is ignored and
        laser will turn on after warmup regardless.
        """
        val = value.value if isinstance(value, BoolStrEnum) else value
        self._writecmd(LGCmd.AUTOMATIC_KEY, val)

    @property
    def power_setpoint_memory(self):
        """Return the stored start-up power setpoint in mW.

        This is the power level used at startup (stored in nonvolatile memory).
        """
        power_W = self._readcmd(OperationalQuery.POWER_LEVEL_MEMORY)
        return float(power_W) * 1000

    @power_setpoint_memory.setter
    def power_setpoint_memory(self, power_mW):
        """Set the stored start-up power setpoint in mW.

        Note: Unlike LX/LS, the immediate power command on LG is volatile.
        Use this to set the power level that persists across power cycles.
        """
        self._writecmd(OperationalCmd.POWER_LEVEL_MEMORY, str(power_mW / 1000))

    def clear_baseplate_fault(self):
        """Clear a latching baseplate temperature fault.

        The LG baseplate fault is latching - even after temperature drops
        below 30°C, user must cycle the enable signal to clear it.
        This method cycles KSWCMD: 0 -> 1 -> 0 as per manual instructions.

        Note: If fault was caused by open/shorted sensor, it cannot be cleared
        and laser must be returned to factory.
        """
        self.disable()
        sleep(0.1)
        self.enable()
        sleep(0.1)
        self.disable()


class ObisLaserBox:

    def __init__(self, port):
        """Class for the Obis Laser Box which contains LS and LX lasers.
        No direct communication is needed but useful in order to open serial port and
        share between lasers"""
        self.ser = Serial(port, **OBIS_COM_SETUP)



if __name__ == "__main__":
    from inpromptu import Inpromptu
    obis = ObisLS("/dev/ttyACM0")
    # Create a REPL to interact with the object.
    Inpromptu(obis).cmdloop()

    # Connect.
    # Set analog modulation.
    # enable when we start imaging.
    # disable when we stop.
    # disable CDRH
    # TODO set power level
