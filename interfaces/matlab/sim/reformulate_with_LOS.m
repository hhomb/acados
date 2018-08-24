function [ gnsf, reordered_model ] = ...
        reformulate_with_LOS( model, gnsf, print_info)
%   This file is part of acados.
%
%   acados is free software; you can redistribute it and/or
%   modify it under the terms of the GNU Lesser General Public
%   License as published by the Free Software Foundation; either
%   version 3 of the License, or (at your option) any later version.
%
%   acados is distributed in the hope that it will be useful,
%   but WITHOUT ANY WARRANTY; without even the implied warranty of
%   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
%   Lesser General Public License for more details.
%
%   You should have received a copy of the GNU Lesser General Public
%   License along with acados; if not, write to the Free Software Foundation,
%   Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
%
%   Author: Jonathan Frey: jonathanpaulfrey(at)gmail.com

%% Description:
% This function takes an intitial transcription of the implicit ODE model
% "model" into "gnsf" and reformulates "gnsf" with a linear output system
% (LOS), containing as many states of the model as possible.
% Therefore it might be that the state vector and the implicit function
% vector have to be reordered. This reordered model is part of the output,
% namely reordered_model.

%% import CasADi and load models

import casadi.*

% % model
x = model.x;
xdot = model.xdot;
u = model.u;
z = model.z;

% % GNSF
% get dimensions
nx  = gnsf.nx;
nz  = gnsf.nz;

% get model matrices
A  = gnsf.A;
B  = gnsf.B;
C  = gnsf.C;
E  = gnsf.E;
c  = gnsf.c;

A_LO = gnsf.A_LO;

y = gnsf.y;

phi_old = gnsf.phi_expr;

if print_info
disp(' ');
disp('=================================================================');
disp('=== the algorithm will now try to detect linear output system ===');
disp('=================================================================');
disp(' ');
end

%% build initial I_x1 and I_x2_candidates
% I_x1: all components of x for which either xii or xdot_ii enters y;
% I_LOS_candidates: the remaining components

I_nsf_components = [];
I_LOS_candidates = [];
for ii = 1:nx
    if or(y.which_depends(x(ii)), y.which_depends(xdot(ii)))
        % i.e. xii or xiidot are part of y, and enter phi_expr
        if print_info
            disp(['xii is part of x1, ii = ', num2str(ii)]);
        end
        I_nsf_components = union(I_nsf_components, ii);
    else
        % i.e. neither xii nor xiidot are part of y, i.e. enter phi_expr
        I_LOS_candidates = union(I_LOS_candidates, ii);
    end
end
if print_info
    disp(' ');
end
for ii = 1:nz
    if y.which_depends(z(ii))
        % i.e. xii or xiidot are part of y, and enter phi_expr
        if print_info
            disp(['zii is part of z1, ii = ', num2str(ii)]);
        end
        I_nsf_components = union(I_nsf_components, ii + nx);
    else
        % i.e. neither xii nor xiidot are part of y, i.e. enter phi_expr
        I_LOS_candidates = union(I_LOS_candidates, ii + nx);
    end
end

if print_info
disp(' ');
end

new_nsf_components = I_nsf_components;
I_nsf_eq = [];
unsorted_dyn = 1:nx + nz;
xdot_z = [xdot; z];

%% determine components of Linear Output System
% determine maximal index set I_x2
% such that the components x(I_x2) can be written as a LOS
while true
    %% find equations corresponding to I_nsf_components
    for ii = new_nsf_components
        I_eq = intersect(find(E(:,ii)), unsorted_dyn);
        if length(I_eq) == 1
            i_eq = I_eq;
        elseif length(I_eq) > 1 % x_ii_dot occurs in more than 1 eq linearly
            number_of_eq = 1;
            candidate_dependencies = zeros(length(I_eq), 1);
            for eq = I_eq
                candidate_dependencies(number_of_eq) = ...
                    length(find(E(eq, I_LOS_candidates)));
                number_of_eq = number_of_eq + 1;
            end
            [~, number_of_eq] = min(candidate_dependencies);
            i_eq = I_eq(number_of_eq);
        else %% x_ii_dot does not occur linearly in any of the unsorted dynamics
            % TODO; test this
            % find the equation with least linear dependencies on
            % I_LOS_cancidates
            candidate_dependencies = zeros(length(unsorted_dyn), 1);
            I_x2_candidates = intersect(I_LOS_candidates, 1:nx);
            for eq = unsorted_dyn
                candidate_dependencies(number_of_eq) = ...
                    length(find(E(eq, I_LOS_candidates)))
                  + length(find(A(eq, I_x2_candidates)));
                number_of_eq = number_of_eq + 1;
            end
            [~, number_of_eq] = min(candidate_dependencies);
            i_eq = unsorted_dyn(number_of_eq);
            %% add 1 * [xdot,z](ii) to both sides of i_eq
            E(i_eq, ii) = 1;
            i_phi = find(C(i_eq,:));
            if isempty(i_phi)
                i_phi = length(gnsf.phi_expr) + 1;
                C( i_eq, i_phi) = 1; % add columns to C with 1 entry
            end
            gnsf.phi_expr(i_phi) = gnsf.phi_expr(i_phi) + ...
                E(i_eq, ii) / C(i_eq, i_phi) * xdot_z(ii);
        end
        I_nsf_eq = union(I_nsf_eq, i_eq);
        % remove i_eq from unsorted_dyn
        temp = find(unsorted_dyn == i_eq);
        unsorted_dyn(temp) = [];
    end

    %% add components to I_x1
    for eq = I_nsf_eq
        I_linear_dependence = find(E(eq,:));
        I_linear_dependence = union( find(A(eq,:)), I_linear_dependence);
        I_nsf_components = union(I_linear_dependence, I_nsf_components);
    end
    %
    new_nsf_components = intersect(I_LOS_candidates, I_nsf_components);    
    
    if isempty( new_nsf_components )
        break;
    end
    % remove new_nsf_components from candidates
    I_LOS_candidates = setdiff( I_LOS_candidates, new_nsf_components );
end

I_LOS_components = I_LOS_candidates;
I_LOS_eq = setdiff( 1:nx+nz, I_nsf_eq );

I_x1 = intersect(I_nsf_components, 1:nx);
I_z1 = intersect(I_nsf_components, nx+1:nx+nz);
I_z1 = I_z1 - nx;

I_x2 = intersect(I_LOS_components, 1:nx);
I_z2 = intersect(I_LOS_components, nx+1:nx+nz);
I_z2 = I_z2 - nx;


%% permute x, xdot

if isempty(I_x1)
    x1 = [];
    x1dot = [];
else
    x1 = x(I_x1);
    x1dot = xdot(I_x1);
end

if isempty(I_x2)
    x2 = [];
    x2dot = [];
else
    x2 = x(I_x2);
    x2dot = xdot(I_x2);
end

if isempty(I_z1)
    z1 = [];
else
    z1 = z(I_z1);
end
if isempty(I_z2)
    z2 = [];
else
    z2 = z(I_z2);
end

gnsf.xdot = [x1dot; x2dot];
gnsf.x = [x1; x2];
gnsf.z = [z1; z2];

gnsf.nx1 = size(x1,1);
gnsf.nx2 = size(x2,1);
gnsf.nz1 = size(z1,1);
gnsf.nz2 = size(z2,1);

%% define reordered_model
reordered_model = model;
reordered_model.x = gnsf.x;
reordered_model.xdot = gnsf.xdot;
reordered_model.z = gnsf.z;
reordered_model.f_impl_expr = model.f_impl_expr([I_nsf_eq, I_LOS_eq]);

f_LO = [];
%% rewrite I_LOS_eq as LOS
for eq = I_LOS_eq
    i_LO = find( I_LOS_eq == eq );
    f_LO = vertcat(f_LO, ...
            A(eq, I_x1) * x1 + B(eq, :) * u + c(eq) + C(eq,:) * phi_old...
            - E(eq, I_nsf_components) * [x1; z1]);
    E_LO(i_LO, :) = E(eq, I_LOS_components);
    A_LO(i_LO, :) = A(eq, I_x2);    
end

f_LO = f_LO.simplify();
gnsf.A_LO = A_LO;
gnsf.E_LO = E_LO;
gnsf.f_lo_expr = f_LO;

%% remove I_LOS_eq from NSF type system
gnsf.A = gnsf.A(I_nsf_eq, I_x1);
gnsf.B = gnsf.B(I_nsf_eq, :);
gnsf.C = gnsf.C(I_nsf_eq, :);
gnsf.E = gnsf.E(I_nsf_eq, I_nsf_components);
gnsf.c = gnsf.c(I_nsf_eq, :);


%% reduce phi, C
C_new = [];
phi_new = [];
for ii = 1:size(gnsf.C, 2) % n_colums of C
    if ~all(gnsf.C(:,ii) == 0) % if column ~= 0
        C_new = [C_new, gnsf.C(:,ii)];
        phi_new = [phi_new; gnsf.phi_expr(ii)];
    end
end

gnsf.C = C_new;

gnsf.phi_expr = phi_new;
gnsf.n_out = length(phi_new);

[ gnsf ] = determine_input_nonlinearity_function( gnsf );

check_reformulation(reordered_model, gnsf, print_info);


if print_info
    disp('Successfully detected Linear Output System');
    disp(['==>>  moved  ', num2str(gnsf.nx2), ' differential states and ',...
        num2str(gnsf.nz2),' algebraic variables to the Linear Output System']);
    disp(['==>>  recuced output dimension of phi from  ',...
        num2str(length(phi_old)), ' to ', num2str(length(gnsf.phi_expr))]);
end

end


