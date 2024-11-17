from neopia import *

n = Neosoco()

fd = FaceDetection()
if fd.camera_open(0):
    while True:
        if fd.start_detection() > 0:
            print('Kimdir kirdi!!!')
            n.led_on()
            n.buzzer()
            n.led_off()