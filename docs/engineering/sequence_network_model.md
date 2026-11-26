# ND-005 — Sequence Network and Ybus Model

## Scope

ND-005 converts the registered balanced three-phase physical network into three
independent symmetrical-component network models and assembles their sparse
nodal-admittance matrices. It does not yet solve a short-circuit boundary-value
problem; that belongs to the fault-analysis increments.

## System bases

The three-phase apparent-power base is common to the study. The line-to-line
voltage base is specified per physical bus, because a multi-voltage network has
multiple voltage levels. `SystemBaseSet.from_network()` initializes each bus
voltage base from that bus's nominal voltage. Transformer winding voltage bases
must match the winding rated voltages.

For each bus k:

\[
Z_{B,k}=\frac{V_{B,k,LL}^{2}}{S_B},\qquad
Y_{B,k}=\frac{1}{Z_{B,k}}
\]

Line/cable branch values supplied in SI are converted using the base of the
connected voltage level. Series impedance is divided by Zbase; shunt admittance
is multiplied by Zbase.

## Network abstractions

`SequenceNetwork` contains:

- `SequenceNode`: physical bus or auxiliary transformer star node;
- `SequenceBranch`: two-terminal series branch with optional end shunts and a
  complex from-side tap;
- `SequenceShunt`: shunt to the sequence reference, including Thevenin sources;
- `DomainDiagnostic`: errors, warnings and explicit blocked-path information;
- `nonlinear_source_ids`: converter sources that require a current-injection
  solver rather than a fixed Thevenin stamp.

`SequenceNetworkSet` groups positive, negative and zero sequence networks.

## Ybus stamping

For a branch with series admittance y, from-side complex tap a, and terminal
shunt admittances ysh,f and ysh,t, the assembler stamps:

\[
Y_{ff}=\frac{y+y_{sh,f}}{|a|^2},\quad
Y_{ft}=-\frac{y}{a^*},\quad
Y_{tf}=-\frac{y}{a},\quad
Y_{tt}=y+y_{sh,t}
\]

For a Thevenin source with internal sequence voltage E and impedance Z, its
Norton equivalent is stamped as Y=1/Z on the diagonal and I=Y E on the right-
hand-side vector. Negative- and zero-sequence source internal voltages are zero
in this model.

The assembler uses SciPy COO accumulation and returns a CSR matrix. Explicit
sparse LU factorization is available through `YBusMatrix.factorize()`. Factorization
is refused when the sequence model contains ERROR diagnostics; an empty matrix,
floating or unreferenced network is not silently regularized. The matrix result
also preserves converter source IDs so a future nonlinear/current-injection
solver cannot mistake the passive Ybus for a complete converter-inclusive model.

## Transformer sequence treatment

### Two-winding transformers

Positive- and negative-sequence leakage impedances are referred to the system
base and stamped as a two-terminal branch. The vector-group clock displacement
is represented as a complex tap: the negative-sequence tap is the conjugate of
the positive-sequence tap. The tap convention is documented on
`SequenceBranch.tap_from`.

The initial reduced zero-sequence adapter supports the following explicit cases:

- grounded star/zigzag on both windings: a series zero-sequence branch, including
  the 3Zn neutral terms on both sides;
- grounded star/zigzag on one winding and delta on the other: a grounding shunt
  at the grounded winding terminal, including its 3Zn term;
- configurations without a declared closed return path: no zero-sequence stamp,
  with an informational diagnostic.

The supplied transformer Z0 data must be a manufacturer- or test-derived
sequence equivalent appropriate to the actual vector group and core construction.
ND-005 does not infer Z0 from Z1, derive a magnetizing/core-return branch from
geometry, or select empirical core-type correction factors.

### Three-winding transformers

Positive- and negative-sequence pairwise test impedances are converted to star
arms and connected through a deterministic internal node. Pairwise vector-group
clock numbers define winding taps.

No three-winding zero-sequence circuit is inferred in ND-005, including the
all-grounded-star case. Pairwise short-circuit impedance data and winding
connection labels alone do not fully specify the zero-sequence external port
network, delta circulating-current paths, or magnetic core return path. ND-005
also does not yet expose a multiport zero-sequence model-provider contract for
this equipment. The builder therefore emits an ERROR diagnostic for every
three-winding zero-sequence request. A later increment must add an explicit,
validated manufacturer/model-specific multiport equivalent before this case can
be solved. This avoids constructing a plausible but physically unsupported
network.

## Source treatment

Thevenin-type sources implementing `SourceModelProvider` are stamped using their
sequence availability status:

- AVAILABLE: stamp the sequence impedance and positive-sequence Norton source;
- BLOCKED: do not stamp a path and record an INFO diagnostic;
- UNSPECIFIED: do not guess; record an ERROR diagnostic.

Converter sources implementing `FaultCurrentCapabilityProvider` are not
converted into fixed impedances. Their identifiers and current capabilities
remain available for a future controlled current-injection solver; the current
sequence model records a WARNING.

## Topology and singularity

The builder analyzes connectivity to a common sequence reference using NetworkX.
Components without a path to the reference are reported as warnings. The sparse
assembler exposes LU factorization, which raises `SingularAdmittanceMatrixError`
when the assembled matrix is singular. No artificial shunt or numerical epsilon
is injected to hide a physically floating sequence network.

## Explicit non-goals of ND-005

- no short-circuit current solution yet;
- no fault interconnection strategy yet;
- no IEC 60909 correction factors;
- no automatic conductor-geometry parameter derivation;
- no converter control/dynamic current-injection solver;
- no general zero-sequence model for every three-winding transformer connection;
- no phase-domain (unbalanced prefault) network model.


## Physical line length metadata (ND-007)

`SequenceBranch.length_km` is populated by the sequence-network builder for
`Line` equipment and its overhead-line/underground-cable subclasses. It is metadata
for interior fault localization; it does not alter the ND-005 Ybus stamp. Lumped
series reactances and transformer equivalents do not receive a physical line length
and cannot be selected as line-interior fault targets. See
`short_circuit_line_faults.md` for the ND-007 branch-splitting procedure.
