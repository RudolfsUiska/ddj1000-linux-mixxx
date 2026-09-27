# Pioneer DDJ-1000 on Linux with Mixxx

Everything needed to DJ with a **Pioneer DJ / AlphaTheta DDJ-1000** on Linux
in [Mixxx](https://mixxx.org):

- **Audio driver**: the stock Linux kernel sees the DDJ-1000's MIDI but not
  its sound card. This adds the missing `snd-usb-audio` quirk
  (6 outputs / 12 inputs, 24-bit, 44.1 kHz) as a DKMS module that rebuilds
  itself on kernel updates.
- **Mixxx mapping**: all 4 decks, mixer, jog wheels (scratch, bend, search),
  8 pad modes x 2 pages, loops, sync, key controls, Beat FX, browser.
- **Jog screens**: the DDJ-1000's jog displays only work after a
  rekordbox-style login. A small background service does that login and
  shows time, BPM, tempo, key, cue marker, beat grid, the colour waveform and
  the track's cover art. Tracks without a cover show a custom label
  (default: "Kalte" on the left decks, "Studio" on the right).

## Requirements

- Debian, Ubuntu, Linux Mint or similar (the installer uses `apt`)
- Linux kernel 6.6 or newer (`uname -r`)
- Mixxx 2.5 or newer (`sudo add-apt-repository ppa:mixxx/mixxx && sudo apt install mixxx`)

## Install

```sh
git clone https://github.com/RudolfsUiska/ddj1000-linux-mixxx.git
cd ddj1000-linux-mixxx
./install.sh
```

The installer asks for your password (sudo). It:

1. installs build tools and Python packages,
2. builds and installs the driver with DKMS. The first build downloads the
   matching kernel sources from kernel.org (~140 MB, cached),
3. sets up device permissions, a fixed ALSA card number and real-time audio,
4. copies the Mixxx mappings to `~/.mixxx/controllers`,
5. installs and starts the `ddj1000-screens` user service.

Options: `--no-driver` (mappings and screens only), `--no-screens`
(driver and mappings only).

Then **log out and back in once**, plug in the DDJ-1000 and set up Mixxx.

## Set up Mixxx

Open **Preferences**:

**Sound Hardware**
- Sound API: **ALSA**, Sample rate: **44100 Hz**
- Main: **DDJ-1000: USB Audio (hw:1,0)**, channels **1-2**
- Headphones: **DDJ-1000: USB Audio (hw:1,0)**, channels **3-4**
- Booth (optional): same device, channels **5-6**

**Controllers**
- **DDJ-1000 MIDI 1**: load **Pioneer DDJ-1000**, tick *Enabled*
- **DDJ-1000 Screens**: load **Pioneer DDJ-1000 Screens**, tick *Enabled*

Restart Mixxx. Start the DDJ-1000 before Mixxx; the jog screens switch
from the Pioneer DJ / rekordbox logos to the track view within a few seconds.

On the DDJ-1000, set every channel's **INPUT SELECT** switch to the USB port
(A or B) the computer is plugged into.

## Usage notes

- **Mixing** happens in Mixxx; faders, EQs, trims and the crossfader are
  plain MIDI. The **master, booth and headphone knobs** and the mic inputs
  work in the controller's hardware.
- **Beat FX** controls Mixxx effect unit 1 when CH SELECT is CH1-CH4. With
  CH SELECT on MASTER the controller's own Beat FX is used.
- **Color FX** knobs control each channel's quick effect (filter).
- **Pads**: hot cue, pad FX (loop rolls), beat jump, sampler, keyboard,
  pad FX 2 (brake, spinback, reverse roll, stutter, rolls), beat loop and
  key shift; PAGE buttons switch to page 2.
- **Custom labels** for tracks without a cover:

  ```sh
  python3 ~/.local/share/ddj1000-screens/make_labels.py "Left text" "Right text"
  systemctl --user restart ddj1000-screens
  ```

  Or put any image at `~/.config/ddj1000-screens/left.jpg` / `right.jpg`.
  The jog screen shows only the **top half** of the image.
- **Waveforms** are computed when a track loads (2-3 s, then cached). To
  compute them for the whole library in advance:

  ```sh
  python3 ~/.local/share/ddj1000-screens/precache_waveforms.py
  ```

## Troubleshooting

| Problem | Fix |
|---|---|
| No "DDJ-1000: USB Audio" in Mixxx | `cat /proc/asound/cards` should list `DDJ1000`. If not: `dkms status`, then replug the DDJ-1000 or reboot. |
| Jog screens say **no audio driver** | Check the service: `journalctl --user -u ddj1000-screens -f`. It should log `connected to DDJ-1000`. Start Mixxx after the DDJ-1000 is on. |
| Jog screens show logos only | The service is not running: `systemctl --user status ddj1000-screens`. |
| Screens stop updating after restarting the service | Restart Mixxx as well. |
| Crackles | Log out/in after installing (real-time priority), raise the audio buffer in Mixxx. |

To remove everything: `./uninstall.sh`

## How it works

- `driver/`: `apply_quirk.py` adds the DDJ-1000 entry to the kernel's
  `sound/usb/quirks-table.h`; `prepare.sh` runs during each DKMS build to
  fetch and patch the sources for that kernel.
- `mixxx/`: the mappings. `gen_xml.py` generates the main XML from the
  DDJ-1000 MIDI message list.
- `screens/`: `ddj_link.py` (login handshake), `ddj1000_screens.py`
  (service), `waveform.py`, `make_labels.py`.
- `docs/PROTOCOL.md`: the jog-screen protocol, decoded from USB captures of
  rekordbox.

## Credits

- The login handshake follows the
  [Pioneer CDJ HID analysis](https://swiftb0y.github.io/CDJHidProtocol/hid-analysis/handshake.html)
  by the Mixxx community.
- The first DDJ-1000 audio quirk:
  [lSANCHOl/ddj1000-linux](https://github.com/lSANCHOl/ddj1000-linux).
- MIDI messages: Pioneer DJ "DDJ-1000 List of MIDI message" v1.00.

This project is not affiliated with Pioneer DJ / AlphaTheta. It exists so
that owners can use their own hardware with free software.

## License

GPL-2.0-or-later (see `LICENSE`). The driver part is derived from the Linux
kernel (GPL-2.0).
