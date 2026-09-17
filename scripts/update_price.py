#!/usr/bin/env python3
"""
公式サイト（聖徳自動車学園）の料金ページを取得し、
表(<table>)の中身を price-data.json に書き出すスクリプト。

GitHub Actions から定期的に実行される想定。
公式サイトの構造が変わって表がうまく取れなかった場合は、
既存の price-data.json を壊さないよう、何もせずエラー終了する。
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SOURCE_URL = "https://www.shotoku-ds.net/guidance/price.html"
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "price-data.json"

# 全角・半角どちらの数字にもマッチ（価格らしい表かどうかの簡易判定に使う）
DIGIT_RE = re.compile(r"[0-9\uFF10-\uFF19]")


def looks_like_price_table(rows: list[list[str]]) -> bool:
    """数字が1つでも含まれていれば「価格っぽい表」とみなす（記号は問わない）"""
    for row in rows:
        for cell in row:
            if DIGIT_RE.search(cell):
                return True
    return False


def extract_tables(html: str):
    soup = BeautifulSoup(html, "lxml")

    all_tables = soup.find_all("table")
    print(f"[INFO] ページ内の <table> 要素数: {len(all_tables)}", file=sys.stderr)

    # ページ内の見出し(h1-h6)とtableを出現順にまとめて走査し、
    # 各tableの直前に出てきた見出しをキャプションとして扱う。
    heading_tags = {"h1", "h2", "h3", "h4", "h5", "h6"}
    current_caption = ""
    results = []
    skipped = 0

    for el in soup.find_all(list(heading_tags) + ["table"]):
        if el.name in heading_tags:
            text = el.get_text(strip=True)
            if text:
                current_caption = text
            continue

        # el.name == "table"
        table_rows = []
        headers = []
        trs = el.find_all("tr")
        for i, tr in enumerate(trs):
            ths = tr.find_all("th")
            tds = tr.find_all("td")
            if ths and not tds and i == 0:
                headers = [th.get_text(strip=True) for th in ths]
                continue
            cells = tr.find_all(["td", "th"])
            row = [c.get_text(strip=True) for c in cells]
            if any(row):
                table_rows.append(row)

        preview = table_rows[0] if table_rows else []
        print(
            f"[INFO] table candidate: caption='{current_caption}' "
            f"rows={len(table_rows)} first_row={preview}",
            file=sys.stderr,
        )

        if not table_rows:
            skipped += 1
            continue
        if not looks_like_price_table(table_rows):
            skipped += 1
            continue

        results.append({
            "caption": current_caption or "料金表",
            "headers": headers,
            "rows": table_rows,
        })

    print(
        f"[INFO] 採用: {len(results)} 個 / 除外: {skipped} 個",
        file=sys.stderr,
    )

    return results


def main():
    try:
        resp = requests.get(
            SOURCE_URL,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ShotokuPriceSync/1.0)"},
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"[ERROR] 公式サイトの取得に失敗しました: {e}", file=sys.stderr)
        sys.exit(1)

    tables = extract_tables(resp.text)

    # 安全チェック：1個も取れていない場合のみ中止（サイトの完全な構造変化などを想定）。
    MIN_TABLES = 1
    if len(tables) < MIN_TABLES:
        print(
            f"[ERROR] 料金表が1つも取得できませんでした。"
            "公式サイトの構造が変わった可能性があるため、更新を中止します。",
            file=sys.stderr,
        )
        sys.exit(1)

    data = {
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_url": SOURCE_URL,
        "tables": tables,
    }

    OUTPUT_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"[OK] {len(tables)} 個の料金表を price-data.json に書き出しました。")


if __name__ == "__main__":
    main()
