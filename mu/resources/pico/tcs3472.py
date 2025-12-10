from time import sleep_ms
from machine import Pin

# Source code from https://www.az-delivery.de/en/blogs/azdelivery-blog-fur-arduino-und-raspberry-pi/tcs3472-farberkennungssensor-mit-i2c-in-micropython-teil-1

class TCS3472:
    HWADR  = const(0x29)

    ENABLE = const(0x00)
    ATIME  = const(0x01) # 256 âˆ’ Integration Time / 2.4 ms
    WTIME  = const(0x03)
    AILTL  = const(0x04)
    AILTH  = const(0x05)
    AIHTL  = const(0x06)
    AIHTH  = const(0x07)
    PERS   = const(0x0c)
    CONFIG = const(0x0d)
    CONTROL= const(0x0f)
    ID     = const(0x12)
    STATUS = const(0x13)
    CLEARL = const(0x14)
    CLEARH = const(0x15)
    REDL   = const(0x16)
    REDH   = const(0x17)
    GREENL = const(0x18)
    GREENH = const(0x19)
    BLUEL  = const(0x1a)
    BLUEH  = const(0x1b)

    CMD    = const(0x80) # 1 SFunc; 0 RegAdr
    AUTOINC= const(0x20)
    TYPEMASK=const(0x60)
    SFUNC  = const(0x60)
    ADRMASK= const(0x1F)
    CCICLR = const(0x06)

    AIEN   = const(0x10) # ADC-IRQ enable
    WEN    = const(0x08) # Wait enabble
    AEN    = const(0x02) # ADC enable
    PON    = const(0x01) # Power on
    WLONG  = const(0x01) # 256 - Wait Time / 2.4ms

    GAINx1 = const(0x00)
    GAINx4 = const(0x01)
    GAINx16= const(0x02)
    GAINx60= const(0x03)
    GAIN=["x1","x4","x16","x60"]

    AINTMASK=const(1<<4)
    AVALIDMASK=const(0x01)

    PART = {0x44: "TCS34725",
            0x4d: "TCS34727" }

    PERSIST= {0:"every",
            1: 1,
            2: 2,
            3: 3,
            4: 5,
            5: 10,
            6: 15,
            7: 20,
            8: 25,
            9: 30,
            10: 35,
            11: 40,
            12: 45,
            13: 50,
            14: 55,
            15: 60}

    def __init__(self, i2c, itime=100, wtime=3, gain=GAINx1, led=14):
        self.i2c=i2c
        self.Itime=itime
        self.Atime=255
        self.Wtime=255
        self.Again=gain
        self.Wlong=0
        self.LED=Pin(led,Pin.OUT,value=0)
        self.LED.value(0)
        self.running=False
        self.wakeUp()
        print("Constructor of TCS3472-class")
        print("Integration Time",self.setAtime(itime),"ms")
        self.setWtime(wtime)
        print("Wait Time",self.getWait(),"ms")
        self.setGain(gain)
        print("Gain is",self.GAIN[self.getGain()])
        print("Chip is a ",self.getID())

    def writeByte(self, adr, data):
        buf=bytearray(2)
        buf[1]=data & 0xff #
        buf[0]= adr | CMD
        self.i2c.writeto(HWADR,buf)

    def writeWord(self, adr, data):
        buf=bytearray(3)
        buf[1]=data & 0xff #
        buf[2]=data >> 8   # HIGH-Byte first (big endian)
        buf[0]= AUTOINC | adr | CMD
        self.i2c.writeto(HWADR,buf)

    def readByte(self, adr): #Register adresse
        buf=bytearray(1)
        buf[0]= adr | CMD
        self.i2c.writeto(HWADR,buf)
        buf=self.i2c.readfrom(HWADR,1)
        return buf[0]

    def readWord(self, adr): #Register adresse
        buf=bytearray(2)
        buf[0]=AUTOINC | adr | CMD
        self.i2c.writeto(HWADR,buf[0:1])
        buf=self.i2c.readfrom(HWADR,2)
        return buf[0] | buf[1] << 8

    def getStatus(self):
        return self.readByte(STATUS)

    def getEnable(self):
        return self.readByte(ENABLE)

    def getAtime(self):
        return self.readByte(ATIME)

    def getItime(self):
        self.Itime=int(2.4*(256-self.getAtime()))
        return self.Itime

    def getWait(self):
        return 2.4*(256-self.readByte(WTIME))

    def getGain(self):
        return self.readByte(CONTROL)

    def getID(self):
        return self.PART[self.readByte(ID)]

    def getPersistance(self):
        self.fieldVal=self.readByte(PERS)
        return self.PERSIST[self.fieldVal]

    def getThresholds(self):
        low=self.readWord(AILTL)
        high=self.readWord(AIHTL)
        return low,high

    def setThresholds(self,low=0,high=0):
        self.writeWord(AILTL,low)
        self.writeWord(AIHTL,high)

    def setGain(self,val):
        assert val in range(4)
        self.gain=val
        self.writeByte(CONTROL,val)

    def setAtime(self,intTime):
        self.Atime=256-int(intTime/12*5)
        self.writeByte(ATIME, self.Atime)
        self.Itime=int(2.4*(256-self.getAtime()))
        return self.Itime

    def setWtime(self,waitTime):
        assert 2 < waitTime <= 7400
        if waitTime > 614:
            self.setWlong(1)
            wt = waitTime / 12
        else:
            self.setWlong(0)
            wt = waitTime
        self.Wtime=256-int(wt/12*5)
        self.writeByte(WTIME, self.Wtime)

    def setWlong(self, wlong):
        assert wlong in range(2)
        self.Wlong=wlong
        self.writeByte(CONFIG,wlong)

    def setPersistance(self,val):
        assert val in self.PERSIST.values()
        for k,v in self.PERSIST.items():
            if val == v:
                self.fieldVal= k
                self.writeByte(PERS,k)
                return

    def wakeUp(self):
        self.setEnable(pon=1) # Idle State
        sleep_ms(3)
        self.running=True

    def toSleep(self):
        h=self.readByte(ENABLE)
        self.writeByte(ENABLE,h & (255-(PON+AEN)))
        self.running=False


    def setEnable(self, aien=None, wen=None, aen=None, pon=None):
        enable=self.readByte(ENABLE)
        if aien is not None:
            assert aien in [0,1]
            enable &= (255-AIEN)
            enable |= (aien << 4)
        if wen is not None:
            assert wen in [0,1]
            enable &= (255-WEN)
            enable |= (wen <<3)
        if aen is not None:
            assert aen in [0,1]
            enable &= (255-AEN)
            enable |= (aen << 1)
        if pon is not None:
            assert pon in [0,1]
            enable &= (255-PON)
            enable |= pon
        self.writeByte(ENABLE,enable)
        return enable

    def startSingle(self):
        self.wakeUp()
        self.setEnable(aen=1) # Idle and ADC on
        sleep_ms(3) # wait for initialisation
        sleep_ms(int((256-self.Atime)*12/5)+1) # conversion time
        vals=self.getRawValues()
        self.setEnable(pon=1,aen=0)
        return vals

    def start(self,wtime):
        self.wakeUp()
        self.setWtime(wtime)
        self.writeByte(ENABLE, WEN | PON | AEN) # loop
        sleep_ms(int(self.getWait()))
        sleep_ms(self.getItime())

    def stop(self):
        self.setEnable(aen=0, wen=0)

    def getRawValues(self):
        self.clear= self.readWord(CLEARL)
        self.red  = self.readWord(REDL)
        self.green= self.readWord(GREENL)
        self.blue = self.readWord(BLUEL)
        return self.clear,self.red,self.green,self.blue

    def getRGB(self):
        c,r,g,b=self.startSingle()
        if c==0:
            r,g,b=0,0,0
        else:
            r = int(r/c*255+0.5)
            g = int(g/c*255+0.5)
            b = int(b/c*255+0.5)
        return r,g,b

    # Correlated Color Temperature by McCamy
    def calcCCT(self,r,g,b):
        if r==0 and g==0 and b==0:
            return 0
        else:
            X = -0.14282 * r + 1.54924 * g - 0.95641 * b
            Y = -0.32466 * r + 1.57837 * g - 0.73191 * b
            Z = -0.68202 * r + 0.77073 * g + 0.56332 * b
            xc = X/(X+Y+Z)
            yc = Y/(X+Y+Z)
            n = (xc-0.3320)/(0.1858-yc)
            cct=449.0*(n**3) + 3525.0*(n**2) + 6823.3*n + 5520.33
            return int(cct)

    def clearClearChannelIRQ(self):
        buf=bytearray(1)
        buf[0]=SFUNC | CCICLR | CMD
        #print("0b{:08b}".format(buf[0]))
        self.i2c.writeto(HWADR,buf)

    def led(self,val=None):
        if val is not None:
            self.LED.value(val)
        else:
            return self.LED.value()

if __name__ == "__main__":
    from machine import SoftI2C,Pin,PWM
    i2c=SoftI2C(Pin(22),Pin(21))
    tcs=TCS3472(i2c,led=14)

