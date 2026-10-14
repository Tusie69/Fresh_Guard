"""Create a small browser page containing demo QR codes for Feature 2."""

import argparse
from html import escape
from pathlib import Path
from urllib.parse import quote


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="http://192.168.0.106:5000",
                        help="FreshGuard host reachable by the phone")
    parser.add_argument("--output", default="tools/food_qr_demo.html")
    args = parser.parse_args()

    host = args.host.rstrip("/")
    foods = (
        ("Apple", "FG-APPLE-001", "FG-FRUIT"),
        ("Milk", "FG-MILK-001", "FG-DAIRY"),
    )
    cards = []
    for name, food_id, category in foods:
        target = f"{host}/add-food?food_id={quote(food_id)}&category={quote(category)}"
        image = "https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=" + quote(target, safe="")
        cards.append(
            f"<article><h2>{escape(name)}</h2><img alt='{escape(name)} QR' src='{escape(image)}'>"
            f"<p>{escape(target)}</p></article>"
        )
    Path(args.output).write_text(
        "<!doctype html><meta charset='utf-8'><title>FreshGuard Food QR Demo</title>"
        "<style>body{font:16px sans-serif;display:flex;gap:24px;flex-wrap:wrap}article{max-width:340px}img{width:300px}</style>"
        + "".join(cards), encoding="utf-8"
    )
    print(f"Wrote {args.output}; open it on a screen visible to the phone camera.")


if __name__ == "__main__":
    main()
