"""Fallback TTS via edge-tts CLI subprocess (isolates websocket hanging)."""
import subprocess
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def synthesize_cli(text, voice, rate='+0%', pitch='+0Hz', volume='+0%', output_path=None, timeout=20):
    """Call edge-tts CLI as a subprocess. Returns output path or None."""
    if output_path is None:
        import uuid
        output_path = f"_cli_{uuid.uuid4().hex[:8]}.mp3"

    cmd = [
        sys.executable, '-m', 'edge_tts',
        '--text', text,
        '--voice', voice,
        '--write-media', output_path,
    ]
    if rate != '+0%':
        cmd.extend(['--rate', rate])
    if pitch != '+0Hz':
        cmd.extend(['--pitch', pitch])
    if volume != '+0%':
        cmd.extend(['--volume', volume])

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
        )
        if r.returncode != 0:
            print(f"    ⚠️  CLI TTS error: {r.stderr.strip()}")
            return None
        if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
            return output_path
        return None
    except subprocess.TimeoutExpired:
        print(f"    ⚠️  CLI TTS timeout ({timeout}s)")
        return None
    except Exception as e:
        print(f"    ⚠️  CLI TTS exception: {e}")
        return None
