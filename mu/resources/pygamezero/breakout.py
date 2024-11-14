from pgzhelper import *

TITLE = 'Breakout'
WIDTH = 800
HEIGHT = 600

GAP_FROM_SCREEN = 50
ball = Actor('ball', (WIDTH / 2, HEIGHT / 2))
ball.radius = ball.width / 2
bar = Actor('bar', (WIDTH / 2, HEIGHT - GAP_FROM_SCREEN))

# Create 4 x 8 block dummy
blocks = []
for block_row in range(4):
    for block_col in range(8):
        block = Actor(
            'block', 
            (block_col * 100, block_row * 32 + GAP_FROM_SCREEN),
            anchor=('left', 'top')
        )
        blocks.append(block)

# Set velocity of ball
vx = 5
vy = -5


def draw():
    screen.blit('background', (0, 0))
    ball.draw()
    bar.draw()
    for block in blocks:
        block.draw()
        
def update():
    global vx, vy
    
    # Limit the movement of bar in the window
    if bar.left < 0:
        bar.left = 0
    if bar.right > WIDTH:
        bar.right = WIDTH
    
    # Move the ball by velocity
    ball.move_ip(vx, vy)

    # When the ball hits left or rignt wall
    if ball.left < 0 or ball.right > WIDTH:
        vx = -vx  # Make x of velocity opposite direction
        sounds.wall.play()
        
    # When the ball hits upper wall
    if ball.top < 0: 
        vy = -vy  # Make y of velocity opposite direction
        sounds.wall.play()
        
    # When the ball hits the bar
    if ball.circle_colliderect(bar) == True:
        ball.y -= 10  # 10픽셀 수직으로 먼저 튀어오르기
        vy = -vy  # Make y of velocity opposite direction
        sounds.bar.play()
        
    # When the ball hits the block
    b_index = ball.collidelist(blocks) 
    if b_index != -1:
        vy = -vy  # Make y of velocity opposite direction
        sounds.block.play()
        blocks.pop(b_index)
        
    # Exit the game
    if ball.bottom > HEIGHT:
        sounds.die.play()
        game.exit()
        
    if not blocks:
        sounds.win.play()
        vx = 0
        vy = 0

def on_mouse_move(pos):
    x, y = pos
    bar.centerx = x