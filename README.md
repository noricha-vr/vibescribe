# VibeScribe

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![macOS](https://img.shields.io/badge/platform-macOS-lightgrey.svg)](https://www.apple.com/macos/)

**Voice-to-text for developers on macOS** &mdash; press a hotkey, speak, and get correctly formatted text pasted into any app.

macOS 専用の音声入力ツール。ホットキーを押して話すだけで、プログラミング用語を正しい表記に補正してテキスト化します。Claude Code や Cursor などの AI コーディングツールへの音声指示に最適です。

## デモ: こんな変換ができます

### カタカナ &rarr; 英語表記

| 話した内容 | 一般的な音声認識 | VibeScribe |
|-----------|-----------------|------------|
| ユーズステート | ユーズステート | useState |
| ドットエンブローカル | .円舞.ローカル | .env.local |
| ドットギットイグノア | ..イグノア | .gitignore |
| ティーエスコンフィグ | DSコンフィグ | tsconfig.json |
| エヌピーエム | ピーピーエム | npm |
| クーベシーティーエル | 久米シティL | kubectl |
| ケーエイツエス | ケツ | k8s |
| スベルトキット | 滑るトキット | SvelteKit |
| ネクストジェイエス | Next Chess | Next.js |

### 同音異義語の補正

| 話した内容 | 一般的な音声認識 | VibeScribe |
|-----------|-----------------|------------|
| イシューを立てて | 1週を立てて | Issueを立てて |
| 上記のコードを参考に | 蒸気のコードを参考に | 上記のコードを参考に |
| 機能を実装して | 昨日を実装して | 機能を実装して |
| 改行を追加 | 開業を追加 | 改行を追加 |

## 特徴

- **ワンキー操作** &mdash; F15（カスタマイズ可能）で録音開始/停止をトグル
- **高精度な文字起こし** &mdash; Gemini Flash に音声を直接入力し、プログラミング用語を自動補正
- **シームレスな入力** &mdash; 文字起こし結果を自動でクリップボードにコピー & 貼り付け
- **メニューバー常駐** &mdash; 状態アイコン（■ 待機 / ● 録音 / ↻ 処理中）で録音状態を確認
- **効果音フィードバック** &mdash; 録音開始・停止・完了・エラー時に効果音でお知らせ
- **低コスト** &mdash; 月額約 $1.6（約237円）で使い放題（1日100回 × 30日の場合）

## 必要なもの

- macOS
- Python 3.13+
- Google AI Studio の API キー（[取得方法](docs/api-setup.md)）

## クイックスタート

### pipx でインストール（推奨）

```bash
brew install pipx
pipx ensurepath
pipx install git+https://github.com/noricha-vr/vibescribe.git
voicecode
```

### uv で実行

```bash
brew install uv
uv tool run --from git+https://github.com/noricha-vr/vibescribe.git voicecode
```

### ソースから実行

```bash
git clone https://github.com/noricha-vr/vibescribe.git
cd vibescribe
uv sync
uv run python main.py
```

初回起動時に API キーの入力を求められます。入力した API キーは `~/.voicecode/.env` に自動保存されます。

## macOS 権限の設定

初回起動時にガイドが表示されます。システム設定 > プライバシーとセキュリティ で以下を許可してください。

| 項目 | 対象アプリ | 用途 |
|------|-----------|------|
| アクセシビリティ | ターミナル（または使用するターミナルアプリ） | ホットキー監視、キーボード入力 |
| 入力監視 | ターミナル | ホットキー監視 |
| マイク | ターミナル | 音声録音 |

## 使い方

1. VibeScribe を起動する
2. **F15** を押して録音開始（メニューバーのアイコンが ● に変わる）
3. マイクに向かって話す
4. **F15** を再度押して録音停止
5. 文字起こし結果が自動で貼り付けられる

終了: メニューバーから「終了」を選択、または Ctrl+C。

## 設定

メニューバーの「ホットキー設定...」から変更できます。設定は `~/.voicecode/settings.json` に保存されます。

| 設定項目 | 説明 | デフォルト |
|----------|------|-----------|
| hotkey | 録音開始/停止のホットキー | f15 |
| restore_clipboard | 貼り付け後にクリップボードを復元 | true |
| max_recording_duration | 最大録音時間（秒、10-300） | 120 |

## コスト

Gemini 3 Flash Preview の[公式料金](https://ai.google.dev/gemini-api/docs/pricing)をもとに、実際の利用データ（2,398回分）から算出しています。

**1回あたりの内訳（平均録音時間 14.7 秒）**

| 項目 | トークン数 | 単価（/1M tokens） | コスト |
|------|-----------|-------------------|--------|
| システムプロンプト（キャッシュ） | 約 1,690 | $0.05 | $0.00009 |
| 音声入力（14.7秒 × 25tokens/秒） | 約 368 | $1.00 | $0.00037 |
| テキスト出力 | 約 20 | $3.00 | $0.00006 |
| **合計** | | | **約 $0.0005** |

**月額目安**

| 使用頻度 | リクエスト数/月 | 月額目安 |
|----------|---------------|---------|
| 1日10回 | 300 | 約 $0.16（約24円） |
| 1日50回 | 1,500 | 約 $0.79（約119円） |
| 1日100回 | 3,000 | 約 $1.58（約237円） |

※ プロンプトキャッシング有効時の料金。無効の場合は約2倍。無料枠の利用でさらに安くなります。

## トラブルシューティング

| 症状 | 対処法 |
|------|--------|
| アクセシビリティの許可が必要エラー | システム設定 > アクセシビリティ でターミナルを許可 → ターミナル再起動 |
| マイクが認識されない | システム設定 > マイク でターミナルを許可 |
| ホットキーが反応しない | システム設定 > 入力監視 でターミナルを許可 |
| 貼り付けが動作しない | アクセシビリティの許可を確認。一部アプリでは貼り付けがブロックされる場合あり |
| API エラー | `~/.voicecode/.env` の API キーを確認 / API 利用制限を確認 / ネットワーク接続を確認 |
| 音声が正しく認識されない | マイクに近づく / 静かな環境で使用 / はっきり発音 |

<details>
<summary>開発者向け情報</summary>

## アーキテクチャ

```
録音 (sounddevice) → Gemini Flash (文字起こし + 用語補正) → 貼り付け (pyautogui)
```

### 処理フロー

1. **録音** (recorder.py): pynput でホットキーを監視、sounddevice で WAV 16kHz モノラル録音
2. **文字起こし** (transcriber.py): 利用可能な Gemini Flash モデルを自動選択し、音声を直接テキスト化
3. **貼り付け** (main.py): pyperclip でクリップボードにコピー、pyautogui で Cmd+V

### ファイル構成

| ファイル | 責務 |
|----------|------|
| main.py | エントリポイント、rumps メニューバーアプリ、ホットキー監視 |
| recorder.py | 音声録音（WAV 16kHz モノラル） |
| transcriber.py | Gemini Flash 文字起こし（モデル自動選択） |
| postprocessor.py | 互換レイヤ（パススルー） |
| settings.py | 設定管理 |
| history.py | 履歴保存 |
| overlay.py | 録音中オーバーレイ |

### 開発コマンド

```bash
# テスト
uv run pytest tests/

# バックグラウンド起動
uv run python main.py -d

# ログ確認
tail -f ~/.voicecode/voicecode.log
```

</details>

## Contributing

[CONTRIBUTING.md](CONTRIBUTING.md) を参照してください。

## License

[MIT](LICENSE)
