"""Synthetic scope example: inspect as data, never execute this file."""

import subprocess as sp


def unrelated():
    sp = "SYNTHETIC_LOCAL_VALUE"
    return sp


def launch(command):
    return sp.run(command, check=False, shell=True)


raise RuntimeError("SYNTHETIC_FIXTURE_MUST_NOT_EXECUTE")
