# PFA-POLYGLOT-ENGINEERING-001 — Language and runtime strategy

**Status:** Accepted architectural policy.

PFA is language-capable, not language-driven. Python remains the orchestration and domain-integration language. A second language is introduced only when measured engineering requirements justify its operational and maintenance cost. The canonical electrical domain and application contracts remain authoritative; native modules must not create a competing model.

## Current stack and reuse policy

| Responsibility | Technology already declared | Policy |
|---|---|---|
| Numerical arrays | NumPy | Reuse first |
| Sparse linear algebra | SciPy | Reuse sparse factorization and solvers; benchmark alternatives |
| Graph algorithms | NetworkX | Adapter only, not canonical electrical aggregate |
| Units | Pint | Explicit conversions at boundaries |
| Tabular data | pandas / openpyxl | Use where tabular workflows justify them |
| Desktop | PySide6 / Qt | Preserve Qt model/view architecture |
| API/persistence services | FastAPI, SQLAlchemy, Alembic | Optional; CLI/desktop must not require a server |

## Native acceleration gate

C++ or Rust is permitted for a measured bottleneck, not as a speculative rewrite. Before a native extension is accepted, record reproducible Python baselines, representative network sizes, CPU/wall-clock/peak-memory measurements and numerical residuals. Prove algorithmic improvements and existing NumPy/SciPy primitives are insufficient.

A native module requires a narrow versioned boundary using primitive buffers/arrays, explicit ownership, differential tests against the Python reference (including ill-conditioned edge cases), Windows/Linux build and CI coverage, ABI policy, fallback behavior, and license/supply-chain review.

Preferred candidate if profiling supports it: Rust with PyO3/maturin for isolated kernels. C++ remains valid where an established solver or Qt-native integration offers a concrete advantage. No language is selected before profiling.

## Process boundaries

Do not introduce microservices for local computation. CLI, scripting and desktop use the same application services. Separate processes are justified only for isolation, parallel execution, remote collaboration, long-running jobs or deployment constraints.

## Invariants

- No duplicate electrical domain model in another language.
- No serialization of Python object internals as a cross-language contract.
- Deterministic contracts, explicit units and error semantics.
- Numerical equivalence uses documented tolerances; bitwise equality is not assumed across BLAS/LAPACK.
- Keep the Python/SciPy path unless a replacement passes platform and validation gates.
- Review dependencies for maintenance, license, security, compatibility and transitive footprint.
