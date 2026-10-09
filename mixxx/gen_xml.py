#!/usr/bin/env python3
"""Generate "Pioneer DDJ-1000.midi.xml" for Mixxx from the DDJ-1000 MIDI list."""
import sys
from xml.sax.saxutils import escape

P = "PioneerDDJ1000."
controls = []


def ctl(desc, status, midino, group, key, opts=None):
    controls.append((desc, status, midino, group, key, opts))


def script(desc, status, midino, group, fn):
    ctl(desc, status, midino, group, P + fn, "script-binding")


def direct(desc, status, midino, group, key):
    ctl(desc, status, midino, group, key, "normal")


def fourteen(desc, status, msb, group, key):
    ctl(desc + " (MSB)", status, msb, group, key, "fourteen-bit-msb")
    ctl(desc + " (LSB)", status, msb + 0x20, group, key, "fourteen-bit-lsb")


def script14(desc, status, msb, group, fn):
    script(desc + " (MSB)", status, msb, group, fn)
    script(desc + " (LSB)", status, msb + 0x20, group, fn)


# ---- decks (MIDI channels 1-4) ----
for n in range(4):
    g = f"[Channel{n + 1}]"
    d = f"Deck {n + 1}"
    note, cc = 0x90 + n, 0xB0 + n
    script(f"{d} PLAY/PAUSE", note, 0x0B, g, "play")
    direct(f"{d} SHIFT+PLAY - stutter", note, 0x47, g, "play_stutter")
    direct(f"{d} CUE", note, 0x0C, g, "cue_default")
    direct(f"{d} SHIFT+CUE - jump to start", note, 0x48, g, "start")
    script(f"{d} JOG touch", note, 0x36, g, "jogTouch")
    script(f"{d} SHIFT+JOG touch", note, 0x67, g, "jogTouch")
    script(f"{d} JOG top rotate (vinyl on)", cc, 0x22, g, "jogTop")
    script(f"{d} JOG top rotate (vinyl off)", cc, 0x23, g, "jogBend")
    script(f"{d} JOG side rotate", cc, 0x21, g, "jogBend")
    script(f"{d} SEARCH+JOG rotate", cc, 0x29, g, "jogSearch")
    script(f"{d} SHIFT+JOG top rotate", cc, 0x1F, g, "jogSearch")
    script(f"{d} SHIFT+JOG side rotate", cc, 0x26, g, "jogSearch")
    script14(f"{d} TEMPO", cc, 0x00, g, "tempo")
    script14(f"{d} SHIFT+TEMPO", cc, 0x05, g, "tempo")
    script(f"{d} MASTER TEMPO - key lock", note, 0x1A, g, "toggleKeylock")
    script(f"{d} SHIFT+MASTER TEMPO - tempo range", note, 0x60, g, "cycleTempoRange")
    script(f"{d} DECK SELECT", note, 0x72, g, "deckSelect")
    script(f"{d} BEAT SYNC", note, 0x58, g, "sync")
    script(f"{d} SHIFT+BEAT SYNC - sync leader", note, 0x5C, g, "syncLeader")
    direct(f"{d} KEY SYNC", note, 0x65, g, "sync_key")
    direct(f"{d} SHIFT+KEY SYNC - key up", note, 0x1C, g, "pitch_up")
    direct(f"{d} KEY RESET", note, 0x64, g, "reset_key")
    direct(f"{d} SHIFT+KEY RESET - key down", note, 0x1F, g, "pitch_down")
    script(f"{d} LOOP IN / 1/2X (halves a playing loop)", note, 0x10, g, "loopIn")
    direct(f"{d} SHIFT+LOOP IN - halve loop", note, 0x4C, g, "loop_halve")
    script(f"{d} LOOP OUT / 2X (doubles a playing loop)", note, 0x11, g, "loopOut")
    direct(f"{d} SHIFT+LOOP OUT - double loop", note, 0x4D, g, "loop_double")
    script(f"{d} 4 BEAT LOOP/EXIT", note, 0x14, g, "fourBeatLoop")
    direct(f"{d} SHIFT+4 BEAT LOOP - reloop", note, 0x50, g, "reloop_toggle")
    script(f"{d} QUANTIZE", note, 0x35, g, "toggleQuantize")
    script(f"{d} SLIP", note, 0x40, g, "toggleSlip")
    direct(f"{d} SLIP REVERSE - hold", note, 0x15, g, "reverseroll")
    script(f"{d} SHIFT+SLIP REVERSE - reverse", note, 0x38, g, "toggleReverse")
    direct(f"{d} SEARCH <<", note, 0x5E, g, "back")
    direct(f"{d} SEARCH << long", note, 0x70, g, "back")
    direct(f"{d} SHIFT+SEARCH << - jump 32 beats back", note, 0x51, g, "beatjump_32_backward")
    direct(f"{d} SEARCH >>", note, 0x5F, g, "fwd")
    direct(f"{d} SEARCH >> long", note, 0x71, g, "fwd")
    direct(f"{d} SHIFT+SEARCH >> - jump 32 beats forward", note, 0x53, g, "beatjump_32_forward")
    direct(f"{d} MEMORY - set cue", note, 0x3D, g, "cue_set")
    direct(f"{d} SHIFT+MEMORY - clear cue", note, 0x3E, g, "cue_clear")
    script(f"{d} SHIFT", note, 0x3F, g, "shiftButton")
    for m, name in ((0x1B, "HOT CUE"), (0x1E, "PAD FX1"), (0x20, "BEAT JUMP"), (0x22, "SAMPLER"),
                    (0x69, "KEYBOARD"), (0x6B, "PAD FX2"), (0x6D, "BEAT LOOP"), (0x6F, "KEY SHIFT")):
        script(f"{d} pad mode {name}", note, m, g, "modeButton")
    for i in range(16):
        script(f"{d} PAGE {'<' if i < 8 else '>'} (mode {i % 8})", note, 0x24 + i, g, "pageButton")

# ---- mixer channels (MIDI channels 1-4) ----
for n in range(4):
    g = f"[Channel{n + 1}]"
    d = f"CH{n + 1}"
    note, cc = 0x90 + n, 0xB0 + n
    fourteen(f"{d} CHANNEL FADER", cc, 0x13, g, "volume")
    script14(f"{d} TRIM", cc, 0x04, g, "trim")
    script14(f"{d} EQ HI", cc, 0x07, g, "eq")
    script14(f"{d} EQ MID", cc, 0x0B, g, "eq")
    script14(f"{d} EQ LOW", cc, 0x0F, g, "eq")
    script(f"{d} headphone CUE", note, 0x54, g, "togglePfl")
    direct(f"{d} SHIFT+headphone CUE - tap BPM", note, 0x68, g, "bpm_tap")
    for m, pos in ((0x16, "A"), (0x1D, "THRU"), (0x18, "B")):
        script(f"{d} CROSSFADER ASSIGN {pos}", note, m, g, "crossfaderAssign")

# ---- browser + global mixer (MIDI channel 7) ----
L = "[Library]"
M = "[Master]"
script("BROWSE rotate", 0xB6, 0x40, L, "browseRotate")
script("SHIFT+BROWSE rotate - page", 0xB6, 0x64, L, "browseRotateShift")
for m, deck in ((0x46, 1), (0x47, 2), (0x48, 3), (0x49, 4)):
    script(f"BROWSE press - load deck {deck}", 0x96, m, L, "browsePress")
for m in (0x5D, 0x5E, 0x6D, 0x6F):
    script("SHIFT+BROWSE press - open item", 0x96, m, L, "browseShiftPress")
script("BACK", 0x96, 0x65, L, "back")
direct("SHIFT+BACK - focus forward", 0x96, 0x66, L, "MoveFocusForward")
script("VIEW - maximize library", 0x96, 0x7A, L, "view")
fourteen("CROSSFADER", 0xB6, 0x1F, M, "crossfader")
script14("MASTER LEVEL", 0xB6, 0x08, M, "masterLevel")
script14("BOOTH LEVEL", 0xB6, 0x09, M, "boothLevel")
script14("HEADPHONES MIXING", 0xB6, 0x0C, M, "headphoneMix")
script14("HEADPHONES LEVEL", 0xB6, 0x0D, M, "headphoneLevel")
script("MASTER CUE", 0x96, 0x63, M, "masterCue")
script("SHIFT+MASTER CUE", 0x96, 0x62, M, "masterCue")
for n in range(4):
    script14(f"COLOR FX parameter CH{n + 1}", 0xB6, 0x17 + n, f"[QuickEffectRack1_[Channel{n + 1}]]", "colorFx")
for m, name in ((0x00, "DUB ECHO"), (0x01, "PITCH"), (0x02, "NOISE"), (0x03, "FILTER")):
    script(f"COLOR FX {name}", 0x96, m, M, "colorFxButton")
script14("SAMPLER VOL", 0xB6, 0x03, "[Sampler1]", "samplerVolume")
script("SAMPLER CUE", 0x96, 0x69, "[Sampler1]", "samplerCue")

# ---- beat FX (MIDI channel 5) ----
U = "[EffectRack1_EffectUnit1]"
for m in range(0x20, 0x2E):
    script(f"BEAT FX SELECT position {m - 0x20}", 0x94, m, U, "fxSelect")
for m, name in zip(range(0x10, 0x17), ("CH1", "CH2", "CH3", "CH4", "MASTER", "MIC", "SAMPLER")):
    script(f"BEAT FX CH SELECT {name}", 0x94, m, U, "fxChannel")
script14("BEAT FX LEVEL/DEPTH", 0xB4, 0x02, U, "fxLevel")
script("BEAT FX ON/OFF", 0x94, 0x47, U, "fxOnOff")
script("SHIFT+BEAT FX ON/OFF - all off", 0x94, 0x43, U, "fxAllOff")
script("BEAT < - focus previous effect", 0x94, 0x4A, U, "fxBeatLeft")
script("BEAT > - focus next effect", 0x94, 0x4B, U, "fxBeatRight")
script("SHIFT+BEAT < - meta down", 0x94, 0x66, U, "fxBeatLeftShift")
script("SHIFT+BEAT > - meta up", 0x94, 0x6B, U, "fxBeatRightShift")

# ---- pads (MIDI channels 8-15) ----
MODES = ("HOT CUE", "PAD FX1", "BEAT JUMP", "SAMPLER", "KEYBOARD", "PAD FX2", "BEAT LOOP", "KEY SHIFT")
for n in range(4):
    g = f"[Channel{n + 1}]"
    for shift in (0, 1):
        status = 0x97 + n * 2 + shift
        for m in range(0x80):
            desc = (f"Deck {n + 1} {'SHIFT+' if shift else ''}PAD {(m & 7) + 1} "
                    f"({MODES[m >> 4]} page {((m >> 3) & 1) + 1})")
            script(desc, status, m, g, "pad")


def render():
    out = ['<?xml version="1.0" encoding="utf-8"?>',
           '<MixxxMIDIPreset schemaVersion="1" mixxxVersion="2.5">',
           '    <info>',
           '        <name>Pioneer DDJ-1000</name>',
           '        <author>Generated from the DDJ-1000 MIDI message list v1.00</author>',
           '        <description>4-deck mapping for the Pioneer DJ / AlphaTheta DDJ-1000 (rekordbox layout). '
           'Route Main to outputs 1-2 and Headphones to outputs 3-4 of the DDJ-1000 sound card.</description>',
           '    </info>',
           '    <controller id="DDJ-1000">',
           '        <scriptfiles>',
           '            <file functionprefix="PioneerDDJ1000" filename="Pioneer-DDJ-1000-script.js"/>',
           '        </scriptfiles>',
           '        <controls>']
    for desc, status, midino, group, key, opts in controls:
        opt = {"script-binding": "<script-binding/>", "normal": "<normal/>",
               "fourteen-bit-msb": "<fourteen-bit-msb/>", "fourteen-bit-lsb": "<fourteen-bit-lsb/>"}[opts]
        out += ['            <control>',
                f'                <description>{escape(desc)}</description>',
                f'                <group>{escape(group)}</group>',
                f'                <key>{escape(key)}</key>',
                f'                <status>0x{status:02X}</status>',
                f'                <midino>0x{midino:02X}</midino>',
                f'                <options>{opt}</options>',
                '            </control>']
    out += ['        </controls>',
            '        <outputs/>',
            '    </controller>',
            '</MixxxMIDIPreset>', '']
    return "\n".join(out)


seen = {}
for c in controls:
    k = (c[1], c[2])
    if k in seen:
        sys.exit(f"duplicate mapping 0x{k[0]:02X} 0x{k[1]:02X}: {seen[k]} / {c[0]}")
    seen[k] = c[0]

open(sys.argv[1] if len(sys.argv) > 1 else "Pioneer DDJ-1000.midi.xml", "w", encoding="utf-8").write(render())
print(len(controls), "controls")
