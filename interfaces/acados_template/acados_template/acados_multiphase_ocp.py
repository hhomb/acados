# -*- coding: future_fstrings -*-
#
# Copyright (c) The acados authors.
#
# This file is part of acados.
#
# The 2-Clause BSD License
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice,
# this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
# this list of conditions and the following disclaimer in the documentation
# and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.;
#

from typing import Optional, Union
import numpy as np
from copy import deepcopy

import os

from .acados_model import AcadosModel
from .acados_ocp_cost import AcadosOcpCost
from .acados_ocp_constraints import AcadosOcpConstraints
from .acados_dims import AcadosOcpDims
from .acados_ocp_options import AcadosOcpOptions

from .acados_ocp import AcadosOcp

from .utils import get_acados_path, format_class_dict, get_shared_lib_ext


def find_non_default_fields_of_obj(obj: Union[AcadosOcpCost, AcadosOcpConstraints], stage_type='all') -> list:

    all_fields = [field for field in dir(obj) if not field.startswith("_")]
    if isinstance(obj, AcadosOcpConstraints):
        all_fields.remove('x0') # x0 is a special case and translated to other fields
        all_fields = [field for field in all_fields if not field.startswith("J")] # only idx* fields to avoid prints
    all_fields = [field for field in all_fields if not callable(getattr(obj, field))]

    if stage_type == 'all':
        pass
    elif stage_type == 'initial':
        all_fields = [field for field in all_fields if field.endswith("_0")]
    elif stage_type == 'terminal':
        all_fields = [field for field in all_fields if field.endswith("_e")]
    else:
        raise Exception(f"stage_type {stage_type} not supported.")

    obj_type = type(obj)
    dummy_obj = obj_type()
    nondefault_fields = []
    for field in all_fields:
        val = getattr(obj, field)
        default_val = getattr(dummy_obj, field)
        if isinstance(val, np.ndarray):
            if not np.array_equal(val, default_val):
                nondefault_fields.append(field)
        elif val != default_val:
            nondefault_fields.append(field)

    return nondefault_fields


class AcadosMultiphaseOcp:
    """
    Class containing the description of an optimal control problem with multiple phases.

    This object can be used to create an :py:class:`acados_template.acados_ocp_solver.AcadosOcpSolver`.

    :param N_list: list containing the number of shooting intervals for each phase

    Initial cost and constraints are defined by the first phase, terminal cost and constraints by the last phase.
    All other phases are treated as intermediate phases, where only dynamics and path cost and constraints are used.

    Limitations:
    - state dimension must be the same for all phases (all other dimensions can be different), extending would require defining a transition function.
    - solver options are shared between all phases. Interesting options to set phase-wise are:
        - integrator_type
        - collocation_type
        - cost_discretization
    """
    def __init__(self, N_list: list):

        if not isinstance(N_list, list) or len(N_list) < 1:
            raise Exception("N_list must be a list of integers.")
        if any([not isinstance(N, int) for N in N_list]):
            raise Exception("N_list must be a list of integers.")

        n_phases = len(N_list)

        self.n_phases = n_phases
        self.N_list = N_list

        self.name = 'multiphase_ocp'
        self.model = [AcadosModel() for _ in range(n_phases)]
        """Model definitions, type :py:class:`acados_template.acados_model.AcadosModel`"""
        self.cost = [AcadosOcpCost() for _ in range(n_phases)]

        """Cost definitions, type :py:class:`acados_template.acados_ocp.AcadosOcpCost`"""
        self.constraints = [AcadosOcpConstraints() for _ in range(n_phases)]
        """Constraints definitions, type :py:class:`acados_template.acados_ocp.AcadosOcpConstraints`"""

        self.phases_dims = [AcadosOcpDims() for _ in range(n_phases)]

        self.dummy_ocp_list = []

        # NOTE: this is the same for AcadosOcp
        self.solver_options = AcadosOcpOptions()
        """Solver Options, type :py:class:`acados_template.acados_ocp.AcadosOcpOptions`"""

        acados_path = get_acados_path()

        self.acados_include_path = os.path.join(acados_path, 'include').replace(os.sep, '/') # the replace part is important on Windows for CMake
        """Path to acados include directory (set automatically), type: `string`"""
        self.acados_lib_path = os.path.join(acados_path, 'lib').replace(os.sep, '/') # the replace part is important on Windows for CMake
        """Path to where acados library is located, type: `string`"""
        self.shared_lib_ext = get_shared_lib_ext()

        # get cython paths
        from sysconfig import get_paths
        self.cython_include_dirs = [np.get_include(), get_paths()['include']]

        self.__parameter_values = [np.array([]) for _ in range(n_phases)]

        self.code_export_directory = 'c_generated_code'
        """Path to where code will be exported. Default: `c_generated_code`."""

    @property
    def parameter_values(self):
        """:math:`p` - list of initial values for parameter vector.
        Type: `list` of `numpy.ndarray` of shape `(np_i, )`.
        - can be updated stagewise."""
        return self.__parameter_values

    @parameter_values.setter
    def parameter_values(self, parameter_values):
        if not isinstance(parameter_values, list):
            raise Exception('parameter_values must be a list of numpy.ndarrays.')
        elif len(parameter_values) != self.n_phases:
            raise Exception('parameter_values must be a list of length n_phases.')
        self.__parameter_values = parameter_values


    def set_phase(self, ocp: AcadosOcp, phase_idx: int) -> None:
        self.model[phase_idx] = ocp.model
        self.cost[phase_idx] = ocp.cost
        self.constraints[phase_idx] = ocp.constraints
        self.parameter_values[phase_idx] = ocp.parameter_values
        return

    def make_consistent(self) -> None:

        opts = self.solver_options

        self.N_horizon = sum(self.N_list)

        # compute phase indices
        phase_idx = np.cumsum([0] + self.N_list).tolist()

        self.start_idx = phase_idx[:-1]
        self.end_idx = phase_idx[1:]

        self.cost_start_idx = phase_idx.copy()
        self.cost_start_idx[0] += 1

        # make model names unique if necessary
        model_name_list = [self.model[i].name for i in range(self.n_phases)]
        n_names = len(set(model_name_list))
        if n_names != self.n_phases:
            print(f"model names are not unique: got {model_name_list}")
            print("adding _i to model names")
            for i in range(self.n_phases):
                self.model[i].name = f"{self.model[i].name}_{i}"
            model_name_list = [self.model[i].name for i in range(self.n_phases)]
            print(f"new model names are {model_name_list}")


        for i in range(self.n_phases):

            # create dummy ocp
            ocp = AcadosOcp()
            ocp.dims = self.phases_dims[i]
            ocp.dims.N = self.N_horizon # NOTE: to not change options when making ocp consistent
            ocp.model = self.model[i]
            ocp.constraints = self.constraints[i]
            ocp.cost = self.cost[i]
            ocp.parameter_values = self.parameter_values[i]
            ocp.solver_options = opts

            if i != self.n_phases - 1:
                nondefault_fields = []
                nondefault_fields += find_non_default_fields_of_obj(ocp.cost, stage_type='terminal')
                nondefault_fields += find_non_default_fields_of_obj(ocp.constraints, stage_type='terminal')
                nondefault_fields += find_non_default_fields_of_obj(ocp.model, stage_type='terminal')
                if len(nondefault_fields) > 0:
                    print(f"Phase {i} contains non-default terminal fields: {nondefault_fields}, which will be ignored.")
            elif i != 0:
                nondefault_fields = []
                nondefault_fields += find_non_default_fields_of_obj(ocp.cost, stage_type='initial')
                nondefault_fields += find_non_default_fields_of_obj(ocp.constraints, stage_type='initial')
                nondefault_fields += find_non_default_fields_of_obj(ocp.model, stage_type='initial')
                if len(nondefault_fields) > 0:
                    print(f"Phase {i} contains non-default initial fields: {nondefault_fields}, which will be ignored.")

            print(f"Calling make_consistent for phase {i}.")
            ocp.make_consistent()

            self.dummy_ocp_list.append(ocp)

        nx_list = [self.phases_dims[i].nx for i in range(self.n_phases)]
        if len(set(nx_list)) != 1:
            raise Exception(f"make_consistent: all phases must have the same dimension nx, detected nx_list = {nx_list}.")
        return


    def to_dict(self) -> dict:
        # Copy ocp object dictionary
        ocp_dict = dict(deepcopy(self).__dict__)
        del ocp_dict['dummy_ocp_list']

        # convert acados classes to dicts
        for key, v in ocp_dict.items():
            if isinstance(v, (AcadosOcpOptions)):
                ocp_dict[key]=dict(getattr(self, key).__dict__)
            if isinstance(v, list):
                for i, item in enumerate(v):
                    if isinstance(item, (AcadosModel, AcadosOcpDims, AcadosOcpConstraints, AcadosOcpCost)):
                        ocp_dict[key][i] = format_class_dict(dict(item.__dict__))

        ocp_dict = format_class_dict(ocp_dict)
        return ocp_dict
