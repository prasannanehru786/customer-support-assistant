from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from backend.support_app.config import AUDIO_DIR, ensure_runtime_dirs
from backend.support_app.models import VoiceTranscript


def transcribe_audio(audio_file: Any) -> VoiceTranscript:
    if not audio_file:
        return VoiceTranscript()
    ensure_runtime_dirs()
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False, dir=AUDIO_DIR) as temp_file:
        temp_file.write(audio_file.getvalue())
        temp_path = Path(temp_file.name)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return VoiceTranscript(
            error="Voice was recorded, but faster-whisper is not installed in this environment."
        )

    model_name = os.getenv("WHISPER_MODEL", "tiny")
    try:
        model = WhisperModel(model_name, device=os.getenv("WHISPER_DEVICE", "cpu"), compute_type="int8")
        segments, _info = model.transcribe(str(temp_path), beam_size=1)
    except Exception as exc:
        return VoiceTranscript(error=f"Voice transcription failed: {exc}")
    transcript = " ".join(segment.text.strip() for segment in segments).strip()
    if not transcript:
        return VoiceTranscript(error="No speech was detected in the recording.")
    return VoiceTranscript(text=transcript)


def synthesize_speech(text: str, run_id: str) -> Path | None:
    if os.getenv("ENABLE_VOICE", "false").lower() != "true":
        return None
    ensure_runtime_dirs()
    output_path = AUDIO_DIR / f"{run_id}.wav"
    speech_text = text[:1500]
    piper = shutil.which("piper")
    voice_model = os.getenv("PIPER_VOICE_MODEL")
    if piper and voice_model:
        process = subprocess.run(
            [piper, "--model", voice_model, "--output_file", str(output_path)],
            input=speech_text,
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode == 0 and output_path.exists():
            return output_path

    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    if espeak:
        process = subprocess.run(
            [espeak, "-w", str(output_path), speech_text],
            capture_output=True,
            check=False,
        )
        if process.returncode == 0 and output_path.exists():
            return output_path

    say = shutil.which("say")
    afconvert = shutil.which("afconvert")
    if say and afconvert:
        temp_dir = Path(tempfile.gettempdir())
        temp_aiff = temp_dir / f"{run_id}.aiff"
        temp_wav = temp_dir / f"{run_id}.wav"
        try:
            say_process = subprocess.run(
                [say, "-o", str(temp_aiff), speech_text],
                capture_output=True,
                check=False,
            )
            if say_process.returncode != 0 or not temp_aiff.exists():
                return None
            convert_process = subprocess.run(
                [afconvert, "-f", "WAVE", "-d", "LEI16", str(temp_aiff), str(temp_wav)],
                capture_output=True,
                check=False,
            )
            if convert_process.returncode == 0 and temp_wav.exists():
                try:
                    shutil.copyfile(temp_wav, output_path)
                    if output_path.exists():
                        return output_path
                except OSError:
                    return temp_wav
        finally:
            temp_aiff.unlink(missing_ok=True)
            if temp_wav != output_path and not output_path.exists():
                pass
            else:
                temp_wav.unlink(missing_ok=True)
    return None
