from micropython import const
import struct
import bluetooth
import network
import socket
import time
from machine import Pin, ADC


# Advertising payloads are repeated packets of the following form:
#   1 byte data length (N + 1)
#   1 byte type (see constants below)
#   N bytes type-specific data

_ADV_TYPE_FLAGS = const(0x01)
_ADV_TYPE_NAME = const(0x09)
_ADV_TYPE_UUID16_COMPLETE = const(0x3)
_ADV_TYPE_UUID32_COMPLETE = const(0x5)
_ADV_TYPE_UUID128_COMPLETE = const(0x7)
_ADV_TYPE_UUID16_MORE = const(0x2)
_ADV_TYPE_UUID32_MORE = const(0x4)
_ADV_TYPE_UUID128_MORE = const(0x6)
_ADV_TYPE_APPEARANCE = const(0x19)


# Generate a payload to be passed to gap_advertise(adv_data=...).
def advertising_payload(limited_disc=False, br_edr=False, name=None, services=None, appearance=0):
    payload = bytearray()

    def _append(adv_type, value):
        nonlocal payload
        payload += struct.pack("BB", len(value) + 1, adv_type) + value

    _append(
        _ADV_TYPE_FLAGS,
        struct.pack("B", (0x01 if limited_disc else 0x02) + (0x18 if br_edr else 0x04)),
    )

    if name:
        _append(_ADV_TYPE_NAME, name)

    if services:
        for uuid in services:
            b = bytes(uuid)
            if len(b) == 2:
                _append(_ADV_TYPE_UUID16_COMPLETE, b)
            elif len(b) == 4:
                _append(_ADV_TYPE_UUID32_COMPLETE, b)
            elif len(b) == 16:
                _append(_ADV_TYPE_UUID128_COMPLETE, b)

    # See org.bluetooth.characteristic.gap.appearance.xml
    if appearance:
        _append(_ADV_TYPE_APPEARANCE, struct.pack("<h", appearance))

    return payload


def decode_field(payload, adv_type):
    i = 0
    result = []
    while i + 1 < len(payload):
        if payload[i + 1] == adv_type:
            result.append(payload[i + 2 : i + payload[i] + 1])
        i += 1 + payload[i]
    return result


def decode_name(payload):
    n = decode_field(payload, _ADV_TYPE_NAME)
    return str(n[0], "utf-8") if n else ""


def decode_services(payload):
    services = []
    for u in decode_field(payload, _ADV_TYPE_UUID16_COMPLETE):
        services.append(bluetooth.UUID(struct.unpack("<h", u)[0]))
    for u in decode_field(payload, _ADV_TYPE_UUID32_COMPLETE):
        services.append(bluetooth.UUID(struct.unpack("<d", u)[0]))
    for u in decode_field(payload, _ADV_TYPE_UUID128_COMPLETE):
        services.append(bluetooth.UUID(u))
    return services


# This example demonstrates a peripheral implementing the Nordic UART Service (NUS).

# This example demonstrates the low-level bluetooth module. For most
# applications, we recommend using the higher-level aioble library which takes
# care of all IRQ handling and connection management. See
# https://github.com/micropython/micropython-lib/tree/master/micropython/bluetooth/aioble

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

_FLAG_READ = const(0x0002)
_FLAG_WRITE_NO_RESPONSE = const(0x0004)
_FLAG_WRITE = const(0x0008)
_FLAG_NOTIFY = const(0x0010)

# This UUID is for HM-10 BLE module
_UART_UUID = bluetooth.UUID("0000ffe0-0000-1000-8000-00805f9b34fb")
_UART_TX = (
    bluetooth.UUID("0000ffe1-0000-1000-8000-00805f9b34fb"),
    _FLAG_NOTIFY | _FLAG_WRITE_NO_RESPONSE,
)
_UART_RX = (
    bluetooth.UUID("0000ffe2-0000-1000-8000-00805f9b34fb"),
    _FLAG_READ,
)
_UART_SERVICE = (
    _UART_UUID,
    (_UART_TX, _UART_RX),
)

# For Bluetooth
class BLESimplePeripheral:
    def __init__(self, ble, name="mpy-uart"):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._handle_rx, self._handle_tx),) = self._ble.gatts_register_services((_UART_SERVICE,))
        self._connections = set()
        self._write_callback = None
        self._payload = advertising_payload(name=name, services=[_UART_UUID])
        self._advertise()

    def _irq(self, event, data):
        # Track connections so we can send notifications.
        if event == _IRQ_CENTRAL_CONNECT:
            conn_handle, _, _ = data
            print("New connection", conn_handle)
            self._connections.add(conn_handle)
        elif event == _IRQ_CENTRAL_DISCONNECT:
            conn_handle, _, _ = data
            print("Disconnected", conn_handle)
            self._connections.remove(conn_handle)
            # Start advertising again to allow a new connection.
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            conn_handle, value_handle = data
            value = self._ble.gatts_read(value_handle)
            if value_handle == self._handle_rx and self._write_callback:
                self._write_callback(value)

    def send(self, data):
        for conn_handle in self._connections:
            self._ble.gatts_notify(conn_handle, self._handle_tx, data)

    def is_connected(self):
        return len(self._connections) > 0

    def _advertise(self, interval_us=500000):
        print("Starting advertising")
        self._ble.gap_advertise(interval_us, adv_data=self._payload)

    def on_write(self, callback):
        self._write_callback = callback


# For WiFi
class WifiSimplePeripheral:
    def __init__(self, mode="STA", ssid=None, password=None):
        self._write_callback = None

        if mode == "STA":  # Station mode
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)
            if self.wlan.active():
                print("Wi-Fi interface activated successfully!")
            else:
                print("Wi-Fi activation failed!")
            if ssid is None or password is None:
                raise ValueError("SSID and password are required for Station mode")
            self._connect(ssid, password)
        elif mode == "AP":  # Access Point mode
            self.wlan = network.WLAN(network.AP_IF)
            if ssid is None: ssid = "mywifi"
            if password is None: password = "12345678"
            self.wlan.config(ssid = ssid, password = password)
            self.wlan.active(True)
            if not self.wlan.active():
                raise RuntimeError("Failed to activate Wi-Fi interface")
            print(f"Access Point started with SSID and PWD: {ssid} {password}")
        else:
            raise ValueError("Invalid mode. Use 'STA' or 'AP'")

        #Print IP address after activation
        ip_address = self.wlan.ifconfig()[0]
        print(f"Wi-Fi is running in {mode} mode. IP address: {ip_address}")

    def _connect(self, ssid, password, timeout=30):
        try:
            print("Connecting to WiFi...", ssid)
            self.wlan.connect(ssid, password)
            start_time = time.time()
            while not self.wlan.isconnected():
                if time.time() - start_time > timeout:
                    raise OSError("Wi-Fi connection timeout")
            print("Connected to", ssid, "with IP:", self.wlan.ifconfig()[0])
        except OSError as e:
            print("Wi-Fi connection error:", e)
            self.wlan.disconnect()

    def _create_server_socket(self):
        try:
            addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
            tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            tcp_socket.bind(addr)
            tcp_socket.listen(5)
            print("Listening on", addr)
            return tcp_socket
        except Exception as e:
            print("Server creation failed:", e)
            return None  # Ensure it returns None if an error occurs

    def open_webserver(self, html, handle_request):
        srv_socket = self._create_server_socket()
        if srv_socket is None:
            return None
        self._write_callback = handle_request

        try:
            while True:
                client_socket = srv_socket.accept()[0]
                client_socket.send(html)

                # When user sent Post request by pressing a button in the web page
                request = client_socket.recv(1024)
                request = str(request)
                try:
                    request = request.split()[1]
                # The pass is important because we cannot always split a request
                except IndexError:
                    pass
                if request:
                    self._write_callback(request)

                client_socket.close()
        except OSError as e:
            client_socket.close()
            print("Error: connection closed")