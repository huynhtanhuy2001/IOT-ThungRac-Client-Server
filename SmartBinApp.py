# ==============================================
# Configuration
#   Some often-tweaked parameters during testing
# ==============================================

import os
os.environ['KIVY_HOME'] = "/home/pi/.kivy"

# model configuration file, taken from training enviroment
config_path = "data/config.json"

# path to the best weights, taken from the training enviroment
weights_path = "data/best_weights_11.h5"

# Kivy resizes the camera image to size before displaying
frame_size = 1180, 1180

# ====================
# Initialise LED Strip
# ====================

print("[i] Initialising LED Strip")

from neopixel import *
from threading import Thread
import time

red = Color(0, 255, 0)
green = Color(255, 0, 0)
blue = Color(0, 0, 255)
yellow = Color(255, 255, 0)

# Create NeoPixel object with appropriate configuration.
strip = Adafruit_NeoPixel(25, 18, 800000, 10, False, 100, 0)

# Intialize the library (must be called once before other functions).
strip.begin()


class lightshow():
    """
    A thread that's sole purpose is to show you the loading progress.
    The model takes around 110 seconds to load, so that's what the progress bar shows you.
    It's a bit naive, but it's also here for fun.
    """

    def __init__(self):
        # Initiate properties
        global strip
        self.stopped = False
        self.start_time = None
        self.progress = 0
        self.pixels = strip.numPixels()

    def start(self):
        # start the thread to read frames from the video stream
        self.start_time = time.time()
        Thread(target=self.update, args=()).start()
        return self

    def update(self):
        # keep looping infinitely until the thread is stopped
        global strip, yellow, green
        while True:
            if self.stopped:
                return
            elif self.progress == 100:
                self.stop()
            else:
                time.sleep(0.6)
                self.progress += 0.5
                for i in range(int((self.progress+4.4)/100*self.pixels)):
                    strip.setPixelColor(i, red)
                for i in range(int((self.progress+2.6)/100*self.pixels)):
                    strip.setPixelColor(i, yellow)
                for i in range(int(self.progress/100*self.pixels)):
                    strip.setPixelColor(i, green)
                strip.show()

    def stop(self):
        self.stopped = True

# ====================================
# Computer Vision Pipeline
#   Components (as threads):
#     1. Camera stream (PiVideoStream)
#     2. Inference (prediction) stream
# ====================================


# start the progress bar animation
progress_bar = lightshow().start()

print("[i] Initialising Computer Vision pipeline")
import cv2
import json
import numpy as np
from box_utils import draw_boxes
from object_detection_model import ObjectDetection

with open(config_path) as config_buffer:
    config = json.load(config_buffer)

from camera import PiVideoStream

print("[i] Loading feature extractor:", config['model']['backend'])
print("[+] Trained labels:", config['model']['labels'])
print("[i] Building model... This will take a while... (< 2 mins)")

load_start = time.time()

model = ObjectDetection(backend=config['model']['backend'],
                        input_size=config['model']['input_size'],
                        labels=config['model']['labels'],
                        max_box_per_image=config['model']['max_box_per_image'],
                        anchors=config['model']['anchors'])

print("[i] Model took", (time.time()-load_start), "seconds to load")

print("[c] Starting video capture")
cap = PiVideoStream().start()

print("[i] Loading weights from", weights_path)
model.load_weights(weights_path)


class predictions():
    """
    Streaming inferences independently of camera and UI updates
    Makes use of the following global variables:
      1. current frame from camera stream
      2. currently loaded object detection model
    """

    def __init__(self):
        self.boxes = ["can", "bottle", "ken",
                      "grace", "frank", "tim", "shelly"]
        self.stopped = False

    def start(self):
        # start the thread to read frames from the video stream
        Thread(target=self.update, args=()).start()
        return self

    def update(self):
        global model, frame
        # keep looping infinitely until the thread is stopped
        while True:
            if self.stopped:
                return
            else:
                self.boxes = model.predict(frame)

    def read(self):
        return self.boxes

    def stop(self):
        self.stopped = True

# =========
# IOT Setup
#   1. Import firebase iot functions
#   2. Authenticate and instantiate firebase
#   3. Reset firebase on first run
# =========


from iot import *
#firebase = firebase_setup()
# firebase_reset(firebase)

# ======================================================
# Perform one inference to test if everything is working
# ======================================================

print("[i] Running self-test")
try:
    frame = cap.read()  # read one frame from the stream
    boxes = model.predict(frame)  # get bounding boxes
    # if previous line succeded, our model is functional; start the predictions stream
    pred = predictions().start()
    print("[+] Self-test: OK")
except Exception as error:
    print("[!] Fatal error", end=": ")
    print(error)
    exit()

# ==============================
# Kivy Configuration
#   Only needed on the first run
# ==============================

from kivy.config import Config
Config.set('graphics', 'fullscreen', 'fake')
Config.set('graphics', 'fbo', 'hardware')
Config.set('graphics', 'show_cursor', 1)
Config.set('graphics', 'borderless', 0)
Config.set('kivy', 'exit_on_escape', 1)
Config.write()

# ========================
# GUI Setup
#   Necessary Kivy imports
# =========================

from kivy.app import App
from kivy.graphics import *
from kivy.graphics.texture import Texture
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.core.window import Window

Builder.load_file('app_layout.kv')  # Kivy layout file


# Declare individual screens

class MainView(Screen):
    """
    This is the main screen, shown when the app starts.
    It displays the camera feed and 3 buttons
    """

    def __init__(self, **kwargs):
        global cap, frame, frame_size

        # capture and render the first frame
        self.frame_size = frame_size
        frame = cap.read()
        image = cv2.flip(frame, 0)
        image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        image = cv2.resize(image, frame_size)
        buf = image.tostring()
        self.image_texture = Texture.create(size=(image.shape[1], image.shape[0]), colorfmt='rgb')
        self.image_texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')

        # coordinates of Trashy
        self.t_x = 0
        self.t_y = 0

        self.current_user = 'No user yet'
        self.tickcount = 0
        self.labels = ["can", "bottle", "ken",
                       "grace", "frank", "tim", "shelly"]
        self.users = ["ken", "grace", "frank", "tim", "shelly"]

        super(MainView, self).__init__(**kwargs)
        Clock.schedule_interval(self.tick, 0.06)

    def tick(self, dt):
        global pred, cap, frame, strip, red, green, blue
        #global firebase

        can_detected, bottle_detected = False, False
        #self.tickcount += 1

        # Process frame from OpenCV
        frame = cap.read()
        image = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        boxes = pred.read()
        image = draw_boxes(image, boxes, config['model']['labels'])
        image = cv2.resize(cv2.flip(image, 0), self.frame_size)
        buf = image.tostring()

        # Update displayed image in user interface camera view
        self.image_texture = Texture.create(
            size=(self.frame_size), colorfmt='rgb')
        self.image_texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')
        self.ids.cameraView.texture = self.image_texture

        if len(boxes) > 0:
            # Trashy avatar follows the bounding box of the detected entity
            # Augmented Reality :)
            self.t_x = int((boxes[0].xmin-0.5) * 1000) - 80
            self.t_y = -1 * (int((boxes[0].ymin-0.5) * 1000) + 80)
            self.ids.trashyView.opacity = 1.0
            self.ids.trashyView.pos = (self.t_x, self.t_y)
            display_label = ""
            for box in boxes:
                # Obtain current entity prediction label
                curr_label = box.get_label()
                if self.labels[curr_label] == "can":
                    can_detected = True
                if self.labels[curr_label] == "bottle":
                    bottle_detected = True
                # if self.labels[curr_label] in self.users:
                    # Update current user property if a valid entity label is detected
                 #   self.current_user = self.labels[curr_label]

            if can_detected == True:
                # Set led lights at the 'cans' box to green to signal user
                for i in range(8):
                    strip.setPixelColor(i, red)
                for i in range(15, 25):
                    strip.setPixelColor(i, green)
                display_label = display_label + \
                    "\nThrow your can in the recycling bin\nPlease wash the can first!"

                # Increment firebase user count for cans by 1 every time a can is detected with a valid user
                # Also only updates every 10 ticks to reduce lag
                # if self.current_user in self.users and self.tickcount % 10 == 0:
                #    firebase_update(firebase, self.current_user, 'cans', 1)

            if bottle_detected == True:
                # Set led lights at the 'blue' box to green to signal user
                for i in range(8):
                    strip.setPixelColor(i, red)
                for i in range(8, 15):
                    strip.setPixelColor(i, blue)
                display_label = display_label + \
                    "\nThrow your bottle into the recycling bin\nPlease empty it first!"

                # Increment firebase user count for bottles by 1 every time a bottle is detected with a valid user
                # Also only updates every 10 ticks to reduce lag
                # if self.current_user in self.users and self.tickcount % 10 == 0:
                #    firebase_update(firebase, self.current_user, 'bottles', 1)
            self.ids.labelObjDet.text = display_label
        else:
            # Trashy avatar disappears and message popup
            self.ids.trashyView.opacity = 0.0
            self.ids.labelObjDet.text = "No recyclable trash detected"
        strip.show()
        # reset the LED strip to original state (but don't show it!)
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, red)
        for i in range(8):
            strip.setPixelColor(i, green)

    def quit(self):
        # Stop predictions and video capture
        global strip
        pred.stop()
        cap.stop()
        # Turn off led strip
        for i in range(strip.numPixels()):
            strip.setPixelColor(i, Color(0, 0, 0))
        strip.show()
        # Exit kivy
        Window.close()
        App.get_running_app().stop()
        exit()


class InfoView(Screen):
    """Secondary screen that displays information about recycling in Singapore"""

    def __init__(self, **kwargs):
        super(InfoView, self).__init__(**kwargs)


class AboutView(Screen):
    """Secondary screen that displays information about this project"""

    def __init__(self, **kwargs):
        super(AboutView, self).__init__(**kwargs)

# ==========================================
# Tie everything together and launch the app
# ==========================================


# everything works! set LED strip to initial state
for i in range(strip.numPixels()):
    strip.setPixelColor(i, red)
for i in range(8):
    strip.setPixelColor(i, green)
strip.show()

print("[u] Loading UI")
Window.clearcolor = (1, 1, 1, 1)  # set white background

# setup Kivy screen manager
sm = ScreenManager()
sm.add_widget(MainView(name='mainView'))
sm.add_widget(InfoView(name='infoView'))
sm.add_widget(AboutView(name='aboutView'))


class SmartBinApp(App):
    # Main Kivy app
    def build(self):
        return sm


# Run SmartBinApp and exit if running fails
try:
    SmartBinApp().run()
except KeyboardInterrupt:
    pred.stop()
    cap.stop()
    print('exciting due to KeyboardInterrupt')
    for i in range(strip.numPixels()):
        strip.setPixelColor(i, Color(0, 0, 0))
    strip.show()
    App.get_running_app().stop()
    exit()
