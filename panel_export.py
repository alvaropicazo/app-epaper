"""Pack a 648x480 image into the raw format of the Waveshare 5.83" e-Paper (G).
 
Format (from Waveshare's manual): 2 bits per pixel, 4 pixels per byte,
the first pixel in the highest bits, rows left to right, top to bottom.
Codes: black 00, white 01, yellow 10, red 11.  Example: 0x1B = B, W, Y, R.
A full frame is 648 / 4 * 480 = 77,760 bytes.
"""
from pathlib import Path
 
from PIL import Image
 
W, H = 648, 480
FRAME_BYTES = W // 4 * H  # 77760
 
 
def pack_for_panel(img, rgb_to_code):
    """img: PIL image of exactly 648x480 that only contains colors from rgb_to_code.
    rgb_to_code: {(r, g, b): 0..3}. Returns the packed bytes."""
    if img.size != (W, H):
        raise ValueError(f"image must be {W}x{H}, got {img.size[0]}x{img.size[1]}")
    lookup = {bytes(rgb): code for rgb, code in rgb_to_code.items()}
    data = img.convert("RGB").tobytes()
    out = bytearray(FRAME_BYTES)
    for i in range(W * H):
        key = data[3 * i:3 * i + 3]
        try:
            code = lookup[key]
        except KeyError:
            raise ValueError(f"pixel {i} has a color that is not a panel color: {tuple(key)}")
        out[i >> 2] |= code << (6 - 2 * (i & 3))
    return bytes(out)
 
 
def save_panel_bin(img, path, rgb_to_code):
    data = pack_for_panel(img, rgb_to_code)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    print(f"Saved {path} ({len(data)} bytes)")
