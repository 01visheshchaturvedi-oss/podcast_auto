# Deep Analysis of Existing Code & Reference Audio

## Folder Structure
```
podcast_auto/
├── podcast_agent.py          # CLI entry point (204 lines)
├── engine/                   # Core engine package
│   ├── __init__.py           # Exports
│   ├── tts_engine.py         # edge-tts with emotion prosody (326 lines)
│   ├── tts_wrapper.py        # Windows taskkill wrapper (58 lines)
│   ├── tts_cli.py            # Standalone CLI fallback (43 lines)
│   ├── emotion_ssml.py       # Keyword-based emotion detection (309 lines)
│   ├── podcast_builder.py    # Script parsing + assembly (226 lines)
│   └── audio_effects.py      # Broadcast mastering chain (332 lines)
├── transcribe.txt            # 168-turn Hindi podcast script
├── raw_code.txt              # Original source data
├── 14-05-26-AI AKASHVANI REVISION.m4a  # Reference audio (20.3 min)
├── smoke_test.py, analyze_audio.py, verify_quality.py  # Test utilities
├── run.bat                   # Windows launcher
├── .devcontainer/devcontainer.json  # Codespaces config
└── .gitignore
```

## Reference Audio Characteristics
- **Format**: AAC (m4a), 256 kbps CBR, 44100 Hz, Stereo
- **Duration**: 20.3 minutes (1216s)
- **Loudness**: -16.3 LUFS (broadcast standard)
- **LRA**: 4.7 LU (consistent podcast delivery)
- **Encoder**: Google (processed through Google ecosystem)
- The ref audio IS edge-tts generated (Swara + Madhur) with quality mastering

## What's Good in Current Code
1. **Emotion detection**: 7 emotion categories with Hindi+English keyword patterns
2. **Audio mastering**: Full broadcast chain (EQ, compressor, stereo widen, limiter, reverb, noise gate)
3. **Cross-platform**: OS-detect pattern (Linux SIGKILL, Windows taskkill)
4. **Fallback chain**: edge-tts params → edge-tts bare → gTTS
5. **Rate limiting**: Batches of 12 calls with delay to avoid Microsoft throttling

## What's Missing / Lacking
1. **NO express-as styles** - Microsoft TTS has `mstts:express-as` (cheerful, sad, serious, excited, empathetic, etc.) but code avoids all SSML due to elongation issue with prosody tags
2. **Emotion detection is keyword-only** - no context awareness
3. **No background music** - pure speech only
4. **Basic crossfades** - simple gap + crossfade instead of overlap-based
5. **No voice caching** - re-generates same phrases
6. **No inline mood annotations** - can't mark lines as [excited] or [serious]
7. **Turn-level emotion only** - not per-sentence
8. **devcontainer ffmpeg feature** - fails on Codespaces (ghcr.io auth)

## Improvement Strategy for v2
1. Keep free-only: edge-tts + gTTS, no paid APIs
2. Try mstts:express-as WITHOUT prosody tags (likely won't cause elongation)
3. Add background music (CC0/free) with audio ducking
4. Overlap-based crossfades (pydub overlay)
5. Inline mood annotations in script
6. Multi-sentence emotion per turn
7. Voice caching (phrase dedup)
8. Mastering tuned to -16 LUFS (matching reference)
