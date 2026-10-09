#!/usr/bin/env python3
"""Load the DDJ-1000 Beat FX effects into Mixxx effect units 1 and 2.

    python3 setup_beatfx.py [~/.mixxx]

The mapping's FX SELECT knob picks one of these slots:
  unit 1: Echo, Reverb, Flanger, Phaser
  unit 2: Tremolo, Moog ladder filter, Bitcrusher, Autopan
Run it while Mixxx is closed (Mixxx rewrites effects.xml when it exits).
Other units, the quick effects (Color FX) and the EQs are left alone.
"""
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

UNITS = [
    ["echo", "reverb", "flanger", "phaser"],
    ["tremolo", "moogladder4filter", "bitcrusher", "autopan"],
]


def effect(effect_id):
    e = ET.Element("Effect")
    ET.SubElement(e, "MetaParameterValue").text = "0.5"
    ET.SubElement(e, "Id").text = "org.mixxx.effects." + effect_id
    ET.SubElement(e, "BackendType").text = "Built-In"
    return e


def main():
    settings = os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else "~/.mixxx")
    path = os.path.join(settings, "effects.xml")
    if subprocess.run(["pgrep", "-f", "bin/mixxx"], capture_output=True).returncode == 0:
        sys.exit("Close Mixxx first: it rewrites effects.xml when it exits.")
    if not os.path.exists(path):
        sys.exit("%s not found; start and close Mixxx once first." % path)

    tree = ET.parse(path)
    chains = tree.getroot().findall("./Rack/Chains/EffectChain")
    if len(chains) < len(UNITS):
        sys.exit("unexpected effects.xml layout (fewer than %d effect units)" % len(UNITS))
    for chain, effects in zip(chains, UNITS):
        slots = chain.find("Effects")
        old = list(slots)
        for child in old:
            slots.remove(child)
        for i in range(max(len(old), len(effects))):
            slots.append(effect(effects[i]) if i < len(effects) else ET.Element("Effect"))
        mix = chain.find("MixMode")
        if mix is not None:
            mix.text = "DRY/WET"

    shutil.copy2(path, path + ".bak-beatfx-" + time.strftime("%Y%m%d-%H%M%S"))
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print("Beat FX effects written to", path)


if __name__ == "__main__":
    main()
