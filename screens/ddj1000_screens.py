#!/usr/bin/env python3
"""DDJ-1000 jog screen service for Mixxx.

Logs in to the DDJ-1000 the way rekordbox does (SysEx challenge-response),
keeps the session alive and drives both jog screens over HID: time, length,
BPM, tempo, key, cue marker, beat grid and artwork. Tracks without cover art
show "Kalte" (left decks) or "Studio" (right decks).

Deck state comes from Mixxx through the virtual MIDI port "DDJ-1000 Screens"
(mapping "Pioneer DDJ-1000 Screens"); cover art and file paths come from
Mixxx's library database.
"""
import ctypes
import fcntl
import glob
import io
import logging
import os
import queue
import sqlite3
import threading
import time

import rtmidi
from PIL import Image

import ddj_link
import waveform

log = logging.getLogger("ddj1000-screens")
HERE = os.path.dirname(os.path.abspath(__file__))
MIXXX_DB = os.path.expanduser("~/.mixxx/mixxxdb.sqlite")
PORT_NAME = "DDJ-1000 Screens"
CONFIG_DIR = os.path.expanduser("~/.config/ddj1000-screens")
# Artwork for tracks without a cover: left decks (1, 3) and right decks (2, 4).
# ~/.config/ddj1000-screens/left.jpg / right.jpg override the bundled labels.
LABELS = {1: "left", 2: "right", 3: "left", 4: "right"}
DEFAULT_LABELS = {"left": "labels/kalte.jpg", "right": "labels/studio.jpg"}
MAX_JPEG = 32 * 58 - 2          # the size rekordbox uses; known to display
STATE_MAGIC = [0x7D, 0x44, 0x31]  # F0 7D 44 31 <deck> ... F7 (non-commercial ID)

USBDEVFS_CONTROL = 0xC0185500
DRIVER_CHECK_INTERVAL = 5
# Status frames: rekordbox sends ~120/s to a playing deck. Playing decks get a
# frame every tick, paused/empty decks every IDLE_EVERY ticks.
TICK = 0.01
IDLE_EVERY = 10
# Mixxx reports positions every 20 ms, and they move in audio-buffer steps
# (~23 ms), so snapping to each report makes the platter jitter. A playing
# deck's position instead runs on a smoothing clock: it always moves forward
# at the track speed, reports only trim that speed (up to MAX_CORRECTION), and
# it snaps only when a report is further off than SNAP_MS (cue, seek, loop).
MAX_EXTRAPOLATION = 0.25
SNAP_MS = 100.0
CORRECTION_GAIN = 1 / 800.0
MAX_CORRECTION = 0.05


class UsbCtrl(ctypes.Structure):
    _fields_ = [("bRequestType", ctypes.c_uint8), ("bRequest", ctypes.c_uint8),
                ("wValue", ctypes.c_uint16), ("wIndex", ctypes.c_uint16),
                ("wLength", ctypes.c_uint16), ("timeout", ctypes.c_uint32),
                ("data", ctypes.c_void_p)]


def announce_driver():
    """Send the vendor request Pioneer's audio driver makes (C0 00 0000 8003).

    Without it the jog screens show "no audio driver" while audio streams.
    Returns True if the request went through."""
    for id_file in glob.glob("/sys/bus/usb/devices/*/idVendor"):
        base = os.path.dirname(id_file)
        try:
            if open(id_file).read().strip() != "2b73" or                     open(base + "/idProduct").read().strip() != "0020":
                continue
            dev = "/dev/bus/usb/%03d/%03d" % (int(open(base + "/busnum").read()),
                                              int(open(base + "/devnum").read()))
            fd = os.open(dev, os.O_RDWR)
        except OSError as e:
            log.warning("driver announce: %s", e)
            return False
        try:
            buf = ctypes.create_string_buffer(2)
            req = UsbCtrl(0xC0, 0x00, 0x0000, 0x8003, 2, 1000, ctypes.cast(buf, ctypes.c_void_p))
            fcntl.ioctl(fd, USBDEVFS_CONTROL, req)
            return True
        except OSError as e:
            log.warning("driver announce failed: %s", e)
            return False
        finally:
            os.close(fd)
    return False


def audio_running():
    try:
        return "Status: Running" in open("/proc/asound/DDJ1000/stream0").read()
    except OSError:
        return False


# Filler copied from rekordbox (meaning unknown, constant across tracks).
CUE_SLOTS = bytes.fromhex("0a00") + bytes.fromhex("9e2f270100") * 10


def time_field(ms):
    """[minutes][seconds][milliseconds LE16], as the DDJ displays it."""
    ms = max(0, int(ms))
    return bytes([min(ms // 60000, 255), (ms // 1000) % 60]) + (ms % 1000).to_bytes(2, "little")


def chunked(deck, cmd, payload):
    total = max(1, -(-len(payload) // 58))
    payload += bytes(total * 58 - len(payload))
    return [bytes([deck << 4, cmd]) + (i + 1).to_bytes(2, "little") + total.to_bytes(2, "little")
            + payload[i * 58:(i + 1) * 58] for i in range(total)]


# Mixxx key number (1-12 C..B major, 13-24 Cm..Bm minor) -> DDJ key code.
KEY_CODES = [0x00,
             0x01, 0x03, 0x05, 0x07, 0x09, 0x0B, 0x0D, 0x0F, 0x11, 0x13, 0x15, 0x17,
             0x08, 0x0A, 0x0C, 0x0E, 0x10, 0x12, 0x14, 0x16, 0x18, 0x02, 0x04, 0x06]


class Deck:
    def __init__(self, number):
        self.number = number
        self.loaded = False
        self.playing = False
        self.leader = False
        self.position = 0
        self.duration = 0
        self.bpm = 0.0
        self.file_bpm = 0.0
        self.pitch = 0.0
        self.key = 0
        self.shift = 0
        self.cue = -1
        self.phase = 0
        self.stamp = 0.0    # time.monotonic() of the last Mixxx update
        self.clock = None   # smoothing clock: [position ms, time, correction]
        self.clock_running = False
        self.last_shown = None
        self.track = None   # (duration_ms, file_bpm) of the track whose data was sent

    def speed(self):
        return 1 + self.pitch / 100

    def observe(self, now):
        """Feed a Mixxx position report into the smoothing clock."""
        if not self.playing or self.clock is None or not self.clock_running:
            # Paused, or (re)starting: restart the clock from the report.
            self.clock = [float(self.position), now, 0.0]
            self.clock_running = self.playing
            self.last_shown = None
            return
        pos, since, corr = self.clock
        predicted = pos + (now - since) * 1000 * self.speed() * (1 + corr)
        error = self.position - predicted
        if abs(error) > SNAP_MS:
            self.clock = [float(self.position), now, 0.0]
            self.last_shown = None
        else:
            corr = max(-MAX_CORRECTION, min(MAX_CORRECTION, error * CORRECTION_GAIN))
            self.clock = [predicted, now, corr]

    def current_position(self, now):
        if not self.playing or self.clock is None:
            return self.position
        pos, since, corr = self.clock
        elapsed = min(max(now - since, 0.0), MAX_EXTRAPOLATION)
        position = pos + elapsed * 1000 * self.speed() * (1 + corr)
        if self.last_shown is not None and position < self.last_shown and self.speed() > 0:
            position = self.last_shown         # never step backwards while playing
        self.last_shown = position
        return max(0, min(position, self.duration))

    def status(self, now):
        f = bytearray(64)
        f[0], f[1], f[4] = self.number << 4, 0x21, 0x21
        position = self.current_position(now)
        at_cue = self.cue >= 0 and abs(position - self.cue) < 50
        f[2] = 0x18 if self.playing or not self.loaded or at_cue else 0x1A
        f[3] = 0x0A if self.leader else 0x08
        f[5] = 0x81 if self.leader else 0x01
        f[27] = 0x80
        f[61] = 0x0D
        f[60] = 0x80
        if not self.loaded:
            f[9] = 0x10
            return bytes(f)
        f[9], f[58] = 0xB4, 0x01
        f[11:15] = time_field(position)
        f[15:19] = time_field(self.duration)
        # BPM: integer, then tenths in the high nibble. rekordbox leaves the low
        # nibble 0; anything else makes the screen show 999.99.
        bpm = round(self.bpm * 10)
        f[21], f[22] = min(bpm // 10, 255), (bpm % 10) << 4
        f[38], f[39] = f[21], f[22]
        f[23:25] = max(-32768, min(32767, round(self.pitch * 100))).to_bytes(2, "little", signed=True)
        if self.cue >= 0:
            f[29:33] = time_field(self.cue)
            f[53:57] = time_field(self.cue)
        if 0 < self.key < len(KEY_CODES):
            f[60] = 0x80 | KEY_CODES[self.key]
            f[61] = 0x0D + max(-12, min(12, self.shift))
        return bytes(f)


class Screens:
    def __init__(self):
        self.decks = {n: Deck(n) for n in (1, 2, 3, 4)}
        self.hid = None
        self.out = None
        self.midi_in = None
        self.sysex = queue.Queue()
        self.hid_queue = queue.Queue()
        self.connected = False
        self.last_state = 0
        self.lock = threading.Lock()
        self.cover_cache = {}
        self.waves = {}            # deck number -> (track key, waveform bytes)
        self.wave_jobs = queue.Queue()
        threading.Thread(target=self.wave_worker, daemon=True).start()

    # ---- devices -------------------------------------------------------
    @staticmethod
    def find_hid():
        for uevent in glob.glob("/sys/class/hidraw/hidraw*/device/uevent"):
            if "DDJ-1000" in open(uevent).read():
                return "/dev/" + uevent.split("/")[4]
        return None

    def open_midi(self):
        out = rtmidi.MidiOut(rtmidi.API_LINUX_ALSA, name="DDJ-1000 Screens link")
        port = next((i for i, p in enumerate(out.get_ports()) if p.startswith("DDJ-1000:")), None)
        if port is None:
            return False
        inp = rtmidi.MidiIn(rtmidi.API_LINUX_ALSA, name="DDJ-1000 Screens link")
        inp.ignore_types(sysex=False, timing=True, active_sense=True)
        in_port = next(i for i, p in enumerate(inp.get_ports()) if p.startswith("DDJ-1000:"))
        out.open_port(port, "link out")
        inp.open_port(in_port, "link in")
        inp.set_callback(self.on_ddj_midi)
        self.out, self.midi_in = out, inp
        return True

    def close(self):
        for dev in (self.midi_in, self.out):
            try:
                dev.close_port()
            except Exception:
                pass
        if self.hid is not None:
            try:
                os.close(self.hid)
            except OSError:
                pass
        self.hid = self.out = self.midi_in = None
        self.connected = False

    def on_ddj_midi(self, event, _data=None):
        msg = bytes(event[0])
        if msg[:1] == b"\xF0" and msg[:9] == ddj_link.PFX:
            self.sysex.put(msg)

    def wait_sysex(self, stage, timeout=1.0):
        end = time.time() + timeout
        while time.time() < end:
            try:
                msg = self.sysex.get(timeout=max(0.01, end - time.time()))
            except queue.Empty:
                break
            if len(msg) > 9 and msg[9] == stage:
                return msg
        return None

    def send_midi(self, data):
        self.out.send_message(list(data))

    # ---- connection ----------------------------------------------------
    def connect(self):
        path = self.find_hid()
        if not path or not self.open_midi():
            self.close()
            return False
        try:
            self.hid = os.open(path, os.O_RDWR)
        except OSError as e:
            log.warning("cannot open %s: %s", path, e)
            self.close()
            return False
        if not ddj_link.handshake(self.send_midi, self.wait_sysex):
            log.warning("handshake failed")
            self.close()
            return False
        for msg in ddj_link.SETUP:
            self.send_midi(msg)
        announce_driver()
        self.connected = True
        for deck in self.decks.values():
            deck.track = None      # resend everything to a freshly connected unit
        log.info("connected to DDJ-1000 (%s)", path)
        return True

    def hid_write(self, reports):
        for r in reports:
            os.write(self.hid, b"\x00" + r)

    # ---- Mixxx side ----------------------------------------------------
    def on_mixxx(self, event, _data=None):
        msg = event[0]
        if len(msg) < 4 + 28 + 1 or msg[0] != 0xF0 or msg[1:4] != STATE_MAGIC:
            return
        v = msg[4:-1]

        def num(i, n):
            x = 0
            for b in v[i:i + n]:
                x = (x << 7) | b
            return x

        deck = self.decks.get(v[0] + 1)
        if deck is None:
            return
        with self.lock:
            deck.loaded = bool(v[1] & 1)
            deck.playing = bool(v[1] & 2)
            deck.leader = bool(v[1] & 4)
            deck.position = num(2, 4)
            deck.stamp = time.monotonic()
            deck.duration = num(6, 4)
            deck.bpm = num(10, 3) / 100
            deck.file_bpm = num(13, 3) / 100
            deck.pitch = (num(16, 3) - 100000) / 100
            deck.key = v[19]
            deck.shift = v[20] - 64
            cue = num(21, 4)
            deck.cue = -1 if cue == 0x0FFFFFFF else cue
            deck.phase = num(25, 3)
            deck.observe(deck.stamp)
        if time.time() - self.last_state > 2:
            log.info("receiving deck state from Mixxx")
        self.last_state = time.time()

    # ---- track data ----------------------------------------------------
    def lookup_track(self, deck):
        try:
            db = sqlite3.connect("file:%s?mode=ro" % MIXXX_DB, uri=True, timeout=2)
            rows = db.execute(
                "SELECT t.location, l.bpm, l.coverart_location FROM library l "
                "JOIN track_locations t ON l.location = t.id "
                "WHERE l.mixxx_deleted = 0 AND abs(l.duration * 1000 - ?) < 30",
                (deck.duration,)).fetchall()
            db.close()
        except sqlite3.Error as e:
            log.warning("library lookup failed: %s", e)
            return None
        if not rows:
            return None
        rows.sort(key=lambda r: abs((r[1] or 0) - deck.file_bpm))
        return rows[0]

    def cover_for(self, track):
        if track is None:
            return None
        path, _, cover_location = track
        if path in self.cover_cache:
            return self.cover_cache[path]
        image = None
        try:
            import mutagen
            f = mutagen.File(path)
            data = None
            if f is not None and f.tags is not None:
                if hasattr(f.tags, "getall"):
                    pics = f.tags.getall("APIC")
                    data = pics[0].data if pics else None
                elif "covr" in f.tags:
                    data = bytes(f.tags["covr"][0])
            if data is None and hasattr(f, "pictures") and f.pictures:
                data = f.pictures[0].data
            if data:
                image = Image.open(io.BytesIO(data))
        except Exception as e:
            log.debug("no embedded cover in %s: %s", path, e)
        if image is None:
            folder = os.path.dirname(path)
            names = [cover_location] if cover_location else []
            names += ["cover.jpg", "folder.jpg", "front.jpg", "cover.png", "folder.png"]
            for name in names:
                candidate = os.path.join(folder, name)
                if name and os.path.isfile(candidate):
                    try:
                        image = Image.open(candidate)
                        break
                    except Exception:
                        pass
        jpeg = self.encode_cover(image) if image is not None else None
        self.cover_cache[path] = jpeg
        return jpeg

    @staticmethod
    def encode_cover(image):
        image = image.convert("RGB")
        w, h = image.size
        side = min(w, h)
        image = image.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
        image = image.resize((80, 80), Image.LANCZOS)
        for quality in range(85, 15, -5):
            buf = io.BytesIO()
            image.save(buf, "JPEG", quality=quality, subsampling=2, progressive=False)
            if len(buf.getvalue()) <= MAX_JPEG:
                return buf.getvalue()
        return None

    def label(self, side):
        custom = os.path.join(CONFIG_DIR, side + ".jpg")
        if os.path.isfile(custom):
            try:
                data = open(custom, "rb").read()
                if len(data) <= MAX_JPEG and data[:2] == bytes.fromhex("ffd8"):
                    return data
                return self.encode_cover(Image.open(io.BytesIO(data)))
            except Exception as e:
                log.warning("bad label %s: %s", custom, e)
        return open(os.path.join(HERE, DEFAULT_LABELS[side]), "rb").read()

    def beat_grid(self, deck):
        if deck.file_bpm <= 0:
            return (0).to_bytes(2, "little")
        beat = 60000 / deck.file_bpm
        t, n, out = deck.phase, 0, bytearray()
        while t < deck.duration and n < 4000:
            out += bytes([n % 4 + 1]) + int(t).to_bytes(3, "little")
            t += beat
            n += 1
        return n.to_bytes(2, "little") + bytes(out)

    def wave_worker(self):
        """Compute waveforms off the main loop (ffmpeg decode takes seconds)."""
        while True:
            number, key, path = self.wave_jobs.get()
            try:
                data = waveform.cached(path)
            except Exception as e:
                log.warning("waveform for %s failed: %s", path, e)
                continue
            if data:
                with self.lock:
                    self.waves[number] = (key, data)

    def send_track(self, deck):
        number = deck.number
        if not deck.loaded:
            self.hid_write(chunked(number, 0x30, bytes(116)))
            self.hid_write(chunked(number, 0x2F, bytes(58)))
            self.hid_write(chunked(number, 0x2B, bytes(58)))
            return
        length = time_field(deck.duration)
        track = self.lookup_track(deck)
        jpeg = self.cover_for(track)
        if jpeg is None:
            jpeg = self.label(LABELS[number])
        self.hid_write(chunked(number, 0x30, length + bytes(112)))
        self.hid_write(chunked(number, 0x2D, length + CUE_SLOTS))
        self.hid_write(chunked(number, 0x2F, self.beat_grid(deck)))
        self.hid_write(chunked(number, 0x2C, bytes(73 * 58)))
        if track:
            self.wave_jobs.put((number, deck.track, track[0]))
        self.hid_write(chunked(number, 0x2B, len(jpeg).to_bytes(2, "little") + jpeg))
        log.info("deck %d: %s (%s)", number, track[0] if track else "unknown track",
                 "cover" if track and self.cover_cache.get(track[0]) else LABELS[number] + " label")

    # ---- main loop -----------------------------------------------------
    def run(self):
        mixxx_in = rtmidi.MidiIn(rtmidi.API_LINUX_ALSA, name=PORT_NAME)
        mixxx_in.ignore_types(sysex=False, timing=True, active_sense=True)
        mixxx_in.open_virtual_port(PORT_NAME)
        mixxx_in.set_callback(self.on_mixxx)
        # Mixxx lists a MIDI controller only if it has an input side too.
        mixxx_out = rtmidi.MidiOut(rtmidi.API_LINUX_ALSA, name=PORT_NAME)
        mixxx_out.open_virtual_port(PORT_NAME)
        log.info("virtual MIDI port %r ready", PORT_NAME)

        last_keepalive = 0
        last_announce = 0
        last_audio_check = 0
        was_running = running = False
        tick = 0
        next_tick = time.monotonic()
        while True:
            if not self.connected:
                if not self.connect():
                    time.sleep(2)
                    continue
                last_keepalive = 0
            try:
                now = time.time()
                if now - last_keepalive >= 0.2:
                    self.send_midi(ddj_link.KEEPALIVE)
                    last_keepalive = now
                if now - last_audio_check >= 1:
                    running = audio_running()
                    last_audio_check = now
                if (running and not was_running) or now - last_announce >= DRIVER_CHECK_INTERVAL:
                    if running and not was_running:
                        log.info("audio stream started; announcing driver")
                    announce_driver()
                    last_announce = now
                was_running = running
                if now - self.last_state > 2:
                    # Mixxx not running: show empty decks.
                    if any(d.loaded for d in self.decks.values()):
                        log.info("no deck state from Mixxx; showing empty decks")
                    with self.lock:
                        for deck in self.decks.values():
                            deck.loaded = False
                tick += 1
                with self.lock:
                    decks = list(self.decks.values())
                    mono = time.monotonic()
                    frames = [d.status(mono) for d in decks
                              if d.playing or tick % IDLE_EVERY == 0]
                    changed = [d for d in decks
                               if d.track != ((d.duration, round(d.file_bpm, 1)) if d.loaded else None)]
                    for d in changed:
                        d.track = (d.duration, round(d.file_bpm, 1)) if d.loaded else None
                for d in changed:
                    self.send_track(d)
                with self.lock:
                    ready = [(n, data) for n, (key, data) in self.waves.items()
                             if self.decks[n].track == key]
                    self.waves.clear()
                for n, data in ready:
                    self.hid_write(chunked(n, 0x2C, data))
                for frame in frames:
                    self.hid_write([frame])
                next_tick += TICK
                delay = next_tick - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                else:
                    next_tick = time.monotonic()   # fell behind; don't try to catch up
            except (OSError, rtmidi.SystemError) as e:
                log.warning("DDJ-1000 connection lost: %s", e)
                self.close()
                time.sleep(2)
                next_tick = time.monotonic()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    Screens().run()
