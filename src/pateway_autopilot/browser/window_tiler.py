"""
Window Tiler — macOS Window Grid Positioning
=============================================

Tiles Camoufox windows in a grid pattern.
macOS only — no-op on other platforms.
"""

import asyncio
import platform
import math


def get_screen_size() -> tuple[int, int]:
    """Get screen size. Returns (width, height)."""
    if platform.system() == "Darwin":
        try:
            import subprocess

            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # Parse resolution from output
            import re
            for line in result.stdout.split("\n"):
                if "Resolution:" in line:
                    match = re.search(r"(\d+)\s*x\s*(\d+)", line)
                    if match:
                        return int(match.group(1)), int(match.group(2))
        except Exception:
            pass

    # Default fallback
    return 1920, 1080


async def get_screen_size_async() -> tuple[int, int]:
    """Get screen size without blocking event loop."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_screen_size)


def _calculate_grid(win_count: int) -> tuple[int, int]:
    """Calculate optimal grid dimensions for given window count.

    Returns (cols, rows) that creates a near-square grid.
    """
    if win_count <= 0:
        return 1, 1
    if win_count <= 2:
        return win_count, 1
    cols = math.ceil(math.sqrt(win_count))
    rows = math.ceil(win_count / cols)
    return cols, rows


def tile_all_camoufox_windows():
    """Tile all Camoufox windows in a grid.

    macOS only — uses AppleScript.
    """
    if platform.system() != "Darwin":
        return

    try:
        import subprocess

        screen_w, screen_h = get_screen_size()
        script = f"""
        tell application "System Events"
            set camoufoxProcesses to every process whose name contains "camoufox"
            repeat with proc in camoufoxProcesses
                set winCount to count of windows of proc
                if winCount > 0 then
                    set screenWidth to {screen_w}
                    set screenHeight to {screen_h}
                    set cols to 2
                    set rows to 2
                    set winWidth to screenWidth div cols
                    set winHeight to screenHeight div rows
                    repeat with i from 1 to winCount
                        set col to (i - 1) mod cols
                        set row to (i - 1) div cols
                        set x to col * winWidth
                        set y to row * winHeight
                        set position of window i of proc to {{x, y}}
                        set size of window i of proc to {{winWidth, winHeight}}
                    end repeat
                end if
            end repeat
        end tell
        """

        result = subprocess.run(["osascript", "-e", str(script)], capture_output=True, timeout=15)
        if result.returncode != 0 and result.stderr:
            from ..utils.logger import log_warn
            log_warn(f"Window tiling failed: {result.stderr.decode('utf-8', errors='replace')[:200]}")

    except Exception:
        pass


async def tile_all_camoufox_windows_async():
    """Async version — runs system_profiler off the event loop."""
    if platform.system() != "Darwin":
        return

    try:
        screen_w, screen_h = await get_screen_size_async()

        # Calculate dynamic grid based on window count
        import subprocess
        # Get window count first
        count_script = '''
        tell application "System Events"
            set total to 0
            repeat with proc in (every process whose name contains "camoufox")
                set total to total + (count of windows of proc)
            end repeat
            return total
        end tell
        '''
        result = subprocess.run(["osascript", "-e", count_script], capture_output=True, text=True, timeout=10)
        win_count = 1
        if result.returncode == 0 and result.stdout.strip().isdigit():
            win_count = int(result.stdout.strip())

        cols, rows = _calculate_grid(win_count)

        script = f"""
        tell application "System Events"
            set camoufoxProcesses to every process whose name contains "camoufox"
            repeat with proc in camoufoxProcesses
                set winCount to count of windows of proc
                if winCount > 0 then
                    set screenWidth to {screen_w}
                    set screenHeight to {screen_h}
                    set cols to {cols}
                    set rows to {rows}
                    set winWidth to screenWidth div cols
                    set winHeight to screenHeight div rows
                    repeat with i from 1 to winCount
                        set col to (i - 1) mod cols
                        set row to (i - 1) div cols
                        set x to col * winWidth
                        set y to row * winHeight
                        set position of window i of proc to {{x, y}}
                        set size of window i of proc to {{winWidth, winHeight}}
                    end repeat
                end if
            end repeat
        end tell
        """

        result = subprocess.run(["osascript", "-e", str(script)], capture_output=True, timeout=15)
        if result.returncode != 0 and result.stderr:
            from ..utils.logger import log_warn
            log_warn(f"Window tiling failed: {result.stderr.decode('utf-8', errors='replace')[:200]}")

    except Exception:
        pass
