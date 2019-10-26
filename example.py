import avea
import time

print("searching for Avea bulbs !")
bulb_list = avea.discover_avea_bulbs()
if len(bulb_list) == 0:
    print("no bulbs found..")
    exit()

print("Found",str(len(bulb_list)),"bulb(s) !")

for bulb in bulb_list:
    print("Bulb name is : "+bulb.get_name())

    print("Setting to white")
    bulb.set_rgb(255,255,255)
    time.sleep(2)

    print("Now to red")
    bulb.set_rgb(255,0,0)
    time.sleep(2)

    print("And now a smooth transition to blue in 4s at 60fps")
    bulb.set_smooth_transition(0,0,255,4,60)
    time.sleep(2)

    print("Finally, off")
    bulb.set_rgb(0,0,0)