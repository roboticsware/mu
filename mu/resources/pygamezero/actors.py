from pgzhelper import *
from abc import ABC, abstractmethod


class CheckOutOfScreen(ABC):
    def __init__(self, screen):
        self.s_width, self.s_height = screen

    @abstractmethod
    def is_out_of_screen(self):
        pass


class Bullet(Actor, CheckOutOfScreen):
    def __init__(self, img_name, pos, angle, walls, screen):
        Actor.__init__(self, img_name, pos)
        CheckOutOfScreen.__init__(self, screen)
        self.angle = angle
        self.walls = walls

    def is_out_of_screen(self):
        if self.x > self.s_width or self.x < 0 or \
            self.y > self.s_height or self.y < 0:
            return True
        else:
            return False

    def move(self):
        if self.angle == 0:
            self.x += 5
        elif self.angle == 90:
            self.y -= 5
        elif self.angle == 180:
            self.x -= 5
        elif self.angle == 270:
            self.y += 5


class Explosion(Actor):
    def __init__(self, img_names, pos):
        super().__init__(img_names[0], pos)
        self.images = img_names
        self.fps = 8
        self.duration = 15

    def update(self):
        self.animate()
        self.duration -= 1


class Tank(Actor, CheckOutOfScreen):
    def __init__(self, img_name, pos, angle, walls, screen):
        Actor.__init__(self, img_name, pos)
        CheckOutOfScreen.__init__(self, screen)
        self._original_pos = None
        self.angle = angle
        self.walls = walls
        self.bullets = []
        self.explosions = []


    def is_out_of_screen(self):
        if self.right > self.s_width or self.left < 0 or \
            self.bottom > self.s_height or self.top < 0:
                return True
        else:
            return False

    def move(self):
        self._original_pos = self.pos
        if self.angle == 180:
            self.x -= 2
        elif self.angle == 0:
            self.x += 2
        elif self.angle == 90:
            self.y -= 2
        elif self.angle == 270:
            self.y += 2

        # Check out of screen
        if self.is_out_of_screen():
            self.pos = self._original_pos

        # Check walls
        if self.collidelist(self.walls) != -1:
            self.pos = self._original_pos

    def fire(self, image, sound_obj=None):
        bullet = Bullet(image, self.pos, self.angle, self.walls, (self.s_width, self.s_height))
        self.bullets.append(bullet)
        if sound_obj:
            sound_obj.play()

    def collidelist_bullets(self, tanks):
        tank_index = -1

        for bullet in self.bullets:
            bullet.move()

            # Check out of screen
            if bullet.is_out_of_screen():
                self.bullets.remove(bullet)

            # Check walls
            wall_index = bullet.collidelist(self.walls)
            if wall_index != -1:
                del self.walls[wall_index]
                self.bullets.remove(bullet)

            # Check tanks
            tank_index = bullet.collidelist(tanks)
            if tank_index != -1:
                self.bullets.remove(bullet)
                explosion = Explosion(["explosion3", "explosion4"], \
                    tanks[tank_index].pos)
                self.explosions.append(explosion)

        # Animate explosion
        for explosion in self.explosions:
            explosion.update()
            if explosion.duration == 0:
                self.explosions.remove(explosion)

        return tank_index

    def draw(self):
        super().draw()
        for bullet in self.bullets:
            bullet.draw()
        for explosion in self.explosions:
            explosion.draw()
            