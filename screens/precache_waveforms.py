#!/usr/bin/env python3
"""Pre-compute jog-screen waveforms for every track in the Mixxx library."""
import os, sqlite3, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import waveform
db = sqlite3.connect("file:%s?mode=ro" % os.path.expanduser("~/.mixxx/mixxxdb.sqlite"), uri=True)
paths = [r[0] for r in db.execute("SELECT t.location FROM library l JOIN track_locations t ON l.location = t.id WHERE l.mixxx_deleted = 0")]
done = failed = 0
start = time.time()
for p in paths:
    try:
        waveform.cached(p); done += 1
    except Exception as e:
        failed += 1; print("failed:", p, e, flush=True)
    if (done + failed) % 50 == 0:
        print("%d/%d in %.0f s" % (done + failed, len(paths), time.time() - start), flush=True)
print("finished: %d ok, %d failed, %.0f s" % (done, failed, time.time() - start))
