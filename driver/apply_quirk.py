#!/usr/bin/env python3
"""Add Pioneer DJ / AlphaTheta DDJ-1000 (2b73:0020) audio support to a
Linux sound/usb source directory.

    python3 apply_quirk.py path/to/sound/usb

The DDJ-1000 uses a vendor-specific audio interface like the DDJ-800 and
DJM-900NXS2: 6 channels out on EP 0x01, 12 channels in on EP 0x82,
S24_3LE at 44.1 kHz, with the capture stream as implicit feedback.
Needs kernel 6.6 or newer (QUIRK_DATA_* macros).
"""
import os
import sys

ENTRY = """{
	/*
	 * Pioneer DJ / AlphaTheta DDJ-1000
	 * PCM is 6 channels out, 12 channels in @ 44.1 fixed, S24_3LE
	 * The Feedback for the output is the input
	 */
	USB_DEVICE_VENDOR_SPEC(0x2b73, 0x0020),
	QUIRK_DRIVER_INFO {
		QUIRK_DATA_COMPOSITE {
			{
				QUIRK_DATA_AUDIOFORMAT(0) {
					.formats = SNDRV_PCM_FMTBIT_S24_3LE,
					.channels = 6,
					.iface = 0,
					.altsetting = 1,
					.altset_idx = 1,
					.endpoint = 0x01,
					.ep_attr = USB_ENDPOINT_XFER_ISOC|
						USB_ENDPOINT_SYNC_ASYNC,
					.rates = SNDRV_PCM_RATE_44100,
					.rate_min = 44100,
					.rate_max = 44100,
					.nr_rates = 1,
					.rate_table = (unsigned int[]) { 44100 }
				}
			},
			{
				QUIRK_DATA_AUDIOFORMAT(0) {
					.formats = SNDRV_PCM_FMTBIT_S24_3LE,
					.channels = 12,
					.iface = 0,
					.altsetting = 1,
					.altset_idx = 1,
					.endpoint = 0x82,
					.ep_idx = 1,
					.ep_attr = USB_ENDPOINT_XFER_ISOC|
						USB_ENDPOINT_SYNC_ASYNC|
					USB_ENDPOINT_USAGE_IMPLICIT_FB,
					.rates = SNDRV_PCM_RATE_44100,
					.rate_min = 44100,
					.rate_max = 44100,
					.nr_rates = 1,
					.rate_table = (unsigned int[]) { 44100 }
				}
			},
			QUIRK_COMPOSITE_END
		}
	}
},

"""

# The DDJ-1000 entry goes right before the DJM-900NXS2 one, which has the
# same layout and exists in every kernel this patch supports.
TABLE_ANCHOR = "\t * Pioneer DJ DJM-900NXS2\n"
SET_FORMAT_ANCHOR = "\tcase USB_ID(0x2b73, 0x000a): /* Pioneer DJM-900NXS2 */\n"
SET_FORMAT_LINE = "\tcase USB_ID(0x2b73, 0x0020): /* Pioneer DDJ-1000 */\n"


def fail(msg):
    sys.exit("apply_quirk: " + msg)


def main(directory):
    table_path = os.path.join(directory, "quirks-table.h")
    quirks_path = os.path.join(directory, "quirks.c")
    table = open(table_path).read()
    quirks = open(quirks_path).read()

    if "0x2b73, 0x0020" in table:
        print("apply_quirk: DDJ-1000 already supported by this kernel's source")
        return
    if "QUIRK_DATA_COMPOSITE" not in table:
        fail("this kernel is too old (needs 6.6+ quirk macros)")

    anchor = table.find(TABLE_ANCHOR)
    if anchor < 0:
        fail("DJM-900NXS2 entry not found in quirks-table.h")
    start = table.rfind("{\n\t/*\n", 0, anchor)
    if start < 0:
        fail("could not find the start of the DJM-900NXS2 entry")
    table = table[:start] + ENTRY + table[start:]

    if SET_FORMAT_ANCHOR not in quirks:
        fail("DJM-900NXS2 case not found in quirks.c")
    quirks = quirks.replace(SET_FORMAT_ANCHOR, SET_FORMAT_ANCHOR + SET_FORMAT_LINE, 1)

    open(table_path, "w").write(table)
    open(quirks_path, "w").write(quirks)
    print("apply_quirk: patched", directory)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        fail("usage: apply_quirk.py path/to/sound/usb")
    main(sys.argv[1])
