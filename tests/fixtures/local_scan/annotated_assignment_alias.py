"""Synthetic annotated capture: inspect as data, never execute this file."""

import subprocess as sp

runner: object = sp.run


def launch(command):
    copy = command
    return runner(copy, check=False, shell=True)


raise RuntimeError("SYNTHETIC_FIXTURE_MUST_NOT_EXECUTE")
