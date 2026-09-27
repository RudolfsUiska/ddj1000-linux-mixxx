-- WirePlumber 0.4: leave the DDJ-1000 sound card to Mixxx (direct ALSA).
table.insert(alsa_monitor.rules, {
  matches = {
    { { "device.name", "matches", "alsa_card.usb-AlphaTheta*DDJ-1000*" } },
    { { "device.name", "matches", "alsa_card.usb-Pioneer*DDJ-1000*" } },
  },
  apply_properties = { ["device.disabled"] = true },
})
