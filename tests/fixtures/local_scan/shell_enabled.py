"""Static input only. SentinelForge must never import or execute this file."""

import subprocess


def launch(command):
    return subprocess.run(command, shell=True, check=False)


raise RuntimeError("This fixture must not be executed.")
