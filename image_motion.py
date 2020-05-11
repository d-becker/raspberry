#!/usr/bin/env python3

import argparse
import io
import os
import sys

import PIL
import PIL.ImageChops as ImageChops
import PIL.ImageStat as ImageStat

# Prevent kivy from parsing CLI arguments so we can have our own.
os.environ["KIVY_NO_ARGS"] = "1"

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.graphics.texture import Texture
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.image import Image as ImageWidget
from kivy.uix.label import Label
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

    def __init__(self, image_widget, alert_image_widget):
        self.image_widget = image_widget
        self.alert_image_widget = alert_image_widget
        self.alert_image_widget.texture = self.image_widget.texture

    def update_image(self, img):
        """
        Replace the displayed image with 'img'.
        """
        core_image = self.__to_core_image(img)
        self.image_widget.texture = core_image.texture

        self.alert_image_widget.texture = Texture.create(size=core_image.texture.size)

    def motion_alert(self):
        """
        Displays a motion alert.
        """
        self.alert_image_widget.texture = self.image_widget.texture

    @staticmethod
    def __to_core_image(img):
        data = io.BytesIO()
        img.save(data, format='jpeg')
        data.seek(0)
        core_image = CoreImage(data, ext='jpg')
        return core_image

class GuiApp(App):
    """
    The class handling the graphical user interface.
    """

    def __init__(self, title, displayed_image, alert_image, **kwargs):
        super(GuiApp, self).__init__(**kwargs)
        self.title = title

        self.box_layout = BoxLayout(orientation='horizontal')
        self.labelled_img = self.LabelledImage("Normal image", displayed_image)
        self.labelled_alert = self.LabelledImage("Alert", alert_image)

        self.box_layout.add_widget(self.labelled_img)
        self.box_layout.add_widget(self.labelled_alert)

    class LabelledImage(BoxLayout):
        """
        An image widget with a label widget above it.
        """

        def __init__(self, text, displayed_image, **kwargs):
            super(GuiApp.LabelledImage, self).__init__(orientation='vertical', **kwargs)
            self.label = Label(text=text, size_hint=(1, 0.1))
            self.displayed_image = displayed_image

            self.add_widget(self.label)
            self.add_widget(self.displayed_image)

    def build(self):
        return self.box_layout

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

        self.old_gray_image = None
        self.new_gray_image = None
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
        cropped = img.crop(self.crop_box)
        gray = cropped.convert('L')
        return cropped, gray

    def __update_images(self):
        self.old_gray_image = self.new_gray_image
        self.new_image, self.new_gray_image = self.__preprocess_image(
            self.camera.capture())

    def __update_display(self):
        print("Updating image.")
        self.image_display.update_image(self.new_image)

    def __handle_motion(self):
        if self.old_gray_image is None or self.new_gray_image is None:
            return

        diff_score = detect_motion_gray(self.old_gray_image, self.new_gray_image,
            self.pixel_threshold)
        if diff_score > self.motion_threshold:
            print("Motion detected, score: {}.".format(diff_score))
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

    return detect_motion_gray(gray1, gray2, pixel_diff_threshold)

def detect_motion_gray(gray1, gray2, pixel_diff_threshold):
    """
    Like 'detect_motion' but on already grayscale images.
    """
    diff = ImageChops.difference(gray1, gray2)
    diff_thresholded = diff.point(lambda p: p > pixel_diff_threshold)
    return ImageStat.Stat(diff_thresholded).mean[0]

def create_diffs(imgs, threshold):
    pairs = list(zip(imgs, imgs[1:]))
    return [detect_motion(im1, im2, threshold) for (im1, im2) in pairs]

def print_list(l):
    for i, elem in enumerate(l):
        print("%i: %i" %(i, elem))

def start_normal_process(pixel_threshold,
        motion_threshold,
        box,
        mock):
    """
    Start the application. for 'pixel_threshold' and 'motion_threshold', see Backend. If
    'mock' is true, MockCamera is used and no images are actually taken. This is also the
    case if the 'picamera' module could not be imported (for example the script is not
    running on a Raspberry Pi).
    """
    camera = Camera.create_camera(mock)
    displayed_image = ImageWidget(allow_stretch=True)
    alert_image = ImageWidget(allow_stretch=True)
    image_display = ImageDisplay(displayed_image, alert_image)

    gui_app = GuiApp('Normal', displayed_image, alert_image)
    backend = Backend(camera, image_display, box, pixel_threshold, motion_threshold)

    backend.update()

    # Schedule an update to happen periodically. This will trigger capturing a new image,
    # displaying it and alerting if motion is detected.
    Clock.schedule_interval(lambda dt: backend.update(), 2)

    gui_app.run()

def create_parser():
    parser = argparse.ArgumentParser()

    parser.add_argument("-m", "--mock", action='store_true',
        help="Use a mock camera with pre-captured images.")
    parser.add_argument("-p", "--pixel_threshold", type=int, default=10,
        choices=range(0, 256),
        help="Threshold (in intensity) for determining"
             "if two pixel values should be treated as different")
    parser.add_argument("-t", "--motion_threshold", type=float, default=0.015,
        help="The ratio of \"different\" pixels between two images above"
             "which it is considered that there is motion between the images.")
    parser.add_argument("-b", "--box", type=int, nargs=4, default=(450, 170, 740, 410),
        help="The coordinates of the region of interest (left, upper, right, lower).")

    return parser

def main():
    parser = create_parser()
    args = parser.parse_args()

    # box_samples = (215, 245, 495, 480)
    # box_night_samples = (450, 170, 740, 410)

    start_normal_process(pixel_threshold=args.pixel_threshold,
        motion_threshold=args.motion_threshold, box=args.box, mock=args.mock)

if __name__ == "__main__":
    main()
