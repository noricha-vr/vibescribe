#!/usr/bin/env python3
"""Gemini 3 Flashに音声ファイルを投げて処理速度を計測する。"""

import os
import time
from pathlib import Path

import google.genai as genai
import google.genai.types as genai_types

# 設定
AUDIO_FILE = Path.home() / ".voicecode/history/2026-02-03_114629.wav"
MODEL = "gemini-3-flash-preview"
NUM_TESTS = 3


def test_audio_transcription(audio_path: Path, test_num: int) -> dict:
    """音声ファイルを送信して処理時間を計測する。"""
    results = {}

    print(f"\n--- テスト {test_num} ---")

    # 1. ファイル読み込み
    t0 = time.time()
    with open(audio_path, "rb") as f:
        audio_data = f.read()
    results["file_read"] = time.time() - t0
    print(f"1. ファイル読み込み: {results['file_read']:.3f}s ({len(audio_data)/1024:.1f}KB)")

    # 2. クライアント初期化
    t1 = time.time()
    client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
    results["client_init"] = time.time() - t1
    print(f"2. クライアント初期化: {results['client_init']:.3f}s")

    # 3. API呼び出し
    t2 = time.time()
    response = client.models.generate_content(
        model=MODEL,
        contents=[
            "この音声を文字起こししてください。句読点を補完し、技術用語は正しい表記にしてください。文字起こし結果のみを返してください。",
            genai_types.Part.from_bytes(data=audio_data, mime_type="audio/wav"),
        ],
        config=genai_types.GenerateContentConfig(
            thinking_config=genai_types.ThinkingConfig(
                thinking_level=genai_types.ThinkingLevel.MINIMAL
            ),
        ),
    )
    results["api_call"] = time.time() - t2
    print(f"3. API呼び出し: {results['api_call']:.3f}s")

    # 4. 結果取得
    t3 = time.time()
    text = response.text.strip()
    results["result_parse"] = time.time() - t3
    print(f"4. 結果パース: {results['result_parse']:.3f}s")

    # 合計
    results["total"] = sum(results.values())
    print(f"合計: {results['total']:.3f}s")
    print(f"結果: {text}")

    return results


def main():
    if not os.environ.get("GOOGLE_API_KEY"):
        print("GOOGLE_API_KEY が未設定です。")
        return

    if not AUDIO_FILE.exists():
        print(f"音声ファイルが見つかりません: {AUDIO_FILE}")
        return

    print(f"音声ファイル: {AUDIO_FILE}")
    print(f"モデル: {MODEL}")
    print(f"テスト回数: {NUM_TESTS}")

    all_results = []
    for i in range(1, NUM_TESTS + 1):
        results = test_audio_transcription(AUDIO_FILE, i)
        all_results.append(results)
        if i < NUM_TESTS:
            time.sleep(1)  # レートリミット対策

    # 平均値
    print("\n" + "=" * 50)
    print("平均値")
    print("=" * 50)
    avg = {}
    for key in all_results[0].keys():
        avg[key] = sum(r[key] for r in all_results) / len(all_results)
        print(f"{key}: {avg[key]:.3f}s")


if __name__ == "__main__":
    main()
