import io
import re
import threading
import wave
import winsound
from pathlib import Path
from typing import Optional

import espeakng_loader
import numpy as np
import sherpa_onnx
from phonemizer import phonemize
from phonemizer.backend.espeak.wrapper import EspeakWrapper


class JarvisTTS:
    """Локальный офлайн-синтезатор речи для OpenJarvis (sherpa-onnx + phonemizer)."""

    _espeak_initialized = False
    _init_lock = threading.Lock()

    def __init__(
        self,
        model_dir: str | Path = "workspace/jarvis_voice/tts_model",
        model_name: str = "ru_RU-dmitri-medium.onnx",
        tokens_name: str = "tokens.txt",
        num_threads: int = 4,
        speed: float = 1.05,
        silence_scale: float = 0.25,
    ) -> None:
        self.model_dir = Path(model_dir)
        self.speed = speed
        self._speak_lock = threading.Lock()

        self._init_espeak()

        model_path = (self.model_dir / model_name).resolve()
        tokens_path = (self.model_dir / tokens_name).resolve()

        if not model_path.exists() or not tokens_path.exists():
            raise FileNotFoundError(
                f"Файлы модели не найдены в {self.model_dir}. "
                f"Проверьте наличие {model_name} и {tokens_name}."
            )

        cfg = sherpa_onnx.OfflineTtsConfig(
            model=sherpa_onnx.OfflineTtsModelConfig(
                vits=sherpa_onnx.OfflineTtsVitsModelConfig(
                    model=str(model_path),
                    tokens=str(tokens_path),
                ),
                provider="cpu",
                num_threads=num_threads,
            ),
            silence_scale=silence_scale,
        )
        self.tts = sherpa_onnx.OfflineTts(cfg)

    @classmethod
    def _init_espeak(cls) -> None:
        with cls._init_lock:
            if not cls._espeak_initialized:
                EspeakWrapper.set_library(espeakng_loader.get_library_path())
                EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
                cls._espeak_initialized = True

    @staticmethod
    def _clean_text(text: str) -> str:
        """Удаляет блоки кода, ссылки и Markdown-символы перед озвучиванием."""
        text = re.sub(r"```[\s\S]*?```", " блок кода опущен. ", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
        text = re.sub(r"[*_#~>|]+", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Разбивает текст на предложения для корректных интонационных пауз."""
        parts = re.split(r"(?<=[.!?…])\s+", text)
        return [p.strip() for p in parts if p.strip()]

    def synthesize_wav_bytes(
        self, text: str, speed: Optional[float] = None, sid: int = 0
    ) -> bytes:
        """Генерирует WAV-поток в памяти (bytes) без записи на диск."""
        cleaned = self._clean_text(text)
        if not cleaned:
            return b""

        sentences = self._split_sentences(cleaned)
        ipa_sentences = phonemize(
            sentences,
            language="ru",
            backend="espeak",
            strip=True,
            preserve_punctuation=True,
            with_stress=True,
        )

        codepoints: list[list[int]] = []
        for ipa in ipa_sentences:
            ipa_str = " ".join(ipa) if isinstance(ipa, tuple) else str(ipa)
            if ipa_str.strip():
                codepoints.append([ord(ch) for ch in ipa_str])

        if not codepoints:
            return b""

        gen_cfg = sherpa_onnx.GenerationConfig()
        gen_cfg.sid = sid
        gen_cfg.speed = speed if speed is not None else self.speed
        gen_cfg.phoneme_codepoints = codepoints

        # Заглушка с тем же числом предложений для синхронизации пауз
        dummy_text = " ".join(["a."] * len(codepoints))
        audio = self.tts.generate(dummy_text, config=gen_cfg)

        if not audio.samples or audio.sample_rate <= 0:
            return b""

        pcm = (
            np.clip(np.array(audio.samples, dtype=np.float32), -1.0, 1.0) * 32767
        ).astype(np.int16)

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(audio.sample_rate)
            wf.writeframes(pcm.tobytes())

        return buf.getvalue()

    def speak(
        self, text: str, speed: Optional[float] = None, block: bool = True
    ) -> None:
        """Озвучивает текст напрямую из RAM. При block=False не блокирует поток."""
        wav_bytes = self.synthesize_wav_bytes(text, speed=speed)
        if not wav_bytes:
            return

        def _play() -> None:
            with self._speak_lock:
                # SND_MEMORY воспроизводит буфер из памяти; требуется синхронный режим
                winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)

        if block:
            _play()
        else:
            threading.Thread(target=_play, daemon=True).start()

    def stop(self) -> None:
        """Мгновенно прерывает текущее воспроизведение."""
        winsound.PlaySound(None, winsound.SND_PURGE)


if __name__ == "__main__":
    jarvis = JarvisTTS()
    jarvis.speak(
        "Системы OpenJarvis инициализированы, сэр. "
        "Синтез речи работает напрямую из оперативной памяти. "
        "Жду ваших указаний."
    )
