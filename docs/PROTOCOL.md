# DDJ-1000 jog-screen protocol

Decoded from USB captures of rekordbox 7.2.19 on Windows (USBPcap), then
reimplemented and tested on Linux. All values are as seen on a DDJ-1000
(USB 2b73:0020).

## USB interfaces

| Interface | Use |
|---|---|
| 0 (vendor, alt 1) | audio: EP 0x01 out (6 ch), EP 0x82 in (12 ch), S24_3LE, 44.1 kHz, implicit feedback |
| 1-2 | USB-MIDI (EP 0x04 out, EP 0x85 in) |
| 3 | HID, vendor page 0xFFA0, 64-byte reports, no report IDs (EP 0x06 out, EP 0x87 in) |

Capture channels 11/12 carry the master mix (a loopback of what the unit
plays).

## 1. Audio driver request

Pioneer's audio driver sends one vendor request after enumeration:

    bmRequestType 0xC0, bRequest 0x00, wValue 0x0000, wIndex 0x8003, wLength 2  -> 00 00

If audio streams without it, the jog screens show **"no audio driver"**.

## 2. Login (SysEx)

SysEx prefix: `F0 00 40 05 00 00 02 00 00` (the model byte after `02` is
`00` for the DDJ-1000). Then a TLV: `[stage][length incl. these 2 bytes][args...]`.
Each argument is `[type][length incl. 2][value]`. Binary values are split
into nibbles (`0x12 0x34` -> `01 02 03 04`).

| Stage | Direction | Content |
|---|---|---|
| `50 01` | host -> unit | keepalive, every 200 ms; unit answers `11 02` |
| `12` | host -> unit | 01 "PioneerDJ", 02 "rekordbox", 03 seedA (8 random bytes) |
| `13` | unit -> host | 01 "PioneerDJ", 02 "DDJ1000", 04 hashA, 03 seedE (4 bytes) |
| `14` | host -> unit | 01, 02, 04 hashE, 05 device ID |
| `15 02` | unit -> host | accepted |

- `secret = seedE XOR 0x680131FB` (the PioneerDJ constant)
- `hashA = FNV-1a(seedA + secret)` (lets the host check the unit)
- `hashE = FNV-1a(seedE + secret)`
- FNV-1a: 32-bit, offset basis 0x811C9DC5, prime 0x01000193; integers big-endian
- DDJ-1000 device ID (as rekordbox sends it): `87 A0 8E EA C0 90 34 76 0B 90`

seedE is random each time, so a recorded answer cannot be replayed.

After `15`, rekordbox sends three setup messages (replayed as-is, meaning
unknown): `00 0B 31 00 00 00 00 00`, `00 0C 00 00 02 0E 0E 00 00 00`,
`00 0A 00 28 00 26 00 08 15 62 14 28 16 00...`. `03 01` requests a dump of all
fader and knob positions.

**Do not** send `9F 09 00` (plain-MIDI "PC app connect") while logged in: the
unit resets its USB connection.

## 3. HID reports (host -> unit)

Every report is 64 bytes:

    [deck << 4] [command] [chunk index, LE16, from 1] [chunk count, LE16] [58 bytes data]

Larger payloads are split over several reports and zero-padded.

### 0x21 deck status (single report, sent continuously, ~25-100 Hz)

Offsets are into the full 64-byte report.

| Bytes | Meaning |
|---|---|
| 2 | `0x18` playing or at cue, `0x1A` paused |
| 3, 5 | `0x08`/`0x01`; `0x0A`/`0x81` on the tempo-master deck |
| 4 | `0x21` |
| 9 | `0xB4` track loaded, `0x10` empty |
| 11-14 | elapsed time: minutes, seconds, milliseconds (LE16) |
| 15-18 | track length, same format |
| 21-22 | BPM: integer, then the two decimals as nibbles (`96 90` = 150.90) |
| 23-24 | tempo in 0.01 % steps, signed LE16 (`e8 03` = +10.00 %) |
| 27 | `0x80` |
| 29-32, 53-56 | cue point time |
| 38-39 | BPM again |
| 58 | `0x01` when loaded |
| 60 | `0x80` + key code (as in the MIDI list: 0x01 C, 0x02 Am, ... 0x18 Abm) |
| 61 | `0x0D` + key shift in semitones |

### Sent once per track load

| Cmd | Chunks | Payload |
|---|---|---|
| 0x30 | 2 | track length (4-byte time), zeros |
| 0x2D | 1 | track length, then `0a 00` + 10 x `9e 2f 27 01 00` (constant) |
| 0x2F | n | beat grid: count LE16, then per beat `[beat in bar 1-4][ms LE24]` |
| 0x2C | 73 | waveform, see below |
| 0x2B | 32 | artwork, see below; 1 zero chunk = no artwork (record icon) |

### 0x2C waveform

`0x80`, then 600 columns spread over the track, 7 bytes each:

    [outer colour RGB565 LE] [inner colour RGB565 LE] [outer height] [inner height] [00]

Heights are 0-40. rekordbox draws the peak in the outer colour and the
average level in a brighter inner colour.

### 0x2B artwork

`[length LE16][JPEG]`, zero-padded. The image is an 80x80 baseline JPEG
(4:2:0), about 1.8 KB (32 chunks). The jog screen shows only its top half.
