from pgzhelper import *
import random

WIDTH = 800
HEIGHT = 600

backgrounds = []
background1 = Actor("background1", (WIDTH / 2, HEIGHT / 2))
backgrounds.append(background1)
background2 = Actor("background2", (WIDTH / 2, (HEIGHT / 2) - HEIGHT))
backgrounds.append(background2)
player = Actor("player", (400, 500))

MAX_BULLETS = 3
bullets = []

enemies = []
enemy_bullets = []
explosions = []

score = 0
game_over = False

music.play('main_theme')


def move_player():
    if keyboard.right:
        player.x += 5
    if keyboard.left:
        player.x -= 5
    if keyboard.up:
        player.y -= 5
    if keyboard.down:
        player.y += 5
    if player.right > WIDTH:
        player.right = WIDTH
    if player.left < 0:
        player.left = 0
    if player.bottom > HEIGHT:
        player.bottom = HEIGHT
    if player.top < 0:
        player.top = 0


def shoot_bullets():
    if keyboard.space and len(bullets) < MAX_BULLETS:
        sounds.sfx_sounds_interaction25.play()
        bullet_delay = 5
        bullet = Actor("player_bullet")
        bullet.pos = player.pos
        bullet.angle = 90
        bullets.append(bullet)

    for bullet in bullets:
        bullet.move_forward(15)
        if bullet.y < 0:
            bullets.remove(bullet)


def create_enemies():
    if random.randint(0, 1000) > 980:
        enemy = Actor("enemy1_1")
        enemy.images = ["enemy1_1", "enemy1_2"]
        enemy.fps = 5
        enemy.y = -50
        enemy.x = random.randint(100, WIDTH - 100)
        enemy.direction = random.randint(-100, -80)
        enemies.append(enemy)

    for enemy in enemies:
        enemy.move_in_direction(4)
        enemy.animate()
        if enemy.top > HEIGHT:
            enemies.remove(enemy)
        if random.randint(0, 1000) > 990:
            bullet = Actor("enemy_bullet")
            bullet.pos = enemy.pos
            bullet.angle = random.randint(0, 359)
            enemy_bullets.append(bullet)

    for bullet in enemy_bullets:
        bullet.move_forward(5)
        if bullet.x < 0 or bullet.x > WIDTH or bullet.y < 0 or bullet.y > HEIGHT:
            enemy_bullets.remove(bullet)



def check_collision():
    global score, game_over

    for bullet in bullets:
        enemy_index = bullet.collidelist(enemies)
        if enemy_index != -1:
            bullets.remove(bullet)
            explosion = Actor("explosion1")
            explosion.pos = enemies[enemy_index].pos
            explosion.images = ["explosion1", "explosion2"]
            explosion.fps = 8
            explosion.duration = 15
            explosions.append(explosion)
            del enemies[enemy_index]
#             enemies.remove(enemies[enemy_index])
            score += 1

    for explosion in explosions:
        explosion.animate()
        explosion.duration -= 1
        if explosion.duration == 0:
            explosions.remove(explosion)

    if player.collidelist(enemy_bullets) != -1 or player.collidelist(enemies) != -1:
        game_over = True


def draw_text():
    screen.draw.text("Score " + str(score), (50, 0), color="black", fontsize=30)
    if game_over:
        screen.draw.text(
            "Game over", midbottom=(WIDTH / 2, HEIGHT / 2), color="blue", fontsize=100
        )


def draw():
    for background in backgrounds:
        background.draw()
    player.draw()
    for enemy in enemies:
        enemy.draw()
    for bullet in bullets:
        bullet.draw()
    for explosion in explosions:
        explosion.draw()
    for bullet in enemy_bullets:
        bullet.draw()
    draw_text()


def update():
    for background in backgrounds:
        background.y += 3
        if background.top > HEIGHT:
            background.y = (HEIGHT / 2) - HEIGHT

    create_enemies()
    if game_over == False:
        move_player()
        shoot_bullets()
    check_collision()
