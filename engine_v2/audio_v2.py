"""
Enhanced Audio Processing v2 for Hindi Podcasts

Provides:
- Broadcast mastering chain tuned to -16 LUFS (matching reference)
- Background music mixing with audio ducking
- Overlap-based crossfades (better than gap+fade)
- Loudness matching
"""
import os
import subprocess
import tempfile
import struct
import numpy as np
from pydub import AudioSegment
from pydub.effects import normalize
from typing import Optional, Tuple


# ── Loudness Analysis ─────────────────────────────────────────────
def analyze_loudness(audio: AudioSegment) -> dict:
    """
    Analyze audio loudness using ffmpeg ebur128 filter.
    Returns dict with I (integrated LUFS), LRA, peak.
    Falls back to sample-based estimation if ffmpeg not available.
    """
    # Try ffprobe/ffmpeg path
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return _estimate_loudness(audio)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        in_path = f.name
    try:
        audio.export(in_path, format='wav')
        r = subprocess.run(
            [ffmpeg, '-i', in_path, '-af', 'ebur128=framelog=quiet',
             '-f', 'null', '-'],
            capture_output=True, text=True, timeout=30
        )
        output = r.stderr
        result = {}
        for line in output.split('\n'):
            if 'I:' in line and 'LUFS' in line:
                try:
                    result['integrated'] = float(line.split('I:')[1].split('LUFS')[0].strip())
                except:
                    pass
            if 'LRA:' in line:
                try:
                    result['lra'] = float(line.split('LRA:')[1].split('LU')[0].strip())
                except:
                    pass
            if 'Peak:' in line:
                try:
                    result['peak'] = float(line.split('Peak:')[1].split('dB')[0].strip())
                except:
                    pass
        return result
    except:
        return _estimate_loudness(audio)
    finally:
        try:
            os.remove(in_path)
        except:
            pass


def _estimate_loudness(audio: AudioSegment) -> dict:
    """Simple loudness estimation without ffmpeg."""
    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    if audio.channels == 2:
        samples = samples.reshape(-1, 2)
        samples = (samples[:, 0] + samples[:, 1]) / 2
    rms = np.sqrt(np.mean(samples ** 2))
    peak = np.max(np.abs(samples))
    # Rough RMS-to-LUFS conversion
    lufs = -20 * np.log10(max(rms / 32768, 1e-10)) - 0.7
    return {
        'integrated': -min(abs(lufs), 30),
        'peak': 20 * np.log10(max(peak / 32768, 1e-10)),
        'rms': rms,
    }


def _find_ffmpeg() -> Optional[str]:
    """Find ffmpeg executable."""
    candidates = [
        'ffmpeg',
        r'C:\Users\sk\AppData\Local\hermes\git\usr\local\bin\ffmpeg.exe',
        r'C:\Users\sk\AppData\Local\ms-playwright\ffmpeg-1011\ffmpeg-win64.exe',
        '/usr/bin/ffmpeg',
        '/usr/local/bin/ffmpeg',
    ]
    for c in candidates:
        try:
            subprocess.run([c, '-version'], capture_output=True, timeout=5)
            return c
        except:
            continue
    return None


# ── Loudness Matching ─────────────────────────────────────────────
class MatchLoudness:
    """Match audio loudness to a target LUFS level."""

    TARGET_LUFS = -16.0  # Matching reference audio

    @classmethod
    def process(cls, audio: AudioSegment, target: float = None) -> AudioSegment:
        """Scale audio to match target loudness."""
        if target is None:
            target = cls.TARGET_LUFS

        analysis = analyze_loudness(audio)
        current = analysis.get('integrated', -20)
        if current is None or current >= 0:
            return normalize(audio)

        # Gain needed
        gain_db = target - current
        if abs(gain_db) < 0.5:
            return audio

        # Apply gain
        gain_linear = 10 ** (gain_db / 20)
        samples = np.array(audio.get_array_of_samples()).astype(np.float64)
        samples = samples * gain_linear

        # Prevent clipping
        max_val = np.max(np.abs(samples))
        if max_val > 32767:
            samples = samples * (32767 / max_val)

        samples = samples.astype(np.int16)
        return audio._spawn(samples.tobytes())


# ── EQ (Broadcast Vocal Curve) ────────────────────────────────────
def parametric_eq_v2(audio: AudioSegment) -> AudioSegment:
    """
    Enhanced broadcast EQ curve for Hindi speech.
    Uses ffmpeg's equalizer filter for precision.
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return audio

    bands = [
        (80, 2.5, 0.7),      # Low-end warmth
        (180, 0.5, 0.8),     # Slight body
        (280, -3.0, 1.2),    # Remove muddiness (more aggressive)
        (600, 0.0, 0.8),     # Neutral
        (1200, 0.5, 0.7),    # Slight presence
        (2800, 3.5, 0.9),    # Presence boost for clarity
        (5000, 2.0, 0.7),    # Clarity/shine
        (8000, 1.5, 0.6),    # Air
        (12000, 3.0, 0.5),   # High-end sparkle
    ]

    # Build ffmpeg filter string
    filter_parts = []
    for freq, gain, q in bands:
        if abs(gain) < 0.5:
            continue
        filter_parts.append(f"equalizer=f={freq}:t=q:w={q}:g={gain}")

    if not filter_parts:
        return audio

    filter_str = ','.join(filter_parts)

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_in:
        in_path = f_in.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_out:
        out_path = f_out.name

    try:
        audio.export(in_path, format='wav')
        subprocess.run(
            [ffmpeg, '-y', '-i', in_path, '-af', filter_str, out_path],
            capture_output=True, timeout=30
        )
        return AudioSegment.from_wav(out_path)
    except:
        return audio
    finally:
        try:
            os.remove(in_path)
        except:
            pass
        try:
            os.remove(out_path)
        except:
            pass


# ── Compressor (Broadcast Style) ──────────────────────────────────
def broadcast_compressor_v2(audio: AudioSegment,
                            threshold: float = -18,
                            ratio: float = 3.5,
                            attack_ms: float = 3,
                            release_ms: float = 60,
                            makeup_db: float = 3) -> AudioSegment:
    """
    Enhanced broadcast compressor with smoother envelope.
    """
    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    max_val = np.max(np.abs(samples))
    if max_val == 0:
        return audio

    samples = samples / max_val
    eps = 1e-10
    db = 20 * np.log10(np.abs(samples) + eps)

    # Compute gain reduction
    gain_reduction = np.zeros_like(db)
    mask = db > threshold
    gain_reduction[mask] = (threshold - db[mask]) * (1 - 1.0 / ratio)

    # Smooth with envelope follower (attack/release)
    smoothed = np.zeros_like(gain_reduction)
    current = 0.0
    attack_coeff = 1.0 - np.exp(-1.0 / (attack_ms * audio.frame_rate / 1000))
    release_coeff = 1.0 - np.exp(-1.0 / (release_ms * audio.frame_rate / 1000))

    for i in range(len(gain_reduction)):
        target = gain_reduction[i]
        if target < current:
            # Attack (gain reduction increasing)
            current += (target - current) * attack_coeff
        else:
            # Release (gain reduction decreasing)
            current += (target - current) * release_coeff
        smoothed[i] = current

    # Apply
    compressed = samples * (10 ** (smoothed / 20))

    # Make-up gain
    compressed = compressed * (10 ** (makeup_db / 20))

    compressed = np.clip(compressed, -1, 1)
    compressed = (compressed * 32767).astype(np.int16)

    return audio._spawn(compressed.tobytes())


# ── Stereo Widening ───────────────────────────────────────────────
def stereo_widen_v2(audio: AudioSegment, width: float = 0.35) -> AudioSegment:
    """
    Mid-side stereo widening.
    width: 0.0 = mono, 0.5 = moderate, 1.0 = aggressive
    """
    if audio.channels != 2:
        return audio

    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    left = samples[0::2]
    right = samples[1::2]

    mid = (left + right) / 2
    side = (left - right) / 2

    mid_gain = 1.0 - width * 0.3
    side_gain = 0.3 + width * 0.7

    new_mid = mid * mid_gain
    new_side = side * side_gain

    new_left = new_mid + new_side
    new_right = new_mid - new_side

    max_val = max(np.max(np.abs(new_left)), np.max(np.abs(new_right)))
    if max_val > 32767:
        new_left = new_left * (32767 / max_val)
        new_right = new_right * (32767 / max_val)

    output = np.column_stack((new_left, new_right)).ravel().astype(np.int16)
    return audio._spawn(output.tobytes())


# ── Limiter ───────────────────────────────────────────────────────
def brickwall_limiter(audio: AudioSegment, ceiling_db: float = -1.0) -> AudioSegment:
    """True peak limiter to prevent clipping."""
    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    max_val = np.max(np.abs(samples))
    if max_val == 0:
        return audio

    ceiling = 10 ** (ceiling_db / 20) * 32767
    if max_val > ceiling:
        samples = samples * (ceiling / max_val)

    samples = samples.astype(np.int16)
    return audio._spawn(samples.tobytes())


# ── Overlap Crossfade ─────────────────────────────────────────────
def overlap_crossfade(prev: AudioSegment, next_seg: AudioSegment,
                      overlap_ms: int = 150) -> AudioSegment:
    """
    Smooth speaker transition via overlapping crossfade.
    Fades out prev while fading in next over overlap_ms.
    Better than gap+crossfade since it's continuous.
    """
    if len(prev) < overlap_ms or len(next_seg) < overlap_ms:
        return prev + next_seg

    # Fade out end of prev
    prev_fade = prev[-overlap_ms:].fade_out(overlap_ms)
    prev_body = prev[:-overlap_ms]

    # Fade in start of next
    next_fade = next_seg[:overlap_ms].fade_in(overlap_ms)
    next_body = next_seg[overlap_ms:]

    # Overlay the fade segments
    overlay = prev_fade.overlay(next_fade)

    return prev_body + overlay + next_body


# ── Background Music Mixing ───────────────────────────────────────
def audio_duck(speech: AudioSegment, music: AudioSegment,
               duck_db: float = -8.0,
               attack_ms: int = 100, release_ms: int = 300) -> AudioSegment:
    """
    Mix speech over background music with ducking.
    Music volume lowers when speech is present.
    """
    # Match lengths
    if len(music) < len(speech):
        # Loop music if needed
        repeats = (len(speech) // len(music)) + 1
        music = music * repeats
    music = music[:len(speech)]

    # Ensure same channels
    if music.channels != speech.channels:
        if speech.channels == 2 and music.channels == 1:
            music = music.set_channels(2)
        elif speech.channels == 1 and music.channels == 2:
            music = music.set_channels(1)

    # Analyse speech for silence/speech detection
    speech_samples = np.array(speech.get_array_of_samples()).astype(np.float64)
    if speech.channels == 2:
        speech_samples = speech_samples.reshape(-1, 2)
        speech_mono = (speech_samples[:, 0] + speech_samples[:, 1]) / 2
    else:
        speech_mono = speech_samples

    frame_rate = speech.frame_rate
    rms = np.sqrt(np.mean(speech_mono ** 2))
    if rms == 0:
        rms = 1

    # Build ducking envelope (per sample, smoothed)
    duck_envelope = np.ones(len(speech_mono))
    threshold = rms * 0.15  # Below this = silence
    duck_gain = 10 ** (duck_db / 20)  # e.g., -8dB = 0.398

    attack_samples = int(frame_rate * attack_ms / 1000)
    release_samples = int(frame_rate * release_ms / 1000)

    target_gain = 1.0  # 1.0 = full music
    current_gain = 1.0

    # Apply envelope follower
    att_coeff = np.exp(-1.0 / attack_samples) if attack_samples > 0 else 0
    rel_coeff = np.exp(-1.0 / release_samples) if release_samples > 0 else 0

    for i in range(len(speech_mono)):
        energy = abs(speech_mono[i])
        if energy > threshold:
            target_gain = duck_gain  # Lower music when speech present
        else:
            target_gain = 1.0  # Full music during silence

        if target_gain < current_gain:
            # Attack (duck fast)
            current_gain = target_gain + (current_gain - target_gain) * att_coeff
        else:
            # Release (come back slowly)
            current_gain = target_gain + (current_gain - target_gain) * rel_coeff

        duck_envelope[i] = current_gain

    # Apply ducking envelope to music
    music_samples = np.array(music.get_array_of_samples()).astype(np.float64)

    if music.channels == 2:
        for i in range(min(len(duck_envelope), len(music_samples) // 2)):
            idx = i * 2
            music_samples[idx] *= duck_envelope[i]
            music_samples[idx + 1] *= duck_envelope[i]
    else:
        for i in range(min(len(duck_envelope), len(music_samples))):
            music_samples[i] *= duck_envelope[i]

    music_samples = np.clip(music_samples, -32767, 32767).astype(np.int16)
    ducked_music = music._spawn(music_samples.tobytes())

    # Mix speech + ducked music
    mixed = speech.overlay(ducked_music, gain_during_overlay=-6)  # music -6dB baseline
    return mixed


def mix_background_music(speech: AudioSegment,
                         music_path: Optional[str] = None,
                         volume_db: float = -18.0) -> AudioSegment:
    """
    Add background music to speech.
    If no music_path provided, generates a subtle ambient drone.

    Returns mixed AudioSegment.
    """
    if music_path and os.path.exists(music_path):
        try:
            music = AudioSegment.from_file(music_path)
        except:
            music_path = None

    if not music_path:
        # Generate a gentle ambient drone using sine waves
        music = _generate_ambient_drone(len(speech), speech.frame_rate)

    # Reduce music volume relative to speech
    music = music - abs(volume_db) if volume_db < 0 else music

    # Match sample rate
    if music.frame_rate != speech.frame_rate:
        music = music.set_frame_rate(speech.frame_rate)

    # Apply ducking
    return audio_duck(speech, music)


def _generate_ambient_drone(duration_ms: int, sample_rate: int = 44100) -> AudioSegment:
    """
    Generate a subtle ambient drone using stacked sine waves.
    Creates a warm, podcast-appropriate background tone.
    """
    import math

    num_samples = int(sample_rate * duration_ms / 1000)
    t = np.arange(num_samples) / sample_rate

    # Stack a few gentle sine waves at low volumes
    drone = np.zeros(num_samples)
    frequencies = [55, 82, 110, 146.83, 220]  # A2, E2, A3, D3, A4
    amplitudes = [0.008, 0.004, 0.003, 0.002, 0.001]  # Very quiet

    for freq, amp in zip(frequencies, amplitudes):
        drone += amp * np.sin(2 * np.pi * freq * t)

    # Add a tiny bit of noise for warmth
    drone += np.random.normal(0, 0.002, num_samples)

    # Normalize
    max_val = np.max(np.abs(drone))
    if max_val > 0:
        drone = drone * (0.05 / max_val)  # Keep at -26dB

    # Convert to int16
    drone_int16 = (drone * 32767).astype(np.int16)

    # Create stereo AudioSegment
    stereo = np.column_stack((drone_int16, drone_int16)).ravel().astype(np.int16)

    return AudioSegment(
        stereo.tobytes(),
        frame_rate=sample_rate,
        sample_width=2,
        channels=2
    )


# ── Mastering Chain ───────────────────────────────────────────────
def master_podcast_v2(audio: AudioSegment,
                      target_loudness: float = -16.0,
                      use_music: bool = False,
                      music_path: Optional[str] = None) -> AudioSegment:
    """
    Full podcast mastering chain v2:
    1. Stereo upmix (if mono)
    2. EQ (broadcast vocal curve)
    3. Compression (broadcast style, smoother)
    4. Stereo widening (subtle)
    5. Brickwall limiting
    6. Loudness matching to target (-16 LUFS)
    7. Normalization

    Matches reference audio characteristics.
    """
    # Ensure stereo
    if audio.channels == 1:
        audio = audio.set_channels(2)

    # Ensure 44.1kHz
    if audio.frame_rate < 44100:
        audio = audio.set_frame_rate(44100)

    print("  🎛️  Mastering: EQ (vocal curve)...")
    audio = parametric_eq_v2(audio)

    print("  🎛️  Mastering: Compression...")
    audio = broadcast_compressor_v2(audio, threshold=-20, ratio=4.0, makeup_db=4)

    print("  🎛️  Mastering: Stereo widening...")
    audio = stereo_widen_v2(audio, width=0.35)

    print("  🎛️  Mastering: Limiting...")
    audio = brickwall_limiter(audio, ceiling_db=-1.0)

    print("  🎛️  Mastering: Loudness matching...")
    audio = MatchLoudness.process(audio, target_loudness)

    print("  🎛️  Mastering: Normalization...")
    audio = normalize(audio)

    return audio
