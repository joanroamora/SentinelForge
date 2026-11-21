"""Negative case for the explicit shell=True rule; not a security certification."""

import subprocess


def launch(arguments):
    return subprocess.run(arguments, shell=False, check=False)
