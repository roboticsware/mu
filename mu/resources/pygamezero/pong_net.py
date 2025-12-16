import random
import math
from nethelper import NetNode

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

# Score
FINAL_SCORE = 11

# Network
SERVER_IP = 'localhost'  # Relay server's IP addr
is_host = False  # If player is host or not
peer_id = ''     # Peer's ID
MAX_PEERS = 2  # Maximum players
num_peers = 0  # Current players
my_bar = ''


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

    def reinit(self):
        self._b1_score = -1
        self._b2_score = -1

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

    def pos_update(self, center, vel):
        self.centerx, self.centery = center
        self.vx, self.vy = vel

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

    def collide_wall(self, sound_only=False):
        # Upper or lower wall
        if self.top < 0 or self.bottom > HEIGHT:
            if not sound_only:
                self.vy = -self.vy  # Reverse the y direction of the velocity
            sounds.wall.play()

        # Left wall
        if self.left < 0:
            if not sound_only:
                self.reset()
            sounds.die.play()
            return 'b2'

        # Right wall
        if self.right > WIDTH:
            if not sound_only:
                self.reset()
            sounds.die.play()
            return 'b1'
        
        return ''

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

    def pos_update(self, center):
        self.centerx, self.centery = center

    def collide_ball(self, sound_only=False):
        if self.colliderect(self.ball):
            if not sound_only:
                # Jump forward 10 pixels
                if self.ball.vx < 0:  # bar1
                    self.ball.x += 10
                else:  # bar2
                    self.ball.x -= 10
                self.ball.vx = -self.ball.vx  * SPEED_UP # Reverse the x direction of the velocity
                ''' 공이 윗측 진입하면서 반사판 윗측에 부딪힐 때 또는
                    공이 아래측 진입하면서 반사판 아래측에 부딪힐 때는 진입방향 그대로 반사 '''
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
net = NetNode()

def connect_server():
    global is_host, peer_id, my_bar
    
    # First connected person will be host(Player1) 
    if net.connect(SERVER_IP, "Player1", "pong_game", wait=True):
        is_host = True
        peer_id = "Player2"
        my_bar = bar1
        print("Connected as host (Player 1)")
    else:  # If the host exists, the other will be peer(Player2)
        if net.connect(SERVER_IP, "Player2", "pong_game", wait=True):
            is_host = False
            peer_id =  "Player1"
            my_bar = bar2
            print("Connected as peer (Player 2)")
        else:
            print("Failed to connect. The group is full.")
            exit()

# Make a connection to server before the game starts
connect_server()

def draw():
    screen.clear()
    screen.draw.line((WIDTH/2, GAP_FROM_SCR), (WIDTH/2, HEIGHT - GAP_FROM_SCR), \
        color='grey')
    if not score.is_game_over():
        ball.draw()
    bar1.draw()
    bar2.draw()
    score.draw()
    if num_peers < MAX_PEERS:
        screen.draw.text('Waiting for a peer connection...', (WIDTH/6, HEIGHT/2), color='blue', fontsize=50)


def handle_recv_messages():
    # Should be called repeately to receive the messages
    net.process_recv()

    # Seperation of specific messages
    game_start = net.get_msg(peer_id, 'game_start')
    bar_pos = net.get_msg(peer_id, 'bar_pos', clear=False)
    ball_pos = net.get_msg("Player1", 'ball_pos', clear=False)
    who_win = net.get_msg("Player1", 'score')

    # Game Start
    if game_start:
        score.reset()
        ball.reset()

    # Ball
    if ball_pos:
        ball.pos_update(ball_pos['center'], ball_pos['vel'])

    # Bar
    if bar_pos:
        if is_host:
            bar2.pos_update(bar_pos)
        else:  # Plyer2
            bar1.pos_update(bar_pos)

    # Score
    if who_win:
        score.add(who_win)


def update():
    global num_peers

    # Process the messages from the network
    handle_recv_messages()

    # Bar
    if keyboard.a or keyboard.up:
        my_bar.up()
    if keyboard.z or keyboard.down:
        my_bar.down()
    net.send_msg(peer_id, 'bar_pos', my_bar.center)

    for bar in bars:
        if is_host:
            bar.collide_ball()
        else:  # Plyer2
            bar.collide_ball(sound_only=True)

    # Condition of Game Start
    if score.is_game_over():
        # Either one can start the game first
        if num_peers == MAX_PEERS and keyboard.space: 
            score.reset()
            ball.reset()
            net.send_msg(peer_id, 'game_start', True)
    else:  # Ball
        if is_host:
            ball.move()
            net.send_msg('Player2', 'ball_pos', {'center':ball.center, 'vel':(ball.vx, ball.vy)})
            who_win = ball.collide_wall()
            if who_win:  # Score
                score.add(who_win)
                net.send_msg('Player2', 'score', who_win)
                ball.reset()
        else:  # Plyer2
            ball.move()
            ball.collide_wall(sound_only=True)

    # Peer's disconnection
    num_peers = len(net.get_peers())
    if num_peers < MAX_PEERS:
        if is_host:
            score.reinit()
            ball.reset()
        else:  # Plyer2 
            print("The host is disconnected.")
            exit()  # If the peer is host, exit the game

    # Should be called repeately to send the messages
    net.process_send()