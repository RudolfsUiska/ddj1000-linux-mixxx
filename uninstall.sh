#!/bin/sh
# Remove everything install.sh added. Run as your normal user.
set -u

PKG=snd-usb-audio-ddj1000

systemctl --user disable --now ddj1000-screens.service 2>/dev/null
rm -f "$HOME/.config/systemd/user/ddj1000-screens.service"
systemctl --user daemon-reload
rm -rf "$HOME/.local/share/ddj1000-screens"
rm -f "$HOME/.config/wireplumber/main.lua.d/51-ddj1000-disable.lua" \
      "$HOME/.config/wireplumber/wireplumber.conf.d/51-ddj1000-disable.conf"
rm -f "$HOME/.mixxx/controllers/Pioneer DDJ-1000.midi.xml" \
      "$HOME/.mixxx/controllers/Pioneer-DDJ-1000-script.js" \
      "$HOME/.mixxx/controllers/Pioneer DDJ-1000 Screens.midi.xml" \
      "$HOME/.mixxx/controllers/Pioneer-DDJ-1000-Screens-script.js"

for ver in $(sudo dkms status "$PKG" 2>/dev/null | sed -n "s#^$PKG/\([^,:]*\).*#\1#p" | sort -u); do
    sudo dkms remove "$PKG/$ver" --all
    sudo rm -rf "/usr/src/$PKG-$ver"
done
sudo rm -rf /var/cache/snd-usb-audio-ddj1000
sudo rm -f /etc/modprobe.d/ddj1000.conf /etc/udev/rules.d/70-ddj1000.rules \
           /etc/security/limits.d/95-audio-rt.conf
sudo udevadm control --reload-rules
sudo depmod -a

echo "Removed. Reboot (or replug the DDJ-1000) to go back to the stock driver."
echo "Waveform cache left in ~/.cache/ddj1000-screens (delete it if you like)."
