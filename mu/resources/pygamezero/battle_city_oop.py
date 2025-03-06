import random
from actors import Tank

WIDTH = 800
HEIGHT = 600

winner = ""

# Delay of Enemy tank's moving
enemy_move_cnt = 0
ENEMY_MOVE_DELAY = 20

# Delay of My tank's bullet re-loading
bullet_delay_cnt = 0
BULLET_DELAY = 50

# 50x50 pixel sized walls
walls = []
WALL_SIZE = 50
for x in range(int(WIDTH / WALL_SIZE)):
    # # Substract 2 to blank both first and last row
    for y in range(int(HEIGHT / WALL_SIZE - 2)):
        # Randomly leave blank without wall
        if random.randint(0, 100) < 50:
            wall = Actor("wall", anchor=("left", "top"))
            wall.x = x * WALL_SIZE
            wall.y = y * WALL_SIZE + WALL_SIZE  # Add WALL_SIZE to blank first row
            walls.append(wall)

# Creation of My tank
tank = Tank("tank_blue", (400, 575), 90, walls, (WIDTH, HEIGHT))

# Creation of Enemy tank
enemies = []
MAX_ENEMIES = 3
for i in range(MAX_ENEMIES):
    enemies.append(Tank("tank_red", (400, 25), 270, walls, (WIDTH, HEIGHT)))


def draw():
    screen.blit("grass", (0, 0))  # Draw background
    tank.draw()
    for enemy in enemies:
        enemy.draw()
    for wall in walls:
        wall.draw()
    if winner:
        screen.draw.text(
            winner + " Win!", midbottom=(WIDTH / 2, HEIGHT / 2), fontsize=100
        )

def update():
    global enemy_move_cnt, bullet_delay_cnt, winner

    # My tank
    if winner == "":
        if keyboard.left:
            tank.angle = 180
            tank.move()
        elif keyboard.right:
            tank.angle = 0
            tank.move()
        elif keyboard.up:
            tank.angle = 90
            tank.move()
        elif keyboard.down:
            tank.angle = 270
            tank.move()

        if bullet_delay_cnt == 0:  # Re-lading possible after the delay ends
            if keyboard.space:
                tank.fire("bulletblue2", sounds.sfx_exp_medium12)
                bullet_delay_cnt = BULLET_DELAY
        else:
            bullet_delay_cnt -= 1

        enemy_idx = tank.collidelist_bullets(enemies)
        if enemy_idx != -1:
            del enemies[enemy_idx]
            if len(enemies) == 0:
                winner = "You"

    # Enemy tank
    for enemy in enemies:
        choice = random.randint(0, 3)
        if enemy_move_cnt > 0:  # Move tank
            enemy_move_cnt -= 1
            enemy.move()
        elif choice == 0:  # Init movement delay
            enemy_move_cnt = ENEMY_MOVE_DELAY
        elif choice == 1:  # Turn directions
            enemy.angle = random.randint(0, 3) * 90
        else:  # Fire canon shot
            enemy.fire("bulletred2")

        tank_idx = enemy.collidelist_bullets([tank])
        if tank_idx != -1:
            winner = "Enemy"
