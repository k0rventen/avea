# Control of an Elgato Avea bulb using Python

[![PyPI](https://img.shields.io/pypi/v/avea.svg)](https://pypi.org/project/avea/)
[![Language grade: Python](https://img.shields.io/lgtm/grade/python/g/k0rventen/avea.svg?)](https://lgtm.com/projects/g/k0rventen/avea/context:python)
[![Build Status](https://travis-ci.com/k0rventen/avea.svg?branch=master)](https://travis-ci.com/k0rventen/avea)


The [Avea bulb from Elgato](https://www.amazon.co.uk/Elgato-Avea-Dynamic-Light-Android-Smartphone/dp/B00O4EZ11Q) is a light bulb that connects to an iPhone or Android app via Bluetooth.

This project aim to control it using a Bluetooth 4.0 compatible device and some Python magic.

Tested on Raspberry Pi 3 and Zero W (with integrated bluetooth). 

- [Control of an Elgato Avea bulb using Python](#control-of-an-elgato-avea-bulb-using-python)
  - [TL;DR](#tldr)
  - [Library usage](#library-usage)
  - [Code documentation](#code-documentation)
  - [Reverse engineering of the bulb](#reverse-engineering-of-the-bulb)
  - [Communication protocol](#communication-protocol)
    - [Intro](#intro)
    - [Commands and payload explanation](#commands-and-payload-explanation)
    - [Color command](#color-command)
    - [Brightness command](#brightness-command)
  - [Walkthrough & Example](#walkthrough--example)
    - [Brightness](#brightness)
      - [Color](#color)
  - [Python implementation](#python-implementation)
    - [One-liner for color computation](#one-liner-for-color-computation)
    - [Bluepy writeCharacteristic() overwrite](#bluepy-writecharacteristic-overwrite)
    - [Working with notifications using Bluepy](#working-with-notifications-using-bluepy)
  - [TODO](#todo)

## TL;DR

The lib requires [bluepy](https://github.com/IanHarvey/bluepy), so we must install the following dependancy, wheter we use pip or install from source.

**Dependancies**

```
sudo apt install libglib2.0-dev
```

**Then install from pip3**

```bash
sudo apt install python3-pip
sudo pip3 install --upgrade avea
```

**or if you prefer installing from source**

```bash
git clone https://github.com/k0rventen/avea
cd avea
sudo python3 setup.py install
```

## Library usage

You can check the example script `example.py`, to try it directly onto your bulbs :

```bash
sudo python3 example.py
```

Below is a quick how-to of the various methods of the library.

**Note : the discover\_avea\_bulbs() function needs root privileges, due to bluepy's scan(). From your user, you can use sudo -E.**

```python
import avea # Important !

# Get nearby bulbs in a list, then retrieve the name of all bulbs
# using this method requires root privileges (because of bluepy's scan() )
nearbyBulbs = avea.discover_avea_bulbs()
for bulb in nearbyBulbs:
    bulb.get_name()
    print(bulb.name)

# Or create a bulb if you know its address (after a scan for example)
myBulb = avea.Bulb("xx:xx:xx:xx:xx:xx")

# You can set the brightness, color and name
myBulb.set_brightness(2000)                 # ranges from 0 to 4095
myBulb.set_color(0,4095,0,0)                # in order : white, red, green, blue
myBulb.set_rgb(0,255,0)                     # RGB compliant function
myBulb.set_smooth_transition(255,255,0,4,30)   # change to rgb(255,255,0) in 4s with 30 iterations per second
myBulb.set_name("bedroom")                  # new name of the bulb

# And get the brightness, color and name
print(myBulb.get_name())                # Query the name of the bulb
theColor = myBulb.get_color()           # Query the current color
theRgbColor = myBulb.get_rgb()          # Query the bulb in a RGB format
theBrightness = myBulb.get_brightness() # query the current brightness
theAddr = myBulb.addr                   # query the bulb Bluetooth addr
theFwVersion = myBulb.get_fw_version()  # query the bulb firmware version
```

That's it. Pretty simple.

Check the explanations below for more informations, or check the sources !


## Code documentation

## Reverse engineering of the bulb

I've used the informations given by [Marmelatze](https://github.com/Marmelatze/avea_bulb) as well as some reverse engineering using a `btsnoop_hci.log` file from an Android device and Wireshark.

Below is a pretty thorough explanation of the BLE communication and the python implementation to communicate with the bulb.

As BLE communication is quite complicated, you might want to skip all of this if you just want to use the library. But it's quite interesting.


## Communication protocol

### Intro

To communicate the bulb uses Bluetooth 4.0 "BLE", which provide some interesting features for communications, to learn more about it go [here](https://learn.adafruit.com/introduction-to-bluetooth-low-energy/gatt).

To sum up, the bulb emits a set of `services` which have `characteristics`. We use the latter to communicate to the device.

The bulb uses the service `f815e810456c6761746f4d756e696368` and the associated characteristic `f815e811456c6761746f4d756e696368` to send and receive informations about its state (color, name and brightness). We'll transmit over this characteristic.

### Commands and payload explanation

The first bytes of transmission is the command. A few commands are available :

Value | Command
--- | ---
0x35 | set / get bulb color
0x57 | set / get bulb brightness
0x58 | set / get bulb name

### Color command

For the color command, the transmission payload is as follows :

Command | Fading time | Useless byte | White value | Red value | Green value | Blue value
---|---|---|---|---|---|---

Each value of the payload is a 4 hexadecimal value. (The actual values are integers between 0 and 4095)

For each color, a prefix in the hexadecimal value is needed :

Color | prefix
---|---
White| 0x8000
Red | 0x3000
Green | 0x2000
Blue | 0X1000

The values are then formatted in **big-endian** format :

Int | 4-bytes Hexadecimal | Big-endian hex
---|---|---
4095 | 0x0fff| **0xff0f**

### Brightness command

The brightness is also an Int value between 0 and 4095, sent as a big-endian 4-bytes hex value. The transmission looks like this :

Command | Brightness value |
---|---
0x57 | 0xff00

## Walkthrough & Example

Let say we want the bulb to be pink at 75% brightness :

### Brightness

75% brightness is roughly 3072 (out of the maximum 4095):

Int | 4-bytes Hexadecimal | **Big-endian hex**
---|---|---
3072 |0x0C00| **0x000C**

The brightness command will be `0x57000C`

#### Color

Pink is 100% red, 100% blue, no green. (We assume that the white value is also 0.) For each color, we convert the int value to hexadecimal, then we apply the prefix, then we convert to big-endian :

Variables | Int Values | Hexadecimal values | Bitwise XOR | Big-endian values
---|---|---|---|---
White| 0| 0x0000| 0x8000| 0x0080
Red | 4095| 0x0fff| 0x3fff| 0xff3f
Green | 0 | 0x0000| 0x2000 | 0x0020
Blue | 4095| 0x0fff | 0x1fff| 0xff1f


The final byte sequence for a pink bulb will be :

Command | Fading time | Useless byte | White value | Red value | Green value | Blue value
---|---|---|---|---|---|---
`0x35`|`1101`| `0000`| `0080`|`ff3f`|`0020`|`ff1f`


## Python implementation
Below is some python3 code regarding various aspects that are quite interesting.

### One-liner for color computation
To compute the correct values for each color, I created the following conversion (here showing for white) :

```python
white = (int(<value>) | int(0x8000)).to_bytes(2, byteorder='little').hex()
```

### Bluepy writeCharacteristic() overwrite
By default, the btle.Peripheral() object of bluepy only allows to send UTF-8 encoded strings, which are internally converted to hexadecimal. As we craft our own hexadecimal payload, we need to bypass this behavior. A child class of Peripheral() is created and overwrites the writeCharacteristic() method, as follows :

```python
class AveaPeripheral(bluepy.btle.Peripheral):
    def writeCharacteristic(self, handle, val, withResponse=True):
        cmd = "wrr" if withResponse else "wr"
        self._writeCmd("%s %X %s\n" % (cmd, handle, val))
        return self._getResp('wr')
```

### Working with notifications using Bluepy
To reply to our packets, the bulb is using BLE notifications, and some setup is required to be able to receive these notifications with bluepy.

To subscribe to the bulb's notifications, we must send a "0100" to the BLE handle which is just after the one used for communication. As we use handle 0x0028 (40 for bluepy) to communicate, we will send the notification payload to the handle 0x0029 (so 41 for bluepy)

```python
self.bulb.writeCharacteristic(41, "0100")
```
After that, we will receive notifications from the bulb.

## TODO
- Reverse engineer the `ambiances` (which are mood-based scenes).
