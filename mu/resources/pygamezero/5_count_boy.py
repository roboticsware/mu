from pgzhelper import *

WIDTH = 480
HEIGHT = 270

boy = Actor('boy_1', (WIDTH / 2, HEIGHT / 2))
boy.scale = 0.5
boy.images = ['boy_1', 'boy_2', 'boy_3']
boy.fps = 4

times = 0
pressed = False

def draw():
    screen.fill('white')
    boy.draw()
    screen.draw.text('Times: ' + str(times), (20, 20), color='black')

def update():
    global times, pressed
    if pressed:
        if boy.animate() == 0:
            times += 1
            pressed = False

def on_mouse_down():
    global pressed
    pressed = True