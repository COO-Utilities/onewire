"""
Onewire Controller Interface
"""
import asyncio
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
import sys
from typing import List


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

class ONEWIRE:
    """Class for interfacing with OneWire"""
    # pylint: disable=too-many-instance-attributes
    def __init__(self, address, timeout=1, log=True, quiet=True):
        self.address = address
        self.http_port = 80
        self.udp_port = 30303
        self.tcp_port = 15145
        self.timeout = timeout

        self.ow_data = ONEWIREDATA()

        self.reader = None
        self.writer = None

        # Initialize logger
        if log:
            logfile = __name__.rsplit('.', 1)[-1] + '.log'
            self.logger = logging.getLogger(logfile)
            if not self.logger.handlers:
                if quiet:
                    self.logger.setLevel(logging.INFO)
                else:
                    self.logger.setLevel(logging.DEBUG)
                formatter = logging.Formatter(
                    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
                file_handler = logging.FileHandler(logfile)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)
        else:
            self.logger = None

        if self.logger:
            self.logger.info("Logger initialized for ONEWIRE")

    async def __aenter__(self):
        try:
            self.reader, self.writer = await asyncio.open_connection(self.address, self.http_port)
            if self.logger:
                self.logger.info("Connected to %s:%d", self.address, self.http_port)
        except ConnectionRefusedError as err:
            if self.logger:
                self.logger.error("Connection refused: %s", err)
            raise DeviceConnectionError(f"Could not connect to {self.address}") from err
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            if self.logger:
                self.logger.info("Connection closed")
                logging.shutdown()
                self.logger = None

    async def get_data(self):
        """Method to get data from OneWire"""
        query = "GET /details.xml HTTP/1.1\r\n\r\n"
        self.writer.write(query.encode("ascii"))
        await self.writer.drain()

        http_response = await self.reader.readuntil(b'\r\n')
        try:
            self.__http_response_handler(http_response)
        except HttpResponseError as err:
            print(err)
            sys.exit(1)

        while True:
            next_response = await self.reader.readuntil(b'\r\n')
            next_response = next_response.decode("ascii")
            next_response = next_response.split(' ')[0]
            if next_response == "<?xml":
                break

        xml_data = await self.reader.readuntil(b'</Devices-Detail-Response>\r\n')
        self.__xml_data_handler(xml_data)

    def __http_response_handler(self, response):
        response = response.decode("ascii")
        response_code = int(response.split(' ')[1])

        if response_code == 404:
            raise HttpResponseError(f"Http response error: {response_code}")
        # elif response_code == 200:
        #    return

    def __xml_data_handler(self, xml_data):
        root = ET.fromstring(xml_data)
        # ET.register_namespace("", "http://www.embeddeddatasystems.com/schema/owserver")
        for elem in root.iter():
            tag_elements = elem.tag.split("}")
            elem.tag = tag_elements[1]

        if self.logger:
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

async def test_onewire(ow_address) -> ONEWIREDATA:
    """Method to test connection to OneWire"""
    async with ONEWIRE(ow_address) as ow:
        await ow.get_data()

    return ow.ow_data


if __name__ == "__main__":
    OW_ADDRESS = ""
    ow_data = asyncio.run(test_onewire(OW_ADDRESS))
    ow_sensors = ow_data.read_sensors()
    print(ow_sensors)
