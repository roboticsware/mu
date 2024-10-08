from pgzhelper import *
from pgzhelper import Util
from neopia import *

n = Neosoco()
fd = FaceDetection()

WIDTH = 640
HEIGHT =  480
pygame_img = None
detected = False
red_led = Actor('red_led_off', (600, 60))
red_led.images = ['red_led_on', 'red_led_off']
red_led.scale = 0.5
red_led.fps = 15

fd = FaceDetection()
if fd.camera_open(1) is False:
    game.exit()

def draw():
    if detected:
        screen.blit(pygame_img, (0, 0))
        red_led.draw()
        n.led_on()
        n.buzzer()
        n.led_off()
    else:
        screen.blit('living_room', (0, 0))

def update():
    global pygame_img
    global detected

    frame, faces = fd.start_detection(just_rtn_frame=True)
    pygame_img = Util.opencv_to_pygame_img(frame)

    if faces > 0:
        detected = True
        red_led.next_image()
        print('Detected!!!')
    else:
        detected = False


def on_key_down(key):
    if key == keys.SPACE: 
        game.exit()
