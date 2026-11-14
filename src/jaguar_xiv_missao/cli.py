from __future__ import annotations

import argparse
import logging
import re
import time

from .config import Settings


def _video_id(value: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/|/live/|/shorts/)([\w-]{11})", value)
    return match.group(1) if match else value


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="jaguar", description="Funcionário virtual de cortes")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="verifica os feeds uma vez e processa os vídeos novos")
    sub.add_parser("watch", help="repete `run` a cada POLL_INTERVAL_SECONDS")
    p_video = sub.add_parser("process", help="processa um vídeo específico (URL ou ID)")
    p_video.add_argument("video")
    p_chan = sub.add_parser("resolve-channel", help="descobre o channel_id de um @handle")
    p_chan.add_argument("handle")
    sub.add_parser("auth-youtube", help="faz o login OAuth e salva o token")
    args = parser.parse_args(argv)

    settings = Settings()
    logging.basicConfig(
        level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    if args.command == "resolve-channel":
        from .downloader import VideoDownloader

        channel_id, name = VideoDownloader(settings.work_dir).resolve_channel_id(args.handle)
        print(f"{channel_id}  # {name}")
        return
    if args.command == "auth-youtube":
        from .publishing.youtube import load_credentials

        load_credentials(settings.youtube_client_secrets_file, settings.youtube_token_file)
        print(f"Token salvo em {settings.youtube_token_file}")
        return

    from .container import build_pipeline
    from .models import SourceVideo

    pipeline = build_pipeline(settings)
    try:
        if args.command == "run":
            pipeline.run_once()
        elif args.command == "process":
            vid = _video_id(args.video)
            pipeline.store.mark(vid, "failed", "reprocessamento manual")  # libera para reprocessar
            pipeline.process(SourceVideo(id=vid, title=""))
        else:
            while True:
                pipeline.run_once()
                time.sleep(settings.poll_interval_seconds)
    except KeyboardInterrupt:
        pass
    finally:
        pipeline.store.close()
