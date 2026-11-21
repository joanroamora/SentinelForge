"""Synthetic source for the local walkthrough. Never import or execute it."""

import subprocess


def launch(command):
    staged = command
    prepared = staged
    return subprocess.run(prepared, shell=True, check=False)


def launch_with_branch(command, use_example):
    if use_example:
        command = "SYNTHETIC_EXAMPLE_VALUE"
    return subprocess.run(command, shell=True, check=False)


raise RuntimeError("Static fixture: execution is forbidden.")
