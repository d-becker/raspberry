import io
import datetime
import subprocess
import sys
import time

import PIL
import PIL.ImageChops as ImageChops
import PIL.ImageStat as ImageStat

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image as ImageWidget
from kivy.uix.popup import Popup
from kivy.uix.label import Label

try:
    import picamera
except ModuleNotFoundError:
    picamera = None

class Camera:
    @staticmethod
    def create_camera(mock):
        if not mock and picamera is not None:
            return PiCamera()

        return MockCamera()

    def capture(self):
        pass

class PiCamera(Camera):
    def __init__(self):
        self.camera = picamera.PiCamera()
        self.camera.rotation = 180

    def capture(self):
        stream = io.BytesIO()
        self.camera.capture(stream, format='jpeg')
        stream.seek(0)
        return PIL.Image.open(stream)

class MockCamera(Camera):
    def __init__(self):
        self.images = [PIL.Image.open('samples/picture_%i.jpg' % i) for i in range(60)]
        self.index = 15 # TODO: 0.

    def capture(self):
        res = self.images[self.index]
        self.index = (self.index + 1) % len(self.images)
        return res

class ImageDisplay:
    def __init__(self, image_widget):
        self.image_widget = image_widget
        self.alert_widget = ImageWidget()
        self.popup = Popup(title='Alert', content=self.alert_widget, size_hint=(0.4, 0.4))

    def update_image(self, im):
        core_image = self.__to_core_image(im)
        self.image_widget.texture = core_image.texture

    def motion_alert(self, im):
        core_image = self.__to_core_image(im)
        self.alert_widget.texture = core_image.texture
        Clock.schedule_once(lambda dt: self.popup.open(), 0)
        Clock.schedule_once(lambda dt: self.popup.dismiss(), 0.8)

    @staticmethod
    def __to_core_image(im):
        data = io.BytesIO()
        im.save(data, format='png')
        data.seek(0)
        core_image = CoreImage(data, ext='png')
        return core_image

class GuiApp(App):
    def __init__(self, title, displayed_image, **kwargs):
        super(GuiApp, self).__init__(**kwargs)
        self.title = title
        self.displayed_image = displayed_image

    def build(self):
        return self.displayed_image

class Backend:
    def __init__(self,
                 camera,
                 image_display,
                 crop_box,
                 pixel_threshold,
                 motion_threshold):
        self.camera = camera
        self.image_display = image_display

        self.crop_box = crop_box
        self.pixel_threshold = pixel_threshold
        self.motion_threshold = motion_threshold

        self.old_image = None
        self.new_image = None

    def update(self):
        self.__update_images()
        self.__update_display()
        self.__handle_motion()

    def preprocess_image(self, im):
        return im.crop(self.crop_box)

    def __update_images(self):
        self.old_image = self.new_image
        self.new_image = self.preprocess_image(self.camera.capture())

    def __update_display(self):
        print("Updating image.")
        self.image_display.update_image(self.new_image)

    def __handle_motion(self):
        if self.old_image is None or self.new_image is None:
            return

        diff_score = detect_motion(self.old_image, self.new_image, self.pixel_threshold)
        if diff_score > self.motion_threshold:
            print("Motion detected: {}.".format(diff_score))
            self.image_display.motion_alert(self.new_image)

def detect_motion(im1, im2, pixel_diff_threshold):
    gray1 = im1.convert('L')
    gray2 = im2.convert('L')

    diff = ImageChops.difference(gray1, gray2)
    diff_thresholded = diff.point(lambda p: p > pixel_diff_threshold)
    return ImageStat.Stat(diff_thresholded).sum[0]

def create_diffs(imgs, threshold):
    pairs = list(zip(imgs, imgs[1:]))
    return [detect_motion(im1, im2, threshold) for (im1, im2) in pairs]

def print_list(l):
    for i, elem in enumerate(l):
        print("%i: %i" %(i, elem))

def start_alert_process():
    img_data = sys.stdin.buffer.read()
    img_data = io.BytesIO(img_data)
    core_image = CoreImage(img_data, ext='png')
    displayed_image = ImageWidget()
    displayed_image.texture = core_image.texture

    gui_app = GuiApp('Alert', displayed_image)
    Clock.schedule_interval(lambda dt: gui_app.stop(), 1)
    gui_app.run()

def start_normal_process(pixel_threshold = 10,
        motion_threshold = 1000,
        mock = False):
    camera = Camera.create_camera(mock)
    displayed_image = ImageWidget()
    image_display = ImageDisplay(displayed_image)
    box = (215, 245, 495, 480)

    gui_app = GuiApp('Normal', displayed_image)
    backend = Backend(camera, image_display, box, pixel_threshold, motion_threshold)

    backend.update()
    Clock.schedule_interval(lambda dt: backend.update(), 1)

    gui_app.run()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == 'alert':
        start_alert_process()
    else:
        mock = 'mock' in sys.argv[1:]
        start_normal_process(mock=mock)
