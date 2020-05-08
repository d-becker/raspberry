import io
import datetime
import time

import PIL
import PIL.ImageChops as ImageChops
import PIL.ImageStat as ImageStat

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image as ImageWidget

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
        self.index = 0

    def capture(self):
        res = self.images[self.index]
        self.index = (self.index + 1) % len(self.images)
        return res

class ImageDisplay:
    def __init__(self, image_widget):
        self.image_widget = image_widget

    def update_image(self, im):
        data = io.BytesIO()
        im.save(data, format='png')
        data.seek(0)
        core_image = CoreImage(data, ext='png')
        self.image_widget.texture = core_image.texture

    def motion_alert(self, im):
        pass

class GuiApp(App):
    def __init__(self, **kwargs):
        super(GuiApp, self).__init__(**kwargs)
        self.normal_image = ImageWidget()

    def build(self):
        return self.normal_image

class SecurityApp:
    def __init__(self,
                 camera,
                 image_display,
                 pixel_threshold,
                 motion_threshold,
                 mock):
        self.camera = camera
        self.image_display = image_display

        self.pixel_threshold = pixel_threshold
        self.motion_threshold = motion_threshold

        self.old_image = None
        self.new_image = None

    def update(self):
        self.__update_images()
        self.__update_display()
        self.__handle_motion()

    def __wait(self):
        next_second = (datetime.datetime.now() + datetime.timedelta(seconds=1)).replace(
                microsecond=0)
        delay = (next_second - datetime.datetime.now()).total_seconds()
        print("Delay: {}.".format(delay))
        time.sleep(delay)

    def __update_images(self):
        self.old_image = self.new_image
        self.new_image = crop_to_quarter_9_12(self.camera.capture())

    def __update_display(self):
        print("Updating image.")
        self.image_display.update_image(self.new_image)

    def __handle_motion(self):
        if self.old_image is None or self.new_image is None:
            return

        diff_score = detect_motion(self.old_image, self.new_image, self.pixel_threshold)
        if diff_score > self.motion_threshold:
            print("Motion detected: {}.".format(diff_score))
        pass

def detect_motion(im1, im2, pixel_diff_threshold):
    gray1 = im1.convert('L')
    gray2 = im2.convert('L')

    diff = ImageChops.difference(gray1, gray2)
    diff_thresholded = diff.point(lambda p: p > pixel_diff_threshold)
    return ImageStat.Stat(diff_thresholded).sum[0]

def crop_to_quarter_9_12(im):
    box = (215, 245, 495, 480)
    return im.crop(box)

def create_diffs(imgs, threshold):
    pairs = list(zip(imgs, imgs[1:]))
    return [detect_motion(im1, im2, threshold) for (im1, im2) in pairs]

def print_list(l):
    for i, elem in enumerate(l):
        print("%i: %i" %(i, elem))

def main():
    global images, cropped
    images = [PIL.Image.open('samples/picture_%i.jpg' % i) for i in range(60)]
    cropped = [crop_to_quarter_9_12(im) for im in images]

def create_apps(pixel_threshold = 10,
               motion_threshold = 1000,
               mock = False):
    camera = Camera.create_camera(mock)
    gui_app = GuiApp()
    img_display = ImageDisplay(gui_app.normal_image)
    security_app = SecurityApp(camera, img_display, pixel_threshold, motion_threshold, mock)

    Clock.schedule_interval(lambda dt: security_app.update(), 1)

    gui_app.run()

if __name__ == "__main__":
    main()
