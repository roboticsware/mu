from picozero import Robot
import bluetooth
from piconethelper import BLESimplePeripheral

ble = bluetooth.BLE()
p = BLESimplePeripheral(ble)  # Initialize Bluetooth

robot_rover = Robot(left=(2,3), right=(4,5))

def on_rx(v):
    v = v.strip()  # Clean input
    print("RX", v)

    if v == b'F':
        robot_rover.forward()
        print("Moving forward")
    elif v == b'B':
        robot_rover.backward()
        print("Moving backward")
    elif v == b'R':
        robot_rover.right()
        print("Turning right")
    elif v == b'L':
        robot_rover.left()
        print("Turning left")
    elif v == b's':
        robot_rover.stop()
        print("Stopping")

while True:
    if p.is_connected():
        p.on_write(on_rx)