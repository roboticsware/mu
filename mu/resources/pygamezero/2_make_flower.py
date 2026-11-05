from pgzhelper import *

WIDTH = 480
HEIGHT = 270

leaf = Actor('pink_leaf', (WIDTH / 2, HEIGHT / 2), anchor=('middle', 'bottom'))
leaf.scale = 0.5

count = 0

def add_leaf():
    global count
    if count < 6:
        count += 1
    else:
        clock.unschedule(add_leaf)

clock.schedule_interval(add_leaf, 0.5)

def draw():
    for i in range(count):
        leaf.angle = i * 60
        leaf.draw()