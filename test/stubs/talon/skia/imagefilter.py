"""Talon Skia ImageFilter stubs."""


class ImageFilter:
    """Mock Skia ImageFilter for blur, shadow, etc."""

    @staticmethod
    def blur(sigma_x, sigma_y=None):
        return ImageFilter()

    @staticmethod
    def drop_shadow(dx, dy, sigma_x, sigma_y, color):
        return ImageFilter()
