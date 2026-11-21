"""nexus-agent pair | run | status | unpair"""

from __future__ import annotations

import argparse
import asyncio
import logging
import platform
import socket
import sys

from nexus_agent.api import Api, ApiError
from nexus_agent.config import AgentConfig


async def _pair(args: argparse.Namespace) -> int:
    cfg = AgentConfig.load()
    cfg.server = args.server.rstrip("/")
    api = Api(cfg)
    try:
        await api.pair(args.code, args.name or socket.gethostname(), platform.system().lower())
    except ApiError as exc:
        print(f"Pairing failed: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await api.close()
    print(f"Paired as '{cfg.name}'. Start it with: nexus-agent run")
    return 0


async def _run(args: argparse.Namespace) -> int:
    from nexus_agent.runtime import Agent

    cfg = AgentConfig.load()
    if not cfg.paired:
        print(
            "This PC isn't paired yet. In NEXUS open Settings > Devices, make a code, then run:\n"
            "  nexus-agent pair --code XXXX-XXXX",
            file=sys.stderr,
        )
        return 1
    audio = wake = None
    if not args.no_audio:
        try:
            from nexus_agent.devices import OpenWakeWord, SoundDeviceIO

            audio = SoundDeviceIO()
            try:
                wake = OpenWakeWord(args.wake_word or cfg.wake_word_model)
            except Exception as exc:
                logging.warning("Wake word unavailable (%s). Hands-free still works.", exc)
        except ImportError:
            logging.warning("Audio extras not installed: pip install 'nexus-agent[audio]'")
    api = Api(cfg)
    try:
        await Agent(api, audio, wake).run()
    finally:
        await api.close()
    return 1


async def _status(_: argparse.Namespace) -> int:
    cfg = AgentConfig.load()
    if not cfg.paired:
        print("Not paired.")
        return 1
    api = Api(cfg)
    try:
        await api.refresh()
        print(f"Paired as '{cfg.name}' with {cfg.server}. Session is valid.")
        return 0
    except ApiError as exc:
        print(f"Paired with {cfg.server}, but: {exc.message}")
        return 1
    finally:
        await api.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="nexus-agent", description="NEXUS local agent")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pair", help="link this PC to NEXUS with a code from Settings > Devices")
    p.add_argument("--code", required=True)
    p.add_argument("--server", default="http://localhost:8000")
    p.add_argument("--name", default="")
    r = sub.add_parser("run", help="connect and listen (wake word / hands-free)")
    r.add_argument("--wake-word", default="", help="pretrained name or path to a .onnx model")
    r.add_argument("--no-audio", action="store_true", help="link only, no microphone")
    sub.add_parser("status", help="check the pairing")
    sub.add_parser("unpair", help="forget the pairing on this PC")
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    if args.cmd == "unpair":
        cfg = AgentConfig.load()
        cfg.device_id = cfg.refresh_token = ""
        cfg.save()
        print("Forgotten. Also remove the device in NEXUS Settings > Devices.")
        return 0
    handler = {"pair": _pair, "run": _run, "status": _status}[args.cmd]
    try:
        return asyncio.run(handler(args))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
