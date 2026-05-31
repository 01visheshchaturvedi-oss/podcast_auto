"""Analyze the reference audio file using ffprobe/ffmpeg directly."""
import os
import subprocess
import json
import struct
import numpy as np

path = os.path.expanduser('~/Desktop/menu/podcast_auto/14-05-26-AI AKASHVANI REVISION.m4a')
print(f"File exists: {os.path.exists(path)}")
print(f"File size: {os.path.getsize(path) / 1024 / 1024:.1f} MB")

# Git-bash's /usr/local/bin maps to this Windows path
FFPROBE = r'C:\Users\sk\AppData\Local\hermes\git\usr\local\bin\ffprobe.exe'
FFMPEG = r'C:\Users\sk\AppData\Local\hermes\git\usr\local\bin\ffmpeg.exe'

# Also try Spotify's bundled ffmpeg if available
if not os.path.exists(FFPROBE):
    for p in [r'C:\Users\sk\scoop\apps\ffmpeg\current\bin\ffprobe.exe',
              r'C:\ProgramData\chocolatey\bin\ffprobe.exe',
              r'C:\Users\sk\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1.1-full_build\bin\ffprobe.exe']:
        if os.path.exists(p):
            FFPROBE = p
            FFMPEG = p.replace('ffprobe', 'ffmpeg')
            break

print(f"ffprobe exists: {os.path.exists(FFPROBE)}")
print(f"ffmpeg exists: {os.path.exists(FFMPEG)}")

# Get file info
result = subprocess.run(
    [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', path],
    capture_output=True, text=True, timeout=30
)
if result.stderr:
    print(f"\nffprobe stderr: {result.stderr[:300]}")

info = json.loads(result.stdout)
print("\n=== Stream Info ===")
for s in info.get('streams', []):
    print(f"  Codec: {s.get('codec_name', 'N/A')}")
    print(f"  Type: {s.get('codec_type', 'N/A')}")
    print(f"  Sample rate: {s.get('sample_rate', 'N/A')} Hz")
    print(f"  Channels: {s.get('channels', 'N/A')}")
    print(f"  Bit rate: {s.get('bit_rate', 'N/A')} bps")
    print(f"  Duration: {s.get('duration', 'N/A')}s")
    print(f"  Channel layout: {s.get('channel_layout', 'N/A')}")

fmt = info.get('format', {})
print(f"\n=== Format Info ===")
print(f"  Format: {fmt.get('format_name', 'N/A')}")
print(f"  Duration: {fmt.get('duration', 'N/A')}s")
print(f"  Size: {fmt.get('size', 'N/A')} ({int(fmt['size'])/1024/1024:.1f} MB)" if 'size' in fmt else "")
print(f"  Bitrate: {fmt.get('bit_rate', 'N/A')} bps = {int(fmt['bit_rate'])/1000:.0f} kbps" if 'bit_rate' in fmt else "")
tags = fmt.get('tags', {})
if tags:
    print(f"  Tags:")
    for k, v in tags.items():
        print(f"    {k}: {v}")

# Decode first 30s to WAV
import tempfile
with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
    tmp_wav = f.name

try:
    r = subprocess.run(
        [FFMPEG, '-y', '-i', path, '-ss', '0', '-t', '30', '-acodec', 'pcm_s16le', '-f', 'wav', tmp_wav],
        capture_output=True, text=True, timeout=60
    )
    if r.returncode != 0:
        print(f"\nffmpeg error: {r.stderr[:500]}")
    else:
        # Read WAV
        with open(tmp_wav, 'rb') as f:
            data = f.read()
        
        # Quick WAV header parse
        sample_rate = struct.unpack_from('<I', data, 24)[0]
        channels = struct.unpack_from('<H', data, 22)[0]
        bits_per_sample = struct.unpack_from('<H', data, 34)[0]
        
        # Find data chunk
        offset = 12
        data_start = None
        while offset < len(data) - 8:
            chunk_id = data[offset:offset+4]
            chunk_size = struct.unpack_from('<I', data, offset+4)[0]
            if chunk_id == b'data':
                data_start = offset + 8
                data_size = chunk_size
                break
            offset += 8 + chunk_size
        
        if data_start:
            raw = np.frombuffer(data[data_start:data_start+data_size], dtype=np.int16)
            if channels == 2:
                raw = raw.reshape(-1, 2)
                left = raw[:, 0].astype(float)
                right = raw[:, 1].astype(float)
                combined = (left + right) / 2
            else:
                combined = raw.astype(float)
                left = right = combined
            
            dur_sec = len(combined) / sample_rate
            print(f"\n=== Decoded Audio Stats ===")
            print(f"Sample rate: {sample_rate} Hz")
            print(f"Channels: {channels}")
            print(f"Bits per sample: {bits_per_sample}")
            print(f"Duration decoded: {dur_sec:.1f}s / {dur_sec/60:.1f}min")
            
            # Overall stats
            rms = np.sqrt(np.mean(combined**2))
            peak = np.max(np.abs(combined))
            peak_to_rms_db = 20 * np.log10(peak / max(rms, 1))
            print(f"RMS (avg loudness): {rms:.0f}")
            print(f"Peak: {peak}")
            print(f"Peak-to-RMS ratio: {peak_to_rms_db:.1f} dB")
            
            # Stereo analysis
            if channels == 2:
                diff = np.mean(np.abs(left - right))
                corr = np.corrcoef(left[:len(right)], right[:len(left)])[0,1] if len(left)==len(right) else 0
                print(f"Stereo L-R diff: {diff:.1f}")
                print(f"Stereo correlation: {corr:.3f}")
                if abs(corr) < 0.9:
                    print("-> TRUE STEREO (different content per channel)")
                elif corr > 0.99:
                    print("-> MONO / identical channels")
                else:
                    print("-> STEREO WIDE (some panning)")
            
            # Silence detection
            silences = combined[combined < rms*0.05] if rms > 0 else []
            silence_ratio = len(silences) / len(combined) * 100
            print(f"Silence (<5% RMS): {silence_ratio:.1f}% of audio")
            
            # Per-second loudness
            sec_samples = sample_rate
            print(f"\nPer-second loudness (first 30s sample):")
            loud_segments = 0
            quiet_segments = 0
            for s in range(min(30, int(dur_sec))):
                start = s * sec_samples
                end = min(start + sec_samples, len(combined))
                seg = combined[start:end]
                if len(seg) == 0: break
                seg_rms = np.sqrt(np.mean(seg**2))
                bar_len = int(seg_rms / max(rms, 1) * 25) if rms > 0 else 0
                bar = '▓' * min(bar_len, 60)
                status = ""
                if seg_rms > rms * 1.5: 
                    status = " ★"
                    loud_segments += 1
                elif seg_rms < rms * 0.3: 
                    status = " ·"
                    quiet_segments += 1
                print(f"  {s+1:2d}s: {seg_rms:7.0f} {bar}{status}")
            print(f"  → Loud segments: {loud_segments}, Quiet: {quiet_segments}")

finally:
    try: os.remove(tmp_wav)
    except: pass

print("\n✅ Reference audio analysis complete!")
