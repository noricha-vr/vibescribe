# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Reference

| 項目 | 値 |
|------|-----|
| Python | 3.13+ |
| パッケージ管理 | uv |
| ホットキー | F15（デフォルト、メニューバーから変更可能） |
| 文字起こし | Gemini Flash（音声直接入力、モデル自動選択） |
| 設定ディレクトリ | `~/.voicecode/` |
| ログファイル | `~/.voicecode/voicecode.log` |

## プロジェクト概要

macOS専用の音声入力ツール。ホットキー1回で録音→Gemini文字起こし→貼り付けを自動実行する。プログラミング用語のカタカナを英語表記に自動変換する機能が特徴。メニューバーアプリとして常駐し、状態をアイコン（■/●/↻）で表示。

## コマンド

```bash
# 依存関係インストール
uv sync

# 実行（フォアグラウンド）
uv run python main.py

# 実行（バックグラウンド）
uv run python main.py -d

# テスト実行（全テスト）
uv run pytest tests/

# テスト実行（単一ファイル）
uv run pytest tests/test_transcriber.py -v

# テスト実行（特定テスト）
uv run pytest tests/test_transcriber.py::TestTranscriber::test_transcribe_success -v

# インストール（pipx推奨）
pipx install git+https://github.com/noricha-vr/voicecode.git
voicecode

# ログ確認
tail -f ~/.voicecode/voicecode.log

# ビルド（詳細は docs/build.md 参照）
./scripts/build_app.sh  # シェルラッパー版（個人利用向け）
uv run python setup_py2app.py py2app  # py2app版（配布向け）
```

## 環境変数

初回起動時にAPI キーの入力を求められ、`~/.voicecode/.env` に自動保存される。

`.env` に設定する項目:
- `GOOGLE_API_KEY` - Google AI Studio APIキー（必須）
- `VOICECODE_GEMINI_MODEL` - 利用モデル固定（任意、デフォルト: 自動選択）
- `VOICECODE_THINKING_LEVEL` - 思考レベル（任意、デフォルト: minimal）

## アーキテクチャ

```
録音 (sounddevice) → Gemini (音声直接入力) → 貼り付け (pyautogui)
```

### モジュール構成

| ファイル | 責務 |
|----------|------|
| `main.py` | エントリポイント、rumps メニューバーアプリ、ホットキー監視、統合処理 |
| `recorder.py` | 音声録音（sounddevice、WAV 16kHz モノラル） |
| `transcriber.py` | 文字起こし（Gemini Flash API、音声直接入力、モデル自動選択） |
| `postprocessor.py` | 互換レイヤ（現在はパススルー）、システムプロンプト/辞書ローダー |
| `settings.py` | 設定管理（ホットキー、クリップボード復元、最大録音時間） |
| `history.py` | 履歴保存（音声ファイル + メタデータ → `~/.voicecode/history/`） |
| `overlay.py` | 画面オーバーレイ（録音中インジケータ） |

### 処理フロー

1. `VoiceInputTool` (rumps) がホットキー監視（pynput）
2. `AudioRecorder` が音声録音（WAV 16kHz モノラル）
3. `Transcriber` が Gemini Flash で文字起こし（音声を直接 API に入力）
   - 利用可能なモデル（`gemini-3-flash-preview` → `gemini-2.5-flash` 等）を自動選択
   - システムプロンプトで技術用語補正を指示（後処理レイヤは不要）
4. `HistoryManager` が履歴を保存（任意）
5. pyperclip でクリップボードにコピー、pyautogui で Cmd+V

### 重要な設計判断

- **Gemini単段化**: 以前は「Whisper → Gemini後処理」だったが、現在は Gemini に音声を直接入力して文字起こし + 用語補正を一度に実行
- **モデル自動選択**: `PREFERRED_MODELS` リストから利用可能なモデルを自動選択（環境変数で固定も可能）
- **Thinking Level 制御**: `thinking_level` / `thinking_budget` でモデルの推論コストを制御
- **一時ファイル**: WAV ファイルは処理後に自動削除
- **テスト**: `unittest.mock` で API をモック化

## macOS固有の実装

### rumps と PyObjC の併用

| レイヤー | カバー範囲 |
|----------|-----------|
| rumps | メニューバーアプリ基本構造、メニュー項目、通知、タイマー |
| PyObjC | クリップボード操作、システムサウンド、macOS ネイティブ API |

**設計原則**:
- rumps をベースにして、rumps でできないことだけ PyObjC で補う
- rumps 内部で PyObjC を使用しているため、両者は同じイベントループを共有

### 必須権限

システム設定 > プライバシーとセキュリティ で以下を許可（初回起動時に案内される）:

| 項目 | 対象アプリ | 用途 |
|------|-----------|------|
| アクセシビリティ | ターミナル（または VoiceCode.app） | ホットキー監視、キーボード入力 |
| 入力監視 | ターミナル | ホットキー監視 |
| マイク | ターミナル | 音声録音 |

権限チェックは起動時に実行され、不足している場合はエラーメッセージで案内される。

## 既知の課題

- **文字起こしの待ち時間**: Gemini API 呼び出しが5〜10秒かかるケースあり（`504 Deadline expired` 時は10秒超）
- **Thinking Level 制御**: モデルごとに対応差があり、非対応モデルでは `thinking_budget=0` にフォールバック
- **ログローテーション未実装**: `~/.voicecode/voicecode.log` が追記され続けるため、長期運用で肥大化する
