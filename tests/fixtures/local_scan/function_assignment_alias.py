"""Synthetic parser fixture. Analyze as data; never execute this file."""


def launch(command):
    import subprocess as sp
    runner = sp.run
    copy = command
    return runner(copy, shell=True)


raise RuntimeError("FIXTURE_EXECUTION_IS_FORBIDDEN")
