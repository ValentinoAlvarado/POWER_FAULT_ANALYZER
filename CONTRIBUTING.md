# Contributing

1. Use Python 3.13 x64.
2. Create `.venv` and install `python -m pip install -e ".[dev,desktop,reports]"`.
3. Run `python -m pytest -q`, `python -m compileall -q src tests scripts`, and Ruff checks.
4. For GUI changes, run the Windows Qt acceptance scripts in `scripts/`.
5. For electrical changes, preserve explicit terminal topology and add analytical or external-reference cases.
6. Do not mark symbols IEC-conformant without a documented symbol-by-symbol verification against the applicable IEC 60617 edition.
7. New dependencies/assets must be recorded in `docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md` and the release notices.

Please ensure contributions can lawfully be distributed under GPL-3.0-or-later and identify any third-party source or asset.
