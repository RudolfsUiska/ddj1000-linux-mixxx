#!/usr/bin/env python3
"""DDJ-1000 "PC app connect" handshake over SysEx.

Pioneer's mutual challenge-response (documented for CDJs at
https://swiftb0y.github.io/CDJHidProtocol/hid-analysis/handshake.html):
secret = seedE XOR vendor constant, hashes are 32-bit FNV-1a, integers are
big-endian and binary TLV payloads are sent as nibbles (7-bit safe).
"""
import os

PFX = bytes.fromhex("F0 00 40 05 00 00 02 00 00")
VENDOR = b"PioneerDJ"
PRODUCT = b"rekordbox"
VENDOR_SECRET = 0x680131FB                               # PioneerDJ
DEVICE_ID = bytes.fromhex("87A08EEAC09034760B90")         # DDJ-1000 as seen from rekordbox

KEEPALIVE = PFX + bytes([0x50, 0x01, 0xF7])
# Sent by rekordbox right after the handshake (meaning not decoded; replayed as-is).
SETUP = [
    PFX + bytes.fromhex("00 0B 31 00 00 00 00 00 F7"),
    PFX + bytes.fromhex("00 0C 00 00 02 0E 0E 00 00 00 F7"),
    PFX + bytes.fromhex("00 0A 00 28 00 26 00 08 15 62 14 28 16" + " 00" * 36 + " F7"),
]


def fnv1a(data):
    h = 0x811C9DC5
    for b in data:
        h = ((b ^ h) * 0x01000193) & 0xFFFFFFFF
    return h


def spread(data):
    out = bytearray()
    for b in data:
        out += bytes([b >> 4, b & 0x0F])
    return bytes(out)


def unspread(data):
    return bytes((data[i] << 4) | data[i + 1] for i in range(0, len(data) - 1, 2))


def tlv(tag, value):
    return bytes([tag, len(value) + 2]) + value


def message(stage, *args):
    body = b"".join(args)
    return PFX + tlv(stage, body) + b"\xF7"


def parse(sysex):
    """Return (stage, {tag: value}) for a handshake SysEx from the unit."""
    body = sysex[len(PFX):-1]
    stage, length = body[0], body[1]
    args, i = {}, 2
    while i < length:
        tag, ln = body[i], body[i + 1]
        args[tag] = body[i + 2:i + ln]
        i += ln
    return stage, args


def hello(seed_a):
    return message(0x12, tlv(0x01, VENDOR), tlv(0x02, PRODUCT), tlv(0x03, spread(seed_a)))


def answer(seed_e):
    secret = (int.from_bytes(seed_e, "big") ^ VENDOR_SECRET).to_bytes(4, "big")
    hash_e = fnv1a(seed_e + secret).to_bytes(4, "big")
    return message(0x14, tlv(0x01, VENDOR), tlv(0x02, PRODUCT),
                   tlv(0x04, spread(hash_e)), tlv(0x05, spread(DEVICE_ID)))


def check_reply(seed_a, args):
    seed_e = unspread(args[0x03])
    secret = (int.from_bytes(seed_e, "big") ^ VENDOR_SECRET).to_bytes(4, "big")
    return unspread(args[0x04]) == fnv1a(seed_a + secret).to_bytes(4, "big"), seed_e


def handshake(send, wait_sysex):
    """send(bytes); wait_sysex(stage) -> bytes or None. Returns True on success."""
    send(KEEPALIVE)
    wait_sysex(0x11)
    seed_a = os.urandom(8)
    send(hello(seed_a))
    reply = wait_sysex(0x13)
    if not reply:
        return False
    ok, seed_e = check_reply(seed_a, parse(reply)[1])
    if not ok:
        return False
    send(answer(seed_e))
    return wait_sysex(0x15) is not None


if __name__ == "__main__":
    # Self-test against the rekordbox capture.
    seed_a = bytes.fromhex("02664E6EA8E7A2CB")
    assert hello(seed_a) == bytes.fromhex(
        "F0 00 40 05 00 00 02 00 00 12 2A 01 0B 50 69 6F 6E 65 65 72 44 4A 02 0B 72 65 6B 6F 72 64 62 6F 78"
        " 03 12 00 02 06 06 04 0E 06 0E 0A 08 0E 07 0A 02 0C 0B F7")
    reply = bytes.fromhex(
        "F0 00 40 05 00 00 02 00 00 13 2A 01 0B 50 69 6F 6E 65 65 72 44 4A 02 09 44 44 4A 31 30 30 30"
        " 04 0A 01 04 07 0F 0F 0B 04 0B 03 0A 00 00 00 00 05 03 0D 0C F7")
    ok, seed_e = check_reply(seed_a, parse(reply)[1])
    assert ok
    assert answer(seed_e) == bytes.fromhex(
        "F0 00 40 05 00 00 02 00 00 14 38 01 0B 50 69 6F 6E 65 65 72 44 4A 02 0B 72 65 6B 6F 72 64 62 6F 78"
        " 04 0A 05 04 00 08 05 05 0F 0E 05 16 08 07 0A 00 08 0E 0E 0A 0C 00 09 00 03 04 07 06 00 0B 09 00 F7")
    print("self-test OK: generated messages are byte-identical to rekordbox's")
