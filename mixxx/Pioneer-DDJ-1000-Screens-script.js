// Pioneer-DDJ-1000-Screens-script.js
// ****************************************************************************
// * Reports deck state to the ddj1000-screens service, which drives the
// * DDJ-1000 jog screens over HID. Bound to the virtual MIDI port
// * "DDJ-1000 Screens" that the service creates.
// ****************************************************************************
//
// Message: F0 7D 44 31 <deck 0-3> <flags> <position ms: 4x7 bit>
//          <duration ms: 4x7> <bpm*100: 3x7> <file bpm*100: 3x7>
//          <tempo %*100 + 100000: 3x7> <key 0-24> <key shift + 64>
//          <cue ms: 4x7, 0x0FFFFFFF = none> <first beat ms: 3x7> F7
// flags: bit0 loaded, bit1 playing, bit2 sync leader

var PioneerDDJ1000Screens = {};

PioneerDDJ1000Screens.timer = 0;

PioneerDDJ1000Screens.init = function() {
    PioneerDDJ1000Screens.timer = engine.beginTimer(20, PioneerDDJ1000Screens.tick);
};

PioneerDDJ1000Screens.shutdown = function() {
    if (PioneerDDJ1000Screens.timer) {
        engine.stopTimer(PioneerDDJ1000Screens.timer);
        PioneerDDJ1000Screens.timer = 0;
    }
};

PioneerDDJ1000Screens.push = function(out, value, bytes) {
    value = Math.max(0, Math.round(value));
    for (let i = bytes - 1; i >= 0; i--) {
        out.push(Math.floor(value / Math.pow(128, i)) % 128);
    }
};

PioneerDDJ1000Screens.deckMessage = function(deck) {
    const group = "[Channel" + (deck + 1) + "]";
    const push = PioneerDDJ1000Screens.push;
    const loaded = engine.getValue(group, "track_loaded") > 0;
    const duration = engine.getValue(group, "duration");
    const position = engine.getValue(group, "playposition") * duration;
    const fileBpm = engine.getValue(group, "file_bpm");
    const tempo = engine.getValue(group, "rate") * engine.getValue(group, "rateRange") *
        (engine.getValue(group, "rate_dir") || 1) * 100;

    const cuePoint = engine.getValue(group, "cue_point");
    const sampleRate = engine.getValue(group, "track_samplerate");
    const cueMs = cuePoint >= 0 && sampleRate > 0 ? cuePoint / sampleRate / 2 * 1000 : 0x0FFFFFFF;

    // First beat of a constant grid, from the distance to the previous beat.
    let firstBeat = 0;
    if (fileBpm > 0) {
        const beat = 60 / fileBpm;
        const previousBeat = position - engine.getValue(group, "beat_distance") * beat;
        firstBeat = ((previousBeat % beat) + beat) % beat;
    }

    const flags = (loaded ? 1 : 0) |
        (engine.getValue(group, "play") > 0 ? 2 : 0) |
        (engine.getValue(group, "sync_leader") > 0 ? 4 : 0);

    const out = [0xF0, 0x7D, 0x44, 0x31, deck, flags];
    push(out, position * 1000, 4);
    push(out, duration * 1000, 4);
    push(out, engine.getValue(group, "bpm") * 100, 3);
    push(out, fileBpm * 100, 3);
    push(out, tempo * 100 + 100000, 3);
    out.push(Math.max(0, Math.min(24, Math.round(engine.getValue(group, "key")))));
    out.push(Math.max(0, Math.min(127, Math.round(engine.getValue(group, "pitch")) + 64)));
    push(out, cueMs, 4);
    push(out, firstBeat * 1000, 3);
    out.push(0xF7);
    return out;
};

PioneerDDJ1000Screens.tick = function() {
    for (let deck = 0; deck < 4; deck++) {
        const message = PioneerDDJ1000Screens.deckMessage(deck);
        midi.sendSysexMsg(message, message.length);
    }
};
