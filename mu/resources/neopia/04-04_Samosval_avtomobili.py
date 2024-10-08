from neopia import *

n =  Neosoco()
n.servo_reset_degree('out1')

def on_press(key):
    if Keyboard.key_to_str(key) == '4':
        n.servo_rotate_by_degree('out1', 'forward', '20', '60')
    elif Keyboard.key_to_str(key) == '1':
        n.servo_rotate_by_degree('out1', 'forward', '20', '0')
    elif key == Keyboard.ESC:
        return False

# Klaviaturning tugmachasini bosganda "on_press" funksiyasi chaqriladi
Keyboard.read(on_press) 