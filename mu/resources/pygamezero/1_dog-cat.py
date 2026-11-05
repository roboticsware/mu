from pgzhelper import *

WIDTH = 480
HEIGHT = 270

dog = Actor('dog', (100, 150))
dog.scale = 0.5
cat = Actor('cat', (350, 150))
cat.scale = 0.5
cat.flip_x = True

def draw():
    screen.fill('white')
    dog.draw()
    cat.draw()

def dog_talk1():
    dog.say("Bow-wow")

def cat_talk1():
    cat.say("Meow")

def dog_talk2():
    dog.say("Good bye!")

def cat_talk2():
    cat.say("See you!")

clock.schedule(dog_talk1, 1)
clock.schedule(cat_talk1, 2)
clock.schedule(dog_talk2, 4)
clock.schedule(cat_talk2, 6)

