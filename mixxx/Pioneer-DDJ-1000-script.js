// Pioneer-DDJ-1000-script.js
// ****************************************************************************
// * Mixxx mapping script for the Pioneer DJ / AlphaTheta DDJ-1000 (rekordbox).
// * Written against "DDJ-1000 List of MIDI message version 1.00".
// ****************************************************************************
//
// The DDJ-1000 is a software-mixing controller: the computer sends it the
// finished master mix on USB outputs 1/2 and the headphone cue on 3/4
// (5/6 is booth). Channel faders, EQs, trims and the crossfader are plain
// MIDI and are applied by Mixxx. The unit processes the mics, the master
// level and (per the position dump) the booth/headphone knobs in hardware.
//
// MIDI channels (0-based, as passed to callbacks):
//   0-3  deck 1-4 (the firmware switches channel with DECK 1/3, 2/4)
//   4    beat FX
//   6    browser + global mixer
//   7-14 pads: deck1, deck1+SHIFT, deck2, deck2+SHIFT, ...
//
// Implemented:
//   * 4 decks: play/cue, jog (scratch/bend/search), tempo, key lock, sync,
//     key sync/reset, loops, quantize, slip, slip reverse, search
//   * Mixer: faders, crossfader + assign, trim, 3-band EQ, color FX knob
//     (quick effect), headphone cue, channel VU meters
//   * Pads, 8 modes x 2 pages: hot cue, pad FX (rolls), beat jump, sampler,
//     keyboard, pad FX 2 (brake/spinback/...), beat loop, key shift
//   * Beat FX -> Mixxx effect unit 1 (CH1-4); MASTER is left to the hardware
//   * Jog displays: BPM, tempo, elapsed/remaining time, key, sync state,
//     platter position and cue marker
//   * Browser and loading into all four decks

var PioneerDDJ1000 = {};

// ---------------------------------------------------------------------------
// User options
// ---------------------------------------------------------------------------

// Master/booth/headphone knobs: these are processed inside the unit, so
// by default Mixxx ignores their MIDI messages. Set to false if a knob does
// nothing on your unit and Mixxx should apply it instead.
PioneerDDJ1000.hardwareMasterLevel = true;
PioneerDDJ1000.hardwareBoothLevel = true;
PioneerDDJ1000.hardwareHeadphones = true;

// The ddj1000-screens service logs in to the unit (rekordbox HID mode) and
// drives the jog screens. The plain-MIDI screen messages and the "PC app
// connect" note would drop the unit back to MIDI mode ("no audio driver"),
// so they are only sent when this is false.
PioneerDDJ1000.screensService = true;

// Key lock (MASTER TEMPO) on for all decks at startup, so tempo changes keep
// the track's key (a 130 BPM track in 2A stays 2A at 140 BPM). MASTER TEMPO
// still toggles it per deck.
PioneerDDJ1000.keylockOnStart = true;

// Jog wheel ticks per platter revolution (CC 0x22 on a full turn).
PioneerDDJ1000.jogResolution = 2048;
PioneerDDJ1000.vinylMode = true;
PioneerDDJ1000.alpha = 1.0 / 8;
PioneerDDJ1000.beta = PioneerDDJ1000.alpha / 32;
PioneerDDJ1000.bendScale = 0.8;
PioneerDDJ1000.searchScale = 100;

PioneerDDJ1000.tempoRanges = [0.06, 0.10, 0.16, 0.25, 0.50, 1.00];

// Pad LED values (the unit takes a colour number 1-127, 0 = dimmed).
PioneerDDJ1000.padColor = {
    off: 0x00,
    hotcue: 0x7F,        // used when a hot cue has no colour
    roll: 0x7F,
    rollActive: 0x7F,
    beatjump: 0x7F,
    sampler: 0x7F,
    samplerPlaying: 0x7F,
    keyboard: 0x7F,
    padfx2: 0x7F,
    beatloop: 0x7F,
    beatloopActive: 0x7F,
    keyshift: 0x7F,
};

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

PioneerDDJ1000.numDecks = 4;
PioneerDDJ1000.numSamplers = 16;

// Pad mode index = (pad note >> 4); page = (pad note >> 3) & 1.
PioneerDDJ1000.MODE = {
    HOTCUE: 0, PADFX1: 1, BEATJUMP: 2, SAMPLER: 3,
    KEYBOARD: 4, PADFX2: 5, BEATLOOP: 6, KEYSHIFT: 7,
};

// Pad mode buttons on the deck channel: note -> mode.
PioneerDDJ1000.modeButtons = {
    0x1B: 0, 0x1E: 1, 0x20: 2, 0x22: 3,   // HOT CUE, PAD FX1, BEAT JUMP, SAMPLER
    0x69: 4, 0x6B: 5, 0x6D: 6, 0x6F: 7,   // + SHIFT: KEYBOARD, PAD FX2, BEAT LOOP, KEY SHIFT
};

// PAGE buttons send one note per mode; the note tells us the new page.
PioneerDDJ1000.pagePrevBase = 0x24;  // 0x24-0x2B: PAGE < in modes 0-7
PioneerDDJ1000.pageNextBase = 0x2C;  // 0x2C-0x33: PAGE > in modes 0-7

PioneerDDJ1000.rollSizes = [
    [1 / 16, 1 / 8, 1 / 4, 1 / 2, 1, 2, 4, 8],
    [1 / 32, 1 / 16, 1 / 8, 1 / 4, 1 / 2, 1, 2, 4],
];
PioneerDDJ1000.beatjumpSizes = [
    [-1, 1, -2, 2, -4, 4, -8, 8],
    [-16, 16, -32, 32, -64, 64, -128, 128],
];
PioneerDDJ1000.beatloopSizes = [
    [1 / 4, 1 / 2, 1, 2, 4, 8, 16, 32],
    [1 / 32, 1 / 16, 1 / 8, 1 / 4, 64, 128, 256, 512],
];
// Top row raises, bottom row lowers (semitones).
PioneerDDJ1000.keySteps = [
    [1, 2, 3, 4, -1, -2, -3, -4],
    [5, 6, 7, 8, -5, -6, -7, -8],
];

// Mixxx key number (1-12 major C..B, 13-24 minor Cm..Bm) -> DDJ key code.
PioneerDDJ1000.keyCodes = [
    0x00,
    0x01, 0x03, 0x05, 0x07, 0x09, 0x0B, 0x0D, 0x0F, 0x11, 0x13, 0x15, 0x17,
    0x08, 0x0A, 0x0C, 0x0E, 0x10, 0x12, 0x14, 0x16, 0x18, 0x02, 0x04, 0x06,
];

// Beat FX CH SELECT notes (channel 4) -> Mixxx group, or null for sources
// that only the hardware can process.
PioneerDDJ1000.fxChannelSelect = {
    0x10: "[Channel1]", 0x11: "[Channel2]", 0x12: "[Channel3]", 0x13: "[Channel4]",
    0x14: null, 0x15: null, 0x16: null,   // MASTER, MIC, SAMPLER
};

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

PioneerDDJ1000.padMode = [0, 0, 0, 0];
PioneerDDJ1000.padPage = [0, 0, 0, 0];
PioneerDDJ1000.shift = [false, false, false, false];
PioneerDDJ1000.msb = {};
PioneerDDJ1000.lastDisplay = [{}, {}, {}, {}];
PioneerDDJ1000.fxSelectLast = null;
PioneerDDJ1000.fxTarget = null;
PioneerDDJ1000.displayTimer = 0;
PioneerDDJ1000.connections = [];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

PioneerDDJ1000.deckGroup = function(deck) {
    return "[Channel" + (deck + 1) + "]";
};

PioneerDDJ1000.send = function(status, data1, data2) {
    midi.sendShortMsg(status, data1, data2 & 0x7F);
};

PioneerDDJ1000.send14 = function(status, msbControl, value) {
    value = Math.max(0, Math.min(0x3FFF, Math.round(value)));
    midi.sendShortMsg(status, msbControl, (value >> 7) & 0x7F);
    midi.sendShortMsg(status, msbControl + 0x20, value & 0x7F);
};

// Combine a 14-bit CC pair: the unit sends MSB (0x00-0x1F) then LSB (+0x20).
// Returns the 14-bit value on the LSB, undefined on the MSB.
PioneerDDJ1000.fourteenBit = function(status, control, value) {
    const key = status + ":" + (control & 0x1F);
    if (control < 0x20) {
        PioneerDDJ1000.msb[key] = value;
        return undefined;
    }
    const msb = PioneerDDJ1000.msb[key] || 0;
    return (msb << 7) | value;
};

PioneerDDJ1000.padStatus = function(deck, shifted) {
    return 0x97 + deck * 2 + (shifted ? 1 : 0);
};

PioneerDDJ1000.connect = function(group, control, callback) {
    const conn = engine.makeConnection(group, control, callback);
    if (conn) {
        PioneerDDJ1000.connections.push(conn);
    }
    return conn;
};

// ---------------------------------------------------------------------------
// Init / shutdown
// ---------------------------------------------------------------------------

PioneerDDJ1000.init = function() {
    if (engine.getValue("[App]", "num_samplers") < PioneerDDJ1000.numSamplers) {
        engine.setValue("[App]", "num_samplers", PioneerDDJ1000.numSamplers);
    }
    if (engine.getValue("[App]", "num_decks") < PioneerDDJ1000.numDecks) {
        engine.setValue("[App]", "num_decks", PioneerDDJ1000.numDecks);
    }

    // The unit blends cue and master for the headphones itself.
    if (PioneerDDJ1000.hardwareHeadphones) {
        engine.setValue("[Master]", "headMix", -1);
    }

    for (let deck = 0; deck < PioneerDDJ1000.numDecks; deck++) {
        const group = PioneerDDJ1000.deckGroup(deck);
        const status = 0x90 + deck;
        engine.softTakeover(group, "rate", true);
        if (PioneerDDJ1000.keylockOnStart) {
            engine.setValue(group, "keylock", 1);
        }

        const led = function(control, notes) {
            PioneerDDJ1000.connect(group, control, function(value) {
                notes.forEach(function(note) {
                    PioneerDDJ1000.send(status, note, value > 0 ? 0x7F : 0x00);
                });
            }).trigger();
        };
        led("play_indicator", [0x0B, 0x47]);
        led("cue_indicator", [0x0C, 0x48]);
        led("keylock", [0x1A]);
        led("sync_enabled", [0x58, 0x5A]);
        led("quantize", [0x35]);
        led("slip_enabled", [0x40]);
        led("reverse", [0x15]);
        led("pfl", [0x54]);
        led("loop_enabled", [0x10, 0x11, 0x14, 0x4C, 0x4D, 0x50]);

        PioneerDDJ1000.connect(group, "sync_leader", function(value) {
            PioneerDDJ1000.send(status, 0x5C, value > 0 ? 0x7F : 0x00);
            PioneerDDJ1000.send(status, 0x59, value > 0 ? 0x7F : 0x00);
        }).trigger();

        PioneerDDJ1000.connect(group, "orientation", function(value) {
            PioneerDDJ1000.send(status, 0x16, value === 0 ? 0x7F : 0x00);
            PioneerDDJ1000.send(status, 0x1D, value === 1 ? 0x7F : 0x00);
            PioneerDDJ1000.send(status, 0x18, value === 2 ? 0x7F : 0x00);
        });

        const vuStatus = 0xB0 + deck;
        PioneerDDJ1000.connections.push(engine.makeUnbufferedConnection(group, "vu_meter", function(value) {
            PioneerDDJ1000.send(vuStatus, 0x02, Math.round(value * 0x7F));
        }));

        // Pad LEDs follow hot cues, loops and pitch.
        for (let i = 1; i <= 16; i++) {
            PioneerDDJ1000.connect(group, "hotcue_" + i + "_status", PioneerDDJ1000.renderPadsFor(deck));
            PioneerDDJ1000.connect(group, "hotcue_" + i + "_color", PioneerDDJ1000.renderPadsFor(deck));
        }
        ["loop_enabled", "beatloop_size", "pitch_adjust", "track_loaded"].forEach(function(control) {
            PioneerDDJ1000.connect(group, control, PioneerDDJ1000.renderPadsFor(deck));
        });

        // Jog display.
        ["bpm", "rate", "rateRange", "rate_dir", "file_key", "pitch", "track_loaded", "cue_point"].forEach(function(control) {
            PioneerDDJ1000.connect(group, control, PioneerDDJ1000.updateDisplayFor(deck));
        });
        if (!PioneerDDJ1000.screensService) {
            PioneerDDJ1000.send(status, 0x5B, 0x01);  // jog ring LED white
        }
    }

    for (let i = 1; i <= PioneerDDJ1000.numSamplers; i++) {
        const sampler = "[Sampler" + i + "]";
        PioneerDDJ1000.connect(sampler, "track_loaded", PioneerDDJ1000.renderSamplerPads);
        PioneerDDJ1000.connect(sampler, "play", PioneerDDJ1000.renderSamplerPads);
    }

    PioneerDDJ1000.connect("[Master]", "headSplit", function(value) {
        PioneerDDJ1000.send(0x96, 0x63, value ? 0x7F : 0x00);
    });

    PioneerDDJ1000.connect("[EffectRack1_EffectUnit1]", "focused_effect", PioneerDDJ1000.fxLed);
    for (let i = 1; i <= 3; i++) {
        PioneerDDJ1000.connect("[EffectRack1_EffectUnit1_Effect" + i + "]", "enabled", PioneerDDJ1000.fxLed);
    }
    engine.setValue("[EffectRack1_EffectUnit1]", "show_focus", 1);
    if (engine.getValue("[EffectRack1_EffectUnit1]", "focused_effect") === 0) {
        engine.setValue("[EffectRack1_EffectUnit1]", "focused_effect", 1);
    }

    for (let deck = 0; deck < PioneerDDJ1000.numDecks; deck++) {
        PioneerDDJ1000.renderPads(deck);
        PioneerDDJ1000.updateDisplay(deck, true);
    }

    if (!PioneerDDJ1000.screensService) {
        PioneerDDJ1000.displayTimer = engine.beginTimer(50, PioneerDDJ1000.displayTick);
    }

    // Ask the unit to report the current position of every fader and knob.
    // Give the unit a moment to settle after the LED updates above.
    engine.beginTimer(1000, PioneerDDJ1000.requestPositions, true);
};

// "PC APP connect" (note 9, off, on channel 16) makes the unit report every
// fader and knob position. The DDJ-400 style SysEx query only answers over
// raw MIDI, not through the ALSA sequencer that Mixxx uses.
PioneerDDJ1000.requestPositions = function() {
    if (PioneerDDJ1000.screensService) {
        // rekordbox's position request; safe while logged in.
        const request = [0xF0, 0x00, 0x40, 0x05, 0x00, 0x00, 0x02, 0x00, 0x00, 0x03, 0x01, 0xF7];
        midi.sendSysexMsg(request, request.length);
        return;
    }
    midi.sendShortMsg(0x9F, 0x09, 0x00);
};

PioneerDDJ1000.shutdown = function() {
    if (PioneerDDJ1000.displayTimer) {
        engine.stopTimer(PioneerDDJ1000.displayTimer);
        PioneerDDJ1000.displayTimer = 0;
    }
    for (let deck = 0; deck < PioneerDDJ1000.numDecks; deck++) {
        const status = 0x90 + deck;
        [0x0B, 0x47, 0x0C, 0x48, 0x1A, 0x58, 0x5A, 0x5C, 0x59, 0x35, 0x40, 0x15, 0x54,
            0x10, 0x11, 0x14, 0x4C, 0x4D, 0x50].forEach(function(note) {
            PioneerDDJ1000.send(status, note, 0x00);
        });
        PioneerDDJ1000.send(0xB0 + deck, 0x02, 0x00);
        if (!PioneerDDJ1000.screensService) {
            PioneerDDJ1000.send(status, 0x5D, 0x7F);  // hide jog display info
        }
        for (let pad = 0; pad < 8; pad++) {
            const note = (PioneerDDJ1000.padMode[deck] << 4) | (PioneerDDJ1000.padPage[deck] << 3) | pad;
            PioneerDDJ1000.send(PioneerDDJ1000.padStatus(deck, false), note, 0x00);
            PioneerDDJ1000.send(PioneerDDJ1000.padStatus(deck, true), note, 0x00);
        }
    }
    PioneerDDJ1000.send(0x94, 0x47, 0x00);
    PioneerDDJ1000.send(0x94, 0x43, 0x00);
};

// ---------------------------------------------------------------------------
// Browser
// ---------------------------------------------------------------------------

PioneerDDJ1000.relative = function(value) {
    return value < 0x40 ? value : value - 0x80;
};

PioneerDDJ1000.browseRotate = function(channel, control, value) {
    engine.setValue("[Library]", "MoveVertical", PioneerDDJ1000.relative(value));
};

PioneerDDJ1000.browseRotateShift = function(channel, control, value) {
    engine.setValue("[Library]", "ScrollVertical", PioneerDDJ1000.relative(value));
};

// Rotary press: 0x46 deck 1, 0x47 deck 2, 0x48 deck 3, 0x49 deck 4.
PioneerDDJ1000.browsePress = function(channel, control, value) {
    if (!value) {
        return;
    }
    // In the sidebar, open/expand the selected item instead of loading.
    if (engine.getValue("[Library]", "focused_widget") === 2) {
        engine.setValue("[Library]", "GoToItem", 1);
        return;
    }
    const deck = control - 0x46;
    engine.setValue(PioneerDDJ1000.deckGroup(deck), "LoadSelectedTrack", 1);
};

PioneerDDJ1000.browseShiftPress = function(channel, control, value) {
    if (value) {
        engine.setValue("[Library]", "GoToItem", 1);
    }
};

PioneerDDJ1000.back = function(channel, control, value) {
    if (value) {
        engine.setValue("[Library]", "MoveFocusBackward", 1);
    }
};

PioneerDDJ1000.view = function(channel, control, value) {
    if (value) {
        script.toggleControl("[Skin]", "show_maximized_library");
    }
};

// ---------------------------------------------------------------------------
// Deck transport
// ---------------------------------------------------------------------------

PioneerDDJ1000.play = function(channel, control, value, status, group) {
    if (value) {
        script.toggleControl(group, "play");
    }
};

PioneerDDJ1000.shiftButton = function(channel, control, value) {
    PioneerDDJ1000.shift[channel] = value > 0;
};

PioneerDDJ1000.tempo = function(channel, control, value, status, group) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full === undefined) {
        return;
    }
    // "-" end (top) is 0; Mixxx scales rate by rate_dir.
    const direction = engine.getValue(group, "rate_dir") || 1;
    engine.setValue(group, "rate", (full / 8192 - 1) * direction);
};

PioneerDDJ1000.cycleTempoRange = function(channel, control, value, status, group) {
    if (!value) {
        return;
    }
    const ranges = PioneerDDJ1000.tempoRanges;
    const current = engine.getValue(group, "rateRange");
    let next = ranges[0];
    for (let i = 0; i < ranges.length; i++) {
        if (current < ranges[i] - 0.001) {
            next = ranges[i];
            break;
        }
    }
    engine.setValue(group, "rateRange", next);
};

PioneerDDJ1000.sync = function(channel, control, value, status, group) {
    if (value) {
        script.toggleControl(group, "sync_enabled");
    }
};

PioneerDDJ1000.syncLeader = function(channel, control, value, status, group) {
    if (value) {
        engine.setValue(group, "sync_leader", engine.getValue(group, "sync_leader") === 2 ? 0 : 2);
    }
};

PioneerDDJ1000.fourBeatLoop = function(channel, control, value, status, group) {
    if (!value) {
        return;
    }
    if (engine.getValue(group, "loop_enabled")) {
        engine.setValue(group, "reloop_toggle", 1);
    } else {
        engine.setValue(group, "beatloop_4_activate", 1);
    }
};

PioneerDDJ1000.crossfaderAssign = function(channel, control, value, status, group) {
    if (!value) {
        return;
    }
    const orientation = {0x16: 0, 0x1D: 1, 0x18: 2}[control];
    engine.setValue(group, "orientation", orientation);
};

PioneerDDJ1000.toggle = function(key) {
    return function(channel, control, value, status, group) {
        if (value) {
            script.toggleControl(group, key);
        }
    };
};
PioneerDDJ1000.toggleKeylock = PioneerDDJ1000.toggle("keylock");
PioneerDDJ1000.toggleQuantize = PioneerDDJ1000.toggle("quantize");
PioneerDDJ1000.toggleSlip = PioneerDDJ1000.toggle("slip_enabled");
PioneerDDJ1000.toggleReverse = PioneerDDJ1000.toggle("reverse");
PioneerDDJ1000.togglePfl = PioneerDDJ1000.toggle("pfl");

PioneerDDJ1000.deckSelect = function(channel, control, value) {
    if (value) {
        PioneerDDJ1000.updateDisplay(channel, true);
        PioneerDDJ1000.renderPads(channel);
    }
};

// ---------------------------------------------------------------------------
// Jog wheels
// ---------------------------------------------------------------------------

PioneerDDJ1000.jogTouch = function(channel, control, value) {
    const deckNumber = channel + 1;
    if (value && PioneerDDJ1000.vinylMode) {
        engine.scratchEnable(deckNumber, PioneerDDJ1000.jogResolution, 33 + 1 / 3,
            PioneerDDJ1000.alpha, PioneerDDJ1000.beta);
    } else {
        engine.scratchDisable(deckNumber);
    }
};

// Top of the platter (vinyl mode): scratch while touched, bend otherwise.
PioneerDDJ1000.jogTop = function(channel, control, value, status, group) {
    const ticks = value - 0x40;
    if (engine.isScratching(channel + 1)) {
        engine.scratchTick(channel + 1, ticks);
    } else {
        engine.setValue(group, "jog", ticks * PioneerDDJ1000.bendScale);
    }
};

PioneerDDJ1000.jogBend = function(channel, control, value, status, group) {
    engine.setValue(group, "jog", (value - 0x40) * PioneerDDJ1000.bendScale);
};

PioneerDDJ1000.jogSearch = function(channel, control, value, status, group) {
    const ticks = value - 0x40;
    if (!engine.getValue(group, "track_loaded")) {
        return;
    }
    const duration = engine.getValue(group, "duration");
    if (duration <= 0) {
        return;
    }
    // One tick moves ~1/100 s times the search scale.
    const position = engine.getValue(group, "playposition") +
        ticks * PioneerDDJ1000.searchScale / 100 / duration / 10;
    engine.setValue(group, "playposition", Math.max(0, Math.min(1, position)));
};

// ---------------------------------------------------------------------------
// Mixer
// ---------------------------------------------------------------------------

PioneerDDJ1000.eqParameter = {0x07: 3, 0x0B: 2, 0x0F: 1};

PioneerDDJ1000.eq = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full === undefined) {
        return;
    }
    const parameter = PioneerDDJ1000.eqParameter[control - 0x20];
    const group = "[EqualizerRack1_" + PioneerDDJ1000.deckGroup(channel) + "_Effect1]";
    engine.setValue(group, "parameter" + parameter, script.absoluteNonLin(full, 0, 1, 4, 0, 0x3FFF));
};

PioneerDDJ1000.trim = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full !== undefined) {
        engine.setValue(PioneerDDJ1000.deckGroup(channel), "pregain",
            script.absoluteNonLin(full, 0, 1, 4, 0, 0x3FFF));
    }
};

// COLOR FX knobs CC 0x17-0x1A on channel 6 -> quick effect of CH1-4.
PioneerDDJ1000.colorFx = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full === undefined) {
        return;
    }
    const deck = (control - 0x20) - 0x17;
    engine.setParameter("[QuickEffectRack1_" + PioneerDDJ1000.deckGroup(deck) + "]", "super1", full / 0x3FFF);
};

// COLOR FX buttons toggle the quick effects of all channels.
PioneerDDJ1000.colorFxButton = function(channel, control, value) {
    if (!value) {
        return;
    }
    let anyEnabled = false;
    for (let deck = 0; deck < PioneerDDJ1000.numDecks; deck++) {
        anyEnabled = anyEnabled || engine.getValue("[QuickEffectRack1_" + PioneerDDJ1000.deckGroup(deck) + "]", "enabled");
    }
    for (let deck = 0; deck < PioneerDDJ1000.numDecks; deck++) {
        engine.setValue("[QuickEffectRack1_" + PioneerDDJ1000.deckGroup(deck) + "]", "enabled", anyEnabled ? 0 : 1);
    }
    for (let note = 0x00; note <= 0x03; note++) {
        PioneerDDJ1000.send(0x96, note, anyEnabled ? 0x00 : (note === control ? 0x7F : 0x00));
    }
};

PioneerDDJ1000.masterLevel = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full !== undefined && !PioneerDDJ1000.hardwareMasterLevel) {
        engine.setValue("[Master]", "gain", script.absoluteNonLin(full, 0, 1, 5, 0, 0x3FFF));
    }
};

PioneerDDJ1000.boothLevel = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full !== undefined && !PioneerDDJ1000.hardwareBoothLevel) {
        engine.setValue("[Master]", "booth_gain", script.absoluteNonLin(full, 0, 1, 5, 0, 0x3FFF));
    }
};

PioneerDDJ1000.headphoneMix = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full !== undefined && !PioneerDDJ1000.hardwareHeadphones) {
        engine.setValue("[Master]", "headMix", full / 8192 - 1);
    }
};

PioneerDDJ1000.headphoneLevel = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full !== undefined && !PioneerDDJ1000.hardwareHeadphones) {
        engine.setValue("[Master]", "headGain", script.absoluteNonLin(full, 0, 1, 5, 0, 0x3FFF));
    }
};

PioneerDDJ1000.masterCue = function(channel, control, value) {
    if (value && !PioneerDDJ1000.hardwareHeadphones) {
        script.toggleControl("[Master]", "headSplit");
    }
};

PioneerDDJ1000.samplerVolume = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full === undefined) {
        return;
    }
    for (let i = 1; i <= PioneerDDJ1000.numSamplers; i++) {
        engine.setParameter("[Sampler" + i + "]", "volume", full / 0x3FFF);
    }
};

PioneerDDJ1000.samplerCue = function(channel, control, value) {
    if (!value) {
        return;
    }
    const enable = !engine.getValue("[Sampler1]", "pfl");
    for (let i = 1; i <= PioneerDDJ1000.numSamplers; i++) {
        engine.setValue("[Sampler" + i + "]", "pfl", enable);
    }
    PioneerDDJ1000.send(0x96, 0x69, enable ? 0x7F : 0x00);
};

// ---------------------------------------------------------------------------
// Beat FX -> effect unit 1
// ---------------------------------------------------------------------------

PioneerDDJ1000.fxFocusedGroup = function() {
    const focused = engine.getValue("[EffectRack1_EffectUnit1]", "focused_effect") || 1;
    return "[EffectRack1_EffectUnit1_Effect" + focused + "]";
};

PioneerDDJ1000.fxLed = function() {
    const on = engine.getValue(PioneerDDJ1000.fxFocusedGroup(), "enabled") ? 0x7F : 0x00;
    PioneerDDJ1000.send(0x94, 0x47, on);
    PioneerDDJ1000.send(0x94, 0x43, on);
};

// FX SELECT is an absolute selector (notes 0x20-0x2D); step the focused
// effect in the direction it was turned.
PioneerDDJ1000.fxSelect = function(channel, control, value) {
    if (!value) {
        return;
    }
    const last = PioneerDDJ1000.fxSelectLast;
    PioneerDDJ1000.fxSelectLast = control;
    if (last === null || last === control) {
        return;
    }
    engine.setValue(PioneerDDJ1000.fxFocusedGroup(), control > last ? "next_effect" : "prev_effect", 1);
};

PioneerDDJ1000.fxChannel = function(channel, control, value) {
    if (!value) {
        return;
    }
    const target = PioneerDDJ1000.fxChannelSelect[control];
    PioneerDDJ1000.fxTarget = target;
    for (let deck = 0; deck < PioneerDDJ1000.numDecks; deck++) {
        const group = PioneerDDJ1000.deckGroup(deck);
        engine.setValue("[EffectRack1_EffectUnit1]", "group_" + group + "_enable", group === target ? 1 : 0);
    }
};

PioneerDDJ1000.fxLevel = function(channel, control, value, status) {
    const full = PioneerDDJ1000.fourteenBit(status, control, value);
    if (full !== undefined) {
        engine.setParameter("[EffectRack1_EffectUnit1]", "mix", full / 0x3FFF);
    }
};

PioneerDDJ1000.fxOnOff = function(channel, control, value) {
    if (value) {
        script.toggleControl(PioneerDDJ1000.fxFocusedGroup(), "enabled");
    }
};

PioneerDDJ1000.fxAllOff = function(channel, control, value) {
    if (!value) {
        return;
    }
    for (let i = 1; i <= 3; i++) {
        engine.setValue("[EffectRack1_EffectUnit1_Effect" + i + "]", "enabled", 0);
    }
};

PioneerDDJ1000.fxFocus = function(step) {
    return function(channel, control, value) {
        if (!value) {
            return;
        }
        let focused = engine.getValue("[EffectRack1_EffectUnit1]", "focused_effect") || 1;
        focused = ((focused - 1 + step) % 3 + 3) % 3 + 1;
        engine.setValue("[EffectRack1_EffectUnit1]", "focused_effect", focused);
    };
};
PioneerDDJ1000.fxBeatLeft = PioneerDDJ1000.fxFocus(-1);
PioneerDDJ1000.fxBeatRight = PioneerDDJ1000.fxFocus(1);

PioneerDDJ1000.fxMeta = function(step) {
    return function(channel, control, value) {
        if (value) {
            const group = PioneerDDJ1000.fxFocusedGroup();
            engine.setParameter(group, "meta", Math.max(0, Math.min(1, engine.getParameter(group, "meta") + step)));
        }
    };
};
PioneerDDJ1000.fxBeatLeftShift = PioneerDDJ1000.fxMeta(-1 / 16);
PioneerDDJ1000.fxBeatRightShift = PioneerDDJ1000.fxMeta(1 / 16);

// ---------------------------------------------------------------------------
// Pads
// ---------------------------------------------------------------------------

PioneerDDJ1000.modeButton = function(channel, control, value) {
    if (!value) {
        return;
    }
    PioneerDDJ1000.padMode[channel] = PioneerDDJ1000.modeButtons[control];
    PioneerDDJ1000.padPage[channel] = 0;
    PioneerDDJ1000.renderModeButtons(channel);
    PioneerDDJ1000.renderPads(channel);
};

PioneerDDJ1000.pageButton = function(channel, control, value) {
    if (!value) {
        return;
    }
    if (control >= PioneerDDJ1000.pageNextBase) {
        PioneerDDJ1000.padMode[channel] = control - PioneerDDJ1000.pageNextBase;
        PioneerDDJ1000.padPage[channel] = 1;
    } else {
        PioneerDDJ1000.padMode[channel] = control - PioneerDDJ1000.pagePrevBase;
        PioneerDDJ1000.padPage[channel] = 0;
    }
    PioneerDDJ1000.renderModeButtons(channel);
    PioneerDDJ1000.renderPads(channel);
};

PioneerDDJ1000.renderModeButtons = function(deck) {
    const status = 0x90 + deck;
    Object.keys(PioneerDDJ1000.modeButtons).forEach(function(note) {
        const on = PioneerDDJ1000.modeButtons[note] === PioneerDDJ1000.padMode[deck];
        PioneerDDJ1000.send(status, Number(note), on ? 0x7F : 0x00);
    });
};

PioneerDDJ1000.pad = function(channel, control, value) {
    const deck = (channel - 7) >> 1;
    const shifted = ((channel - 7) & 1) === 1;
    const mode = control >> 4;
    const page = (control >> 3) & 1;
    const pad = control & 0x07;
    const group = PioneerDDJ1000.deckGroup(deck);

    // Pads carry their mode and page, so keep our view in sync with the unit.
    if (value && (mode !== PioneerDDJ1000.padMode[deck] || page !== PioneerDDJ1000.padPage[deck])) {
        PioneerDDJ1000.padMode[deck] = mode;
        PioneerDDJ1000.padPage[deck] = page;
        PioneerDDJ1000.renderModeButtons(deck);
        PioneerDDJ1000.renderPads(deck);
    }

    const M = PioneerDDJ1000.MODE;
    switch (mode) {
    case M.HOTCUE: {
        const cue = page * 8 + pad + 1;
        engine.setValue(group, "hotcue_" + cue + (shifted ? "_clear" : "_activate"), value ? 1 : 0);
        break;
    }
    case M.PADFX1: {
        const size = PioneerDDJ1000.rollSizes[page][pad];
        engine.setValue(group, "beatlooproll_" + size + "_activate", value ? 1 : 0);
        break;
    }
    case M.BEATJUMP:
        if (value) {
            engine.setValue(group, "beatjump", PioneerDDJ1000.beatjumpSizes[page][pad] * (shifted ? 2 : 1));
        }
        break;
    case M.SAMPLER: {
        if (!value) {
            break;
        }
        const sampler = "[Sampler" + (page * 8 + pad + 1) + "]";
        if (shifted) {
            if (engine.getValue(sampler, "play")) {
                engine.setValue(sampler, "cue_gotoandstop", 1);
            } else {
                engine.setValue(sampler, "eject", 1);
                engine.setValue(sampler, "eject", 0);
            }
        } else if (engine.getValue(sampler, "track_loaded")) {
            engine.setValue(sampler, "cue_gotoandplay", 1);
        } else {
            engine.setValue(sampler, "LoadSelectedTrack", 1);
        }
        break;
    }
    case M.KEYBOARD:
        if (value) {
            engine.setValue(group, "pitch_adjust", shifted ? 0 : PioneerDDJ1000.keySteps[page][pad]);
            if (!shifted) {
                if (engine.getValue(group, "hotcue_1_status")) {
                    engine.setValue(group, "hotcue_1_gotoandplay", 1);
                } else {
                    engine.setValue(group, "cue_gotoandplay", 1);
                }
            }
        }
        break;
    case M.PADFX2:
        PioneerDDJ1000.padFx2(deck, group, pad, value, page);
        break;
    case M.BEATLOOP:
        if (value) {
            const size = PioneerDDJ1000.beatloopSizes[page][pad];
            engine.setValue(group, "beatloop_" + size + "_toggle", 1);
        }
        break;
    case M.KEYSHIFT:
        if (value) {
            engine.setValue(group, "pitch_adjust", shifted ? 0 : PioneerDDJ1000.keySteps[page][pad]);
        }
        break;
    }
};

// Pad FX 2: momentary deck effects.
PioneerDDJ1000.padFx2 = function(deck, group, pad, value, page) {
    const deckNumber = deck + 1;
    switch (pad) {
    case 0:
        engine.brake(deckNumber, value > 0);
        break;
    case 1:
        engine.spinback(deckNumber, value > 0);
        break;
    case 2:
        engine.setValue(group, "reverseroll", value ? 1 : 0);
        break;
    case 3:
        if (value) {
            engine.setValue(group, "play_stutter", 1);
        }
        break;
    default: {
        const size = PioneerDDJ1000.rollSizes[page][pad];
        engine.setValue(group, "beatlooproll_" + size + "_activate", value ? 1 : 0);
    }
    }
};

PioneerDDJ1000.padColorFor = function(deck, mode, page, pad) {
    const group = PioneerDDJ1000.deckGroup(deck);
    const C = PioneerDDJ1000.padColor;
    const M = PioneerDDJ1000.MODE;
    const loaded = engine.getValue(group, "track_loaded");
    switch (mode) {
    case M.HOTCUE: {
        const cue = page * 8 + pad + 1;
        return engine.getValue(group, "hotcue_" + cue + "_status") ? C.hotcue : C.off;
    }
    case M.PADFX1:
        return loaded ? C.roll : C.off;
    case M.BEATJUMP:
        return loaded ? C.beatjump : C.off;
    case M.SAMPLER: {
        const sampler = "[Sampler" + (page * 8 + pad + 1) + "]";
        if (engine.getValue(sampler, "play")) {
            return C.samplerPlaying;
        }
        return engine.getValue(sampler, "track_loaded") ? C.sampler : C.off;
    }
    case M.KEYBOARD:
    case M.KEYSHIFT: {
        const step = PioneerDDJ1000.keySteps[page][pad];
        const active = Math.round(engine.getValue(group, "pitch_adjust")) === step;
        return active ? (mode === M.KEYBOARD ? C.keyboard : C.keyshift) : C.off;
    }
    case M.PADFX2:
        return loaded ? C.padfx2 : C.off;
    case M.BEATLOOP: {
        const size = PioneerDDJ1000.beatloopSizes[page][pad];
        return engine.getValue(group, "beatloop_" + size + "_enabled") ? C.beatloopActive : C.off;
    }
    }
    return C.off;
};

PioneerDDJ1000.renderPadsAt = function(deck, mode, page) {
    for (let pad = 0; pad < 8; pad++) {
        const note = (mode << 4) | (page << 3) | pad;
        const color = PioneerDDJ1000.padColorFor(deck, mode, page, pad);
        PioneerDDJ1000.send(PioneerDDJ1000.padStatus(deck, false), note, color);
        PioneerDDJ1000.send(PioneerDDJ1000.padStatus(deck, true), note, color);
    }
};

PioneerDDJ1000.renderPads = function(deck) {
    PioneerDDJ1000.renderPadsAt(deck, PioneerDDJ1000.padMode[deck], PioneerDDJ1000.padPage[deck]);
};

PioneerDDJ1000.renderAllPads = function(deck) {
    for (let mode = 0; mode < 8; mode++) {
        PioneerDDJ1000.renderPadsAt(deck, mode, 0);
        PioneerDDJ1000.renderPadsAt(deck, mode, 1);
    }
};

PioneerDDJ1000.renderPadsFor = function(deck) {
    return function() {
        PioneerDDJ1000.renderPads(deck);
    };
};

PioneerDDJ1000.renderSamplerPads = function() {
    for (let deck = 0; deck < PioneerDDJ1000.numDecks; deck++) {
        PioneerDDJ1000.renderPadsAt(deck, PioneerDDJ1000.MODE.SAMPLER, 0);
        PioneerDDJ1000.renderPadsAt(deck, PioneerDDJ1000.MODE.SAMPLER, 1);
    }
};

// ---------------------------------------------------------------------------
// Jog displays
// ---------------------------------------------------------------------------

// Degrees of platter rotation for a position in seconds, at 33 1/3 RPM.
PioneerDDJ1000.angle = function(seconds) {
    const degrees = (seconds * 200) % 360;
    return degrees < 0 ? degrees + 360 : degrees;
};

PioneerDDJ1000.updateDisplayFor = function(deck) {
    return function() {
        PioneerDDJ1000.updateDisplay(deck, false);
    };
};

// Send only values that changed, unless force is set.
PioneerDDJ1000.updateDisplay = function(deck, force) {
    if (PioneerDDJ1000.screensService) {
        return;
    }
    const group = PioneerDDJ1000.deckGroup(deck);
    const status = 0x90 + deck;
    const cc = 0xB0 + deck;
    const loaded = engine.getValue(group, "track_loaded") > 0;
    const next = {visible: loaded ? 0x00 : 0x7F};
    // Resend everything when the display is forced or a track was (un)loaded.
    if (next.visible !== PioneerDDJ1000.lastDisplay[deck].visible) {
        force = true;
    }
    const last = force ? {} : PioneerDDJ1000.lastDisplay[deck];

    if (loaded) {
        next.bpm = Math.round(engine.getValue(group, "bpm") * 10);
        const rate = engine.getValue(group, "rate") * engine.getValue(group, "rateRange") *
            (engine.getValue(group, "rate_dir") || 1);
        next.speed = Math.round(rate * 1000) & 0x3FFF;
        const key = Math.round(engine.getValue(group, "file_key"));
        next.key = PioneerDDJ1000.keyCodes[key] || 0x00;
        next.keyVariation = 0x0D + Math.max(-12, Math.min(12, Math.round(engine.getValue(group, "pitch"))));

        const seconds = engine.getValue(group, "playposition") * engine.getValue(group, "duration");
        const remaining = engine.getValue("[Controls]", "ShowDurationRemaining") === 1;
        const shown = Math.max(0, remaining ? engine.getValue(group, "duration") - seconds : seconds);
        next.timeMode = remaining ? 0x7F : 0x00;
        next.minutes = Math.min(99, Math.floor(shown / 60));
        next.seconds = Math.floor(shown % 60);
        next.position = Math.round(PioneerDDJ1000.angle(seconds));

        const cuePoint = engine.getValue(group, "cue_point");
        const sampleRate = engine.getValue(group, "track_samplerate");
        next.cue = cuePoint >= 0 && sampleRate > 0 ?
            Math.round(PioneerDDJ1000.angle(cuePoint / sampleRate / 2)) : 0x3FFF;
    }

    const changed = function(key) {
        return next[key] !== undefined && next[key] !== last[key];
    };
    if (changed("visible")) {
        PioneerDDJ1000.send(status, 0x5D, next.visible);
    }
    if (changed("bpm")) {
        PioneerDDJ1000.send14(cc, 0x15, next.bpm);
    }
    if (changed("speed")) {
        PioneerDDJ1000.send14(cc, 0x16, next.speed);
    }
    if (changed("key")) {
        PioneerDDJ1000.send(status, 0x49, next.key);
    }
    if (changed("keyVariation")) {
        PioneerDDJ1000.send(status, 0x4A, next.keyVariation);
    }
    if (changed("timeMode")) {
        PioneerDDJ1000.send(status, 0x44, next.timeMode);
    }
    if (changed("minutes")) {
        PioneerDDJ1000.send(status, 0x42, next.minutes);
    }
    if (changed("seconds")) {
        PioneerDDJ1000.send(status, 0x43, next.seconds);
    }
    if (changed("position")) {
        PioneerDDJ1000.send14(cc, 0x14, next.position);
    }
    if (changed("cue")) {
        PioneerDDJ1000.send14(cc, 0x17, next.cue);
    }
    PioneerDDJ1000.lastDisplay[deck] = force ? next : Object.assign(last, next);
};

PioneerDDJ1000.displayTick = function() {
    for (let deck = 0; deck < PioneerDDJ1000.numDecks; deck++) {
        PioneerDDJ1000.updateDisplay(deck, false);
    }
};
