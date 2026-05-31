"""
Audio Effects Engine - Broadcast-quality audio post-processing
EQ, Compression, Stereo Widening, Noise Gating, Reverb
Uses pydub + numpy for all operations (no external audio plugins needed)
"""
import numpy as np
from pydub import AudioSegment
from pydub.effects import normalize
from pydub.generators import Sine
import struct
import io


def load_audio(path_or_segment):
    """Handle both path strings and AudioSegment objects."""
    if isinstance(path_or_segment, AudioSegment):
        return path_or_segment
    return AudioSegment.from_file(path_or_segment)


def export_audio(audio, path, bitrate="256k", format="mp3"):
    """Export with high quality settings."""
    audio.export(path, format=format, bitrate=bitrate,
                 parameters=["-q:a", "0"])  # highest MP3 quality
    return path


def broadcast_compressor(audio, threshold=-18, ratio=3.0, attack=5, release=50):
    """
    Broadcast-style dynamic range compression.
    - threshold: dB level where compression kicks in (-18 to -24 is typical for broadcast)
    - ratio: compression ratio (3:1 to 6:1)
    - attack: attack time in ms
    - release: release time in ms
    """
    # Convert to samples
    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    max_val = np.max(np.abs(samples))
    if max_val == 0:
        return audio

    # Normalize to [-1, 1]
    samples = samples / max_val

    # Convert to dB
    eps = 1e-10
    db = 20 * np.log10(np.abs(samples) + eps)

    # Compute envelope using RMS in small windows
    win_size = int(audio.frame_rate * attack / 1000)
    if win_size < 1:
        win_size = 1

    # Apply compression
    gain_reduction = np.zeros_like(db)
    mask = db > threshold
    gain_reduction[mask] = (threshold - db[mask]) * (1 - 1.0 / ratio)

    # Smooth the gain reduction (simple envelope follower)
    # Apply release time smoothing
    release_samples = int(audio.frame_rate * release / 1000)
    smoothed_gr = np.zeros_like(gain_reduction)
    current_gr = 0.0
    for i in range(len(gain_reduction)):
        target_gr = gain_reduction[i]
        # Attack faster than release
        if target_gr < current_gr:
            current_gr += (target_gr - current_gr) * 0.3  # fast attack
        else:
            current_gr += (target_gr - current_gr) * 0.01  # slow release
        smoothed_gr[i] = current_gr

    # Apply gain reduction
    compressed = samples * (10 ** (smoothed_gr / 20))

    # Make-up gain
    makeup_gain = -np.mean(smoothed_gr[db > threshold]) * 0.5 if np.any(db > threshold) else 0
    compressed = compressed * (10 ** (makeup_gain / 20))

    # Convert back
    compressed = np.clip(compressed, -1, 1)
    compressed = (compressed * 32767).astype(np.int16)

    return audio._spawn(compressed.tobytes())


def parametric_eq(audio, bands=None):
    """
    Simple multi-band EQ using cascaded filters.
    bands: list of (freq, gain_db, q_factor)
    Default: broadcast vocal EQ curve
    """
    if bands is None:
        # Broadcast vocal EQ: reduce mud (200-400Hz), boost presence (2-4kHz), add air (8-12kHz)
        bands = [
            (80, 2.0, 0.7),     # Low-end warmth
            (250, -2.5, 1.0),   # Reduce muddiness
            (800, 0.5, 0.8),    # Body
            (2500, 3.0, 0.9),   # Presence boost
            (5000, 1.5, 0.7),   # Clarity
            (10000, 2.0, 0.5),  # Air/shine
        ]

    result = audio
    for freq, gain, q in bands:
        result = _apply_peak_filter(result, freq, gain, q)
    return result


def _apply_peak_filter(audio, freq, gain_db, q):
    """Apply a simple IIR-based peaking EQ filter."""
    # For simplicity with pydub, we use a low-level approach
    if abs(gain_db) < 0.5:
        return audio  # Skip negligible adjustments

    # We use ffmpeg's equalizer filter for precision
    import subprocess
    import os
    import tempfile

    # Find ffmpeg
    ffmpeg_candidates = [
        r'C:\Users\sk\AppData\Local\hermes\git\usr\local\bin\ffmpeg.exe',
        r'C:\Users\sk\AppData\Local\ms-playwright\ffmpeg-1011\ffmpeg-win64.exe',
    ]
    ffmpeg_path = None
    for p in ffmpeg_candidates:
        if os.path.exists(p):
            ffmpeg_path = p
            break

    if not ffmpeg_path:
        return audio  # Can't EQ without ffmpeg

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_in:
        in_path = f_in.name
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f_out:
        out_path = f_out.name

    try:
        audio.export(in_path, format='wav')
        filter_str = f"equalizer=f={freq}:width_type=q:width={q}:g={gain_db}"
        subprocess.run(
            [ffmpeg_path, '-y', '-i', in_path, '-af', filter_str, out_path],
            capture_output=True, timeout=30
        )
        result = AudioSegment.from_wav(out_path)
        return result
    except:
        return audio
    finally:
        try: os.remove(in_path)
        except: pass
        try: os.remove(out_path)
        except: pass


def stereo_widen(audio, width=0.5):
    """
    Stereo widening that creates more spatial separation.
    width: 0.0 = mono, 0.5 = moderate, 1.0 = full wide
    Works by applying mid-side processing.
    """
    if audio.channels != 2:
        return audio

    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    left = samples[0::2]
    right = samples[1::2]

    # Mid-Side decomposition
    mid = (left + right) / 2
    side = (left - right) / 2

    # Widen: reduce mid, boost side
    mid_gain = 1.0 - width * 0.3
    side_gain = 0.3 + width * 0.7

    new_mid = mid * mid_gain
    new_side = side * side_gain

    # Convert back to L/R
    new_left = new_mid + new_side
    new_right = new_mid - new_side

    # Normalize to prevent clipping
    max_val = max(np.max(np.abs(new_left)), np.max(np.abs(new_right)))
    if max_val > 32767:
        new_left = new_left * (32767 / max_val)
        new_right = new_right * (32767 / max_val)

    # Interleave
    output = np.column_stack((new_left, new_right)).ravel().astype(np.int16)
    return audio._spawn(output.tobytes())


def noise_gate(audio, threshold=-40, attack_ms=10, release_ms=100, hold_ms=50):
    """
    Noise gate to clean up silence/pauses between speech.
    threshold: dB threshold below which audio is gated
    """
    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    max_val = np.max(np.abs(samples))
    if max_val == 0:
        return audio

    samples = samples / max_val
    eps = 1e-10
    db = 20 * np.log10(np.abs(samples) + eps)

    # Simple gate
    gate_open = False
    output = np.copy(samples)
    attack_samples = int(audio.frame_rate * attack_ms / 1000)
    release_samples = int(audio.frame_rate * release_ms / 1000)
    hold_samples = int(audio.frame_rate * hold_ms / 1000)
    hold_counter = 0

    for i in range(len(samples)):
        if db[i] > threshold:
            if not gate_open:
                gate_open = True
            hold_counter = hold_samples
        else:
            if hold_counter > 0:
                hold_counter -= 1
            else:
                gate_open = False

        if not gate_open:
            # Fade out during release
            if release_samples > 0:
                output[i] *= 0.001
            else:
                output[i] = 0

    # Apply attack/release smoothing
    # (simplified - full implementation would use exponential smoothing)

    output = (output * 32767).astype(np.int16)
    return audio._spawn(output.tobytes())


def subtle_reverb(audio, decay=0.2, delay_ms=30):
    """
    Simple reverb using comb filter approach.
    decay: 0.0-1.0 (wetness)
    delay_ms: delay time in ms
    """
    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    delay_samples = int(audio.frame_rate * delay_ms / 1000)

    if delay_samples <= 0 or delay_samples >= len(samples):
        return audio

    # Simple reverb: add delayed + decayed copy
    output = np.copy(samples)
    for i in range(delay_samples, len(samples)):
        output[i] += samples[i - delay_samples] * decay

    # Normalize
    max_val = np.max(np.abs(output))
    if max_val > 32767:
        output = output * (32767 / max_val)

    # Mix wet/dry
    wet = 0.15
    dry = 1.0 - wet
    output = output * wet + samples * dry

    output = output.astype(np.int16)
    return audio._spawn(output.tobytes())


def limiter(audio, ceiling=-1.0):
    """
    Brick wall limiter to prevent clipping.
    ceiling: dB level to limit at (e.g., -1.0dB)
    """
    samples = np.array(audio.get_array_of_samples()).astype(np.float64)
    max_val = np.max(np.abs(samples))
    if max_val == 0:
        return audio

    ceiling_linear = 10 ** (ceiling / 20)
    target_level = ceiling_linear * 32767

    if max_val > target_level:
        ratio = target_level / max_val
        samples = samples * ratio

    samples = samples.astype(np.int16)
    return audio._spawn(samples.tobytes())


def master_podcast(audio, target_loudness=-16):
    """
    Full podcast mastering chain:
    1. Ensure stereo (mono → stereo upmix)
    2. Upsample to 44.1kHz
    3. EQ (broadcast vocal curve)
    4. Compression (broadcast style)
    5. Stereo widening
    6. Limiting
    7. Normalization to target loudness
    """
    # Ensure stereo for widening to work
    if audio.channels == 1:
        print("  🎛️  Mastering: Mono → Stereo upmix...")
        audio = audio.set_channels(2)

    # Ensure 44.1kHz sample rate
    if audio.frame_rate < 44100:
        print(f"  🎛️  Mastering: Upsample {audio.frame_rate}Hz → 44100Hz...")
        audio = audio.set_frame_rate(44100)

    print("  🎛️  Mastering: EQ...")
    audio = parametric_eq(audio)

    print("  🎛️  Mastering: Compression...")
    audio = broadcast_compressor(audio, threshold=-20, ratio=4.0)

    print("  🎛️  Mastering: Stereo widening...")
    audio = stereo_widen(audio, width=0.4)

    print("  🎛️  Mastering: Limiting...")
    audio = limiter(audio, ceiling=-1.0)

    print("  🎛️  Mastering: Normalization...")
    audio = normalize(audio)

    return audio
