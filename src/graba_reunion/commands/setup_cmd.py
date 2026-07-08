"""Comando setup."""
from __future__ import annotations

from graba_reunion.deps_installer import install_project_deps, install_torch_cuda
from graba_reunion.setup_wizard import run_setup_wizard


def cmd_setup(*, install_deps: bool, yes: bool) -> int:
    if install_deps:
        code = install_project_deps(yes=yes)
        if code != 0:
            return code
        return install_torch_cuda(yes=yes)
    return run_setup_wizard()
