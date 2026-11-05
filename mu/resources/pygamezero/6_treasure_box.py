from pgzhelper import *

WIDTH = 960
HEIGHT = 540

treasure = Actor("treasure_box", (WIDTH / 2, HEIGHT / 2))
treasure.images = ["treasure_box", "treasure_box_o"]

input_text = ""
guide_text = "Please input a password."
input_done = False

input_rect = Rect(350, 450, 200, 50)
guide_rect = Rect(300, 50, 400, 50)
password = "1234"


def draw():
    screen.blit("desert", (0, 0))
    treasure.draw()

    # 안내 텍스트 상자
    screen.draw.filled_rect(guide_rect, 'black')
    screen.draw.textbox(guide_text, guide_rect)

    # 입력 텍스트 상자
    screen.draw.filled_rect(input_rect, "pink")
    screen.draw.textbox(input_text, input_rect)


def on_key_down(key, unicode):
    global input_text, guide_text, input_done

    if input_done:
        return  # 이미 엔터키를 눌렀다면 더 이상 키 입력을 받지 않음

    if key == keys.RETURN:
        input_done = True
        if input_text == password:
            guide_text = "You got it!"
            treasure.image = "treasure_box_o"
            sounds.cheer.play()
        else:
            guide_text = "You failed!"
            sounds.warning.play()

        # 3초 뒤에 게임을 안전하게 종료하도록 시계 비서에게 예약
        clock.schedule(game.exit, 3)

    elif key == keys.BACKSPACE:
        input_text = input_text[:-1]
    else:
        input_text += unicode