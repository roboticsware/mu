from pgzhelper import *

WIDTH = 960
HEIGHT = 540

treasure = Actor("treasure_box", (WIDTH / 2, HEIGHT / 2))
treasure.images = ["treasure_box", "treasure_box_o"]

input_text = ""
input_done = False
input_rect = Rect(350, 450, 200, 50)

guide_rect = Rect(300, 50, 400, 50)
password = "1234"

def draw():
    screen.blit("desert", (0, 0))
    treasure.draw()

    # Guide textbox
    screen.draw.filled_rect(guide_rect, 'black')
    if input_done:
        if input_text == password:
            screen.draw.textbox("You got it!", guide_rect)
        else:
            screen.draw.textbox("You failed!", guide_rect)

        pygame.display.update()
        game.exit()
    else:
        screen.draw.textbox("Please input a password.", guide_rect)

    # Input textbox
    screen.draw.filled_rect(input_rect, "pink")
    screen.draw.textbox(input_text, input_rect)


def update():
    if input_done:
        if input_text == password:
            treasure.sel_image("treasure_box_o")
            sounds.cheer.play()
        else:
            sounds.warning.play()


def on_key_down(key, unicode):
    global input_text, input_done

    if key == keys.RETURN:
        input_done = True
    elif key == keys.BACKSPACE:
        input_text = input_text[:-1]
    else:
        input_text += unicode