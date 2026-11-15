"""
Animations written as GIFs whose frames share one palette
"""

from matplotlib import animation
from PIL import Image


class SharedPaletteGifWriter(animation.PillowWriter):
    """
    A Pillow GIF writer whose frames all share one palette

    Pillow quantizes each frame of a GIF to its own palette, so a fixed
    colormap and its colorbar come out in different colors from frame to
    frame and the animation flickers.  This writer keeps the frames, builds
    one palette from a sample of them and quantizes every frame to it,
    without dithering.
    """

    def finish(self):
        """
        Write the frames with one palette
        """
        # the frames PillowWriter keeps until it finishes
        frames = self._frames  # type: ignore[attr-defined]
        # a sample of frames from across the animation, stacked, gives a
        # palette with the colors of all of them
        step = max(1, len(frames) // 24)
        sample = frames[::step]
        width, height = sample[0].size
        stack = Image.new('RGB', (width, height * len(sample)))
        for index, frame in enumerate(sample):
            stack.paste(frame.convert('RGB'), (0, height * index))
        palette = stack.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        quantized = [
            frame.convert('RGB').quantize(
                palette=palette, dither=Image.Dither.NONE
            )
            for frame in frames
        ]
        quantized[0].save(
            self.outfile,
            save_all=True,
            append_images=quantized[1:],
            duration=int(1000 / self.fps),
            loop=0,
            optimize=False,
        )
