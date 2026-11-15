"""htTamer for Windows: the program the installer's shortcut starts.

With no arguments it starts the dashboard on this computer and opens it in the browser.
htTamer runs each measurement as `<python> -m subtune <command>`; in the installed (frozen) copy
that python is this program, so `-m subtune ...` is handled here too.
"""
import sys
import threading
import time
import webbrowser


def main():
    args = sys.argv[1:]
    from subtune.cli import main as cli
    if args[:2] == ["-m", "subtune"]:
        return cli(args[2:])
    if args:
        return cli(args)
    port = 8765
    print("htTamer is starting. Keep this window open while you use it; close it to stop htTamer.")
    print(f"Open http://127.0.0.1:{port} in your browser if it doesn't open by itself.")
    threading.Thread(target=lambda: (time.sleep(2.5), webbrowser.open(f"http://127.0.0.1:{port}")), daemon=True).start()
    return cli(["serve", "--port", str(port)])


if __name__ == "__main__":
    sys.exit(main())
