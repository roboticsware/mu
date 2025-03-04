from picozero import Robot
from piconethelper import WifiSimplePeripheral


# Motor Pins
robot_rover = Robot(left=(2,3), right=(4,5))

def handle_car(request):
    request = request.strip()
    if "/forward" in request:
        robot_rover.forward()
        print("Moving forward")
    elif "/backward" in request:
        robot_rover.backward()
        print("Moving backward")
    elif "/right" in request:
        robot_rover.right()
        print("Turning right")
    elif "/left" in request:
        robot_rover.left()
        print("Turning left")
    elif "/stop" in request:
        robot_rover.stop()
        print("Stopping")

html = ("""
    <html>
    <head>
        <title>Wi-Fi Car Control</title>
    </head>
    <body>
        <center>
            <form action="./forward">
                <input type="submit" value="Forward" style="height:120px; width:120px" />
            </form>

            <table>
                <tr>
                    <td><form action="./left"><input type="submit" value="Left" class="btn"></form></td>
                    <td><form action="./stop"><input type="submit" value="Stop" class="btn"></form></td>
                    <td><form action="./right"><input type="submit" value="Right" class="btn"></form></td>
                </tr>
            </table>

            <form action="./backward">
                <input type="submit" value="Backward" style="height:120px; width:120px" />
            </form>
        </center>

        <style>
            .btn { height: 120px; width: 120px; }
        </style>
    </body>
    </html>
    """)

wifi = WifiSimplePeripheral("AP")  # or "STA" for Station mode if you want to use an wifi router
webserver = wifi.open_webserver(html, handle_car)
if webserver is None:
    print("Failed to create webserver. Exiting...")
    machine.reset()
