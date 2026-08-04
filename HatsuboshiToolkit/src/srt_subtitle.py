import contextlib
import fnmatch
import io
import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import UnityPy
import proto.octodb_pb2 as octop
import src.rich_console as console
from src.config import UNITY_SIGNATURE
from src.decrypt import crypt_by_string
from src.warp_request import send_request


def sanitize_filename(name: str) -> str:
    name = name.strip() or "unnamed"
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)


def quiet_unitypy_call(func, *args, **kwargs):
    with contextlib.redirect_stdout(io.StringIO()):
        return func(*args, **kwargs)


def is_subtitle_entry(value) -> bool:
    return (
        isinstance(value, dict)
        and isinstance(value.get("text"), str)
        and ("from" in value or "to" in value or "length" in value)
    )


def extract_srt_from_bundle(bundle_path: Path) -> list[dict]:
    env = quiet_unitypy_call(UnityPy.load, str(bundle_path))
    results = []

    for obj in env.objects:
        if obj.type.name != "MonoBehaviour":
            continue

        try:
            tree = quiet_unitypy_call(obj.read_typetree)
        except Exception:
            continue

        if not isinstance(tree, dict):
            continue

        subtitles = tree.get("subtitles")
        if not isinstance(subtitles, list) or not subtitles:
            continue
        if not all(is_subtitle_entry(entry) for entry in subtitles):
            continue

        name = tree.get("m_Name") or tree.get("name") or f"pathid_{obj.path_id}"
        results.append(
            {
                "name": name,
                "bundle": bundle_path.name,
                "pathId": obj.path_id,
                "subtitles": subtitles,
            }
        )

    return results


def load_existing_subtitles(path: Path) -> dict:
    if not path.is_file():
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    if not isinstance(data, dict):
        return {}

    subtitles = data.get("subtitles") if isinstance(data.get("subtitles"), dict) else data
    return {
        key: value
        for key, value in subtitles.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def simplify_srt_item(item: dict, existing_translations: dict) -> dict:
    subtitles = {}
    for subtitle in item["subtitles"]:
        raw = subtitle.get("text")
        if not isinstance(raw, str) or not raw or raw in subtitles:
            continue
        subtitles[raw] = existing_translations.get(raw, "")

    return subtitles


def write_srt_items(items: list[dict], output_dir: Path) -> tuple[int, int, int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    exported = 0
    entries = 0
    duplicate_raw = 0

    for item in items:
        base_name = sanitize_filename(item["name"])
        file_name = f"{base_name}.json"
        out_path = output_dir / file_name

        existing_translations = load_existing_subtitles(out_path)
        export_item = simplify_srt_item(item, existing_translations)
        source_count = sum(
            1
            for subtitle in item["subtitles"]
            if isinstance(subtitle, dict) and isinstance(subtitle.get("text"), str) and subtitle.get("text")
        )
        duplicate_raw += max(0, source_count - len(export_item))
        entries += len(export_item)

        with out_path.open("w", encoding="utf-8", newline="\n") as fp:
            json.dump(export_item, fp, ensure_ascii=False, indent=2)
            fp.write("\n")
        exported += 1

    return exported, entries, duplicate_raw


def download_asset_bundle(item, url_format: str, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / item.name
    if output_path.is_file():
        return output_path

    url = url_format.replace("{o}", item.objectName)
    obj = send_request(url, verify=True).content
    if len(obj) == 0:
        raise RuntimeError(f"Empty object '{item.name}'")

    if obj[0:5] != UNITY_SIGNATURE:
        asset_bytes = crypt_by_string(obj, item.name, 0, 0, 256)
    else:
        asset_bytes = obj

    if asset_bytes[0:5] != UNITY_SIGNATURE:
        raise RuntimeError(f"'{item.name}' '{item.md5}' is not a unity asset")

    output_path.write_bytes(asset_bytes)
    return output_path


def export_srt_subtitles(
    database: octop.Database,
    bundle_cache_dir: str,
    output_dir: str,
    pattern: str = "tln_live*",
    workers: int = 12,
    limit: int = 0,
) -> dict:
    bundle_cache_path = Path(bundle_cache_dir)
    output_path = Path(output_dir)
    matches = [item for item in database.assetBundleList if fnmatch.fnmatchcase(item.name, pattern)]
    matches.sort(key=lambda item: item.name)
    if limit > 0:
        matches = matches[:limit]

    failed_downloads = []
    downloaded_paths = []
    workers = max(1, workers)

    def download_worker(item):
        return item.name, download_asset_bundle(item, database.urlFormat, bundle_cache_path)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(download_worker, item): item.name for item in matches}
        for index, future in enumerate(as_completed(futures), 1):
            name = futures[future]
            try:
                _, path = future.result()
                downloaded_paths.append(path)
                console.succeed(f"({index}/{len(matches)}) SRT bundle '{name}' downloaded.")
            except Exception as exc:
                failed_downloads.append({"bundle": name, "error": repr(exc)})
                console.error(f"({index}/{len(matches)}) Failed to download SRT bundle '{name}': {exc}")

    failed_extracts = []
    subtitle_assets = 0
    entries = 0
    duplicate_raw = 0

    for bundle_path in sorted(downloaded_paths):
        try:
            items = extract_srt_from_bundle(bundle_path)
        except Exception as exc:
            failed_extracts.append({"bundle": bundle_path.name, "error": repr(exc)})
            continue

        exported_count, entry_count, duplicate_count = write_srt_items(items, output_path)
        subtitle_assets += exported_count
        entries += entry_count
        duplicate_raw += duplicate_count

    result = {
        "matched_bundles": len(matches),
        "downloaded_bundles": len(downloaded_paths),
        "subtitle_assets": subtitle_assets,
        "entries": entries,
        "duplicate_raw": duplicate_raw,
        "output_dir": str(output_path),
        "bundle_cache_dir": str(bundle_cache_path),
        "failed_downloads": failed_downloads,
        "failed_extracts": failed_extracts,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result
