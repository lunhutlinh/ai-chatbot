import argparse
import json
from pathlib import Path

try:
    from jsonschema import Draft202012Validator, FormatChecker
except ImportError as exc:
    raise ImportError(
        "Missing dependency 'jsonschema'. Install with: pip install jsonschema"
    ) from exc

BASE_DIR = Path(__file__).resolve().parents[2]
DEFAULT_CHUNKS_PATH = BASE_DIR / "data/processed/chunks/chunks.jsonl"
SCHEMA_PATH = Path(__file__).resolve().with_name("chunk.schema.json")


def load_schema(schema_path: Path) -> dict:
    if not schema_path.exists():
        raise FileNotFoundError(f"Schema not found: {schema_path}")
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _business_rule_errors(item: dict, line_no: int) -> list[str]:
    errors: list[str] = []

    text_tokens = len(item.get("chunk_text", "").split())
    declared_tokens = item.get("token_count")
    if isinstance(declared_tokens, int) and declared_tokens != text_tokens:
        errors.append(
            f"line {line_no}: token_count mismatch (declared={declared_tokens}, actual={text_tokens})"
        )

    if item.get("deadline_date") and not item.get("deadline_type"):
        errors.append(
            f"line {line_no}: deadline_date is set but deadline_type is missing"
        )

    if item.get("deadline_type") and not item.get("deadline_date"):
        errors.append(
            f"line {line_no}: deadline_type is set but deadline_date is missing"
        )

    return errors


def validate_chunks_file(chunks_path: Path) -> tuple[bool, list[str], int]:
    if not chunks_path.exists():
        raise FileNotFoundError(f"Chunks file not found: {chunks_path}")

    schema = load_schema(SCHEMA_PATH)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    errors: list[str] = []
    chunk_ids: set[str] = set()
    rows = 0

    with chunks_path.open("r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            rows += 1

            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_no}: invalid JSON ({exc})")
                continue

            schema_errors = sorted(validator.iter_errors(item), key=lambda e: e.path)
            for err in schema_errors:
                path = ".".join(str(p) for p in err.absolute_path) or "<root>"
                errors.append(f"line {line_no}: {path}: {err.message}")

            chunk_id = item.get("chunk_id")
            if isinstance(chunk_id, str):
                if chunk_id in chunk_ids:
                    errors.append(f"line {line_no}: duplicated chunk_id '{chunk_id}'")
                else:
                    chunk_ids.add(chunk_id)

            errors.extend(_business_rule_errors(item, line_no))

    if rows == 0:
        errors.append("chunks file is empty")

    return len(errors) == 0, errors, rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate chunks.jsonl before upsert")
    parser.add_argument(
        "--chunks",
        type=Path,
        default=DEFAULT_CHUNKS_PATH,
        help="Path to chunks.jsonl",
    )
    args = parser.parse_args()

    try:
        ok, errors, rows = validate_chunks_file(args.chunks)
    except Exception as exc:
        print(f"validation_status=error message={exc}")
        raise SystemExit(1) from exc

    if not ok:
        print(f"validation_status=failed rows={rows} error_count={len(errors)}")
        for err in errors[:100]:
            print(f" - {err}")
        if len(errors) > 100:
            print(f" - ... and {len(errors) - 100} more")
        raise SystemExit(1)

    print(f"validation_status=ok rows={rows}")


if __name__ == "__main__":
    main()