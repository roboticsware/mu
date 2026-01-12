from neopia import *

n = Neosoco()

while True:  
    Voice.tts("I'm hearing. Please speak in 3 secconds.")
    print("Eshityapman. 3 soniya ichida gapirib bering.")
    result = Voice.stt()
    print(result)
    if result == "Chiroqni yoq":
        n.led_on()
        wait(3000)
        break
    elif result == "Chiroqni o'chir":
        n.led_off()
        break
