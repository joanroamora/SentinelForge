"""Synthetic literal-true module import: inspect as data, never execute this file."""

if True:
    import subprocess as sp


def launch(command):
    copy = command
    return sp.run(copy, check=False, shell=True)


raise RuntimeError("SYNTHETIC_FIXTURE_MUST_NOT_EXECUTE")
