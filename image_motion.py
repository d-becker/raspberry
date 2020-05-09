#!/usr/bin/env python3

import io
import sys

import PIL
import PIL.ImageChops as ImageChops
import PIL.ImageStat as ImageStat

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image as ImageWidget
from kivy.uix.popup import Popup

# If picamera cannot be imported (for example we are not running on a Raspberry Pi), set
# the name no None so we can later query whether it was imported.
try:
    import picamera
except ModuleNotFoundError:
    picamera = None

class Camera:
    """
    Interface for a camera that can capture images.
    """

    @staticmethod
    def create_camera(mock):
        """
        Creates an object implementing the Camera interface. If 'mock' is True or picamera
        couldn't be imported, a MockCamera object is returned, otherwise a PiCamera
        object.
        """
        if not mock and picamera is not None:
            return PiCamera()

        if not mock:
            print(
                "WARNING: Falling back to mock camera as picamera could not be imported.")
        return MockCamera()

    def capture(self):
        """
        Capture an image and return it as a PIL image.
        """
        pass

class PiCamera(Camera):
    """
    An implementaion of Camera using picamera.
    """

    def __init__(self):
        self.camera = picamera.PiCamera()
        self.camera.rotation = 180

    def capture(self):
        stream = io.BytesIO()
        self.camera.capture(stream, format='jpeg')
        stream.seek(0)
        return PIL.Image.open(stream)

class MockCamera(Camera):
    """
    A mock implementation of Camera. Returns consecutive images from the 'sample'
    directory. When all images have been exhausted, it starts again from the beginning.
    """

    def __init__(self):
        self.images = [PIL.Image.open('samples/picture_%i.jpg' % i) for i in range(60)]
        self.index = 15 # Start from here so that we don't have to wait much for motion.

    def capture(self):
        res = self.images[self.index]
        self.index = (self.index + 1) % len(self.images)
        return res

class ImageDisplay:
    """
    Provides an interface for the Backend to signal changes concerning the displaying of
    the images and alerts.
    """

    def __init__(self, image_widget):
        self.image_widget = image_widget
        self.alert_widget = ImageWidget()
        self.popup = Popup(title='Alert', content=self.alert_widget, size_hint=(0.4, 0.4))

    def update_image(self, img):
        """
        Replace the displayed image with 'img'.
        """
        core_image = self.__to_core_image(img)
        self.image_widget.texture = core_image.texture

    def motion_alert(self):
        """
        Displays a motion alert.
        """
        self.alert_widget.texture = self.image_widget.texture
        Clock.schedule_once(lambda dt: self.popup.open(), 0)
        Clock.schedule_once(lambda dt: self.popup.dismiss(), 1)

    @staticmethod
    def __to_core_image(img):
        data = io.BytesIO()
        img.save(data, format='png')
        data.seek(0)
        core_image = CoreImage(data, ext='png')
        return core_image

class GuiApp(App):
    """
    The class handling the graphical user interface.
    """

    def __init__(self, title, displayed_image, **kwargs):
        super(GuiApp, self).__init__(**kwargs)
        self.title = title
        self.displayed_image = displayed_image

    def build(self):
        return self.displayed_image

class Backend:
    """
    The class coordinating the program. Its 'update' method triggers capturing an image,
    displaying it, detecting motion and alerting.
    """

    def __init__(self,
                 camera,
                 image_display,
                 crop_box,
                 pixel_threshold,
                 motion_threshold):
        """
        Creates a Backend instance.

        Args:
            camera: A Camera instance, used to capture images.
            image_display: An ImageDisplay instance, used to display images.
            crop_box: A 4-tuple with the (left, upper, right, lower) pixel coordinates of
                the part of the image that will be used.
            pixel_threshold: Threshold (in intensity) for determining if two pixel values
                should be treated as different. If the difference in intensity is greater
                than this threshold, they are considered to be different, otherwise the
                same. For more, see 'detect_motion()'.
            motion_threshold: The ratio of "different" pixels between two images above
                which it is considered that there is motion between the images. See
                'pixel_threshold' for when pixels are considered to be different.
        """
        self.camera = camera
        self.image_display = image_display

        self.crop_box = crop_box
        self.pixel_threshold = pixel_threshold
        self.motion_threshold = motion_threshold

        self.old_image = None
        self.new_image = None

    def update(self):
        """
        Update the state of the program: capture an image, display it and detect motion.
        This method should be called periodically.
        """
        self.__update_images()
        self.__update_display()
        self.__handle_motion()

    def __preprocess_image(self, img):
        return img.crop(self.crop_box)

    def __update_images(self):
        self.old_image = self.new_image
        self.new_image = self.__preprocess_image(self.camera.capture())

    def __update_display(self):
        print("Updating image.")
        self.image_display.update_image(self.new_image)

    def __handle_motion(self):
        if self.old_image is None or self.new_image is None:
            return

        diff_score = detect_motion(self.old_image, self.new_image, self.pixel_threshold)
        if diff_score > self.motion_threshold:
            print("Motion detected: {}.".format(diff_score))
            self.image_display.motion_alert()

def detect_motion(im1, im2, pixel_diff_threshold):
    """
    Return a score on how different 'im1' and 'im2' are, i.e. how much "motion" there is
    between them.

    The images are converted to grayscale and their pixel-wise difference is taken. In the
    resulting difference image, pixels with values less than 'pixel_diff_threshold' are
    set to 0, other pixels are set to 1. This means that pixels where the original two
    grayscale images differed only by at most 'pixel_diff_threshold' are considered to be
    the same, those that differed by more are considered to be different. The final score
    is the ratio of 'different' pixels (having value 1) to all pixels in the difference
    image.
    """
    gray1 = im1.convert('L')
    gray2 = im2.convert('L')

    diff = ImageChops.difference(gray1, gray2)
    diff_thresholded = diff.point(lambda p: p > pixel_diff_threshold)
    return ImageStat.Stat(diff_thresholded).mean[0]

def create_diffs(imgs, threshold):
    pairs = list(zip(imgs, imgs[1:]))
    return [detect_motion(im1, im2, threshold) for (im1, im2) in pairs]

def print_list(l):
    for i, elem in enumerate(l):
        print("%i: %i" %(i, elem))

# TODO: Probably we don't need this.
def start_alert_process():
    img_data = sys.stdin.buffer.read()
    img_data = io.BytesIO(img_data)
    core_image = CoreImage(img_data, ext='png')
    displayed_image = ImageWidget()
    displayed_image.texture = core_image.texture

    gui_app = GuiApp('Alert', displayed_image)
    Clock.schedule_interval(lambda dt: gui_app.stop(), 1)
    gui_app.run()

def start_normal_process(pixel_threshold=10,
        motion_threshold=0.015,
        mock=False):
    """
    Start the application. for 'pixel_threshold' and 'motion_threshold', see Backend. If
    'mock' is true, MockCamera is used and no images are actually taken. This is also the
    case if the 'picamera' module could not be imported (for example the script is not
    running on a Raspberry Pi).
    """
    camera = Camera.create_camera(mock)
    displayed_image = ImageWidget(allow_stretch=True)
    image_display = ImageDisplay(displayed_image)
    box = (215, 245, 495, 480)

    gui_app = GuiApp('Normal', displayed_image)
    backend = Backend(camera, image_display, box, pixel_threshold, motion_threshold)

    backend.update()

    # Schedule an update to happen periodically. This will trigger capturing a new image,
    # displaying it and alerting if motion is detected.
    Clock.schedule_interval(lambda dt: backend.update(), 2)

    gui_app.run()

def main():
    mock = 'mock' in sys.argv[1:]
    start_normal_process(mock=mock)

if __name__ == "__main__":
    main()
