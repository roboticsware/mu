import random
import math

# Screen
TITLE = 'pong'
WIDTH = 800
HEIGHT = 600

# Bar
BAR_H = 100
BAR_W = 15
GAP_FROM_SCR = 20

# Ball
BALL_RADIUS = 10
VELOCITY = 5
SPEED_UP = 1.08

# Scoree
FINAL_SCORE = 11


class Score():
    '''
    Shows scores and a winner on the screen
    '''
    def __init__(self, final_score):
        self._final_score = final_score
        self._b1_score = -1
        self._b2_score = -1
        
    def _gameover_draw(self):
        winner = ''
        if self._b1_score == self._final_score:
            winner = 'Player1'
        elif self._b2_score == self._final_score:
            winner = 'Player2'
        if winner:
            screen.draw.text(winner + ' Win!!', (WIDTH/3, HEIGHT/2 - 50), color='blue', fontsize=70)
        screen.draw.text('Press Space to play again', (WIDTH/4, HEIGHT/2 + 50), color='skyblue', fontsize=50)

    def is_game_over(self):
        if (self._b1_score == self._final_score or self._b2_score == self._final_score) \
            or (self._b1_score == -1 and self._b2_score == -1):
            return True
        else:
            return False
        
    def add(self, who):
        if who == 'b1':
            self._b1_score += 1
        elif who == 'b2':
            self._b2_score += 1

    def reset(self):
        self._b1_score = 0
        self._b2_score = 0

    def draw(self):
        screen.draw.text(str(self._b1_score), (WIDTH/4, GAP_FROM_SCR), color='yellow', fontsize=60)
        screen.draw.text(str(self._b2_score), ((WIDTH/4)*3, GAP_FROM_SCR), color='yellow', fontsize=60)
        if self.is_game_over():
            self._gameover_draw()


class Ball(Rect):
    '''
    Ball motion (position, movement) and collision detection
    '''

    def __init__(self, start_pos, velocity, score):
        super().__init__(0, 0, BALL_RADIUS * math.sqrt(2), BALL_RADIUS * math.sqrt(2))
        self.center = start_pos
        self._velocity = velocity
        self.vx = self.vy = self._velocity
        self._score = score
        
    def reset(self):            
        if self._score.is_game_over():
            self.vx = self.vy = 0
        else:
            self.vx = self.vy = self._velocity
            self.vx *= random.choice([-1, 1])
            
        # Throw randomly left or right from the center line
        self.center = (WIDTH/2 , random.randint(BALL_RADIUS*2, \
            HEIGHT - BALL_RADIUS*2))
            
    def move(self):
        # Move the ball with speeds vx and vy
        self.move_ip(self.vx, self.vy)

    def collide_wall(self):
        # Upper or lower wall
        if self.top < 0 or self.bottom > HEIGHT:
            self.vy = -self.vy  # Reverse the y direction of the velocity
            sounds.wall.play()

        # Left wall
        if self.left < 0:
            self._score.add('b2')
            sounds.die.play()
            self.reset()

        # Right wall
        if self.right > WIDTH:
            self._score.add('b1')
            sounds.die.play()
            self.reset()

    def draw(self):
        screen.draw.filled_circle(self.center, BALL_RADIUS, 'white')


class Bar(Rect):
    def __init__(self, x, y, ball):
        super().__init__(x, y, BAR_W, BAR_H)
        self.ball = ball

    def up(self):
        if self.y > 0:
            self.y -= 7

    def down(self):
        if self.y + self.height < HEIGHT:
            self.y += 7

    def collide_ball(self):
        if self.colliderect(self.ball):
            # Jump forward 10 pixels
            if self.ball.vx < 0:  # bar1
                self.ball.x += 10
            else:  # bar2
                self.ball.x -= 10
            self.ball.vx = -self.ball.vx  * SPEED_UP  # Reverse the x direction of the velocity
            ''' When the ball hits the top of the bar, or hits the bottom of the bar,
                it is reflected in the same direction as the ball hit. '''
            if (self.ball.vy > 0 and self.ball.centery < self.centery) or \
                (self.ball.vy < 0 and self.ball.centery > self.centery):
                self.ball.vy = -self.ball.vy * SPEED_UP
            sounds.bar.play()

    def draw(self):
        screen.draw.filled_rect(self, 'white')


# Create main actor objects
score = Score(FINAL_SCORE)
ball = Ball((WIDTH/2, HEIGHT/2), VELOCITY, score)
bar1 = Bar(GAP_FROM_SCR, HEIGHT/2 - BAR_H/2, ball)
bar2 = Bar(WIDTH - BAR_W - GAP_FROM_SCR, HEIGHT/2 - BAR_H/2, ball)
bars = [bar1, bar2]


def draw():
    screen.clear()
    screen.draw.line((WIDTH/2, GAP_FROM_SCR), (WIDTH/2, HEIGHT - GAP_FROM_SCR), \
        color='grey')
    if not score.is_game_over():
        ball.draw()
    bar1.draw()
    bar2.draw()
    score.draw()

def update():
    # Bar
    if keyboard.a:
        bar1.up()
    if keyboard.z:
        bar1.down()
    if keyboard.up:
        bar2.up()
    if keyboard.down:
        bar2.down()
    for bar in bars:
        bar.collide_ball()

    # Condition of Game Start
    if score.is_game_over():
        if keyboard.space: 
            score.reset()
            ball.reset()
    else:  # Ball
        ball.move()
        ball.collide_wall()