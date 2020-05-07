import io

import PIL
import PIL.ImageChops as ImageChops
import PIL.ImageStat as ImageStat

try:
    import picamera
except ModuleNotFoundError:
    picamera = None

class Camera:
    @staticmethod
    def create_camera():
        if picamera is not None:
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

class SecurityCamera:
    def __init__(self, delta_second = 1, pixel_threshold = 10, motion_threshold = 1000):
        self.delta_second = delta_second
        self.pixel_threshold = pixel_threshold
        self.motion_threshold = motion_threshold

        self.old_image = None
        self.new_image = None

        self.camera = Camera.create_camera()

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

if __name__ == "__main__":
    main()
