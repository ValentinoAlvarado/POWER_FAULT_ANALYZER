from uuid import uuid4

import numpy as np
import pytest

from power_fault_analyzer.domain.enums.sequence_type import SequenceType
from power_fault_analyzer.domain.value_objects.diagnostic import (
    DiagnosticSeverity,
    DomainDiagnostic,
)
from power_fault_analyzer.infrastructure.numerical.ybus import (
    IncompleteSequenceNetworkError,
    SingularAdmittanceMatrixError,
    SparseYBusAssembler,
    YBusMatrix,
)
from power_fault_analyzer.network.sequence_networks.models import (
    SequenceBranch,
    SequenceNetwork,
    SequenceNode,
    SequenceShunt,
)


def make_sequence_network(*, source=True):
    node_a, node_b = uuid4(), uuid4()
    source_id = uuid4()
    branch = SequenceBranch(
        id=uuid4(),
        name="AB",
        from_node_id=node_a,
        to_node_id=node_b,
        series_impedance_pu=0.1 + 0.2j,
        shunt_admittance_from_pu=0.01 + 0.02j,
        shunt_admittance_to_pu=0.01 + 0.02j,
    )
    shunts = (SequenceShunt(source_id, "GRID", node_a, 5.0 - 10.0j, 1.0 + 0.0j),) if source else ()
    return (
        SequenceNetwork(
            network_id=uuid4(),
            sequence=SequenceType.POSITIVE,
            nodes=(SequenceNode(node_a, "A"), SequenceNode(node_b, "B")),
            branches=(branch,),
            shunts=shunts,
        ),
        node_a,
        node_b,
    )


def test_ybus_stamps_pi_branch_and_source_norton_injection():
    network, node_a, node_b = make_sequence_network(source=True)
    result = SparseYBusAssembler().assemble(network)
    y = 1.0 / (0.1 + 0.2j)
    expected = np.array(
        [
            [y + 0.01 + 0.02j + 5.0 - 10.0j, -y],
            [-y, y + 0.01 + 0.02j],
        ],
        dtype=np.complex128,
    )
    assert result.matrix.toarray() == pytest.approx(expected)
    assert result.current_injection_pu[result.node_index[node_a]] == pytest.approx(
        (5.0 - 10.0j) * (1.0 + 0.0j)
    )
    assert result.current_injection_pu[result.node_index[node_b]] == 0j


def test_ybus_applies_complex_off_nominal_tap_with_conjugate_stamps():
    node_a, node_b = uuid4(), uuid4()
    tap = np.exp(1j * np.deg2rad(30.0))
    branch = SequenceBranch(
        id=uuid4(),
        name="TAP",
        from_node_id=node_a,
        to_node_id=node_b,
        series_impedance_pu=0.05 + 0.2j,
        tap_from=tap,
    )
    network = SequenceNetwork(
        network_id=uuid4(),
        sequence=SequenceType.POSITIVE,
        nodes=(SequenceNode(node_a, "HV"), SequenceNode(node_b, "LV")),
        branches=(branch,),
        shunts=(),
    )
    matrix = SparseYBusAssembler().assemble(network).to_dense()
    y = 1 / (0.05 + 0.2j)
    assert matrix[0, 0] == pytest.approx(y / abs(tap) ** 2)
    assert matrix[0, 1] == pytest.approx(-y / tap.conjugate())
    assert matrix[1, 0] == pytest.approx(-y / tap)
    assert matrix[1, 1] == pytest.approx(y)


def test_ybus_is_csr_and_exposes_immutable_rhs():
    network, _, _ = make_sequence_network()
    result = SparseYBusAssembler().assemble(network)
    assert result.matrix.format == "csr"
    with pytest.raises(ValueError):
        result.current_injection_pu[0] = 1.0


def test_ybus_factorization_reports_floating_singular_network():
    network, _, _ = make_sequence_network(source=False)
    floating_branch = SequenceBranch(
        id=uuid4(),
        name="FLOATING-AB",
        from_node_id=network.nodes[0].id,
        to_node_id=network.nodes[1].id,
        series_impedance_pu=0.1 + 0.2j,
    )
    floating_network = SequenceNetwork(
        network_id=network.network_id,
        sequence=network.sequence,
        nodes=network.nodes,
        branches=(floating_branch,),
        shunts=(),
    )
    result = SparseYBusAssembler().assemble(floating_network)
    with pytest.raises(SingularAdmittanceMatrixError):
        result.factorize()


def test_ybus_factorization_succeeds_when_network_is_referenced():
    network, _, _ = make_sequence_network(source=True)
    result = SparseYBusAssembler().assemble(network)
    factor = result.factorize()
    assert factor is not None


def test_sequence_network_rejects_branch_referencing_unknown_node():
    node_a, node_b = uuid4(), uuid4()
    branch = SequenceBranch(uuid4(), "BAD", node_a, node_b, 0.1 + 0.2j)
    with pytest.raises(ValueError, match="unknown node"):
        SequenceNetwork(
            network_id=uuid4(),
            sequence=SequenceType.POSITIVE,
            nodes=(SequenceNode(node_a, "A"),),
            branches=(branch,),
            shunts=(),
        )


def test_sequence_network_completeness_tracks_error_diagnostics():
    diagnostic = DomainDiagnostic("SEQ-TEST", "Missing model", DiagnosticSeverity.ERROR)
    model = SequenceNetwork(
        network_id=uuid4(),
        sequence=SequenceType.ZERO,
        nodes=(),
        branches=(),
        shunts=(),
        diagnostics=(diagnostic,),
    )
    assert not model.is_complete


def test_ybus_refuses_factorization_when_sequence_model_has_error_diagnostics():
    diagnostic = DomainDiagnostic(
        "SEQ-MODEL-MISSING",
        "A required equipment sequence model is missing.",
        DiagnosticSeverity.ERROR,
    )
    network, _, _ = make_sequence_network(source=True)
    incomplete_network = SequenceNetwork(
        network_id=network.network_id,
        sequence=network.sequence,
        nodes=network.nodes,
        branches=network.branches,
        shunts=network.shunts,
        diagnostics=(diagnostic,),
    )
    result = SparseYBusAssembler().assemble(incomplete_network)
    assert not result.is_complete
    with pytest.raises(IncompleteSequenceNetworkError, match="SEQ-MODEL-MISSING"):
        result.factorize()


def test_ybus_preserves_nonlinear_source_requirements():
    source_id = uuid4()
    network, _, _ = make_sequence_network(source=True)
    network_with_converter = SequenceNetwork(
        network_id=network.network_id,
        sequence=network.sequence,
        nodes=network.nodes,
        branches=network.branches,
        shunts=network.shunts,
        nonlinear_source_ids=(source_id,),
    )
    result = SparseYBusAssembler().assemble(network_with_converter)
    assert result.requires_nonlinear_source_solver
    assert result.nonlinear_source_ids == (source_id,)


def test_ybus_rejects_non_finite_matrix_entries():
    node_a, node_b = uuid4(), uuid4()
    network = SequenceNetwork(
        network_id=uuid4(),
        sequence=SequenceType.POSITIVE,
        nodes=(SequenceNode(node_a, "A"), SequenceNode(node_b, "B")),
        branches=(
            SequenceBranch(
                id=uuid4(),
                name="EXTREME",
                from_node_id=node_a,
                to_node_id=node_b,
                series_impedance_pu=1.0 + 0j,
                shunt_admittance_from_pu=1e300 + 0j,
                tap_from=2e-15 + 0j,
            ),
        ),
        shunts=(),
    )
    with pytest.raises(ValueError, match="finite complex values"):
        SparseYBusAssembler().assemble(network)


def test_ybus_result_owns_a_copy_of_the_sparse_matrix():
    network, _, _ = make_sequence_network(source=True)
    assembled = SparseYBusAssembler().assemble(network)
    external_matrix = assembled.matrix.copy()
    result = YBusMatrix(
        sequence=assembled.sequence,
        node_ids=assembled.node_ids,
        node_labels=assembled.node_labels,
        matrix=external_matrix,
        current_injection_pu=assembled.current_injection_pu,
        diagnostics=assembled.diagnostics,
        nonlinear_source_ids=assembled.nonlinear_source_ids,
    )
    original_value = result.matrix[0, 0]
    external_matrix[0, 0] = 999.0 + 0j
    assert result.matrix[0, 0] == pytest.approx(original_value)
