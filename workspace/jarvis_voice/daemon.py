import os
import re
import string
import tempfile
import threading
import wave
import winsound
from collections import deque
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")

import espeakng_loader
import numpy as np
import sherpa_onnx
import sounddevice as sd
from faster_whisper import WhisperModel
from phonemizer import phonemize
from phonemizer.backend.espeak.wrapper import EspeakWrapper

import openjarvis.tools  # noqa: F401
from openjarvis.core.config import load_config
from openjarvis.system.builder import SystemBuilder

EspeakWrapper.set_library(espeakng_loader.get_library_path())
EspeakWrapper.set_data_path(espeakng_loader.get_data_path())

SAMPLE_RATE = 16000
BLOCK_SIZE = 1600  # 100 ms
WAKE_RE = re.compile(r"\b(джарвис|джарвиз|джервис|jarvis)\b", re.I)
NOISE_PHRASES = {
    "thank you",
    "thanks for watching",
    "you",
    "go",
    "work",
    "bye",
    "продолжение следует",
}
_PUNCT_TABLE = str.maketrans("", "", string.punctuation + "«»—–…")

BASE_DIR = Path(__file__).resolve().parent
PERSONA_PATH = BASE_DIR / "voice_persona.md"
MODEL_DIR = BASE_DIR / "tts_model_ruslan"


def _to_phoneme_text(value: object) -> str:
    """Преобразует результат phonemize (str, list или tuple) в единую строку."""
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        parts = [_to_phoneme_text(item) for item in value]
        return " ".join(part for part in parts if part)
    return str(value) if value is not None else ""


def normalize_phrase(text: str) -> str:
    cleaned = text.lower().translate(_PUNCT_TABLE)
    return re.sub(r"\s+", " ", cleaned).strip()


def clean_for_speech(raw: str) -> str:
    txt = re.sub(r"```[\s\S]*?```", " Код записан в файл. ", raw)
    txt = re.sub(r"`([^`]+)`", r"\1", txt)
    txt = re.sub(r"[#*_~>|{}\[\]]+", " ", txt)
    txt = re.sub(r"https?://\S+", "ссылка", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt


def extract_reply_text(result: object) -> str:
    if isinstance(result, dict):
        return str(result.get("content") or result.get("response") or "").strip()
    for attr in ("content", "response"):
        val = getattr(result, attr, None)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return str(result).strip()


class RuslanSpeaker:
    def __init__(self, model_dir: Path = MODEL_DIR) -> None:
        self.speaking = threading.Event()
        model_path = (model_dir / "ru_RU-ruslan-medium.onnx").resolve()
        tokens_path = (model_dir / "tokens.txt").resolve()
        if not model_path.is_file() or not tokens_path.is_file():
            raise FileNotFoundError(
                f"Не найдены файлы модели TTS в {model_dir}: "
                f"model={model_path.exists()}, tokens={tokens_path.exists()}"
            )

        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=str(model_path),
                    tokens=str(tokens_path),
                ),
                provider="cpu",
                num_threads=4,
            )
        )
        self.tts = sherpa_onnx.OfflineTts(cfg)

    def speak(self, raw: str) -> None:
        spoken = clean_for_speech(raw)
        if not spoken:
            return
        self.speaking.set()
        try:
            ipa_raw = phonemize(
                spoken,
                language="ru",
                backend="espeak",
                strip=True,
                preserve_punctuation=True,
                with_stress=True,
            )
            ipa_text = _to_phoneme_text(ipa_raw)
            if not ipa_text:
                return

            gen_cfg = sherpa_onnx.GenerationConfig()
            gen_cfg.sid = 0
            gen_cfg.speed = 1.02
            gen_cfg.phoneme_codepoints = [[ord(ch) for ch in ipa_text]]

            audio = self.tts.generate("ok", config=gen_cfg)
            if not audio.samples or audio.sample_rate <= 0:
                return

            samples = np.clip(np.array(audio.samples, dtype=np.float32), -1.0, 1.0)
            pcm16 = (samples * 32767).astype(np.int16)

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = Path(tmp.name)
            try:
                with wave.open(str(wav_path), "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(audio.sample_rate)
                    wf.writeframes(pcm16.tobytes())
                winsound.PlaySound(str(wav_path.resolve()), winsound.SND_FILENAME)
            finally:
                wav_path.unlink(missing_ok=True)
        finally:
            self.speaking.clear()


def measure_noise_threshold(sample_rate: int, block_size: int) -> float:
    with sd.InputStream(
        samplerate=sample_rate, channels=1, dtype="float32", blocksize=block_size
    ) as stream:
        levels = [
            float(np.sqrt(np.mean(stream.read(block_size)[0] ** 2))) for _ in range(10)
        ]
    noise = float(np.mean(levels)) if levels else 0.0
    return max(noise * 4.0, 0.025)


def main() -> None:
    print("[Jarvis Voice] Загрузка мужского голоса Ruslan и STT small...")
    speaker = RuslanSpeaker()
    stt = WhisperModel("small", device="cpu", compute_type="int8")

    cfg = load_config()
    cfg.tools.mcp.enabled = False
    system = (
        SystemBuilder(cfg)
        .engine("lmstudio")
        .model("google/gemma-4-12b")
        .agent("orchestrator")
        .tools(["file_read", "file_write", "shell_exec", "think"])
        .build()
    )
    voice_prompt = (
        PERSONA_PATH.read_text(encoding="utf-8") if PERSONA_PATH.exists() else ""
    )

    thresh = measure_noise_threshold(SAMPLE_RATE, BLOCK_SIZE)
    print(
        f"[Jarvis Voice] Готов (порог={thresh:.4f}). "
        "Скажите: «Джарвис, ...» (Ctrl+C — выход)"
    )
    speaker.speak("Все системы в сети, сэр. Жду ваших указаний.")

    pre_roll: deque[np.ndarray] = deque(maxlen=4)
    frames: list[np.ndarray] = []
    recording = False
    silence_sec = 0.0
    step_sec = BLOCK_SIZE / SAMPLE_RATE

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=BLOCK_SIZE,
        ) as stream:
            while True:
                data, _ = stream.read(BLOCK_SIZE)
                chunk = data[:, 0].copy()

                if speaker.speaking.is_set():
                    pre_roll.clear()
                    frames.clear()
                    recording = False
                    silence_sec = 0.0
                    continue

                rms = float(np.sqrt(np.mean(chunk**2)))
                if not recording:
                    pre_roll.append(chunk)
                    if rms > thresh:
                        recording = True
                        frames = list(pre_roll)
                        silence_sec = 0.0
                else:
                    frames.append(chunk)
                    if rms > thresh:
                        silence_sec = 0.0
                    else:
                        silence_sec += step_sec

                    dur = len(frames) * step_sec
                    if silence_sec >= 1.0 or dur >= 20.0:
                        audio = np.concatenate(frames)
                        frames.clear()
                        pre_roll.clear()
                        recording = False
                        silence_sec = 0.0

                        if dur < 0.7:
                            continue

                        segs, _ = stt.transcribe(
                            audio,
                            language="ru",
                            beam_size=2,
                            vad_filter=True,
                            vad_parameters={
                                "min_silence_duration_ms": 450,
                                "threshold": 0.65,
                            },
                            condition_on_previous_text=False,
                            initial_prompt="Джарвис, открой, закрой, создай проект.",
                        )
                        segments = list(segs)
                        text = " ".join(
                            s.text.strip()
                            for s in segments
                            if getattr(s, "no_speech_prob", 0.0) <= 0.35
                            and getattr(s, "avg_logprob", 0.0) >= -0.95
                        ).strip()
                        if not text or normalize_phrase(text) in NOISE_PHRASES:
                            continue

                        print(f"[Вы]: {text}")
                        match = WAKE_RE.search(text)
                        if not match:
                            continue

                        cmd = (
                            text[match.end() :].lstrip(" ,.!?:;-")
                            or "Коротко подтверди готовность в одном предложении."
                        )
                        print(f"[Команда]: {cmd}")
                        try:
                            raw_res = system.ask(cmd, system_prompt=voice_prompt)
                        except Exception as exc:
                            print(f"[Jarvis Voice] Ошибка агента: {exc}")
                            speaker.speak("Извините, произошла ошибка при обработке.")
                            continue

                        reply = extract_reply_text(raw_res) or "Готово, сэр."
                        print(f"[Джарвис]: {reply}")
                        speaker.speak(reply)
    except KeyboardInterrupt:
        print("\n[Jarvis Voice] Остановка голосового контура.")


if __name__ == "__main__":
    main()
