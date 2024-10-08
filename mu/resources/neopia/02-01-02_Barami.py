# Klaviatura orqali Baramining tezligini boshqarish

from neopia import *

n =  Neosoco()

def on_press(key):
    if Keyboard.key_to_str(key) == '0':
        n.motor_stop('right')
    elif Keyboard.key_to_str(key) == '1':
        n.motor_rotate('right', 'forward', '10')
    elif Keyboard.key_to_str(key) == '2':
        n.motor_rotate('right', 'forward', '50')
    elif Keyboard.key_to_str(key) == '3':
        n.motor_rotate('right', 'forward', '100')
    elif key == Keyboard.ESC:
        return False
    
# Klaviaturning tugmachasini bosganda "on_press" funksiyasi chaqriladi
Keyboard.read(on_press)    