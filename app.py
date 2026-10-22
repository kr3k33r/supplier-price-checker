import argparse
from pathlib import Path
from reconciliation import analyze, inspect, merge, safe_csv
from local_server import serve

ROOT = Path(__file__).resolve().parent


def get_api(path, query):
    if path == "/api/sample":
        return {
            "files": [
                {"name": p.name, "text": p.read_text(encoding="utf-8-sig")}
                for p in sorted((ROOT / "examples").glob("*.csv"))
            ]
        }


def post_api(path, payload):
    if path == "/api/inspect":
        return inspect(payload.get("files"), payload.get("mode", "prices"), payload.get("fields"))
    if path == "/api/analyze":
        mode = payload.get("mode", "prices")
        if mode == "merge":
            result = merge(
                payload.get("files"), payload.get("fields"), payload.get("deduplicate", False)
            )
            output_rows = [
                {**row["values"], "__source": row["source"], "__line": row["line"]}
                for row in result["rows"]
            ]
            output_fields = [field["name"] for field in result["fields"]] + ["__source", "__line"]
            result["downloads"] = {
                "normalized": safe_csv(output_rows, output_fields),
                "issues": safe_csv(result["issues"], ["source", "line", "type", "reason"]),
            }
            return result
        if mode != "prices":
            raise ValueError("Неизвестный режим обработки.")
        result = analyze(payload.get("files"))
        result["downloads"] = {
            "catalog": safe_csv(
                result["products"],
                [
                    "sku",
                    "name",
                    "sources",
                    "min_price",
                    "max_price",
                    "spread",
                    "best_source",
                    "available",
                    "review",
                ],
            ),
            "normalized": safe_csv(
                result["rows"], ["source", "line", "sku", "name", "price", "stock"]
            ),
            "issues": safe_csv(result["issues"], ["source", "line", "sku", "type", "reason"]),
        }
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    serve(ROOT / "web", get_api, post_api, parser.parse_args().port)
