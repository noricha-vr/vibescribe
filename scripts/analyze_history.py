#!/usr/bin/env python3
"""履歴データを分析し、未修正の誤変換パターンを検出する。

Usage:
    uv run python scripts/analyze_history.py
    uv run python scripts/analyze_history.py --days 7
"""

import json
import re
from argparse import ArgumentParser
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

# 同音異義語テーブル（postprocessor.pyと同期）
HOMOPHONE_TABLE = {
    "Issue": {
        "misreadings": ["石", "1周", "2周", "1週", "2週", "一瞬", "異臭", "義手", "異種", "実習", "EC", "ECU"],
        "keywords": ["立てる", "確認", "作成", "閉じる", "GitHub", "PR", "プルリク"],
    },
    "上記": {"misreadings": ["蒸気"], "keywords": ["コード", "参考"]},
    "機能": {"misreadings": ["昨日"], "keywords": ["実装", "追加"]},
    "構成": {"misreadings": ["校正"], "keywords": ["ファイル", "ディレクトリ"]},
    "改行": {"misreadings": ["開業"], "keywords": ["文章", "行", "貼り付け"]},
    "記事": {"misreadings": ["生地"], "keywords": ["ブログ", "投稿", "作成", "編集"]},
}


def load_history(history_dir: Path, days: int | None = None) -> list[dict]:
    """履歴ファイルを読み込む。"""
    history = []
    cutoff = datetime.now() - timedelta(days=days) if days else None

    for json_file in history_dir.glob("*.json"):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if cutoff:
                    ts = datetime.fromisoformat(data["timestamp"])
                    if ts < cutoff:
                        continue
                data["_file"] = json_file.name
                history.append(data)
        except (json.JSONDecodeError, KeyError):
            continue

    return sorted(history, key=lambda x: x["timestamp"], reverse=True)


def detect_unfixed_patterns(history: list[dict]) -> list[dict]:
    """未修正の誤変換パターンを検出する。"""
    unfixed = []

    for entry in history:
        raw = entry.get("raw_transcription", "")
        processed = entry.get("processed_text", "")

        # 修正されなかった（またはほぼ同じ）場合のみチェック
        if raw == processed or _normalize(raw) == _normalize(processed):
            # 同音異義語テーブルの誤変換パターンをチェック
            for correct, info in HOMOPHONE_TABLE.items():
                for misreading in info["misreadings"]:
                    if misreading in raw:
                        # キーワードとの共起をチェック
                        has_keyword = any(kw in raw for kw in info["keywords"])
                        unfixed.append({
                            "raw": raw,
                            "processed": processed,
                            "detected": misreading,
                            "should_be": correct,
                            "has_keyword": has_keyword,
                            "timestamp": entry["timestamp"],
                        })

    return unfixed


def detect_new_patterns(history: list[dict]) -> Counter:
    """頻出する未知のパターンを検出する。"""
    # raw と processed が同じで、プログラミングキーワードを含むものを抽出
    prog_keywords = ["コード", "実装", "関数", "変数", "API", "テスト", "作成", "追加", "修正", "削除"]
    patterns = Counter()

    for entry in history:
        raw = entry.get("raw_transcription", "")
        processed = entry.get("processed_text", "")

        if raw == processed:
            # プログラミング文脈かチェック
            if any(kw in raw for kw in prog_keywords):
                # 漢字2文字の単語を抽出（潜在的な誤変換）
                kanji_words = re.findall(r'[\u4e00-\u9fff]{2}', raw)
                for word in kanji_words:
                    patterns[word] += 1

    return patterns


def _normalize(text: str) -> str:
    """句読点を除去して正規化。"""
    return re.sub(r'[。、．，\.\,\s]', '', text)


def main():
    parser = ArgumentParser(description="履歴データを分析し、未修正の誤変換パターンを検出")
    parser.add_argument("--days", type=int, help="分析対象の日数（指定しない場合は全期間）")
    parser.add_argument("--history-dir", type=Path, default=Path.home() / ".voicecode" / "history")
    args = parser.parse_args()

    if not args.history_dir.exists():
        print(f"履歴ディレクトリが見つかりません: {args.history_dir}")
        return

    history = load_history(args.history_dir, args.days)
    print(f"分析対象: {len(history)} 件の履歴\n")

    # 未修正パターンを検出
    unfixed = detect_unfixed_patterns(history)
    if unfixed:
        print("=" * 50)
        print("未修正の誤変換パターン（同音異義語テーブルに該当）")
        print("=" * 50)
        for i, item in enumerate(unfixed[:10], 1):
            kw_mark = "★" if item["has_keyword"] else ""
            print(f"\n{i}. 「{item['detected']}」→「{item['should_be']}」{kw_mark}")
            print(f"   入力: {item['raw'][:50]}...")
            print(f"   日時: {item['timestamp']}")
    else:
        print("未修正の既知パターンはありません。")

    # 頻出する未知パターンを検出
    print("\n")
    print("=" * 50)
    print("頻出する漢字2文字（潜在的な誤変換候補）")
    print("=" * 50)
    new_patterns = detect_new_patterns(history)
    # 既知の誤変換を除外
    known_misreadings = set()
    for info in HOMOPHONE_TABLE.values():
        known_misreadings.update(info["misreadings"])

    for word, count in new_patterns.most_common(10):
        if word not in known_misreadings and count >= 2:
            print(f"  {word}: {count}回")


if __name__ == "__main__":
    main()
