"""
Window Tiler — macOS Window Grid Positioning
=============================================

Tiles Camoufox windows in a grid pattern.
macOS only — no-op on other platforms.
"""

import platform


def get_screen_size() -> tuple[int, int]:
    """Get screen size. Returns (width, height)."""
    if platform.system() == "Darwin":
        try:
            import subprocess

            result = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True,
                text=True,
            )
            # Parse resolution from output
            for line in result.stdout.split("\n"):
                if "Resolution:" in line:
                    parts = line.split()
                    w = int(parts[1])
                    h = int(parts[3])
                    return w, h
        except Exception:
            pass

    # Default fallback
    return 1920, 1080


def tile_all_camoufox_windows():
    """Tile all Camoufox windows in a grid.

    macOS only — uses AppleScript.
    """
    if platform.system() != "Darwin":
        return

    try:
        import subprocess

        script = """
        tell application "System Events"
            set camoufoxProcesses to every process whose name contains "camoufox"
            repeat with proc in camoufoxProcesses
                set winCount to count of windows of proc
                if winCount > 0 then
                    set screenWidth to 1920
                    set screenHeight to 1080
                    set cols to 2
                    set rows to 2
                    set winWidth to screenWidth div cols
                    set winHeight to screenHeight div rows
                    repeat with i from 1 to winCount
                        set col to (i - 1) mod cols
                        set row to (i - 1) div cols
                        set x to col * winWidth
                        set y to row * winHeight
                        set position of window i of proc to {x, y}
                        set size of window i of proc to {winWidth, winHeight}
                    end repeat
                end if
            end repeat
        end tell
        """

        subprocess.run(["osascript", "-e", script], capture_output=True)

    except Exception:
        pass
