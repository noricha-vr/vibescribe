# プロンプトキャッシング導入前の状態に戻す

## 背景

プロンプトキャッシングのためにシステムプロンプトを2段に分けた（973ace5）以降、精度が悪くなったとのこと。24時間前（268c9a6）の状態に戻す。

## 変更対象ファイル

- `postprocessor.py`

## 変更手順

1. `git show 268c9a6:postprocessor.py > postprocessor.py` で復元
2. 最近追加した同音異義語「記事/生地」の例を追加
3. テスト実行して確認

## 復元後の状態

- 1つの `SYSTEM_PROMPT` にすべて含む（XML形式）
- messages: `[{"role": "user"}, {"role": "system"}]`
- `cache_control` 不使用

## 確認方法

1. `uv run pytest tests/test_postprocessor.py`
2. 実際に音声入力して精度を確認
