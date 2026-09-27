#!/usr/bin/env python3
"""Build the DDJ-1000 jog-screen overview waveform (HID command 0x2C).

Format, from rekordbox captures: one header byte 0x80, then 600 columns of
7 bytes: outer colour (RGB565 LE), inner colour (RGB565 LE), outer height,
inner height (0-40 each), 0x00. rekordbox draws the peak in the outer colour
and the average level in a brighter inner colour; colour follows the
frequency content (bass red, mids green, highs blue).
"""
import hashlib
import os
import subprocess
import sys

import numpy as np

COLUMNS = 600
MAX_HEIGHT = 40
RATE = 11025
CACHE = os.path.expanduser("~/.cache/ddj1000-screens")
# Relative band weights so typical music is not drowned in bass red.
WEIGHTS = np.array([1.0, 1.7, 3.2])


def rgb565(r, g, b):
    r, g, b = (int(max(0, min(1, c)) * m + 0.5) for c, m in ((r, 31), (g, 63), (b, 31)))
    return ((r << 11) | (g << 5) | b).to_bytes(2, "little")


def decode(path):
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-nostdin", "-i", path, "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-"],
        stdout=subprocess.PIPE, check=True, timeout=120).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def columns(samples):
    """Per column: peak, rms and (low, mid, high) band magnitudes."""
    n = len(samples)
    edges = np.linspace(0, n, COLUMNS + 1).astype(int)
    peaks, rms, bands = np.zeros(COLUMNS), np.zeros(COLUMNS), np.zeros((COLUMNS, 3))
    for i in range(COLUMNS):
        chunk = samples[edges[i]:edges[i + 1]]
        if len(chunk) < 16:
            continue
        peaks[i] = np.max(np.abs(chunk))
        rms[i] = np.sqrt(np.mean(chunk * chunk))
        spectrum = np.abs(np.fft.rfft(chunk * np.hanning(len(chunk))))
        freqs = np.fft.rfftfreq(len(chunk), 1 / RATE)
        bands[i] = [np.sqrt(np.sum(spectrum[(freqs >= lo) & (freqs < hi)] ** 2))
                    for lo, hi in ((20, 250), (250, 2500), (2500, RATE / 2))]
    return peaks, rms, bands


def build(path):
    samples = decode(path)
    peaks, rms, bands = columns(samples)
    scale = max(np.max(peaks), 1e-6)
    out = bytearray([0x80])
    for i in range(COLUMNS):
        mix = bands[i] * WEIGHTS
        top = np.max(mix)
        r, g, b = (mix / top) if top > 0 else (0, 0, 0)
        outer = int(round(peaks[i] / scale * MAX_HEIGHT))
        inner = min(outer, int(round(rms[i] / scale * MAX_HEIGHT * 1.6)))
        out += rgb565(r * 0.6, g * 0.6, b * 0.6) + rgb565(r, g, b) + bytes([outer, inner, 0])
    return bytes(out)


def cached(path):
    """Waveform bytes for path, cached on disk by path + size + mtime."""
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = hashlib.sha1(("%s|%d|%d|v1" % (path, st.st_size, int(st.st_mtime))).encode()).hexdigest()
    cache_file = os.path.join(CACHE, key + ".bin")
    try:
        return open(cache_file, "rb").read()
    except OSError:
        pass
    data = build(path)
    os.makedirs(CACHE, exist_ok=True)
    with open(cache_file + ".tmp", "wb") as f:
        f.write(data)
    os.replace(cache_file + ".tmp", cache_file)
    return data


def render(data, png):
    """Preview image, drawn the way the jog screen shows it."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (COLUMNS, 90), (0, 0, 0))
    d = ImageDraw.Draw(img)
    for x in range(COLUMNS):
        c = data[1 + 7 * x: 8 + 7 * x]
        for colour, h in ((c[0:2], c[4]), (c[2:4], c[5])):
            v = int.from_bytes(colour, "little")
            fill = ((v >> 11) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31)
            d.line((x, 45 - h, x, 45 + h), fill=fill)
    img.save(png)


if __name__ == "__main__":
    import time
    t = time.time()
    data = build(sys.argv[1])
    print("%d bytes in %.1f s" % (len(data), time.time() - t))
    if len(sys.argv) > 2:
        render(data, sys.argv[2])
