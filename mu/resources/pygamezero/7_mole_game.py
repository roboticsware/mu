from pgzhelper import *
import random

WIDTH = 960
HEIGHT = 540

hammer = Actor('toy_hammer', (WIDTH / 2, HEIGHT / 2))
hammer.scale = 0.5
hammer.angle = 40
az
score = 0
hammer_pressed = False

GAP_FROM_SCR = 50
moles = []
for _ in range(6):
    mole = Actor('mole')
    mole.scale = 0.5
    mole.anchor = ('left', 'top')
    x = random.randint(GAP_FROM_SCR, WIDTH - mole.width - GAP_FROM_SCR)
    y = random.randint(GAP_FROM_SCR, HEIGHT - mole.height - GAP_FROM_SCR)
    mole.pos = (x, y)
    mole.visible = False
    moles.append(mole)


def draw():
    screen.blit('field', (0, 0))

    for mole in moles:
        if mole.visible:
            mole.draw()

    hammer.draw()
    screen.draw.text('Score: ' + str(score), (20, 20), color='black')


def update():
    global score

    if random.randint(0, 10) == 0 and len(moles) > 0:
        mole = random.choice(moles)
        mole.visible = not mole.visible

    if hammer_pressed:
        for mole in moles:
            if mole.visible and mole.collide_pixel(hammer):
                sounds.toi.play()
                moles.remove(mole)
                score += 1
                if len(moles) == 0:
                    clock.schedule(game.exit, 2)
                break


def on_mouse_move(pos):
    hammer.pos = pos


def on_mouse_down():
    global hammer_pressed
    animate(hammer, angle=75, tween='accelerate', duration=0.1, on_finished=animation_done)
    hammer_pressed = True


def animation_done():
    global hammer_pressed
    animate(hammer, angle=40, tween='accelerate', duration=0.1)
    hammer_pressed = False