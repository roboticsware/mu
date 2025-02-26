import math
import random

# Screen
TITLE = 'pong'
WIDTH = 800
HEIGHT = 600
GAP_FROM_SCR = 20

# Bar
BAR_H = 100
BAR_W = 15

# Ball
vx = 5
vy = 5
BALL_RADIUS = 10
SPEED_UP = 1.05

# Score
FINAL_SCORE = 11
b1_score = -1
b2_score = -1


def reset_ball():
    global vx, vy

    if b1_score == FINAL_SCORE or b2_score == FINAL_SCORE:
        vx = 0
        vy = 0
    else:
        vx = 5
        vy = 5

    # Throw randomly left and right from the center line
    ball.center = (WIDTH/2, random.randint(BALL_RADIUS*2, HEIGHT - BALL_RADIUS*2))
    vx *= random.choice([-1, 1])

def ball_move_collide():
    global vx, vy, b1_score, b2_score

    # Move the ball with speeds vx and vy
    ball.move_ip(vx, vy)

     # Upper or lower wall
    if ball.top < 0 or ball.bottom > HEIGHT:
        vy = -vy  # Reverse the y direction of the velocity
        sounds.wall.play()

    # Left wall
    if ball.left < 0:
        b2_score += 1
        reset_ball()
        sounds.die.play()

    # Right wall
    if ball.right > WIDTH:
        b1_score += 1
        reset_ball()
        sounds.die.play()

def gameover_draw():
    if b1_score == FINAL_SCORE:
        winner = 'Player1'
    else:
        winner = 'Player2'
    screen.draw.text(winner + ' Win!!', (WIDTH/3, HEIGHT/2 - 50), color='blue', fontsize=70)
    screen.draw.text('Press Space to play again', (WIDTH/4, HEIGHT/2 + 50), \
        color='skyblue', fontsize=50)

def bar_move_collide(bar):
    global vx, vy

    if bar == bar1:
        if keyboard.a:
            if bar.y > 0:
                bar.y -= 7
        elif keyboard.z:
            if bar.y + bar.height < HEIGHT:
                bar.y += 7
    else:  # bar2
        if keyboard.up:
            if bar.y > 0:
                bar.y -= 7
        elif keyboard.down:
            if bar.y + bar.height < HEIGHT:
                bar.y += 7

    if bar.colliderect(ball):
        # Jump forward 10 pixels
        if vx < 0:  # bar1
            ball.x += 10
        else:  # bar2
            ball.x -= 10
        vx = -vx  * SPEED_UP  # Reverse the x direction of the velocity
        ''' 공이 윗측 진입하면서 반사판 윗측에 부딪힐 때 또는
            공이 아래측 진입하면서 반사판 아래측에 부딪힐 때는 진입방향 그대로 반사 '''
        if (vy > 0 and ball.centery < bar.centery) or \
            (vy < 0 and ball.centery > bar.centery):
            vy = -vy * SPEED_UP
        sounds.bar.play()


ball = Rect(WIDTH/2, HEIGHT/2, \
        BALL_RADIUS * math.sqrt(2), BALL_RADIUS * math.sqrt(2))
bar1 = Rect(GAP_FROM_SCR, HEIGHT/2 - BAR_H/2, BAR_W, BAR_H)
bar2 = Rect(WIDTH - BAR_W - GAP_FROM_SCR, HEIGHT/2 - BAR_H/2, BAR_W, BAR_H)
bars = [bar1, bar2]


def draw():
    screen.clear()
    # Center line
    screen.draw.line((WIDTH/2, GAP_FROM_SCR), (WIDTH/2, HEIGHT - GAP_FROM_SCR), color='grey')

    # Bar
    for bar in bars:
        screen.draw.filled_rect(bar, 'white')

    # Score
    screen.draw.text(str(b1_score), (WIDTH/4, GAP_FROM_SCR), color='yellow', fontsize=60)
    screen.draw.text(str(b2_score), ((WIDTH/4)*3, GAP_FROM_SCR), color='yellow', fontsize=60)
    if b1_score == FINAL_SCORE or b2_score == FINAL_SCORE:
        gameover_draw()
    else:  # Ball
        screen.draw.filled_circle(ball.center, BALL_RADIUS, 'white')

def update():
    global b1_score, b2_score

    # Bar
    for bar in bars:
        bar_move_collide(bar)

    # Condition of Game Start
    if (b1_score == FINAL_SCORE or b2_score == FINAL_SCORE) or \
        (b1_score == -1 and b2_score == -1):
        if keyboard.space:  
            b1_score = 0
            b2_score = 0
            reset_ball()
    else:  # Ball
        ball_move_collide()