"""文字起こし機能のテスト。"""

import logging
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import google.genai.types as genai_types

from transcriber import TRANSCRIBE_PROMPT, Transcriber


class _MockModel:
    def __init__(self, name: str, actions: list[str] | None = None):
        self.name = name if name.startswith("models/") else f"models/{name}"
        self.supported_actions = actions or ["generateContent"]


class TestTranscriber:
    """Transcriberのテスト。"""

    def test_init_without_api_key_raises_error(self):
        """APIキーがない場合にエラーが発生すること。"""
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="GOOGLE_API_KEY is not set"):
                Transcriber()

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_init_with_api_key(self, mock_list_models, mock_create_client):
        """APIキーで初期化できること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        tr = Transcriber(api_key="test_key")

        mock_create_client.assert_called_once()
        assert tr._model_name == Transcriber.MODEL
        assert "<instructions>" in tr._system_prompt

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_init_with_env_var(self, mock_list_models, mock_create_client):
        """環境変数からAPIキーを取得できること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        with patch.dict("os.environ", {"GOOGLE_API_KEY": "env_key"}, clear=True):
            tr = Transcriber()

        assert tr._api_key == "env_key"

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_init_prefers_preview_model_when_available(self, mock_list_models, mock_create_client):
        """利用可能なら Gemini 3 preview を優先選択すること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel("gemini-3-flash-preview"), _MockModel("gemini-2.5-flash")]

        tr = Transcriber(api_key="test_key")

        assert tr._model_name == "gemini-3-flash-preview"

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_init_uses_model_env_var_when_available(self, mock_list_models, mock_create_client):
        """VOICECODE_GEMINI_MODEL が利用可能なら優先されること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel("gemini-3-flash-preview"), _MockModel("gemini-2.0-flash")]

        with patch.dict(
            "os.environ",
            {
                "GOOGLE_API_KEY": "env_key",
                "VOICECODE_GEMINI_MODEL": "gemini-2.0-flash",
            },
            clear=True,
        ):
            tr = Transcriber()

        assert tr._model_name == "gemini-2.0-flash"

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_init_normalizes_legacy_model_name(self, mock_list_models, mock_create_client):
        """gemini-3.0-flash 指定時は互換モデル名へ正規化すること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.side_effect = RuntimeError("network error")

        with patch.dict(
            "os.environ",
            {
                "GOOGLE_API_KEY": "env_key",
                "VOICECODE_GEMINI_MODEL": "gemini-3.0-flash",
            },
            clear=True,
        ):
            tr = Transcriber()

        assert tr._model_name == "gemini-3-flash-preview"

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_invalid_thinking_level_falls_back_to_default(self, mock_list_models, mock_create_client):
        """無効な thinking level は minimal にフォールバックすること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        with patch.dict(
            "os.environ",
            {
                "GOOGLE_API_KEY": "env_key",
                "VOICECODE_THINKING_LEVEL": "invalid-level",
            },
            clear=True,
        ):
            tr = Transcriber()

        assert tr._thinking_level == genai_types.ThinkingLevel.MINIMAL

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_build_generate_config_uses_thinking_level(self, mock_list_models, mock_create_client):
        """デフォルトは thinking_level 設定で構成されること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        tr = Transcriber(api_key="test_key")
        cfg = tr._build_generate_config()

        assert cfg.system_instruction
        assert cfg.thinking_config.thinking_level == genai_types.ThinkingLevel.MINIMAL

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_build_generate_config_uses_budget0_in_fallback_mode(self, mock_list_models, mock_create_client):
        """thinking fallback モードでは thinking_budget=0 を使うこと。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        tr = Transcriber(api_key="test_key")
        tr._thinking_mode = "budget0"
        cfg = tr._build_generate_config()

        assert cfg.thinking_config.thinking_budget == 0

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_transcribe_file_not_found(self, mock_list_models, mock_create_client):
        """存在しないファイルでエラーが発生すること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        transcriber = Transcriber(api_key="test_key")

        with pytest.raises(FileNotFoundError):
            transcriber.transcribe(Path("/nonexistent/file.wav"))

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_transcribe_success(self, mock_list_models, mock_create_client):
        """正常に文字起こしできること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        mock_response = MagicMock()
        mock_response.text = "テスト結果"

        transcriber = Transcriber(api_key="test_key")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"dummy audio data")
            temp_path = Path(f.name)

        try:
            with patch.object(transcriber, "_generate_content_with_retry", return_value=mock_response) as mock_gen:
                result, elapsed = transcriber.transcribe(temp_path)

            assert result == "テスト結果"
            assert isinstance(elapsed, float)
            assert elapsed >= 0
            mock_gen.assert_called_once()
        finally:
            temp_path.unlink()

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_transcribe_strips_whitespace_and_tags(self, mock_list_models, mock_create_client):
        """結果の空白とXMLタグが除去されること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        mock_response = MagicMock()
        mock_response.text = "  <output>結果</output>  \n"

        transcriber = Transcriber(api_key="test_key")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"dummy audio data")
            temp_path = Path(f.name)

        try:
            with patch.object(transcriber, "_generate_content_with_retry", return_value=mock_response):
                result, elapsed = transcriber.transcribe(temp_path)
            assert result == "結果"
            assert isinstance(elapsed, float)
        finally:
            temp_path.unlink()

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_transcribe_api_error_returns_empty(self, mock_list_models, mock_create_client, caplog):
        """APIエラー時に空文字列を返すこと。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        transcriber = Transcriber(api_key="test_key")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"dummy audio data")
            temp_path = Path(f.name)

        try:
            with patch.object(transcriber, "_generate_content_with_retry", side_effect=RuntimeError("timeout")), \
                 patch.object(transcriber, "_resolve_model_name", return_value=""):
                with caplog.at_level(logging.ERROR, logger="transcriber"):
                    result, elapsed = transcriber.transcribe(temp_path)

            assert result == ""
            assert isinstance(elapsed, float)
            assert elapsed >= 0
            assert any("API呼び出しに失敗" in record.message for record in caplog.records)
        finally:
            temp_path.unlink()

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_transcribe_retries_on_transient_error(self, mock_list_models, mock_create_client):
        """一時的なAPIエラー時に同一モデルで再試行すること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        transcriber = Transcriber(api_key="test_key")
        recovered_response = MagicMock()

        with patch.object(
            transcriber,
            "_generate_content",
            side_effect=[RuntimeError("504 Deadline expired before operation could complete."), recovered_response],
        ) as mock_generate:
            result = transcriber._generate_content_with_retry(b"dummy")

        assert result == recovered_response
        assert mock_generate.call_count == 2

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_generate_content_switches_to_budget0_when_thinking_level_unsupported(self, mock_list_models, mock_create_client):
        """thinking_level 非対応時に thinking_budget=0 へ切替して再試行すること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        transcriber = Transcriber(api_key="test_key")
        recovered_response = MagicMock()

        with patch.object(
            transcriber,
            "_generate_content",
            side_effect=[RuntimeError("Thinking level is not supported for this model."), recovered_response],
        ) as mock_generate:
            result = transcriber._generate_content_with_retry(b"dummy")

        assert result == recovered_response
        assert transcriber._thinking_mode == "budget0"
        assert mock_generate.call_count == 2

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_transcribe_switches_model_on_transient_error(self, mock_list_models, mock_create_client):
        """一時的なAPIエラーが継続する場合にモデル切替して再試行すること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel("gemini-3-flash-preview"), _MockModel("gemini-2.5-flash")]

        transcriber = Transcriber(api_key="test_key")
        recovered_response = MagicMock()
        recovered_response.text = "別モデルで復旧"

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"dummy audio data")
            temp_path = Path(f.name)

        try:
            with patch.object(
                transcriber,
                "_generate_content_with_retry",
                side_effect=[RuntimeError("504 Deadline expired before operation could complete."), recovered_response],
            ) as mock_retry, patch.object(transcriber, "_resolve_model_name", return_value="gemini-2.5-flash"):
                result, elapsed = transcriber.transcribe(temp_path)

            assert result == "別モデルで復旧"
            assert isinstance(elapsed, float)
            assert mock_retry.call_count == 2
            assert transcriber._model_name == "gemini-2.5-flash"
        finally:
            temp_path.unlink()

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_transcribe_logs_result_with_gemini_label(self, mock_list_models, mock_create_client, caplog):
        """文字起こし結果が[Gemini]ラベルでログ出力されること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        mock_response = MagicMock()
        mock_response.text = "テスト結果"

        transcriber = Transcriber(api_key="test_key")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"dummy audio data")
            temp_path = Path(f.name)

        try:
            with patch.object(transcriber, "_generate_content_with_retry", return_value=mock_response):
                with caplog.at_level(logging.INFO, logger="transcriber"):
                    transcriber.transcribe(temp_path)

            assert any(record.message.startswith("[Gemini ") for record in caplog.records)
            assert any("テスト結果" in record.message for record in caplog.records)
            assert any("s] " in record.message for record in caplog.records)
        finally:
            temp_path.unlink()

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_client_generate_content_uses_prompt_and_audio_part(self, mock_list_models, mock_create_client):
        """API呼び出し時にプロンプトと音声Partを渡すこと。"""
        mock_client = MagicMock()
        mock_create_client.return_value = mock_client
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        transcriber = Transcriber(api_key="test_key")
        transcriber._client_generate_content(Transcriber.MODEL, b"audio-bytes")

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == Transcriber.MODEL
        assert call_kwargs["contents"][0] == TRANSCRIBE_PROMPT
        assert len(call_kwargs["contents"]) == 2

    def test_model_constant(self):
        """モデル定数が正しいこと。"""
        assert Transcriber.MODEL == "gemini-2.5-flash"

    def test_timeout_constant(self):
        """タイムアウト定数が正しいこと。"""
        assert Transcriber.TIMEOUT == 10.0

    @pytest.mark.parametrize(
        "message,expected",
        [
            ("403 PERMISSION_DENIED: CachedContent not found", True),
            ("CachedContent not found for API version v1beta", True),
            ("PERMISSION_DENIED: cached content expired", True),
            ("permission_denied something about cached resource", True),
            ("404 model not found", False),
            ("500 internal server error", False),
            ("PERMISSION_DENIED: quota exceeded", False),
        ],
    )
    def test_is_cached_content_error_patterns(self, message, expected):
        """各エラーパターンの CachedContent エラー検出が正しいこと。"""
        error = RuntimeError(message)
        assert Transcriber._is_cached_content_error(error) is expected

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_cached_content_error_fallback_to_system_instruction(self, mock_list_models, mock_create_client):
        """キャッシュ 403 エラー時にキャッシュを無効化してリトライすること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        transcriber = Transcriber(api_key="test_key")
        transcriber._prompt_cache_name_by_model[transcriber._model_name] = "cachedContents/abc123"

        recovered_response = MagicMock()

        with patch.object(
            transcriber,
            "_retry_loop",
            side_effect=[
                RuntimeError("403 PERMISSION_DENIED: CachedContent not found"),
                recovered_response,
            ],
        ) as mock_retry:
            result = transcriber._generate_content_with_retry(b"dummy")

        assert result == recovered_response
        assert mock_retry.call_count == 2
        # キャッシュが削除されていること
        assert transcriber._model_name not in transcriber._prompt_cache_name_by_model

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_cached_content_error_then_transient_error_retries(self, mock_list_models, mock_create_client):
        """キャッシュエラー後に一時エラーが発生してもリトライされること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        transcriber = Transcriber(api_key="test_key")
        transcriber._prompt_cache_name_by_model[transcriber._model_name] = "cachedContents/abc123"

        recovered_response = MagicMock()

        # 1回目の _retry_loop: キャッシュエラーで失敗
        # 2回目の _retry_loop: 成功（内部で transient エラーのリトライが効く）
        with patch.object(
            transcriber,
            "_retry_loop",
            side_effect=[
                RuntimeError("403 PERMISSION_DENIED: CachedContent not found"),
                recovered_response,
            ],
        ) as mock_retry:
            result = transcriber._generate_content_with_retry(b"dummy")

        assert result == recovered_response
        assert mock_retry.call_count == 2
        assert transcriber._model_name not in transcriber._prompt_cache_name_by_model

    @patch("transcriber.Transcriber._create_client")
    @patch("transcriber.Transcriber._client_list_models")
    def test_cached_content_error_then_transient_error_uses_full_retry(self, mock_list_models, mock_create_client):
        """キャッシュエラー後の _retry_loop が transient エラーをリトライできること。"""
        mock_create_client.return_value = MagicMock()
        mock_list_models.return_value = [_MockModel(Transcriber.MODEL)]

        transcriber = Transcriber(api_key="test_key")
        transcriber._prompt_cache_name_by_model[transcriber._model_name] = "cachedContents/abc123"

        recovered_response = MagicMock()

        # _generate_content をモックして完全なフローをテスト
        with patch.object(
            transcriber,
            "_generate_content",
            side_effect=[
                # 1回目の _retry_loop 内: キャッシュエラー
                RuntimeError("403 PERMISSION_DENIED: CachedContent not found"),
                # 2回目の _retry_loop 内: 504 → リトライ → 成功
                RuntimeError("504 Deadline expired"),
                recovered_response,
            ],
        ) as mock_generate:
            result = transcriber._generate_content_with_retry(b"dummy")

        assert result == recovered_response
        assert mock_generate.call_count == 3
        assert transcriber._model_name not in transcriber._prompt_cache_name_by_model
