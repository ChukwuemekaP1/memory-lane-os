"""Shared FFmpeg/ffprobe subprocess helpers (media + studio + archives)."""

from __future__ import annotations

import asyncio


class MediaToolError(Exception):
    """User-safe media tool failure."""


async def run_tool(binary: str, args: list[str], label: str, timeout: int = 600) -> tuple[bytes, str]:
    """Run an ffmpeg-family binary. Returns (stdout, stderr tail)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            binary, *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    except FileNotFoundError:
        raise MediaToolError(f"{label} is unavailable right now.") from None
    except asyncio.TimeoutError:
        raise MediaToolError(f"{label} timed out.") from None
    if proc.returncode != 0:
        raise MediaToolError(f"{label} failed: {err.decode(errors='replace')[-300:]}")
    return out, err.decode(errors="replace")


async def run_ffmpeg(args: list[str], label: str, timeout: int = 600) -> None:
    await run_tool("ffmpeg", ["-y", *args], label, timeout)


async def run_ffprobe_json(args: list[str], timeout: int = 60) -> bytes:
    out, _ = await run_tool("ffprobe", ["-v", "error", "-print_format", "json", *args],
                            "media probe", timeout)
    return out
