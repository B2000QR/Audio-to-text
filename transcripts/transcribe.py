"""Transcribe an audio file with faster-whisper and flag low-confidence segments.

Usage:
    python transcripts/transcribe.py path/to/audio.m4a [--model small] [--language en]

Writes <stem>_transcript.md next to this script, with timestamps per segment and
a list of segments that look unreliable (low log-probability, likely silence
or noise, or repetitive/hallucinated output).
"""

import argparse
import time
from pathlib import Path

from faster_whisper import WhisperModel

# Heuristics mirroring Whisper's own fallback thresholds.
LOW_LOGPROB = -1.0
HIGH_NO_SPEECH = 0.6
HIGH_COMPRESSION = 2.4
LOW_WORD_PROB = 0.4


def ts(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600:02d}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}"


def flag_reasons(seg) -> list:
    reasons = []
    if seg.avg_logprob < LOW_LOGPROB:
        reasons.append(f"low confidence (avg_logprob {seg.avg_logprob:.2f})")
    if seg.no_speech_prob > HIGH_NO_SPEECH:
        reasons.append(f"possible silence/noise (no_speech {seg.no_speech_prob:.2f})")
    if seg.compression_ratio > HIGH_COMPRESSION:
        reasons.append(f"repetitive text (compression {seg.compression_ratio:.2f})")
    if seg.words:
        weak = [w.word.strip() for w in seg.words if w.probability < LOW_WORD_PROB]
        if len(weak) >= max(3, len(seg.words) // 3):
            reasons.append("many uncertain words: " + ", ".join(weak[:8]))
    return reasons


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("audio")
    parser.add_argument("--model", default="small")
    parser.add_argument("--language", default=None)
    parser.add_argument("--out-dir", default=str(Path(__file__).parent))
    args = parser.parse_args()

    audio = Path(args.audio)
    out = Path(args.out_dir) / f"{audio.stem}_transcript.md"

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    start = time.time()
    segments, info = model.transcribe(
        str(audio),
        language=args.language,
        beam_size=5,
        vad_filter=True,
        word_timestamps=True,
    )

    lines, flagged = [], []
    for seg in segments:
        text = seg.text.strip()
        reasons = flag_reasons(seg)
        marker = " ⚠️" if reasons else ""
        lines.append(f"**[{ts(seg.start)} → {ts(seg.end)}]**{marker} {text}")
        if reasons:
            flagged.append((seg, text, reasons))
        print(f"[{ts(seg.start)}] {text}", flush=True)

    elapsed = time.time() - start
    with out.open("w") as f:
        f.write(f"# Transcript: {audio.name}\n\n")
        f.write(f"- Model: faster-whisper `{args.model}` (int8, CPU), VAD on\n")
        f.write(
            f"- Detected language: {info.language} "
            f"(p={info.language_probability:.2f})\n"
        )
        f.write(f"- Audio duration: {ts(info.duration)}\n")
        f.write(f"- Processing time: {elapsed / 60:.1f} min\n")
        f.write(f"- Segments: {len(lines)}, flagged low-confidence: {len(flagged)}\n\n")
        f.write("Segments marked ⚠️ are listed under Low-confidence sections at the end.\n\n")
        f.write("## Transcript\n\n")
        f.write("\n\n".join(lines))
        f.write("\n\n## Low-confidence sections\n\n")
        if not flagged:
            f.write("None detected.\n")
        for seg, text, reasons in flagged:
            f.write(f"- **[{ts(seg.start)} → {ts(seg.end)}]** \"{text}\"\n")
            f.write(f"  - {'; '.join(reasons)}\n")
    print(f"\nWrote {out} ({len(flagged)} flagged segments, {elapsed / 60:.1f} min)")


if __name__ == "__main__":
    main()
