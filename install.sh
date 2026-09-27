#!/bin/sh
# Pioneer DDJ-1000 for Linux + Mixxx: audio driver, Mixxx mappings and the
# jog-screen service. Run as your normal user from the repository folder:
#
#   ./install.sh                 everything
#   ./install.sh --no-driver     skip the kernel driver (mappings + screens only)
#   ./install.sh --no-screens    skip the jog-screen service
#
# Tested on Linux Mint 22 / Ubuntu 24.04 (kernel 6.14). Needs kernel 6.6+.
set -eu

REPO="$(cd "$(dirname "$0")" && pwd)"
PKG=snd-usb-audio-ddj1000
VER="$(sed -n 's/^PACKAGE_VERSION="\(.*\)"/\1/p' "$REPO/driver/dkms.conf")"
PREFIX="$HOME/.local/share/ddj1000-screens"
MIXXX_CONTROLLERS="$HOME/.mixxx/controllers"
DRIVER=1
SCREENS=1

for arg in "$@"; do
    case "$arg" in
        --no-driver) DRIVER=0 ;;
        --no-screens) SCREENS=0 ;;
        -h|--help) sed -n '2,10p' "$0"; exit 0 ;;
        *) echo "unknown option: $arg" >&2; exit 1 ;;
    esac
done

step() { printf '\n==> %s\n' "$*"; }

if [ "$(id -u)" -eq 0 ]; then
    echo "Run this as your normal user; it uses sudo where needed." >&2
    exit 1
fi
if ! command -v apt-get >/dev/null; then
    echo "This installer supports Debian/Ubuntu/Mint (apt). See README for manual steps." >&2
    exit 1
fi

step "Installing packages"
packages="python3"
[ "$DRIVER" = 1 ] && packages="$packages build-essential dkms curl xz-utils linux-headers-$(uname -r)"
[ "$SCREENS" = 1 ] && packages="$packages python3-rtmidi python3-pil python3-mutagen python3-numpy ffmpeg fonts-dejavu-core"
# shellcheck disable=SC2086
sudo apt-get install -y $packages

if [ "$DRIVER" = 1 ]; then
    step "Building the snd-usb-audio driver with DDJ-1000 support (DKMS $PKG/$VER)"
    sudo rm -rf "/usr/src/$PKG-$VER"
    sudo cp -r "$REPO/driver" "/usr/src/$PKG-$VER"
    sudo chmod +x "/usr/src/$PKG-$VER/prepare.sh"
    sudo dkms status "$PKG/$VER" | grep -q . || sudo dkms add "$PKG/$VER"
    sudo dkms build "$PKG/$VER" --force
    # Replace older versions only once the new one has built.
    for old in $(sudo dkms status "$PKG" | sed -n "s#^$PKG/\([^,:]*\).*#\1#p" | sort -u); do
        [ "$old" = "$VER" ] || sudo dkms remove "$PKG/$old" --all
    done
    sudo dkms install "$PKG/$VER" --force

    sudo install -m 644 "$REPO/config/ddj1000-modprobe.conf" /etc/modprobe.d/ddj1000.conf
    if sudo modprobe -r snd_usb_audio 2>/dev/null && sudo modprobe snd_usb_audio; then
        echo "Driver reloaded."
    else
        echo "Could not reload snd_usb_audio (in use) - unplug and replug the DDJ-1000, or reboot."
    fi
fi

step "Device permissions and real-time audio"
sudo install -m 644 "$REPO/config/70-ddj1000.rules" /etc/udev/rules.d/70-ddj1000.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
sudo udevadm trigger --subsystem-match=usb --attr-match=idVendor=2b73
sudo install -m 644 "$REPO/config/95-audio-rt.conf" /etc/security/limits.d/95-audio-rt.conf
sudo usermod -aG audio "$USER"

step "Keeping PipeWire off the DDJ-1000 sound card"
wp="$(wireplumber --version 2>/dev/null | sed -n 's/.*libwireplumber \([0-9]*\.[0-9]*\).*/\1/p' | tail -1)"
case "$wp" in
    0.4)
        mkdir -p "$HOME/.config/wireplumber/main.lua.d"
        cp "$REPO/config/51-ddj1000-disable.lua" "$HOME/.config/wireplumber/main.lua.d/" ;;
    "")
        echo "WirePlumber not found; skipping." ;;
    *)
        mkdir -p "$HOME/.config/wireplumber/wireplumber.conf.d"
        cp "$REPO/config/51-ddj1000-disable.conf" "$HOME/.config/wireplumber/wireplumber.conf.d/" ;;
esac

step "Installing the Mixxx mappings"
mkdir -p "$MIXXX_CONTROLLERS"
cp "$REPO/mixxx/Pioneer DDJ-1000.midi.xml" "$REPO/mixxx/Pioneer-DDJ-1000-script.js" "$MIXXX_CONTROLLERS/"
if [ "$SCREENS" = 1 ]; then
    cp "$REPO/mixxx/Pioneer DDJ-1000 Screens.midi.xml" "$REPO/mixxx/Pioneer-DDJ-1000-Screens-script.js" "$MIXXX_CONTROLLERS/"
else
    # Without the service, let the main mapping use the plain MIDI jog displays.
    sed -i 's/^PioneerDDJ1000.screensService = true;/PioneerDDJ1000.screensService = false;/' \
        "$MIXXX_CONTROLLERS/Pioneer-DDJ-1000-script.js"
fi

if [ "$SCREENS" = 1 ]; then
    step "Installing the jog-screen service"
    mkdir -p "$PREFIX/labels" "$HOME/.config/systemd/user"
    cp "$REPO"/screens/*.py "$PREFIX/"
    cp "$REPO"/screens/labels/*.jpg "$PREFIX/labels/"
    cp "$REPO/config/ddj1000-screens.service" "$HOME/.config/systemd/user/"
    systemctl --user daemon-reload
    systemctl --user enable ddj1000-screens.service
    systemctl --user restart ddj1000-screens.service
fi

cat <<EOF

Done. Finish the setup in Mixxx (Preferences):

  Sound Hardware   Sound API: ALSA, Sample rate: 44100 Hz
                   Main       -> DDJ-1000: USB Audio (hw:1,0), channels 1-2
                   Headphones -> DDJ-1000: USB Audio (hw:1,0), channels 3-4
                   Booth      -> DDJ-1000: USB Audio (hw:1,0), channels 5-6 (optional)
  Controllers      DDJ-1000 MIDI 1   -> "Pioneer DDJ-1000", Enabled
EOF
if [ "$SCREENS" = 1 ]; then
cat <<EOF
                   DDJ-1000 Screens  -> "Pioneer DDJ-1000 Screens", Enabled

Optional:
  Own labels for tracks without a cover:
      python3 $PREFIX/make_labels.py "Left text" "Right text"
      systemctl --user restart ddj1000-screens
  Pre-compute jog-screen waveforms for the whole Mixxx library:
      python3 $PREFIX/precache_waveforms.py
EOF
fi
echo
echo "Log out and back in once (audio group / real-time priority)."
