import time
import click
import json
import shutil
import UnityPy.config
import proto.octodb_pb2 as octop
from pathlib import Path
from google.protobuf.json_format import ParseDict
from src.config import config
from src.octo_manager import DataManger
from src.file_operation import file_operate
from src.resource_download import download_resource
from src.image_process import image_scale
from src.config import UPDATE_PATH, UNITY_VERSION, UPDATE_FLAG
from src.decrypt import decrypt_database_from_api
from src.srt_subtitle import export_srt_subtitles
from src.version import update_config_version
from src.warp_request import request_update


UnityPy.config.FALLBACK_UNITY_VERSION = UNITY_VERSION


def after_download(revision: int, database: octop.Database):
    image_scale(database, f"{UPDATE_PATH}/{revision}/image", f"{UPDATE_PATH}/{revision}/stretch")
    if UPDATE_FLAG:
        file_operate("copy", f"{UPDATE_PATH}/{revision}", "cache", dirs_exist_ok=True)
    else:
        file_operate("move", f"{UPDATE_PATH}/{revision}", "cache")
        shutil.rmtree(f"{UPDATE_PATH}/{revision}", ignore_errors=True)
        config.set("Download settings", "UPDATE_FLAG", "True")
        with open("config.ini", "w", encoding="utf8") as config_file:
            config.write(config_file)


def once(reset: bool, init_download: bool, download_type: str):
    octo_manager = DataManger()
    octo_manager.start_db_update(reset)
    revision = octo_manager.revision
    database = octo_manager.get_diff_and_check_legal(init_download)
    if database:
        download_resource(
            revision,
            database,
            download_type,
        )
        after_download(revision, database)


def loop(reset: bool, init_download: bool, download_type: str, loop_interval: int = 600):
    once(reset, init_download, download_type)
    while True:
        time.sleep(loop_interval)
        octo_manager = DataManger()
        octo_manager.start_db_update()
        revision = octo_manager.revision
        database = octo_manager.get_diff_and_check_legal()
        if database:
            download_resource(
                revision,
                database,
                download_type,
            )
            after_download(revision, database)


def get_database_for_srt(reset: bool, db_revision: int) -> tuple[int, octop.Database] | None:
    manifest_path = Path("cache/OctoManifest.json")

    # GitHub Actions starts with an empty cache. In that case a non-zero
    # revision response is a diff, not a complete manifest, so consume it
    # directly instead of letting DataManger treat it as a full database.
    if not manifest_path.is_file() and db_revision > 0:
        downloaded_bytes = request_update(db_revision)
        if not downloaded_bytes:
            click.echo("No SRTSubtitle update found.")
            return None
        try:
            database = decrypt_database_from_api(downloaded_bytes)
        except Exception as exc:
            click.echo(f"Failed to deserialize the Octo database: {exc}")
            return None
        return database.revision, database

    octo_manager = DataManger()
    octo_manager.start_db_update(reset, db_revision)
    database = octo_manager.get_diff_and_check_legal(init=True)
    if database:
        return octo_manager.revision, database

    if not manifest_path.is_file():
        click.echo("No SRTSubtitle update found.")
        return None

    with manifest_path.open("r", encoding="utf8") as fp:
        database = ParseDict(json.load(fp), octop.Database(), ignore_unknown_fields=True)
    return database.revision, database


def srt(
    reset: bool,
    db_revision: int,
    srt_pattern: str,
    srt_output: str,
    srt_bundle_cache: str,
    srt_workers: int,
    srt_limit: int,
):
    db_result = get_database_for_srt(reset, db_revision)
    if db_result is None:
        return

    revision, database = db_result
    click.echo(f"Using Octo database revision {revision}.")
    result = export_srt_subtitles(
        database=database,
        bundle_cache_dir=srt_bundle_cache,
        output_dir=srt_output,
        pattern=srt_pattern,
        workers=srt_workers,
        limit=srt_limit,
    )
    if result["failed_downloads"] or result["failed_extracts"]:
        raise RuntimeError("SRTSubtitle export failed.")

    Path("cache").mkdir(exist_ok=True)
    with open("cache/revision", "w", encoding="utf8") as fp:
        fp.write(str(revision))


@click.command()
@click.option(
    "--mode",
    default="once",
    type=click.Choice(["once", "loop", "srt"]),
    help="Script mode. Use srt to download tln_live bundles and export SRTSubtitle text-map JSON.",
)
@click.option(
    "--update_version",
    is_flag=True,
    help="Detect the newest available Octo version and update config.ini.",
)
@click.option(
    "--reset",
    default=False,
    type=bool,
    help="Used to reset local database.",
)
@click.option(
    "--init_download",
    default=False,
    type=bool,
    help="Whether to download the full resource on first use.",
)
@click.option(
    "--db_revision",
    default=0,
    type=int,
    help="Set the database revision when reset.",
)
@click.option(
    "--download_type",
    default="ALL",
    type=click.Choice(["ALL", "ab", "resource"]),
    help="Specify the type to download, ab for assetBundle, resource for resource and ALL for both.",
)
@click.option(
    "--loop_interval",
    default=600,
    type=int,
    help="The interval between each check, in seconds.",
)
@click.option(
    "--srt_pattern",
    default="tln_live*",
    type=str,
    help="AssetBundle name pattern for SRTSubtitle export.",
)
@click.option(
    "--srt_output",
    default="cache/SRTSubtitle",
    type=str,
    help="Output directory for SRTSubtitle text-map JSON files.",
)
@click.option(
    "--srt_bundle_cache",
    default="cache/srt_bundles",
    type=str,
    help="Directory for downloaded and decrypted SRTSubtitle AssetBundles.",
)
@click.option(
    "--srt_workers",
    default=12,
    type=int,
    help="Concurrent download workers for SRTSubtitle export.",
)
@click.option(
    "--srt_limit",
    default=0,
    type=int,
    help="Limit SRTSubtitle bundle count; 0 means all matched bundles.",
)
def main(
    mode: str,
    update_version: bool = False,
    reset: bool = False,
    init_download: bool = False,
    db_revision: int = 0,
    download_type: str = "ALL",
    loop_interval: int = 600,
    srt_pattern: str = "tln_live*",
    srt_output: str = "cache/SRTSubtitle",
    srt_bundle_cache: str = "cache/srt_bundles",
    srt_workers: int = 12,
    srt_limit: int = 0,
):
    if update_version:
        click.echo(update_config_version())
        return

    if mode == "once":
        once(reset, init_download, download_type)
    elif mode == "loop":
        loop(reset, init_download, download_type, loop_interval)
    elif mode == "srt":
        srt(reset, db_revision, srt_pattern, srt_output, srt_bundle_cache, srt_workers, srt_limit)


if __name__ == "__main__":
    main()
