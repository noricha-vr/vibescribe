"""音声文字起こしモジュール。

Gemini API (google.genai) に音声を直接入力して文字起こしする。
"""

import logging
import os
import re
import time
from pathlib import Path

import google.genai as genai
import google.genai.types as genai_types

from postprocessor import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


TRANSCRIBE_PROMPT = (
    "この音声を日本語で、省略せずに文字起こししてください。"
)


def _format_timed_log(label: str, elapsed_seconds: float, message: str) -> str:
    """処理時間付きログを見やすい形式で整形する。"""
    return f"[{label} {elapsed_seconds:.2f}s] {message}"


class Transcriber:
    """音声文字起こしクラス。"""

    MODEL = "gemini-2.5-flash"
    MODEL_ENV_VAR = "VOICECODE_GEMINI_MODEL"
    THINKING_LEVEL_ENV_VAR = "VOICECODE_THINKING_LEVEL"
    ENABLE_PROMPT_CACHE_ENV_VAR = "VOICECODE_ENABLE_PROMPT_CACHE"
    PROMPT_CACHE_TTL_ENV_VAR = "VOICECODE_PROMPT_CACHE_TTL"
    DEFAULT_THINKING_LEVEL = "minimal"
    DEFAULT_PROMPT_CACHE_TTL = "3600s"
    MODEL_ALIASES = {
        # 旧命名を受け取った場合でも実在モデルへ寄せる
        "gemini-3.0-flash": "gemini-3-flash-preview",
    }
    PREFERRED_MODELS = (
        "gemini-3-flash-preview",
        MODEL,
        "gemini-2.0-flash",
        "gemini-flash-latest",
    )
    TIMEOUT = 10.0
    MAX_TRANSIENT_RETRIES = 1
    RETRY_BACKOFF_SECONDS = 0.3

    _THINKING_LEVEL_MAP = {
        "minimal": genai_types.ThinkingLevel.MINIMAL,
        "low": genai_types.ThinkingLevel.LOW,
        "medium": genai_types.ThinkingLevel.MEDIUM,
        "high": genai_types.ThinkingLevel.HIGH,
    }

    def __init__(self, api_key: str | None = None):
        """Transcriberを初期化する。

        Args:
            api_key: Google APIキー。Noneの場合は環境変数から取得。

        Raises:
            ValueError: APIキーが設定されていない場合。
        """
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY is not set")

        self._client = self._create_client()
        self._system_prompt = self._build_system_prompt()
        self._thinking_level = self._resolve_thinking_level()
        self._thinking_mode = "level"  # level / budget0
        self._enable_prompt_cache = self._resolve_prompt_cache_enabled()
        self._prompt_cache_ttl = os.getenv(self.PROMPT_CACHE_TTL_ENV_VAR, self.DEFAULT_PROMPT_CACHE_TTL)
        self._prompt_cache_name_by_model: dict[str, str] = {}

        self._model_name = self._resolve_model_name()
        self._ensure_prompt_cache(self._model_name)
        logger.info(f"[Gemini] 使用モデル: {self._model_name}")
        logger.info(f"[Gemini] Thinking mode: {self._thinking_mode} ({self._thinking_level.name})")

    def _create_client(self):
        """Gemini API クライアントを生成する。"""
        return genai.Client(api_key=self._api_key)

    @staticmethod
    def _build_system_prompt() -> str:
        """システムプロンプトを構築する。"""
        return SYSTEM_PROMPT

    def _resolve_thinking_level(self) -> genai_types.ThinkingLevel:
        """Thinking level 設定を解決する。"""
        raw_level = os.getenv(self.THINKING_LEVEL_ENV_VAR, self.DEFAULT_THINKING_LEVEL).strip().lower()
        level = self._THINKING_LEVEL_MAP.get(raw_level)
        if level:
            return level

        logger.warning(
            f"[Gemini] 無効な thinking level のため {self.DEFAULT_THINKING_LEVEL} を使用します: {raw_level}"
        )
        return self._THINKING_LEVEL_MAP[self.DEFAULT_THINKING_LEVEL]

    def _resolve_prompt_cache_enabled(self) -> bool:
        """プロンプトキャッシュ有効化フラグを解決する。"""
        raw = os.getenv(self.ENABLE_PROMPT_CACHE_ENV_VAR, "true").strip().lower()
        return raw not in {"0", "false", "off", "no"}

    @staticmethod
    def _extract_response_text(response: object) -> str:
        """Geminiレスポンスからテキストを抽出する。"""
        direct_text = getattr(response, "text", "")
        if isinstance(direct_text, str) and direct_text:
            return direct_text

        candidates = getattr(response, "candidates", None)
        if not candidates:
            return ""

        parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            if content is None:
                continue
            content_parts = getattr(content, "parts", None)
            if not content_parts:
                continue
            for part in content_parts:
                part_text = getattr(part, "text", None)
                if isinstance(part_text, str):
                    parts.append(part_text)
        return "".join(parts)

    @classmethod
    def _normalize_model_name(cls, model_name: str) -> str:
        """モデル名から先頭の `models/` を除去する。"""
        normalized = model_name.removeprefix("models/").strip()
        return cls.MODEL_ALIASES.get(normalized, normalized)

    @classmethod
    def _build_model_candidates(cls) -> list[str]:
        """候補モデル名リストを構築する。"""
        configured_model = os.getenv(cls.MODEL_ENV_VAR, "").strip()
        candidates: list[str] = []

        if configured_model:
            candidates.append(cls._normalize_model_name(configured_model))

        for model_name in cls.PREFERRED_MODELS:
            if model_name not in candidates:
                candidates.append(model_name)

        return candidates

    def _client_list_models(self):
        """利用可能モデル一覧を取得する。"""
        return list(self._client.models.list())

    def _list_available_models(self) -> list[str]:
        """generateContent に対応した利用可能モデル名一覧を返す。"""
        available_models: list[str] = []
        for model in self._client_list_models():
            actions = getattr(model, "supported_actions", None) or []
            if "generateContent" not in actions:
                continue

            model_name = getattr(model, "name", "")
            if isinstance(model_name, str) and model_name:
                available_models.append(self._normalize_model_name(model_name))

        return available_models

    def _resolve_model_name(self, exclude: set[str] | None = None) -> str:
        """実行時に利用するモデル名を解決する。"""
        excluded_models = exclude or set()
        candidates = self._build_model_candidates()
        configured_model = os.getenv(self.MODEL_ENV_VAR, "").strip()
        configured_model = self._normalize_model_name(configured_model) if configured_model else ""

        try:
            available_models = self._list_available_models()
        except Exception as e:
            if configured_model and configured_model not in excluded_models:
                logger.warning(
                    f"[Gemini] モデル一覧取得に失敗したため環境変数モデルを使用します: {configured_model} ({e})"
                )
                return configured_model

            if self.MODEL not in excluded_models:
                logger.warning(
                    f"[Gemini] モデル一覧取得に失敗したため既定モデルを使用します: {self.MODEL} ({e})"
                )
                return self.MODEL

            return ""

        for candidate in candidates:
            if candidate in available_models and candidate not in excluded_models:
                return candidate

        for available_model in available_models:
            if available_model not in excluded_models:
                logger.warning(f"[Gemini] 候補モデルが見つからないため利用可能モデルにフォールバックします: {available_model}")
                return available_model

        return ""

    @staticmethod
    def _is_model_not_found_error(error: Exception) -> bool:
        """モデル未検出エラーかどうか判定する。"""
        message = str(error).lower()
        return (
            "is not found for api version" in message
            or ("404" in message and "models/" in message and "not found" in message)
        )

    @staticmethod
    def _is_transient_api_error(error: Exception) -> bool:
        """一時的なAPIエラーかどうか判定する。"""
        message = str(error).lower()
        transient_patterns = (
            "deadline expired",
            "timed out",
            "timeout",
            "temporarily unavailable",
            "service unavailable",
        )
        has_http_hint = bool(re.search(r"\b(429|500|502|503|504)\b", message)) or "too many requests" in message
        return any(pattern in message for pattern in transient_patterns) or has_http_hint

    @staticmethod
    def _is_thinking_level_unsupported_error(error: Exception) -> bool:
        """thinking_level 非対応エラーかどうか判定する。"""
        message = str(error).lower()
        return "thinking level is not supported" in message

    def _build_generate_config(self) -> genai_types.GenerateContentConfig:
        """generate_content 用の設定を組み立てる。"""
        if self._thinking_mode == "level":
            thinking_config = genai_types.ThinkingConfig(thinking_level=self._thinking_level)
        else:
            # thinking_level 非対応モデル向けフォールバック
            thinking_config = genai_types.ThinkingConfig(thinking_budget=0)

        cached_content_name = self._prompt_cache_name_by_model.get(self._model_name)
        if cached_content_name:
            return genai_types.GenerateContentConfig(
                cached_content=cached_content_name,
                thinking_config=thinking_config,
                temperature=0.0,
            )

        return genai_types.GenerateContentConfig(
            system_instruction=self._system_prompt,
            thinking_config=thinking_config,
            temperature=0.0,
        )

    def _ensure_prompt_cache(self, model_name: str) -> None:
        """SYSTEM_PROMPT をキャッシュし、以後 cached_content を利用する。"""
        if not self._enable_prompt_cache:
            return

        if model_name in self._prompt_cache_name_by_model:
            return

        try:
            cache = self._client.caches.create(
                model=model_name,
                config=genai_types.CreateCachedContentConfig(
                    system_instruction=self._system_prompt,
                    ttl=self._prompt_cache_ttl,
                    display_name="vibescribe-system-prompt-cache",
                ),
            )
            cache_name = getattr(cache, "name", "")
            if isinstance(cache_name, str) and cache_name:
                self._prompt_cache_name_by_model[model_name] = cache_name
                logger.info(f"[Gemini] Prompt cache created: {cache_name} (model={model_name})")
        except Exception as e:
            logger.warning(f"[Gemini] Prompt cache unavailable. system_instruction fallback を使用します: {e}")

    def _client_generate_content(self, model: str, audio_data: bytes) -> object:
        """Gemini generate_content を呼び出す。"""
        return self._client.models.generate_content(
            model=model,
            contents=[
                TRANSCRIBE_PROMPT,
                genai_types.Part.from_bytes(data=audio_data, mime_type="audio/wav"),
            ],
            config=self._build_generate_config(),
        )

    def _generate_content(self, audio_data: bytes) -> object:
        """現在のモデルで文字起こしを実行する。"""
        return self._client_generate_content(self._model_name, audio_data)

    def _generate_content_with_retry(self, audio_data: bytes) -> object:
        """一時的なAPIエラー時に短いリトライを行う。"""
        last_error: Exception | None = None
        for attempt in range(self.MAX_TRANSIENT_RETRIES + 1):
            try:
                return self._generate_content(audio_data)
            except Exception as e:
                last_error = e

                if self._thinking_mode == "level" and self._is_thinking_level_unsupported_error(e):
                    self._thinking_mode = "budget0"
                    logger.warning("[Gemini] thinking_level 非対応モデルのため thinking_budget=0 に切替します")
                    return self._generate_content(audio_data)

                if not self._is_transient_api_error(e) or attempt >= self.MAX_TRANSIENT_RETRIES:
                    raise

                wait_seconds = self.RETRY_BACKOFF_SECONDS * (attempt + 1)
                logger.warning(
                    f"[Gemini] 一時的なAPIエラーのため再試行します({attempt + 1}/{self.MAX_TRANSIENT_RETRIES}): {e}"
                )
                time.sleep(wait_seconds)

        assert last_error is not None
        raise last_error

    def transcribe(self, audio_path: Path) -> tuple[str, float]:
        """音声ファイルを文字起こしする。"""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        with open(audio_path, "rb") as audio_file:
            audio_data = audio_file.read()

        start_time = time.time()

        try:
            response = self._generate_content_with_retry(audio_data)
        except Exception as e:
            if self._is_model_not_found_error(e) or self._is_transient_api_error(e):
                fallback_model = self._resolve_model_name(exclude={self._model_name})
                if fallback_model:
                    reason = (
                        "モデルが見つからないため"
                        if self._is_model_not_found_error(e)
                        else "一時的なAPIエラーのため"
                    )
                    logger.warning(
                        f"[Gemini] {reason}モデルを切替します: {self._model_name} -> {fallback_model}"
                    )
                    try:
                        self._model_name = fallback_model
                        self._ensure_prompt_cache(self._model_name)
                        response = self._generate_content_with_retry(audio_data)
                    except Exception as retry_error:
                        elapsed = time.time() - start_time
                        logger.error(
                            _format_timed_log(
                                "Gemini",
                                elapsed,
                                f"API呼び出しに失敗しました(model={self._model_name}): {retry_error}",
                            )
                        )
                        return "", elapsed
                else:
                    elapsed = time.time() - start_time
                    logger.error(
                        _format_timed_log(
                            "Gemini",
                            elapsed,
                            f"API呼び出しに失敗しました(model={self._model_name}): {e}",
                        )
                    )
                    return "", elapsed
            else:
                elapsed = time.time() - start_time
                logger.error(
                    _format_timed_log(
                        "Gemini",
                        elapsed,
                        f"API呼び出しに失敗しました(model={self._model_name}): {e}",
                    )
                )
                return "", elapsed

        elapsed = time.time() - start_time
        raw_text = self._extract_response_text(response)
        result = re.sub(r"<[^>]+>", "", raw_text).strip()
        logger.info(
            _format_timed_log(
                "Gemini",
                elapsed,
                f"{result} (model={self._model_name})",
            )
        )
        return result, elapsed
