"""
TTS Engine using Microsoft Edge TTS (edge-tts)
Generates emotional Hindi speech via native Communicate params (rate, pitch, volume)
NO SSML — SSML wrapping causes 5-15x audio elongation on Hindi voices.
"""
import asyncio
import os
import platform
import re
import subprocess
import sys
import edge_tts
from pydub import AudioSegment

from .emotion_ssml import (
    detect_emotion,
    get_ssml_params,
    analyze_script_for_emotions,
)

# ── Voices ──
FEMALE_VOICE = "hi-IN-SwaraNeural"
MALE_VOICE = "hi-IN-MadhurNeural"

# ── Speed Presets ──
MODES = {
    "1": {"label": "Revision  (थोड़ा तेज़)", "female": "+15%", "male": "+5%"},
    "2": {"label": "Learn     (थोड़ा धीमा)", "female": "-10%", "male": "-15%"},
    "3": {"label": "Natural   (सामान्य)",      "female": "+0%",  "male": "+0%"},
    "4": {"label": "Expressive (भावनात्मक)",    "female": "+5%", "male": "+0%"},
}


def split_sentences(text):
    text = re.sub(r'([।.!?])\s*', r'\1\n', text)
    return [s.strip() for s in text.split('\n') if s.strip()]


def silence(ms):
    return AudioSegment.silent(duration=ms)


def _compat_volume(db_val: str) -> str:
    """Convert dB volume to edge-tts percentage format."""
    # SSML uses +/-XdB, edge-tts uses +/-X%
    if db_val.endswith('dB'):
        try:
            db = float(db_val.replace('dB', ''))
            # Rough: +1dB≈+12%, +2dB≈+25%, +3dB≈+40%, +4dB≈+50%
            pct = round(db * 12.5)
            return f"{'+' if pct >= 0 else ''}{pct}%"
        except ValueError:
            pass
    return db_val


class EmotionalTTSEngine:
    """
    TTS Engine that generates speech with emotion-aware prosody.
    Uses edge-tts native params (rate, pitch, volume) — NO SSML.
    Includes rate-limiting to avoid Microsoft throttling + gTTS fallback.
    """

    # Rate-limit state (class-level to span synthesize calls)
    _call_count = 0
    _last_call_time = 0.0
    _BATCH_SIZE = 12       # reset after every 12 calls
    _BATCH_DELAY = 2.0     # delay between each call
    _RESET_DELAY = 8.0     # extra cooldown after batch

    def __init__(self, mode='3', output_dir='podcast_output'):
        self.mode = mode
        self.rate_config = MODES.get(mode, MODES["3"])
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def get_voice(self, role):
        return FEMALE_VOICE if role == "female" else MALE_VOICE

    def get_base_rate(self, role):
        return self.rate_config["female"] if role == "female" else self.rate_config["male"]

    def _resolve_params(self, text, role, emotion_params, base_rate):
        """Convert emotion params to edge-tts compatible rate/pitch/volume."""
        if emotion_params is None:
            emotion = detect_emotion(text)
            emotion_params = get_ssml_params(emotion, role, text)

        raw_rate = emotion_params.get('rate', '0%')
        raw_pitch = emotion_params.get('pitch', '0Hz')
        raw_volume = emotion_params.get('volume', '+0dB')

        # edge-tts v7.2.8 validates: pitch=^[+-]\d+Hz$, volume=^[+-]\d+%$
        if raw_pitch == '0%':
            raw_pitch = '+0Hz'
        raw_volume = _compat_volume(raw_volume)

        # Combine emotion rate + base rate
        combined_rate = raw_rate
        if base_rate and base_rate != '+0%':
            try:
                emo_pct = int(combined_rate.replace('%', '').replace('+', ''))
                base_pct = int(base_rate.replace('%', '').replace('+', ''))
                combined = emo_pct + base_pct
                sign = '+' if combined >= 0 else ''
                combined_rate = f"{sign}{combined}%"
            except ValueError:
                pass

        # Build kwargs — only pass non-default values
        kwargs = {}
        if combined_rate != '+0%':
            kwargs['rate'] = combined_rate
        if raw_pitch != '+0Hz':
            kwargs['pitch'] = raw_pitch
        if raw_volume != '+0%':
            kwargs['volume'] = raw_volume

        if not kwargs:
            return None, emotion_params  # signal: use all defaults

        return kwargs, emotion_params

    async def _rate_limit_delay(self):
        """Enforce inter-call delay + batch reset to avoid Microsoft throttling."""
        EmotionalTTSEngine._call_count += 1
        now = asyncio.get_event_loop().time()

        # Enforce per-call delay
        if EmotionalTTSEngine._last_call_time > 0:
            elapsed = now - EmotionalTTSEngine._last_call_time
            needed = EmotionalTTSEngine._BATCH_DELAY - elapsed
            if needed > 0:
                await asyncio.sleep(needed)

        # Batch reset: after every BATCH_SIZE calls, add extra cooldown
        if EmotionalTTSEngine._call_count % EmotionalTTSEngine._BATCH_SIZE == 0:
            await asyncio.sleep(EmotionalTTSEngine._RESET_DELAY)

        EmotionalTTSEngine._last_call_time = asyncio.get_event_loop().time()
        return EmotionalTTSEngine._call_count

    async def _synthesize_gtts(self, text, voice, out_path):
        """gTTS fallback — works reliably when edge-tts is throttled."""
        from gtts import gTTS
        lang = 'hi' if 'hi-' in voice else 'en'
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: gTTS(text=text, lang=lang, slow=False).save(out_path)
            )
            return os.path.exists(out_path) and os.path.getsize(out_path) > 500
        except Exception:
            return False

    async def _run_cli_async(self, text, voice, kwargs, out_path, timeout=20):
        """Run edge-tts CLI with OS-appropriate timeout handling.
        - Linux: direct subprocess.run(timeout=...) — SIGKILL works properly
        - Windows: via wrapper (manual poll + taskkill /F /T)
        """
        OS = platform.system()
        loop = asyncio.get_event_loop()

        if kwargs:
            rate = kwargs.get('rate', '+0%')
            pitch = kwargs.get('pitch', '+0Hz')
            volume = kwargs.get('volume', '+0%')
        else:
            rate, pitch, volume = '+0%', '+0Hz', '+0%'

        if OS == 'Windows':
            # ── Windows: use wrapper with manual poll + taskkill ──
            wrapper = os.path.join(os.path.dirname(__file__), 'tts_wrapper.py')
            try:
                rc = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        [sys.executable, wrapper, text, voice, out_path, str(timeout),
                         rate, pitch, volume],
                        timeout=timeout + 15,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    ).returncode
                )
                return rc == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 500
            except (subprocess.TimeoutExpired, Exception):
                try:
                    subprocess.run(['C:\\Windows\\System32\\taskkill.exe', '/F', '/IM', 'python.exe',
                                   '/FI', 'WINDOWTITLE eq edge_tts*'],
                                  capture_output=True, timeout=5)
                except:
                    pass
                return False
        else:
            # ── Linux: direct subprocess.run(timeout=...) — SIGKILL works ──
            cmd = [sys.executable, '-m', 'edge_tts', '--text', text,
                   '--voice', voice, '--write-media', out_path]
            if rate != '+0%':
                cmd.extend(['--rate', rate])
            if pitch != '+0Hz':
                cmd.extend(['--pitch', pitch])
            if volume != '+0%':
                cmd.extend(['--volume', volume])

            try:
                rc = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        cmd, timeout=timeout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    ).returncode
                )
                return rc == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 500
            except (subprocess.TimeoutExpired, Exception):
                return False

    async def synthesize(self, text, role, emotion_params=None, base_rate=None):
        """
        Synthesize text with emotional prosody via edge-tts CLI subprocess.
        Falls back to gTTS when edge-tts is throttled.
        Returns (path, emotion_params) or (None, emotion_params).
        """
        voice = self.get_voice(role)
        if base_rate is None:
            base_rate = self.get_base_rate(role)

        tts_kwargs, eparams = self._resolve_params(text, role, emotion_params, base_rate)

        import uuid
        filename = f"_{uuid.uuid4().hex[:8]}.mp3"
        out_path = os.path.join(self.output_dir, filename)

        # ── Attempt 1: edge-tts with emotion params ──
        await self._rate_limit_delay()
        success = await self._run_cli_async(text, voice, tts_kwargs, out_path, 15)
        if success:
            return out_path, eparams

        # ── Attempt 2: edge-tts bare (no emotion params) ──
        fallback_path = out_path.replace('.mp3', '_fb.mp3')
        await self._rate_limit_delay()
        success = await self._run_cli_async(text, voice, None, fallback_path, 20)
        if success:
            return fallback_path, eparams

        # ── Attempt 3: gTTS fallback (always works) ──
        gtts_path = out_path.replace('.mp3', '_gtts.mp3')
        await self._rate_limit_delay()
        success = await self._synthesize_gtts(text, voice, gtts_path)
        if success:
            return gtts_path, eparams

        return None, eparams

    async def synthesize_turn(self, turn_data, index=0):
        """
        Synthesize a full speaker turn with full-turn emotion, falling back
        to per-sentence only if the full turn fails.
        """
        text = turn_data['text']
        role = turn_data['role']
        emotion = turn_data.get('emotion', detect_emotion(text))
        ssml_params = turn_data.get('ssml_params', get_ssml_params(emotion, role, text))
        base_rate = self.get_base_rate(role)

        # Full-turn synthesis (fast path)
        result_path, params = await self.synthesize(text, role, ssml_params, base_rate)
        if result_path:
            clip = AudioSegment.from_mp3(result_path)
            try:
                os.remove(result_path)
            except:
                pass
            return clip, params

        # Per-sentence fallback
        clips = await self._synthesize_sentences(text, role, ssml_params, base_rate)
        if not clips:
            return None, None

        combined = AudioSegment.empty()
        for i, (clip, _) in enumerate(clips):
            if i > 0:
                combined += silence(200)
            combined += clip
        return combined, emotion

    async def _synthesize_sentences(self, text, role, emotion_params=None, base_rate=None):
        """Per-sentence synthesis fallback via CLI subprocess."""
        voice = self.get_voice(role)
        if base_rate is None:
            base_rate = self.get_base_rate(role)

        sentences = split_sentences(text)
        clips = []

        for sent in sentences:
            if not sent.strip():
                continue

            tts_kwargs, _ = self._resolve_params(sent, role, None, base_rate)
            import uuid
            filename = f"_{uuid.uuid4().hex[:8]}.mp3"
            out_path = os.path.join(self.output_dir, filename)

            success = await self._run_cli_async(sent, voice, tts_kwargs, out_path, 15)
            if success:
                clip = AudioSegment.from_mp3(out_path)
                clips.append((clip, {}))
                try:
                    os.remove(out_path)
                except:
                    pass
                continue

            # Bare fallback
            fb_path = out_path.replace('.mp3', '_fb.mp3')
            success = await self._run_cli_async(sent, voice, None, fb_path, 15)
            if success:
                clip = AudioSegment.from_mp3(fb_path)
                clips.append((clip, {}))
                try:
                    os.remove(fb_path)
                except:
                    pass

        return clips
