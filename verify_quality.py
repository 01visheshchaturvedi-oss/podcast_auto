"""Verify the generated podcast quality against reference."""
import os, subprocess, json, struct, numpy as np

GEN_PATH = os.path.expanduser('~/Desktop/menu/podcast_auto/podcast_output/AI_AKASHVANI_EMOTIONAL.mp3')
REF_PATH = os.path.expanduser('~/Desktop/menu/podcast_auto/14-05-26-AI AKASHVANI REVISION.m4a')
FFPROBE = r'C:\Users\sk\AppData\Local\hermes\git\usr\local\bin\ffprobe.exe'
FFMPEG = r'C:\Users\sk\AppData\Local\hermes\git\usr\local\bin\ffmpeg.exe'

print("=" * 60)
print("📊 GENERATED PODCAST vs REFERENCE QUALITY COMPARISON")
print("=" * 60)

for label, path in [("📀 GENERATED (Ours)", GEN_PATH), ("🎯 REFERENCE (Target)", REF_PATH)]:
    print(f"\n--- {label} ---")
    print(f"   File: {os.path.basename(path)}")
    print(f"   Size: {os.path.getsize(path)/1024/1024:.1f} MB")

    # Probe
    result = subprocess.run(
        [FFPROBE, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', path],
        capture_output=True, text=True, timeout=30
    )
    info = json.loads(result.stdout)

    for s in info.get('streams', []):
        if s['codec_type'] == 'audio':
            print(f"   Codec: {s.get('codec_name','?')}")
            print(f"   Sample rate: {s.get('sample_rate','?')} Hz")
            print(f"   Channels: {s.get('channels','?')}")
            print(f"   Bitrate: {s.get('bit_rate','?')} bps")

    fmt = info.get('format', {})
    dur = float(fmt.get('duration', 0))
    print(f"   Duration: {dur:.0f}s ({dur/60:.1f} min)")
    print(f"   Overall bitrate: {int(fmt.get('bit_rate',0))/1000:.0f} kbps")

    # Decode first 10s for loudness analysis
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        tmp_wav = f.name
    try:
        subprocess.run(
            [FFMPEG, '-y', '-i', path, '-ss', str(dur*0.5), '-t', '10',
             '-acodec', 'pcm_s16le', '-f', 'wav', tmp_wav],
            capture_output=True, timeout=30
        )
        with open(tmp_wav, 'rb') as f:
            data = f.read()
        sr = struct.unpack_from('<I', data, 24)[0]
        ch = struct.unpack_from('<H', data, 22)[0]
        # Find data chunk
        offset = 12
        data_start = None
        while offset < len(data) - 8:
            cid = data[offset:offset+4]
            csz = struct.unpack_from('<I', data, offset+4)[0]
            if cid == b'data':
                data_start = offset + 8
                data_size = csz
                break
            offset += 8 + csz
        if data_start:
            raw = np.frombuffer(data[data_start:data_start+data_size], dtype=np.int16)
            if ch == 2:
                raw = raw.reshape(-1, 2)
                s = (raw[:,0].astype(float) + raw[:,1].astype(float)) / 2
            else:
                s = raw.astype(float)
            rms = np.sqrt(np.mean(s**2))
            peak = np.max(np.abs(s))
            print(f"   Loudness (RMS): {rms:.0f}")
            print(f"   Peak: {peak}")
            print(f"   Dynamic range: {20*np.log10(peak/max(rms,1)):.1f} dB")
            # Stereo check
            if ch == 2:
                l = raw[:,0].astype(float)
                r = raw[:,1].astype(float)
                corr = np.corrcoef(l, r)[0,1]
                print(f"   Stereo correlation: {corr:.3f}")
                if corr < 0.9:
                    print(f"   → TRUE STEREO")
                elif corr > 0.99:
                    print(f"   → MONO")
                else:
                    print(f"   → WIDE STEREO")
            # Per-second
            print(f"   Per-second levels (midpoint 10s):")
            for sec in range(min(10, len(s)//sr)):
                seg = s[sec*sr:(sec+1)*sr]
                seg_rms = np.sqrt(np.mean(seg**2))
                bar = '▓' * int(seg_rms / max(rms,1) * 20)
                print(f"     {sec+1}s: {seg_rms:6.0f} {bar}")
    finally:
        try: os.remove(tmp_wav)
        except: pass

print("\n" + "=" * 60)
print("✅ Analysis Complete")
print("=" * 60)
