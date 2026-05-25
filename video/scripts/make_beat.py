#!/usr/bin/env python3
"""Generate an original, royalty-free chillhop beat for the SectorScope class intro.

Deterministic synthesis (no samples, no external audio) -> assets/beat.wav.
Tempo 100 BPM, 5 bars = 12.0s, to match the video timeline.
"""
import os
import struct
import wave

import numpy as np

SR = 44100
BPM = 100.0
BEAT = 60.0 / BPM          # 0.60s
BAR = 4 * BEAT             # 2.40s
BARS = 5                   # -> 12.0s total
TOTAL = BARS * BAR
N = int(TOTAL * SR)

rng = np.random.default_rng(7)   # fixed seed -> deterministic noise


def t_for(n):
    return np.arange(n) / SR


def adsr(n, a, d, s, r, sustain=0.6):
    """Simple linear ADSR envelope over n samples."""
    env = np.zeros(n)
    a_n, d_n, r_n = int(a * SR), int(d * SR), int(r * SR)
    a_n = min(a_n, n)
    d_n = min(d_n, max(0, n - a_n))
    r_n = min(r_n, max(0, n - a_n - d_n))
    s_n = max(0, n - a_n - d_n - r_n)
    i = 0
    if a_n:
        env[i:i + a_n] = np.linspace(0, 1, a_n); i += a_n
    if d_n:
        env[i:i + d_n] = np.linspace(1, sustain, d_n); i += d_n
    if s_n:
        env[i:i + s_n] = sustain; i += s_n
    if r_n:
        env[i:i + r_n] = np.linspace(sustain, 0, r_n); i += r_n
    return env


def place(buf, sig, start_s):
    i = int(start_s * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += sig[:j - i]


# ---------------------------------------------------------------- drums
def kick(dur=0.34, gain=0.95):
    n = int(dur * SR)
    t = t_for(n)
    pitch = 52 + 70 * np.exp(-t * 32)        # 122Hz -> 52Hz sweep
    phase = 2 * np.pi * np.cumsum(pitch) / SR
    body = np.sin(phase) * np.exp(-t * 7.5)
    click = np.sin(2 * np.pi * 1800 * t) * np.exp(-t * 120) * 0.25
    return (body + click) * gain


def snare(dur=0.22, gain=0.42):
    n = int(dur * SR)
    t = t_for(n)
    noise = rng.standard_normal(n)
    # crude bandpass shaping via difference + decay
    noise = np.convolve(noise, np.array([1, -0.6]), mode="same")
    tone = np.sin(2 * np.pi * 190 * t) * np.exp(-t * 22) * 0.5
    return (noise * np.exp(-t * 26) + tone) * gain


def hat(dur=0.05, gain=0.16):
    n = int(dur * SR)
    t = t_for(n)
    noise = rng.standard_normal(n)
    noise = np.convolve(noise, np.array([1, -0.85]), mode="same")  # high-pass-ish
    return noise * np.exp(-t * 90) * gain


# ---------------------------------------------------------------- tonal
def note(freq, dur, gain, kind="pad", detune=0.0):
    n = int(dur * SR)
    t = t_for(n)
    if kind == "pad":
        osc = (np.sin(2 * np.pi * freq * t)
               + 0.5 * np.sin(2 * np.pi * (freq * (1 + detune)) * t)
               + 0.22 * np.sin(2 * np.pi * 2 * freq * t)
               + 0.1 * np.sin(2 * np.pi * 3 * freq * t))
        env = adsr(n, 0.18, 0.25, 0.0, 0.5, sustain=0.75)
    elif kind == "bass":
        osc = np.sin(2 * np.pi * freq * t) + 0.18 * np.sin(2 * np.pi * 2 * freq * t)
        env = adsr(n, 0.006, 0.12, 0.0, 0.18, sustain=0.55)
    else:  # pluck melody (triangle-ish)
        osc = (np.sin(2 * np.pi * freq * t)
               + 0.18 * np.sin(2 * np.pi * 2 * freq * t)
               + 0.07 * np.sin(2 * np.pi * 3 * freq * t))
        env = adsr(n, 0.004, 0.16, 0.0, 0.3, sustain=0.0)
    return osc * env * gain


NOTES = {  # equal temperament, A4 = 440
    "F2": 87.31, "G2": 98.00, "A2": 110.00, "C3": 130.81, "E3": 164.81,
    "F3": 174.61, "G3": 196.00, "A3": 220.00, "B3": 246.94, "C4": 261.63,
    "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00, "A4": 440.00,
    "B4": 493.88, "C5": 523.25, "D5": 587.33, "E5": 659.25,
}

# vi - IV - I - V in C major, one chord per bar (warm, "pastel" mood)
PROG = [
    ("A2", ["A3", "C4", "E4", "G4"]),    # Am7
    ("F2", ["F3", "A3", "C4", "E4"]),    # Fmaj7
    ("C3", ["C4", "E4", "G4", "B4"]),    # Cmaj7
    ("G2", ["G3", "B3", "D4", "E4"]),    # G6
]

# gentle pentatonic top-line motif (scale degrees within each bar), in beats
MELODY = [
    [(0.0, "E4"), (1.5, "G4"), (2.5, "A4")],
    [(0.0, "C5"), (1.5, "A4"), (3.0, "G4")],
    [(0.0, "G4"), (1.0, "E4"), (2.5, "G4")],
    [(0.5, "D5"), (2.0, "B4"), (3.0, "A4")],
]


def build():
    L = np.zeros(N)
    R = np.zeros(N)

    for bar in range(BARS):
        b0 = bar * BAR
        chord_root, chord_notes = PROG[bar % 4]
        mel = MELODY[bar % 4]

        # --- drums ---
        # kick on beats 1 and 3, plus a soft pickup before the loop turnaround
        for beat in (0, 2):
            k = kick()
            place(L, k, b0 + beat * BEAT)
            place(R, k, b0 + beat * BEAT)
        if bar % 4 == 3:
            k = kick(gain=0.6)
            place(L, k, b0 + 3.5 * BEAT)
            place(R, k, b0 + 3.5 * BEAT)
        # snare on beats 2 and 4
        for beat in (1, 3):
            s = snare()
            place(L, s, b0 + beat * BEAT)
            place(R, s, b0 + beat * BEAT)
        # hats on every eighth note with light swing + velocity variation
        for e in range(8):
            swing = 0.06 * BEAT if e % 2 == 1 else 0.0
            g = 0.16 if e % 2 == 0 else 0.11
            h = hat(gain=g)
            pan = 0.12 * (1 if e % 2 else -1)        # slight stereo motion
            place(L, h * (1 - pan), b0 + e * 0.5 * BEAT + swing)
            place(R, h * (1 + pan), b0 + e * 0.5 * BEAT + swing)

        # --- pad chord (held for the bar) ---
        for idx, nm in enumerate(chord_notes):
            det = 0.004 * (1 if idx % 2 else -1)
            v = note(NOTES[nm], BAR * 0.98, 0.085, "pad", detune=det)
            pan = 0.18 * (idx - 1.5) / 1.5            # spread the voices
            place(L, v * (1 - pan * 0.5), b0)
            place(R, v * (1 + pan * 0.5), b0)

        # --- bass: root on 1, fifth/octave movement on the "and" of 3 ---
        bass = note(NOTES[chord_root], BEAT * 1.9, 0.5, "bass")
        place(L, bass, b0)
        place(R, bass, b0)
        bass2 = note(NOTES[chord_root] * 1.5, BEAT * 1.2, 0.34, "bass")
        place(L, bass2, b0 + 2.5 * BEAT)
        place(R, bass2, b0 + 2.5 * BEAT)

        # --- melody (skip first bar of the loop for breathing room) ---
        if bar >= 1:
            for beat, nm in mel:
                m = note(NOTES[nm], BEAT * 1.1, 0.13, "pluck")
                place(L, m * 0.9, b0 + beat * BEAT)
                place(R, m, b0 + beat * BEAT)

    # --- master bus: gentle one-pole low-pass (warmth) ---
    def lp_fast(x, a=0.30):
        b = 1 - a
        y = np.empty_like(x)
        y[0] = a * x[0]
        # iterative but on float64; acceptable for 84s
        acc = y[0]
        xa = x * a
        for i in range(1, len(x)):
            acc = xa[i] + b * acc
            y[i] = acc
        return y

    L = lp_fast(L)
    R = lp_fast(R)

    # soft-clip limiter
    def limit(x):
        peak = np.max(np.abs(x)) + 1e-9
        x = x / peak * 1.05
        x = np.tanh(x * 1.1) / np.tanh(1.1)
        return x

    L = limit(L)
    R = limit(R)

    # fades
    fin = int(0.6 * SR)
    fout = int(2.0 * SR)
    fade_in = np.linspace(0, 1, fin)
    fade_out = np.linspace(1, 0, fout)
    for ch in (L, R):
        ch[:fin] *= fade_in
        ch[-fout:] *= fade_out

    # headroom
    L *= 0.85
    R *= 0.85
    return L, R


def write_wav(path, L, R):
    inter = np.empty(len(L) * 2, dtype=np.int16)
    inter[0::2] = np.clip(L, -1, 1) * 32767
    inter[1::2] = np.clip(R, -1, 1) * 32767
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(inter.tobytes())


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "..", "assets", "beat.wav")
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    L, R = build()
    write_wav(out, L, R)
    print(f"wrote {out}  ({TOTAL:.2f}s, {len(L)} samples/ch)")
