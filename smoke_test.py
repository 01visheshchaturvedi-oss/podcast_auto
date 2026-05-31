"""Quick smoke test: verify param-based TTS works without elongation."""
import asyncio, sys, json, subprocess
sys.path.insert(0, 'C:/Users/sk/Desktop/menu/podcast_auto')
from engine.tts_engine import EmotionalTTSEngine

ffprobe = r'C:\Users\sk\AppData\Local\hermes\git\usr\local\bin\ffprobe.exe'

async def test():
    engine = EmotionalTTSEngine(mode="4", output_dir="podcast_output")
    
    cases = [
        ("male", "हम बिल्कुल।", "short emphasis"),
        ("female", "वाओ यह तो बहुत शानदार है!", "excited"),
        ("male", "देखिए आईबीसीआई एक्चुअली एनवायरनमेंट डिप्लोमेसी का नया चेहरा है।", "long serious"),
        ("female", "हाँ, एकदम सही पकड़ा।", "agreement"),
    ]
    
    for role, text, desc in cases:
        path, params = await engine.synthesize(text, role)
        if path:
            r = subprocess.run([ffprobe, '-v', 'quiet', '-print_format', 'json', '-show_format', path],
                              capture_output=True, text=True, timeout=10)
            d = json.loads(r.stdout)['format']['duration']
            words = len(text.split())
            print(f"{desc:25s} | words={words:2d} | dur={float(d):.2f}s | {(float(d)/max(words,1)):.2f}s/word")
        else:
            print(f"{desc:25s} | ❌ FAILED")

asyncio.run(test())
