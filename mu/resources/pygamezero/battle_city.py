from pgzhelper import *
import random

WIDTH = 800
HEIGHT = 600

bullets = []
bullet_delay_cnt = 0
BULLET_DELAY = 50
enemy_bullets = []
explosions = []
winner = ''

tank = Actor("tank_blue", (400, 575))
tank.angle = 90

ENEMY_MOVE_DELAY = 20
MAX_ENEMIES = 3
enemies = []
for i in range(MAX_ENEMIES):
    enemy = Actor("tank_red")
    enemy.angle = 270
    enemy.x = (i + 1) * WIDTH / (MAX_ENEMIES + 1)
    enemy.y = 25
    enemy.move_cnt = 0
    enemies.append(enemy)

walls = []
WALL_SIZE = 50
# 50x50 pixel sized walls
for x in range(int(WIDTH / WALL_SIZE)):  
    # Substract 2 to blank both first and last row
    for y in range(int(HEIGHT / WALL_SIZE - 2)):  
        # Randomly leave blank without wall
        if random.randint(0, 100) < 50:  
            wall = Actor("wall", anchor=("left", "top"))
            wall.x = x * WALL_SIZE
            wall.y = y * WALL_SIZE + WALL_SIZE  # Add WALL_SIZE to blank first row
            walls.append(wall)


def move_player(player):
    # Save the original position of the tank
    original_x = player.x
    original_y = player.y

    if player == tank:  # My tank
        if keyboard.right:
            player.angle = 0
            player.x += 2
        elif keyboard.left:
            player.angle = 180
            player.x -= 2
        elif keyboard.up:
            player.angle = 90
            player.y -= 2
        elif keyboard.down:
            player.angle = 270
            player.y += 2
    else:  # Enemy
        if player.angle == 0:
            player.x += 2
        elif player.angle == 90:
            player.y -= 2
        elif player.angle == 180:
            player.x -= 2
        elif player.angle == 270:
            player.y += 2

    # Return player to original position if colliding with wall
    if player.collidelist(walls) != -1:
        player.x = original_x
        player.y = original_y

    # Don't drive off the screen!
    if player.left < 0 or player.right > WIDTH \
        or player.top < 0 or player.bottom > HEIGHT:
        player.x = original_x
        player.y = original_y


def fire_bullets(player, bullets):
    if player == tank:
        bullet = Actor("bulletblue2")
    else:
        bullet = Actor("bulletred2")

    bullet.angle = player.angle
    bullet.pos = player.pos
    bullets.append(bullet)


def collide_bullets(bullets):
    global winner

    for bullet in bullets:
        if bullet.angle == 0:
            bullet.x += 5
        elif bullet.angle == 90:
            bullet.y -= 5
        elif bullet.angle == 180:
            bullet.x -= 5
        elif bullet.angle == 270:
            bullet.y += 5

        # Walls
        wall_index = bullet.collidelist(walls)
        if wall_index != -1:
            del walls[wall_index]
            bullets.remove(bullet)
        
        # Out of screen
        if bullet.x < 0 or bullet.x > 800 \
            or bullet.y < 0 or bullet.y > 600:
            bullets.remove(bullet)

        # Enemies
        if bullets != enemy_bullets:
            enemy_index = bullet.collidelist(enemies)
            if enemy_index != -1:
                bullets.remove(bullet)
                explosion = Actor("explosion3")
                explosion.pos = enemies[enemy_index].pos
                explosion.images = ["explosion3", "explosion4"]
                explosion.fps = 8
                explosion.duration = 15
                explosions.append(explosion)
                del enemies[enemy_index]
                if len(enemies) == 0:
                    winner = "You"
        else:
            if bullet.colliderect(tank):
                winner = "Enemy"

    # Animate explosion
    for explosion in explosions:
        explosion.animate()
        explosion.duration -= 1
        if explosion.duration == 0:
            explosions.remove(explosion)


def draw():
    screen.blit('grass', (0, 0))
    tank.draw()
    for enemy in enemies:
        enemy.draw()
    for wall in walls:
        wall.draw()
    for bullet in bullets:
        bullet.draw()
    for bullet in enemy_bullets:
        bullet.draw()
    for explosion in explosions:
        explosion.draw()

    if winner:
        screen.draw.text(winner + " Win!", \
            midbottom=(WIDTH / 2, HEIGHT / 2), fontsize=100)


def update():
    global bullet_delay_cnt, enemy_move_cnt

    # This part is for my tank
    if winner == '':
        move_player(tank)
        if bullet_delay_cnt == 0:  # Re-launch possible after the delay ends
            if keyboard.space:
                sounds.sfx_exp_medium12.play()
                fire_bullets(tank, bullets)
                bullet_delay_cnt = BULLET_DELAY
        else:
            bullet_delay_cnt -= 1
        collide_bullets(bullets)

    # This part is for the enemies
    for enemy in enemies:
        choice = random.randint(0, 2)
        if enemy.move_cnt > 0:  # Move tank
            enemy.move_cnt -= 1
            move_player(enemy)
        elif choice == 0:  # Init movement delay
            enemy.move_cnt = ENEMY_MOVE_DELAY
        elif choice == 1:  # Turn directions
            enemy.angle = random.randint(0, 3) * 90
        else:  # Fire canon shot
            fire_bullets(enemy, enemy_bullets)
    collide_bullets(enemy_bullets)
