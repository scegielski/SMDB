"""Build original MIDI lounge cues and portable PCM renditions (no external synth)."""
from pathlib import Path
import struct
import wave
import numpy as np

ROOT = Path(__file__).resolve().parent / 'assets' / 'weather_music'
RATE, TPQ = 22050, 480


def variable(value):
    parts = [value & 127]
    while value >> 7:
        value >>= 7
        parts.insert(0, (value & 127) | 128)
    return bytes(parts)


def compose(name, bpm, progression, melody):
    events = []
    beat = 60 / bpm
    bars = 16
    for bar in range(bars):
        root, chord = progression[bar % len(progression)]
        start = bar * 4
        for b in (0, 2):
            events.append((start + b, 1.8, root - 12 if b == 0 else root - 5, 1, 56))
        for b in (0, 1.5, 3):
            for interval in chord:
                events.append((start + b, 1.25 if b < 3 else .8, root + 12 + interval, 0, 37))
        for i, interval in enumerate(melody[bar % len(melody)]):
            if interval is not None:
                events.append((start + i * .5, .38 if i % 2 else .7, root + 24 + interval, 2, 47))
    total = int((bars * 4 * beat + 2) * RATE)
    audio = np.zeros((total, 2), dtype=np.float64)
    midi = [(0, b'\xff\x51\x03' + round(60000000 / bpm).to_bytes(3, 'big'))]
    for channel, program in ((0, 4), (1, 33), (2, 11)):
        midi.append((0, bytes((0xC0 + channel, program))))
    for at, length, note, channel, velocity in events:
        midi.extend(((round(at * TPQ), bytes((0x90 + channel, note, velocity))),
                     (round((at + length) * TPQ), bytes((0x80 + channel, note, 0)))))
        duration = length * beat
        t = np.arange(int((duration + .35) * RATE)) / RATE
        freq = 440 * 2 ** ((note - 69) / 12)
        phase = 2 * np.pi * freq * t
        envelope = (1 - np.exp(-t * 65)) * np.exp(-t * (1.4 if channel == 1 else 2.6))
        envelope *= np.minimum(1, np.maximum(0, (duration + .35 - t) / .35))
        signal = (np.sin(phase) + .25 * np.sin(phase * 2) + .08 * np.sin(phase * 3)) if channel == 1 else np.sin(phase + 1.1 * np.sin(phase * (2 if channel == 0 else 3)) * np.exp(-t * 4))
        signal *= envelope * velocity / 127 * .12
        offset = round(at * beat * RATE)
        end = min(total, offset + len(signal))
        pan = (.7, .5) if channel == 0 else (.5, .7) if channel == 2 else (.65, .65)
        for side in range(2):
            audio[offset:end, side] += signal[:end - offset] * pan[side]
    audio *= np.minimum(1, np.arange(total) / RATE)[:, None]
    audio *= np.minimum(1, (total - np.arange(total)) / RATE / 2)[:, None]
    # A short, soft stereo room echo.
    for delay, gain in ((.08, .12), (.16, .07)):
        count = round(delay * RATE)
        audio[count:] += audio[:-count].copy() * gain
    audio = np.clip(audio, -.8, .8)
    ROOT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ROOT / (name + '.wav')), 'w') as file:
        file.setnchannels(2)
        file.setsampwidth(2)
        file.setframerate(RATE)
        file.writeframes((audio * 32767).astype('<i2').tobytes())
    track, previous = bytearray(), 0
    for tick, message in sorted(midi, key=lambda entry: entry[0]):
        track += variable(tick - previous) + message
        previous = tick
    track += variable(round(bars * 4 * TPQ) - previous) + b'\xff\x2f\x00'
    (ROOT / (name + '.mid')).write_bytes(b'MThd' + struct.pack('>IHHH', 6, 0, 1, TPQ) + b'MTrk' + struct.pack('>I', len(track)) + track)


if __name__ == '__main__':
    compose('evening_breeze', 88, [(48, (4,7,11,14)), (45, (3,7,10,14)), (50, (3,7,10,14)), (43, (4,7,10,14))],
            [(4,None,7,9,None,7,4,None),(3,None,7,None,10,7,None,3),(7,None,10,7,None,5,3,None),(4,None,7,10,None,9,7,None)])
    compose('local_outlook', 96, [(53, (4,7,11,14)), (50, (3,7,10,14)), (55, (3,7,10,14)), (48, (4,7,10,14))],
            [(7,None,4,2,None,4,7,None),(3,None,5,7,None,10,7,None),(7,None,3,5,None,7,10,None),(4,None,2,0,None,4,7,None)])
    compose('quiet_horizon', 80, [(51, (4,7,11,14)), (48, (3,7,10,14)), (53, (3,7,10,14)), (46, (4,7,10,14))],
            [(4,None,None,7,11,None,7,None),(7,None,10,None,7,None,3,None),(3,None,7,None,10,None,7,None),(4,None,7,None,10,9,7,None)])
