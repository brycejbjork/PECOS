#  =========================================================================  #
#   Copyright 2018 National Technology & Engineering Solutions of Sandia,
#   LLC (NTESS). Under the terms of Contract DE-NA0003525 with NTESS,
#   the U.S. Government retains certain rights in this software.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#  =========================================================================  #

"""
Simple error generator meant to demonstrate a basic error generator that produces errors.
"""
from .class_errors_circuit import ErrorCircuits
from ..circuits.quantum_circuit import QuantumCircuit
from .parent_class_error_gen import ParentErrorGen


class XZGen(ParentErrorGen):
    """
    A simple error generator for the depolarizing model.

    This error generator does not allow much modification of the error model.
    """

    measurements = {'measure X', 'measure Y', 'measure Z'}
    inits = {'init |0>', 'init |1>', 'init |+>', 'init |->', 'init |+i>', 'init |-i>'}
    two_qubits = {'CNOT', 'CZ', 'SWAP', 'G'}

    inits_z = {'init |0>', 'init |1>'}
    inits_x = {'init |+>', 'init |->'}
    inits_y = {'init |+i>', 'init |-i>'}

    error_two_paulis_collection = [
        ('I', 'X'), ('I', 'Z'),
        ('X', 'I'), ('X', 'X'), ('X', 'Z'),
        ('Z', 'I'), ('Z', 'X'), ('Z', 'Z')]

    def __init__(self, model_level='circuit', has_idle_errors=False, perp_errors=False):
        """

        Args:
            model_level(str):
            has_idle_errors(bool):
            perp_errors(bool):
        """

        super().__init__()

        self.has_idle_errors = has_idle_errors
        self.perp_error = perp_errors

        self.gen = self.generator_class()
        self.gen.set_gate_group('measurements', self.measurements)
        self.gen.set_gate_group('inits', self.inits)
        self.gen.set_gate_group('two_qubits', self.two_qubits)

        xerror = self.gen.ErrorStaticSymbol('X')
        zerror = self.gen.ErrorStaticSymbol('Z')
        xerror_before = self.gen.ErrorStaticSymbol('X', after=False)
        zerror_before = self.gen.ErrorStaticSymbol('Z', after=False)
        pauli_errors = self.gen.ErrorSet({'X', 'Z'})
        pauli_errors_before = self.gen.ErrorSet({'X', 'Z'}, after=False)
        two_pauli_errors = self.gen.ErrorSetTwoQuditTensorProduct(self.error_two_paulis_collection)

        if model_level == 'code_capacity':

            self.has_data_errors = True
            self.has_unitary_errors = False
            self.has_meas_errors = False

            # Data qubit errors
            self.gen.set_gate_error('data', pauli_errors.error_func)

            # Don't generate any other errors

        elif model_level == 'phenomenological':

            self.has_data_errors = True
            self.has_unitary_errors = False
            self.has_meas_errors = True

            # Generate data errors
            self.gen.set_default_error('data', pauli_errors.error_func)

            # Generate measurement errors
            self.gen.set_group_error('measurements', pauli_errors_before.error_func)
            # Don't generate any other errors

        elif model_level == 'circuit':

            self.has_data_errors = False
            self.has_unitary_errors = True
            self.has_meas_errors = True

            # Don't generate data errors
            self.gen.set_gate_error('data', False)  # Don't generate errors for data qudits.

            # Generate measurement errors (before errors)
            self.gen.set_group_error('measurements', pauli_errors_before.error_func)
            # Set two-qubits
            self.gen.set_group_error('two_qubits', two_pauli_errors.error_func)
            # By default generate pauli errors. (It is expected that this is only for one-qubit and init gates.)
            self.gen.set_default_error(pauli_errors.error_func)
        else:
            raise Exception('Can not handle model_level == %s' % model_level)

        # If errors need to be perpendicular to inits and measurements.
        if self.perp_error and model_level != 'code_capacity':
            self.gen.set_gate_error('measure X', zerror_before.error_func)
            self.gen.set_gate_error('measure Y', zerror_before.error_func)
            self.gen.set_gate_error('measure Z', xerror_before.error_func)

            if model_level == 'circuit':
                self.gen.set_group_error(self.inits_x, zerror.error_func)
                self.gen.set_group_error(self.inits_y, zerror.error_func)
                self.gen.set_group_error(self.inits_z, xerror.error_func)

        if has_idle_errors:
            self.gen.set_gate_error('idle', pauli_errors.error_func)

    def start(self, logical_circuit, error_params):
        """
        Start up at the beginning of a circuit simulation.

        Args:
            logical_circuit:
            error_params:

        Returns:

        """

        self.error_circuits = ErrorCircuits()
        self.logical_circuit = logical_circuit
        self.error_params = error_params

        return self.error_circuits

    def generate(self, logical_gate, logical_coord, tick_index):
        """
        Returns before errors, after errors, and replaced locations for the given key (args).

        Returns:

        """

        # Simple model where for each gate there is a probability "p" for an X, Y, or Z error to occur.

        before = QuantumCircuit()
        after = QuantumCircuit()
        replace = set([])

        # instr_index = logical_coord[1].instr_index
        instr_index = logical_coord[1]

        # Need to iterate over the tick.
        instr_circuit = logical_gate.circuits[instr_index]

        # Data errors
        # -----------
        if self.has_data_errors and tick_index == 0:
            data_qudits = logical_gate.qecc.data_qudit_set

            self.gen.create_errors(self, 'data', data_qudits, after, before, replace)

        # unitary and measurement errors
        # ------------------------------
        if self.has_meas_errors or self.has_unitary_errors:
            for symbol, gate_locations in instr_circuit.items(tick_index, params=False):

                self.gen.create_errors(self, symbol, gate_locations, after, before, replace)

        # idle errors
        # -----------
        if self.has_idle_errors:
            inactive_qudits = logical_gate.qecc.qudit_set - instr_circuit.active_qudits[tick_index]
            self.gen.create_errors(self, 'idle', inactive_qudits, after, before, replace)

        self.error_circuits.add_circuits(key=(logical_coord, tick_index), before_errors=before, after_errors=after)

        # return {'before': before, 'after': after}
