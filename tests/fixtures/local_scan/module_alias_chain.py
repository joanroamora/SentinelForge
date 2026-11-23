"""Synthetic module capture chain: inspect as data, never execute this file."""

import subprocess as sp

first = sp.run
runner = first


def launch(command):
    copy = command
    return runner(copy, check=False, shell=True)


raise RuntimeError("SYNTHETIC_FIXTURE_MUST_NOT_EXECUTE")
