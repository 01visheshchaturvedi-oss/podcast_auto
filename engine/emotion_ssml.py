"""
Emotion-Aware SSML Generator for Hindi Podcasts
Analyzes text content and generates context-appropriate SSML prosody

Maps Hindi emotional cues, sentence types, and discourse patterns
to pitch, rate, volume, and emphasis parameters for natural speech.
"""

import re
from typing import Dict, List, Optional, Tuple

# ── Pitch Reference ───────────────────────────────────────────────
# Microsoft Hindi TTS baseline:
#   Male (hi-IN-MadhurNeural): natural pitch ~160-180Hz
#   Female (hi-IN-SwaraNeural): natural pitch ~220-260Hz

# ── Emotion Keyword Detection (Hindi + English mix) ────────────────

# Excitement / high-energy markers
EXCITED_PATTERNS = [
    r'\bवाओ\b', r'\bवाह\b', r'\bग्रेट\b', r'\bब्रिलियंट\b',
    r'\bपरफेक्ट\b', r'\bएक्सैक्टली\b', r'\bएग्जैक्टली\b',
    r'\bहिस्टोरिक\b', r'\bमैसिव\b', r'\bह्यूज\b',
    r'\bक्या बात\b', r'\bबहुत ही\b', r'\bबेहद\b',
    r'\bज़बरदस्त\b', r'\bशानदार\b', r'\bगज़ब\b',
    r'\bसक्सेसफुली\b', r'\bलैंडमार्क\b',
    r'\bवाओ\b', r'\bओह\b',
    r'\bअब्सोलुटली\b', r'\bबिल्कुल सही\b',
]

# Question markers
QUESTION_PATTERNS = [
    r'\?', r'\bक्या\b', r'\bक्यों\b', r'\bकैसे\b', r'\bकहाँ\b',
    r'\bकब\b', r'\bकौन\b', r'\bकितना\b', r'\bकितने\b',
    r'\bहै ना\b', r'\bराइट\b\?', r'\bहै न\b', r'\bन?\b$',
    r'\bसमझे\b', r'\bसमझिए\b', r'\bपता है\b',
]

# Emphasis / importance markers
EMPHASIS_PATTERNS = [
    r'\bसबसे बड़ा\b', r'\bसबसे ज़रूरी\b', r'\bमेन\b',
    r'\bक्रूशियल\b', r'\bइंपॉर्टेंट\b', r'\bजरूरी\b',
    r'\bध्यान दें\b', r'\bयाद रखें\b', r'\bगौर करें\b',
    r'\bबिल्कुल\b', r'\bबेसिक\b', r'\bक्लियर\b',
    r'\bमिनिमम\b', r'\bकम से कम\b',
    r'\bगारंटी\b', r'\bसॉलिड\b', r'\bस्ट्रांग\b',
    r'\bज़ीरो\b', r'\bएकदम\b',
]

# Serious / analytical markers
SERIOUS_PATTERNS = [
    r'\bदेखिए\b', r'\bसमझिए\b', r'\bअसल में\b',
    r'\bएक्चुअली\b', r'\bटेक्निकल\b',
    r'\bकॉम्प्लेक्स\b', r'\bएनालिसिस\b', r'\bडीप डाइव\b',
    r'\bगहराई\b', r'\bगहन\b', r'\bडिटेल्ड\b',
    r'\bलॉजिक\b', r'\bफंडा\b', r'\bकॉन्सेप्ट\b',
]

# Transition / connector markers (normal conversational)
TRANSITION_PATTERNS = [
    r'\bचलिए\b', r'\bतो\b', r'\bअब\b', r'\bवैसे\b',
    r'\bहालांकि\b', r'\bलेकिन\b', r'\bपर\b',
    r'\bहाँ\b', r'\bहां\b', r'\bजी हां\b',
    r'\bवेलकम\b', r'\bआपका स्वागत\b',
]

# Quick affirmation markers
AFFIRMATION_PATTERNS = [
    r'^(हाँ|हां|हम|हूं|जी|राइट\?|हम्म|अच्छा|आई सी|मेक सेंस|मेक्स सेंस)$',
    r'\bहाँ\b', r'\bहां\b', r'\bहम्म\b',
    r'\bराइट\b\??$', r'\bटोटल सेंस\b',
]

# Call-to-action / quiz markers (engaging, energetic)
QUIZ_PATTERNS = [
    r'\bसवाल\b', r'\bक्विज\b', r'\bटेस्ट\b',
    r'\bकितना याद\b', r'\bसेल्फ असेसमेंट\b',
    r'\bरैपिड फायर\b', r'\bमेंटल चेक\b',
    r'\bबताइए\b', r'\bजवाब\b', r'\bउत्तर\b',
]


def detect_emotion(text: str) -> Dict[str, float]:
    """
    Analyze text for emotional/prosodic markers.
    Returns scores for: excitement, questioning, emphasis, seriousness, transition, affirmation, quiz
    """
    scores = {
        'excitement': 0.0,
        'question': 0.0,
        'emphasis': 0.0,
        'serious': 0.0,
        'transition': 0.0,
        'affirmation': 0.0,
        'quiz': 0.0,
    }

    lower = text.lower().strip()
    words = len(text.split())
    if words == 0:
        return scores

    # Check each pattern category
    for pattern in EXCITED_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['excitement'] += 1.0

    for pattern in QUESTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['question'] += 1.0

    for pattern in EMPHASIS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['emphasis'] += 1.0

    for pattern in SERIOUS_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['serious'] += 1.0

    for pattern in TRANSITION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['transition'] += 0.5

    for pattern in AFFIRMATION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['affirmation'] += 1.0

    for pattern in QUIZ_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            scores['quiz'] += 1.5

    # Normalize by text length
    for key in scores:
        scores[key] = min(scores[key], 3.0)  # Cap at 3

    # Short texts get different treatment
    if words <= 3:
        # Short affirmations should be natural, not emphasized
        if scores['affirmation'] > 0:
            scores['affirmation'] = min(scores['affirmation'], 1.5)

    return scores


def get_ssml_params(emotion_scores: Dict[str, float], role: str, text: str) -> Dict[str, str]:
    """
    Convert emotion scores to SSML parameters.
    Returns dict with: pitch, rate, volume, emphasis_words, style
    """
    params = {
        'pitch': '0%',       # Default: no pitch change
        'rate': '0%',        # Default: normal rate
        'volume': '+0dB',    # Default: normal volume
        'emphasis_count': 0,
    }

    # Base rate depends on role
    if role == 'female':
        base_rate = '+5%'   # Slightly faster for female
    else:
        base_rate = '+0%'

    # ── Excitement → higher pitch, faster, louder ──
    if emotion_scores['excitement'] >= 2:
        params['pitch'] = '+60Hz'
        params['rate'] = '+18%'
        params['volume'] = '+4dB'
    elif emotion_scores['excitement'] >= 1:
        params['pitch'] = '+30Hz'
        params['rate'] = '+10%'
        params['volume'] = '+2dB'

    # ── Question → rising pitch at end ──
    if emotion_scores['question'] >= 1:
        params['pitch'] = '+40Hz' if params['pitch'] == '0%' else '+50Hz'
        params['rate'] = '+5%' if params['rate'] == '0%' else '+8%'

    # ── Emphasis → slower, slightly louder ──
    if emotion_scores['emphasis'] >= 2:
        params['rate'] = '-8%'
        params['volume'] = '+3dB'
        params['pitch'] = '+20Hz'
    elif emotion_scores['emphasis'] >= 1:
        if params['rate'] == '0%':
            params['rate'] = '-5%'
        params['volume'] = '+2dB'

    # ── Serious → slower, lower pitch ──
    if emotion_scores['serious'] >= 2:
        params['pitch'] = '-30Hz'
        params['rate'] = '-12%'
        params['volume'] = '+1dB'
    elif emotion_scores['serious'] >= 1:
        if params['pitch'] == '0%':
            params['pitch'] = '-15Hz'
        params['rate'] = '-8%'

    # ── Quiz → energetic, engaging, faster ──
    if emotion_scores['quiz'] >= 1:
        params['pitch'] = '+40Hz' if params['pitch'] == '0%' else '+45Hz'
        params['rate'] = '+15%'

    # ── Affirmation → gentle, lower ──
    if emotion_scores['affirmation'] >= 1:
        if params.get('pitch') == '0%':
            params['pitch'] = '-5Hz'
        params['volume'] = '+1dB'

    # ── Transition → neutral, slight energy ──
    if emotion_scores['transition'] >= 1 and params['rate'] == '0%':
        params['rate'] = '+5%'

    # ── Override: very short texts (< 3 words) stay natural ──
    words = len(text.split())
    if words <= 3 and emotion_scores['excitement'] < 2:
        params['pitch'] = '0%'
        if params['rate'] not in ('0%', '+5%'):
            params['rate'] = '+3%'

    # Apply base rate from role on top
    # We only apply base rate if no strong emotional override
    if emotion_scores['excitement'] < 1 and emotion_scores['quiz'] < 1:
        if base_rate != '0%' and params['rate'] == '0%':
            params['rate'] = base_rate

    return params


def wrap_in_ssml(text: str, voice: str, params: Dict[str, str], rate: str = '+0%') -> str:
    """
    Wrap text in full SSML with emotional prosody.
    """
    # Clean text for SSML (escape XML special chars)
    text_clean = (text
                  .replace('&', '&amp;')
                  .replace('<', '&lt;')
                  .replace('>', '&gt;')
                  .replace('"', '&quot;')
                  .replace("'", '&apos;'))

    pitch = params.get('pitch', '0%')
    volume = params.get('volume', '+0dB')
    speech_rate = params.get('rate', '0%')

    ssml = f"""<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis"
             xmlns:mstts="http://www.w3.org/2001/mstts" xml:lang="hi-IN">
    <voice name="{voice}">
        <prosody pitch="{pitch}" rate="{speech_rate}" volume="{volume}">
            {text_clean}
        </prosody>
    </voice>
</speak>"""

    return ssml


def analyze_script_for_emotions(script: List[Dict]) -> List[Dict]:
    """
    Analyze entire script and enrich each turn with emotion data.
    Also adds pause recommendations between speakers.
    """
    enriched = []
    for i, turn in enumerate(script):
        text = turn['text']
        role = turn['role']

        emotion = detect_emotion(text)
        ssml_params = get_ssml_params(emotion, role, text)

        enriched_turn = {
            **turn,
            'emotion': emotion,
            'ssml_params': ssml_params,
        }

        # Determine pause after this turn
        if i < len(script) - 1:
            next_role = script[i + 1]['role']
            if next_role != role:
                # Speaker change - add break
                enriched_turn['break_after'] = '500ms'
            else:
                # Same speaker continues
                enriched_turn['break_after'] = '300ms'
        else:
            enriched_turn['break_after'] = '1000ms'

        enriched.append(enriched_turn)

    return enriched


# ── Test / Demo ────────────────────────────────────────────────────
if __name__ == "__main__":
    test_texts = [
        ("Female", "वाओ दैट्स अ बिग चेंज। और एक चीज हाईलाइट करना चाहूंगी।"),
        ("Male", "देखिए, यह ग्राउंड लेवल पर समझना बहुत जरूरी है।"),
        ("Female", "सवाल एक। शुगरकेन का एफआरपी क्या सेट हुआ है?"),
        ("Male", "हाँ, एकदम सही पकड़ा।"),
        ("Female", "तो यह तो वही बात हुई ना?"),
        ("Male", "बिल्कुल बिल्कुल सही पकड़ा। यह एनालॉजी यहां बिल्कुल फिट बैठती है।"),
    ]

    for role, text in test_texts:
        emotion = detect_emotion(text)
        params = get_ssml_params(emotion, role, text)
        print(f"\n[{role}] {text}")
        print(f"  Emotion: {emotion}")
        print(f"  SSML: pitch={params['pitch']}, rate={params['rate']}, vol={params['volume']}")
