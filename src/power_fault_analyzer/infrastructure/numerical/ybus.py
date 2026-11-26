"""Sparse Ybus assembly and sparse factorization for sequence networks."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING
from uuid import UUID

import numpy as np
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.linalg import splu

from power_fault_analyzer.domain.enums.sequence_source_kind import SequenceSourceKind
from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.network.sequence_networks.models import SequenceNetwork

if TYPE_CHECKING:
    from scipy.sparse.linalg import SuperLU


class SingularAdmittanceMatrixError(RuntimeError):
    """Raised when a sparse Ybus matrix cannot be factorized."""


class IncompleteSequenceNetworkError(RuntimeError):
    """Raised when an incomplete sequence model is used for numerical factorization."""


@dataclass(frozen=True, slots=True)
class YBusMatrix:
    """Sparse nodal admittance matrix and Norton current-injection vector."""

    sequence: SequenceType
    node_ids: tuple[UUID, ...]
    node_labels: tuple[str, ...]
    matrix: csr_matrix = field(repr=False, compare=False)
    current_injection_pu: np.ndarray = field(repr=False, compare=False)
    diagnostics: tuple[DomainDiagnostic, ...] = ()
    node_index: Mapping[UUID, int] = field(init=False, repr=False, compare=False)
    nonlinear_source_ids: tuple[UUID, ...] = ()
    source_current_injections_pu: Mapping[UUID, np.ndarray] = field(
        default_factory=dict, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.sequence, SequenceType):
            raise TypeError("sequence must be a SequenceType value.")
        if not isinstance(self.matrix, csr_matrix):
            raise TypeError("matrix must be a SciPy CSR sparse matrix.")
        matrix = self.matrix.copy().tocsr()
        matrix.sum_duplicates()
        matrix.sort_indices()
        if not isinstance(self.node_ids, tuple) or any(
            not isinstance(node_id, UUID) for node_id in self.node_ids
        ):
            raise TypeError("node_ids must be a tuple of UUID values.")
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("node_ids must be unique.")
        if not isinstance(self.node_labels, tuple) or any(
            not isinstance(label, str) or not label.strip() for label in self.node_labels
        ):
            raise TypeError("node_labels must be a tuple of non-empty strings.")
        if not isinstance(self.diagnostics, tuple) or any(
            not isinstance(item, DomainDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be a tuple of DomainDiagnostic values.")
        if not isinstance(self.nonlinear_source_ids, tuple) or any(
            not isinstance(source_id, UUID) for source_id in self.nonlinear_source_ids
        ):
            raise TypeError("nonlinear_source_ids must be a tuple of UUID values.")
        size = len(self.node_ids)
        if matrix.shape != (size, size):
            raise ValueError("Ybus dimensions must match the number of nodes.")
        if not np.isfinite(matrix.data.real).all() or not np.isfinite(matrix.data.imag).all():
            raise ValueError("Ybus matrix must contain finite complex values.")
        object.__setattr__(self, "matrix", matrix)
        if len(self.node_labels) != size:
            raise ValueError("node_labels length must match node_ids length.")
        injection = np.asarray(self.current_injection_pu, dtype=np.complex128).copy()
        if injection.shape != (size,):
            raise ValueError("Current-injection vector must have one value per node.")
        if not np.isfinite(injection.real).all() or not np.isfinite(injection.imag).all():
            raise ValueError("Current-injection vector must contain finite values.")
        injection.setflags(write=False)
        object.__setattr__(self, "current_injection_pu", injection)
        if not isinstance(self.source_current_injections_pu, Mapping):
            raise TypeError("source_current_injections_pu must be a mapping.")
        source_vectors: dict[UUID, np.ndarray] = {}
        for source_id, vector in self.source_current_injections_pu.items():
            if not isinstance(source_id, UUID):
                raise TypeError("Source contribution keys must be UUID values.")
            copied = np.asarray(vector, dtype=np.complex128).copy()
            if copied.shape != (size,):
                raise ValueError("Every source injection vector must match Ybus dimensions.")
            if not np.isfinite(copied.real).all() or not np.isfinite(copied.imag).all():
                raise ValueError("Source injection vectors must contain finite values.")
            copied.setflags(write=False)
            source_vectors[source_id] = copied
        object.__setattr__(self, "source_current_injections_pu", MappingProxyType(source_vectors))
        object.__setattr__(
            self,
            "node_index",
            MappingProxyType({node: i for i, node in enumerate(self.node_ids)}),
        )
        # Freeze sparse storage arrays against accidental mutation through the result.
        self.matrix.data.setflags(write=False)
        self.matrix.indices.setflags(write=False)
        self.matrix.indptr.setflags(write=False)

    @property
    def is_complete(self) -> bool:
        return not any(item.severity is DiagnosticSeverity.ERROR for item in self.diagnostics)

    @property
    def requires_nonlinear_source_solver(self) -> bool:
        return bool(self.nonlinear_source_ids)

    def to_dense(self) -> np.ndarray:
        return self.matrix.toarray()

    def factorize(self) -> SuperLU:
        """Return a SuperLU factorization or raise an explicit model/matrix error."""
        if not self.is_complete:
            error_codes = [
                item.code for item in self.diagnostics if item.severity is DiagnosticSeverity.ERROR
            ]
            raise IncompleteSequenceNetworkError(
                "Cannot factorize an incomplete sequence network; resolve diagnostics: "
                + ", ".join(error_codes)
            )
        if self.matrix.shape[0] == 0:
            raise SingularAdmittanceMatrixError("Cannot factorize an empty Ybus matrix.")
        try:
            return splu(self.matrix.tocsc())
        except RuntimeError as exc:
            raise SingularAdmittanceMatrixError(
                f"{self.sequence.value}-sequence Ybus is singular or structurally unsolvable: {exc}"
            ) from exc


class SparseYBusAssembler:
    """Stamp series branches, terminal shunts and Thevenin Norton equivalents."""

    def assemble(self, network: SequenceNetwork) -> YBusMatrix:
        if not isinstance(network, SequenceNetwork):
            raise TypeError("network must be a SequenceNetwork value.")
        node_ids = tuple(node.id for node in network.nodes)
        node_labels = tuple(node.label for node in network.nodes)
        indexes = {node_id: index for index, node_id in enumerate(node_ids)}
        rows: list[int] = []
        columns: list[int] = []
        values: list[complex] = []
        injection = np.zeros(len(node_ids), dtype=np.complex128)
        source_injections: dict[UUID, np.ndarray] = {}
        coupled_branch_ids = {
            branch_id
            for item in network.mutual_couplings
            for branch_id in (item.first_branch_id, item.second_branch_id)
        }

        def add(row: int, column: int, value: complex) -> None:
            if value != 0.0j:
                rows.append(row)
                columns.append(column)
                values.append(complex(value))

        for branch in network.branches:
            try:
                i = indexes[branch.from_node_id]
                j = indexes[branch.to_node_id]
            except KeyError as exc:
                raise ValueError(
                    f"Branch '{branch.name}' references an unknown matrix node."
                ) from exc
            tap = branch.tap_from
            if branch.id in coupled_branch_ids:
                # The coupled impedance matrix stamps this branch's series terms.
                # Retain only its terminal shunt admittances here.
                add(i, i, branch.shunt_admittance_from_pu)
                add(j, j, branch.shunt_admittance_to_pu)
                continue
            series_admittance = 1.0 / branch.series_impedance_pu
            tap_abs_sq = abs(tap) ** 2
            yff = (series_admittance + branch.shunt_admittance_from_pu) / tap_abs_sq
            yft = -series_admittance / tap.conjugate()
            ytf = -series_admittance / tap
            ytt = series_admittance + branch.shunt_admittance_to_pu
            add(i, i, yff)
            add(i, j, yft)
            add(j, i, ytf)
            add(j, j, ytt)

        for shunt in network.shunts:
            try:
                index = indexes[shunt.node_id]
            except KeyError as exc:
                raise ValueError(
                    f"Shunt '{shunt.name}' references an unknown matrix node."
                ) from exc
            add(index, index, shunt.admittance_pu)
            source_current = shunt.admittance_pu * shunt.source_voltage_pu
            injection[index] += source_current
            if shunt.source_kind is not SequenceSourceKind.PASSIVE:
                vector = source_injections.setdefault(
                    shunt.id, np.zeros(len(node_ids), dtype=np.complex128)
                )
                vector[index] += source_current

        # A multiport element is supplied as a measured/vendor impedance matrix.
        # Convert the small 3x3 port matrix to its admittance matrix before stamping.
        for element in network.multiport_elements:
            try:
                port_indices = tuple(indexes[item] for item in element.node_ids)
            except KeyError as exc:
                raise ValueError(
                    f"Multiport '{element.name}' references an unknown matrix node."
                ) from exc
            impedance = np.asarray(element.impedance_matrix_pu, dtype=np.complex128)
            try:
                port_admittance = np.linalg.inv(impedance)
            except np.linalg.LinAlgError as exc:
                raise SingularAdmittanceMatrixError(
                    f"Multiport '{element.name}' impedance matrix is singular."
                ) from exc
            if (
                not np.isfinite(port_admittance.real).all()
                or not np.isfinite(port_admittance.imag).all()
            ):
                raise ValueError(f"Multiport '{element.name}' produced non-finite admittance.")
            for local_row, global_row in enumerate(port_indices):
                for local_col, global_col in enumerate(port_indices):
                    add(global_row, global_col, port_admittance[local_row, local_col])

        # Mutual coupling is a 2-branch series impedance matrix. It is stamped
        # through each branch's incidence vector, preserving reciprocity.
        branch_by_id = {branch.id: branch for branch in network.branches}
        for coupling in network.mutual_couplings:
            first = branch_by_id[coupling.first_branch_id]
            second = branch_by_id[coupling.second_branch_id]
            impedance = np.asarray(
                [
                    [first.series_impedance_pu, coupling.mutual_impedance_pu],
                    [coupling.mutual_impedance_pu, second.series_impedance_pu],
                ],
                dtype=np.complex128,
            )
            try:
                coupled_admittance = np.linalg.inv(impedance)
            except np.linalg.LinAlgError as exc:
                raise SingularAdmittanceMatrixError(
                    "Mutually coupled branch impedance matrix is singular."
                ) from exc
            incidences = (
                ((indexes[first.from_node_id], 1.0), (indexes[first.to_node_id], -1.0)),
                ((indexes[second.from_node_id], 1.0), (indexes[second.to_node_id], -1.0)),
            )
            for branch_row in range(2):
                for branch_col in range(2):
                    mutual_admittance = coupled_admittance[branch_row, branch_col]
                    for node_row, sign_row in incidences[branch_row]:
                        for node_col, sign_col in incidences[branch_col]:
                            add(
                                node_row,
                                node_col,
                                sign_row * mutual_admittance * sign_col,
                            )

        matrix = coo_matrix(
            (np.asarray(values, dtype=np.complex128), (rows, columns)),
            shape=(len(node_ids), len(node_ids)),
            dtype=np.complex128,
        ).tocsr()
        matrix.sum_duplicates()
        matrix.sort_indices()
        return YBusMatrix(
            sequence=network.sequence,
            node_ids=node_ids,
            node_labels=node_labels,
            matrix=matrix,
            current_injection_pu=injection,
            diagnostics=network.diagnostics,
            nonlinear_source_ids=network.nonlinear_source_ids,
            source_current_injections_pu=source_injections,
        )
