# Contributing

1. Use Python 3.13 x64.
2. Create `.venv` and install `python -m pip install -e ".[dev,desktop,reports]"`.
3. Run `python -m pytest -q`, `python -m compileall -q src tests scripts`, and Ruff checks.
4. For GUI changes, run the Windows Qt acceptance scripts in `scripts/`.
5. For electrical changes, preserve explicit terminal topology and add analytical or external-reference cases.
6. Do not mark symbols IEC-conformant without a documented symbol-by-symbol verification against the applicable IEC 60617 edition.
7. New dependencies/assets must be recorded in `docs/engineering/THIRD_PARTY_LICENSE_REGISTER.md` and the release notices.

Please ensure contributions can lawfully be distributed under GPL-3.0-or-later and identify any third-party source or asset.

8. For a pull request, state the affected layer (domain, application, infrastructure or interface), the behavior changed, verification performed, and any known model limitation.
9. Never describe an automated test pass as IEC certification or independent validation. Electrical-model changes must identify the supported standard edition, assumptions, input data and explicitly unsupported cases.
10. Do not commit project files, customer data, generated release binaries, API tokens, private keys or machine-specific paths. Keep user study documents outside the application installation directory.

## Pull request checklist

- [ ] Focused change with a clear problem statement and expected behavior.
- [ ] Regression tests added or updated.
- [ ] Ruff, compile checks and relevant pytest suites pass.
- [ ] GUI changes include the Windows acceptance evidence where applicable.
- [ ] New packages, QET symbols and other redistributed assets have documented provenance and licenses.
- [ ] Release notes and user-facing limitations are accurate.
