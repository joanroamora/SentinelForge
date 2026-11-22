"""Synthetic parser fixture. Analyze as data; never execute this file."""

import subprocess

runner = subprocess.run


def launch(command):
    copy = command
    return runner(copy, shell=True)


raise RuntimeError("FIXTURE_EXECUTION_IS_FORBIDDEN")
