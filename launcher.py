"""Launcher for the packaged Windows executable (SDLCOrchestrator.exe).

Build with build_exe.bat (PyInstaller). When frozen, the app source folder
(app.py, pages/, services/, database/) and config.json must sit NEXT TO the
exe; the launcher starts the Streamlit dashboard on http://localhost:8501
and opens it in the browser. No Python installation is needed to run it.
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    if getattr(sys, "frozen", False):
        # Running from the built exe: sources and config.json live beside it.
        root = os.path.dirname(sys.executable)
    else:
        root = os.path.dirname(os.path.abspath(__file__))

    app = os.path.join(root, "app.py")
    if not os.path.exists(app):
        print("app.py was not found next to the executable.")
        print("Keep SDLCOrchestrator.exe inside the sdlc_orchestrator folder.")
        input("Press Enter to exit...")
        return

    os.chdir(root)
    from streamlit.web import cli as stcli

    sys.argv = [
        "streamlit",
        "run",
        app,
        "--server.port", "8501",
        "--server.headless", "false",
    ]
    sys.exit(stcli.main())


if __name__ == "__main__":
    main()
