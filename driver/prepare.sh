#!/bin/sh
# DKMS PRE_BUILD step: fetch sound/usb for the target kernel from kernel.org,
# add the DDJ-1000 quirk and write a Makefile that builds only snd-usb-audio.
#
#   prepare.sh <kernel version>        (e.g. 6.14.0-37-generic)
#
# Tarballs are cached in /var/cache/snd-usb-audio-ddj1000, so a download only
# happens once per kernel series. Set DDJ1000_KSRC=/path/to/linux to use a
# local kernel source tree instead.
set -eu

kver="$1"
here="$(cd "$(dirname "$0")" && pwd)"
series="$(echo "$kver" | sed -E 's/^([0-9]+\.[0-9]+).*/\1/')"
major="${series%%.*}"
cache=/var/cache/snd-usb-audio-ddj1000
src="$here/src"

rm -rf "$src"
mkdir -p "$src"

if [ -n "${DDJ1000_KSRC:-}" ]; then
    cp "$DDJ1000_KSRC"/sound/usb/*.c "$DDJ1000_KSRC"/sound/usb/*.h "$DDJ1000_KSRC"/sound/usb/Makefile "$src/"
else
    tarball="$cache/linux-$series.tar.xz"
    if [ ! -s "$tarball" ]; then
        mkdir -p "$cache"
        url="https://cdn.kernel.org/pub/linux/kernel/v$major.x/linux-$series.tar.xz"
        echo "snd-usb-audio-ddj1000: downloading $url"
        if command -v curl >/dev/null; then
            curl -fsSL --retry 3 -o "$tarball.part" "$url"
        else
            wget -O "$tarball.part" "$url"
        fi
        mv "$tarball.part" "$tarball"
    fi
    tar -xJf "$tarball" -C "$src" --strip-components=3 \
        --wildcards "linux-$series/sound/usb/*.c" "linux-$series/sound/usb/*.h" \
        "linux-$series/sound/usb/Makefile"
fi

python3 "$here/apply_quirk.py" "$src"

# Build only snd-usb-audio; snd-usbmidi-lib and the sub-drivers stay in-tree.
sed -e 's/^obj-\$(CONFIG_SND_USB_AUDIO) += snd-usb-audio.o snd-usbmidi-lib.o/obj-m += snd-usb-audio.o/' \
    -e '/^obj-\$(CONFIG_SND_USB_UA101)/,$d' \
    -e '/^snd-usbmidi-lib-y/d' \
    "$src/Makefile" > "$src/Makefile.ddj1000"
mv "$src/Makefile.ddj1000" "$src/Makefile"
grep -q '^obj-m += snd-usb-audio.o' "$src/Makefile" || {
    echo "snd-usb-audio-ddj1000: unexpected sound/usb/Makefile layout" >&2
    exit 1
}
