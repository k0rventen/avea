"""
Creator : corentin
License : MIT
Source  : https://github.com/k0rventen/avea
Version : 1.2.8
"""

# Standard imports
import time  # for delays

# 3rd party imports
import bluepy  # for BLE transmission

# __all__ definition for __init__.py
__all__ = ["Bulb", "discover_avea_bulbs", "compute_brightness",
           "compute_color", "check_bounds", "AveaDelegate", "AveaPeripheral"]


class Bulb:
    """The class that represents an Avea bulb

    An Bulb object describe a real world Avea bulb.
    It is linked to an AveaPeripheral object for BLE transmissions
    and an AveaDelegate for BLE notifications handling.
    """

    def __init__(self, address):
        """ Just setup some vars"""
        self.addr = address
        self.name = "Unknown"
        self.red = 0
        self.blue = 0
        self.green = 0
        self.brightness = 0
        self.white = 0

    def subscribe_to_notification(self):
        """Subscribe to the bulbs notifications

        41 is the handle for notifications (its the one used to communicate +1)
        0100 is the "enable bit"
        """
        self.bulb.writeCharacteristic(41, "0100")

    def connect(self):
        """Connect to the bulb

        - Create a modified bluepy.btle.Peripheral object (see AveaPeripheral)
        - Connect to the bulb
        - Add a delegate for notifications
        - Send the "enable bit" for notifications

        :return: True if the connection is successful, false otherwise
        """
        self.bulb = AveaPeripheral()
        self.delegate = AveaDelegate(self)

        # Catch if the bulb does not respond instead of crashing the whole script
        try:
            self.bulb.connect(self.addr)
        except Exception: 
            print("Could not connect to the Bulb")
            return False

        self.bulb.withDelegate(self.delegate)
        self.subscribe_to_notification()
        return True

    def disconnect(self):
        """Disconnect from the bulb

        Cleanup properly the bluepy's Peripheral and the Notification's Delegate to avoid weird issues
        """
        try:
            self.bulb.disconnect()
        except Exception:
            pass
        del self.bulb
        del self.delegate

    def set_brightness(self, brightness):
        """Send the specified brightness to the bulb

        :args: - brightness value from 0 to 4095
        """
        if self.connect():
            self.bulb.writeCharacteristic(
                40, compute_brightness(check_bounds(brightness)))
            self.disconnect()

    def get_brightness(self):
        """Retrieve and return the current brightness of the bulb

        :return: Current brightness, from 0 to 4095
        """
        if self.connect():
            time.sleep(0.5)
            self.bulb.writeCharacteristic(40, "57")
            self.bulb.waitForNotifications(1.0)
            self.disconnect()

            return self.brightness

    def set_color(self, white, red, green, blue):
        """ Set the color of the bulb using the full range of colors

        :args: - white value from 0 to 4095
               - red value
               - green value
               - blue value
        """
        if self.connect():
            self.bulb.writeCharacteristic(40, compute_color(check_bounds(white),
                                                            check_bounds(red),
                                                            check_bounds(
                                                                green),
                                                            check_bounds(blue)))
            self.disconnect()

    def set_rgb(self, red, green, blue):
        """Set the color of the bulb in a RGB format

        :args: - red value
               - green value
               - blue value
        """
        if self.connect():
            self.bulb.writeCharacteristic(40, compute_color(check_bounds(0),
                                                            check_bounds(
                                                                red*16),
                                                            check_bounds(
                                                                green*16),
                                                            check_bounds(blue*16)))
            self.disconnect()

    def get_color(self):
        """Retrieve and return the current color of the bulb

        A .5s sleep is here to accommodate for the bulb's response time :
        If get_color() is called directly after set_color(), the transmission
        from the bulb may not be complete and the function may return old/garbage data

        :returns: tuple (white, red, green, blue) with values from 0 to 4095
        """
        if self.connect():
            time.sleep(0.5)
            self.bulb.writeCharacteristic(40, "35")
            self.bulb.waitForNotifications(1.0)
            self.disconnect()

            return self.white, self.red, self.green, self.blue

    def get_rgb(self):
        """Retrieve and return the current color of the bulb in a RGB style

        :returns: tuple (red, green, blue) with values from 0 to 255
        """
        if self.connect():
            time.sleep(0.5)
            self.bulb.writeCharacteristic(40, "35")
            self.bulb.waitForNotifications(1.0)
            self.disconnect()

            return int(self.red/16), int(self.green/16), int(self.blue/16)

    def get_name(self):
        """Get and return the name of the bulb
        
        :returns: Name of the bulb
        """
        if self.connect():
            time.sleep(0.5)
            self.bulb.writeCharacteristic(40, "58")
            self.bulb.waitForNotifications(1.0)
            self.disconnect()

            return self.name

    def set_name(self, name):
        """Set the name of the bulb"""
        if self.connect():
            byteName = name.encode("utf-8")
            command = "58"+byteName.hex()
            self.bulb.writeCharacteristic(40, command)
            self.disconnect()

    def process_notification(self, data):
        """Method called when a notification is send from the bulb

        It is processed here rather than in the handleNotification() function,
        because the latter is not a method of the Bulb class, therefore it can't access
        the Bulb object's data

        :args: - data : the received data from the bulb in hex format
        """
        cmd = data[:1]
        values = data[1:]
        cmd = int(cmd.hex())

        # Convert the brightness value
        if cmd is 57:
            self.brightness = int.from_bytes(values, 'little')

        # Convert the color values
        elif cmd is 35:
            hex = values.hex()
            self.red = int.from_bytes(bytes.fromhex(
                hex[-4:]), "little") ^ int(0x3000)
            self.green = int.from_bytes(bytes.fromhex(
                hex[-8:-4]), "little") ^ int(0x2000)
            self.blue = int.from_bytes(bytes.fromhex(
                hex[-12:-8]), "little") ^ int(0x1000)
            self.white = int.from_bytes(bytes.fromhex(hex[-16:-12]), "little")

        # Convert the name
        elif cmd is 58:
            self.name = values.decode("utf-8")


def discover_avea_bulbs():
    """Scanning feature

    Scan the BLE neighborhood for an Avea bulb
    This method requires the script to be launched as root
    Returns the list of nearby bulbs
    """
    bulb_list = []
    from bluepy.btle import Scanner, DefaultDelegate

    class ScanDelegate(DefaultDelegate):
        """Overwrite of the Scan Delegate class"""

        def __init__(self):
            DefaultDelegate.__init__(self)

    scanner = Scanner().withDelegate(ScanDelegate())
    devices = scanner.scan(4.0)
    for dev in devices:
        for (adtype, desc, value) in dev.getScanData():
            if "Avea" in value:
                bulb_list.append(Bulb(dev.addr))
    return bulb_list


def compute_brightness(brightness):
    """Return the hex code for the specified brightness"""
    value = hex(int(brightness))[2:]
    value = value.zfill(4)
    value = value[2:] + value[:2]
    return "57" + value


def compute_color(w=2000, r=0, g=0, b=0):
    """Return the hex code for the specified colors"""
    color = "35"
    fading = "1101"
    unknow = "0a00"
    white = (int(w) | int(0x8000)).to_bytes(2, byteorder='little').hex()
    red = (int(r) | int(0x3000)).to_bytes(2, byteorder='little').hex()
    green = (int(g) | int(0x2000)).to_bytes(2, byteorder='little').hex()
    blue = (int(b) | int(0x1000)).to_bytes(2, byteorder='little').hex()

    return color + fading + unknow + white + red + green + blue


def check_bounds(value):
    """Check if the given value is out-of-bounds (0 to 4095)

    :args: the value to be checked
    :returns: the checked value
    """
    try:
        if int(value) > 4095:
            return 4095

        elif int(value) < 0:
            return 0
        else:
            return value
    except ValueError:
        print("Value was not a number, returned default value of 0")
        return 0


class AveaDelegate(bluepy.btle.DefaultDelegate):
    """Overwrite of Bluepy's DefaultDelegate class

    It adds a bulb object that refers to the Bulb.bulb object which
    called this delegate.
    It is used to call the bulb.process_notification() function
    """

    def __init__(self, bulbObject):
        self.bulb = bulbObject

    def handleNotification(self, cHandle, data):
        """Overwrite of the async function called when a device sends a notification.

        It's just passing the data to process_notification(),
        which is linked to the emitting bulb (via self.bulb).
        This allows us to use the bulb's functions and interact with the response.
        """
        self.bulb.process_notification(data)


class AveaPeripheral(bluepy.btle.Peripheral):
    """Overwrite of the Bluepy 'Peripheral' class.

    It overwrites only the default writeCharacteristic() method
    """

    def writeCharacteristic(self, handle, val, withResponse=False):
        """Overwrite of the writeCharacteristic method

        By default it only allows strings as input
        As we craft our own paylod, we need to bypass this behavior
        and send hex values directly
        """
        cmd = "wrr" if withResponse else "wr"
        self._writeCmd("%s %X %s\n" % (cmd, handle, val))
        return self._getResp('wr')
