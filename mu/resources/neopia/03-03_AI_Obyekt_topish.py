from neopia import *

n = Neosoco()
od = ObjectDetection() 

if od.camera_open(0):
    while True:
        result = od.start_detection()
        if result:
            obj_names, obj_coords = result
            if 'sports ball' in obj_names:  
                n.led_on('out1', '100')
                n.motor_rotate('both', 'forward', '10')
                wait(1000)
                n.led_off('out1')
            else:
                n.motor_rotate('both', 'left', '10')