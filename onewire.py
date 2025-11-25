"""
Onewire Controller Interface
"""
import socket
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
import sys
from typing import List, Union, Any

from hardware_device_base import HardwareSensorBase

PARAMETER_QUERY = "GET /details.xml HTTP/1.1\r\n\r\n"

@dataclass
class EDS0065DATA:
    """Class to hold data from EDS0065"""
    # pylint: disable=too-many-instance-attributes
    rom_id: str = None
    device_type: str = None
    health: int = None
    channel: int = None
    raw_data: str = None
    relative_humidity: float = None
    temperature: float = None
    humidity: float = None
    dew_point: float = None
    humidex: float = None
    heat_index: float = None
    version: float = None

@dataclass
class EDS0068DATA:
    """Class to hold data from EDS0068"""
    # pylint: disable=too-many-instance-attributes
    rom_id: str = None
    device_type: str = None
    health: int = None
    channel: int = None
    raw_data: str = None
    relative_humidity: float = None
    temperature: float = None
    humidity: float = None
    dew_point: float = None
    humidex: float = None
    heat_index: float = None
    pressure_mb: float = None
    pressure_hg: float = None
    illuminance: int = None
    version: float = None

@dataclass
class ONEWIREDATA:
    """Class to hold data from OneWire"""
    # pylint: disable=too-many-instance-attributes
    poll_count: int = None
    total_devices: int = None
    loop_time: float = None
    ch1_connected: int = None
    ch2_connected: int = None
    ch3_connected: int = None
    ch1_error: int = None
    ch2_error: int = None
    ch3_error: int = None
    ch1_voltage: float = None
    ch2_voltage: float = None
    ch3_voltage: float = None
    voltage_power: float = None
    device_name: str = None
    hostname: str = None
    mac_address: str = None
    datetime: str = None
    eds0065_data: List[EDS0065DATA] = field(default_factory=list)
    eds0068_data: List[EDS0068DATA] = field(default_factory=list)

    def read_sensors(self):
        """Method to read sensor data from OneWire"""
        sensors = []
        for sensor in self.eds0065_data:
            sensors.append(asdict(sensor))
        for sensor in self.eds0068_data:
            sensors.append(asdict(sensor))

        return sensors

    def read_temperature(self):
        """Method to read temperature data from OneWire"""
        temperatures = []
        for sensor in self.eds0065_data:
            if sensor.temperature is not None:
                temperature = {"rom_id": sensor.rom_id, "temperature": sensor.temperature}
                temperatures.append(temperature)
        for sensor in self.eds0068_data:
            if sensor.temperature is not None:
                temperature = {"rom_id": sensor.rom_id, "temperature": sensor.temperature}
                temperatures.append(temperature)

        return temperatures

    def read_humidity(self):
        """Method to read humidity data from OneWire"""
        humidities = []
        for sensor in self.eds0065_data:
            if sensor.humidity is not None:
                humidity = {"rom_id": sensor.rom_id, "humidity": sensor.humidity}
                humidities.append(humidity)
        for sensor in self.eds0068_data:
            if sensor.humidity is not None:
                humidity = {"rom_id": sensor.rom_id, "humidity": sensor.humidity}
                humidities.append(humidity)

        return humidities

class ONEWIRE(HardwareSensorBase):
    """Class for interfacing with OneWire"""
    # pylint: disable=too-many-instance-attributes
    def __init__(self, timeout=1, log=True, logfile=__name__.rsplit(".", 1)[-1]):
        """Instantiate a OneWire device"""

        super().__init__(log, logfile)

        self.host = None
        self.port = 80
        self.timeout = timeout
        self.sock: socket.socket | None = None

        # Instantiated with ONEWIREDATA each time method get_data is called.
        # This avoids continual appending of data and unchecked growth of data structure.
        self.ow_data = None

    def connect(self, host, port, con_type="tcp") -> None:  # pylint: disable=W0221
        """Method to connect to OneWire"""
        if self.validate_connection_params((host, port)):
            if con_type == "tcp":
                self.host = host
                self.port = port
                try:
                    self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self.sock.connect((self.host, self.port))
                    self.sock.settimeout(self.timeout)
                    self._set_connected(True)
                    self.report_info(f"Connected to OneWire at {host}:{port}")
                except (ConnectionRefusedError, OSError) as err:
                    raise DeviceConnectionError(
                        f"Could not connect to {self.host}:{self.port} {err}"
                    ) from err
            else:
                self.report_error(f"Invalid connection type: {con_type}")
                self._set_connected(False)
        else:
            self.report_error(f"Invalid connection arguments: {host}:{port}")
            self._set_connected(False)

    def disconnect(self):
        """
        Close the connection to the controller.
        """
        if not self.is_connected():
            self.report_warning("Already disconnected from the controller")
            return
        try:
            self.logger.info('Closing connection to controller')
            if self.sock:
                self.sock.close()
                self.sock = None
            self._set_connected(False)
            self.report_info('Closed connection to controller')
        except Exception as ex:
            raise IOError(f"Failed to close connection: {ex}") from ex

    def _send_command(self, command: str) -> bool:  # pylint: disable=W0221
        """
        Send a message to the controller (adds newline).

        Args:
            command (str): The message to send (e.g., '3A?').
        """
        if not self.is_connected():
            self.report_error("Device is not connected")
            return False
        try:
            self.logger.debug('Sending: %s', command)
            with self.lock:
                self.sock.sendall(command.encode("ascii"))
        except Exception as ex:
            self.report_error(f"Failed to send message: {ex}")
            raise IOError(f'Failed to write message: {ex}') from ex
        self.logger.debug('Command sent')
        return True

    def _read_reply(self) -> bytes:
        """
        Read a response from the controller.

        Returns:
            str: The received message, stripped of trailing newline.
        """
        if not self.is_connected():
            self.report_error("Device is not connected")
            return b''
        try:
            retval = self.sock.recv(25000)
            self.logger.debug('Received: %s', retval.decode("ascii"))
            return retval
        except Exception as ex:
            raise IOError(f"Failed to _read_reply message: {ex}") from ex

    def get_atomic_value(self, item: str ="") -> Union[list[Any], None]:
        """Get the atomic value from the controller."""
        allowed_items = ["temperature", "humidity", "dew_point"]
        if item not in allowed_items:
            self.logger.error("Item not allowed: %s", item)
            return None
        self.get_data()
        ow_data = self.ow_data.read_sensors()
        value_list = []
        for sensor in ow_data:
            value_list.append(sensor[item])
        return value_list

    def get_data(self):
        """Method to get data from OneWire"""
        if not self.is_connected():
            self.connect(self.host, self.port)
        self._send_command(PARAMETER_QUERY)

        response = self._read_reply()

        http_response = response.decode("ascii").split("\r\n")[0]
        try:
            self.__http_response_handler(http_response)
        except HttpResponseError as err:
            print(err)
            sys.exit(1)

        # fresh copy to avoid continual appending
        self.ow_data = ONEWIREDATA()

        while b'</Devices-Detail-Response>' not in response:
            response += self.sock.recv(1024)
        # at this point the server has dropped the connection, so disconnect
        self.disconnect()

        response = response.decode("ascii")
        xml_data = response.split("?>\r\n")[1]
        self.__xml_data_handler(xml_data)

    def __http_response_handler(self, response):
        response_code = int(response.split(' ')[1])

        self.logger.debug("HTTP response received: %s", response_code)
        if response_code != 200:
            raise HttpResponseError(f"Http response error: {response_code}")

    def __xml_data_handler(self, xml_data):
        root = ET.fromstring(xml_data)

        for elem in root.iter():
            tag_elements = elem.tag.split("}")
            elem.tag = tag_elements[1]

        self.logger.debug("XML data received: %s", ET.tostring(root, encoding='unicode'))
        # ET.dump(root)
        # for elem in root.iter():
        #     print(elem.tag, elem.attrib, elem.text)

        for elem in root.iter():
            self.__device_data_handler(elem)

    def __device_data_handler(self, element):
        # pylint: disable=too-many-branches
        if element.tag == "PollCount":
            self.ow_data.poll_count = int(element.text)
        elif element.tag == "DevicesConnected":
            self.ow_data.total_devices = int(element.text)
        elif element.tag == "LoopTime":
            self.ow_data.loop_time = float(element.text)
        elif element.tag == "DevicesConnectedChannel1":
            self.ow_data.ch1_connected = int(element.text)
        elif element.tag == "DevicesConnectedChannel2":
            self.ow_data.ch2_connected = int(element.text)
        elif element.tag == "DevicesConnectedChannel3":
            self.ow_data.ch3_connected = int(element.text)
        elif element.tag == "DataErrorsChannel1":
            self.ow_data.ch1_error = int(element.text)
        elif element.tag == "DataErrorsChannel2":
            self.ow_data.ch2_error = int(element.text)
        elif element.tag == "DataErrorsChannel3":
            self.ow_data.ch3_error = int(element.text)
        elif element.tag == "VoltageChannel1":
            self.ow_data.ch1_voltage = float(element.text)
        elif element.tag == "VoltageChannel2":
            self.ow_data.ch2_voltage = float(element.text)
        elif element.tag == "VoltageChannel3":
            self.ow_data.ch3_voltage = float(element.text)
        elif element.tag == "VoltagePower":
            self.ow_data.voltage_power = float(element.text)
        elif element.tag == "DeviceName":
            self.ow_data.device_name = str(element.text)
        elif element.tag == "HostName":
            self.ow_data.hostname = str(element.text)
        elif element.tag == "MACAddress":
            self.ow_data.mac_address = str(element.text)
        elif element.tag == "DateTime":
            self.ow_data.datetime = str(element.text)
        elif element.tag == "owd_EDS0065":
            self.__sensor_data_handler(element, sensor_type="EDS0065")
        elif element.tag == "owd_EDS0068":
            self.__sensor_data_handler(element, sensor_type="EDS0068")

    def __sensor_data_handler(self, element, sensor_type):
        # pylint: disable=too-many-branches,too-many-statements
        if sensor_type == "EDS0065":
            eds0065_data = EDS0065DATA()
            for sensor in element:
                if sensor.tag == "ROMId":
                    eds0065_data.rom_id = str(sensor.text)
                elif sensor.tag == "Name":
                    eds0065_data.device_type = str(sensor.text)
                elif sensor.tag == "Health":
                    eds0065_data.health = int(sensor.text)
                elif sensor.tag == "Channel":
                    eds0065_data.channel = int(sensor.text)
                elif sensor.tag == "RawData":
                    eds0065_data.raw_data = str(sensor.text)
                elif sensor.tag == "PrimaryValue":
                    data = sensor.text.split(" ")[0]
                    eds0065_data.relative_humidity = float(data)
                elif sensor.tag == "Temperature":
                    eds0065_data.temperature = float(sensor.text)
                elif sensor.tag == "Humidity":
                    eds0065_data.humidity = float(sensor.text)
                elif sensor.tag == "DewPoint":
                    eds0065_data.dew_point = float(sensor.text)
                elif sensor.tag == "Humidex":
                    eds0065_data.humidex = float(sensor.text)
                elif sensor.tag == "HeatIndex":
                    eds0065_data.heat_index = float(sensor.text)
                elif sensor.tag == "Version":
                    eds0065_data.version = float(sensor.text)

            self.ow_data.eds0065_data.append(eds0065_data)
        elif sensor_type == "EDS0068":
            eds0068_data = EDS0068DATA()
            for sensor in element:
                # print(sensor.tag, sensor.attrib, sensor.text)
                if sensor.tag == "ROMId":
                    eds0068_data.rom_id = str(sensor.text)
                elif sensor.tag == "Name":
                    eds0068_data.device_type = str(sensor.text)
                elif sensor.tag == "Health":
                    eds0068_data.health = int(sensor.text)
                elif sensor.tag == "Channel":
                    eds0068_data.channel = int(sensor.text)
                elif sensor.tag == "RawData":
                    eds0068_data.raw_data = str(sensor.text)
                elif sensor.tag == "PrimaryValue":
                    data = sensor.text.split(" ")[0]
                    eds0068_data.relative_humidity = float(data)
                elif sensor.tag == "Temperature":
                    eds0068_data.temperature = float(sensor.text)
                elif sensor.tag == "Humidity":
                    eds0068_data.humidity = float(sensor.text)
                elif sensor.tag == "DewPoint":
                    eds0068_data.dew_point = float(sensor.text)
                elif sensor.tag == "Humidex":
                    eds0068_data.humidex = float(sensor.text)
                elif sensor.tag == "HeatIndex":
                    eds0068_data.heat_index = float(sensor.text)
                elif sensor.tag == "BarometricPressureMb":
                    eds0068_data.pressure_mb = float(sensor.text)
                elif sensor.tag == "BarometricPressureHg":
                    eds0068_data.pressure_hg = float(sensor.text)
                elif sensor.tag == "Light":
                    eds0068_data.illuminance = int(sensor.text)
                elif sensor.tag == "Version":
                    eds0068_data.version = float(sensor.text)
            self.ow_data.eds0068_data.append(eds0068_data)

class HttpResponseError(Exception):
    """Response Error from OneWire"""
    # pass

class DeviceConnectionError(Exception):
    """Device Connection Error from OneWire"""
    # pass


if __name__ == "__main__":
    OW_ADDRESS = "hs1wireblue"
    OW_PORT = 80
    ow = ONEWIRE()
    ow.connect(OW_ADDRESS, OW_PORT)
    ow.get_data()
    ow_sensors = ow.ow_data.read_sensors()
    print(ow_sensors)
