# -----------------------------------------------------------------------------------------------------
# CONDOR
# Simulator for diffractive single-particle imaging experiments with X-ray lasers
# http://xfel.icm.uu.se/condor/
# -----------------------------------------------------------------------------------------------------
# Copyright 2014 Max Hantke, Filipe R.N.C. Maia, Tomas Ekeberg
# Condor is distributed under the terms of the GNU General Public License
# -----------------------------------------------------------------------------------------------------
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
# This program is distributed in the hope that it will be useful,
# but without any warranty; without even the implied warranty of
# merchantability or fitness for a pariticular purpose. See the
# GNU General Public License for more details.
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA 02111-1307 USA
# -----------------------------------------------------------------------------------------------------
# General note:
# All variables are in SI units by default. Exceptions explicit by variable name.
# -----------------------------------------------------------------------------------------------------

import sys,os
import numpy
import scipy.stats

import logging
logger = logging.getLogger("Condor")
import utils.log
from utils.log import log 

import config
from utils.variation import Variation



class Sample:
    def __init__(self,**kwargs):

        # Check for valid set of keyword arguments
        req_keys = ["number_of_images","number_of_particles"]
        opt_keys = ["number_of_particles_variation","number_of_particles_spread","number_of_particles_variation_n"]
        miss_keys,ill_keys = config.check_input(kwargs.keys(),req_keys,opt_keys)
        if len(miss_keys) > 0: 
            for k in miss_keys:
                log(logger.error,"Cannot initialize Sample instance. %s is a necessary keyword." % k)
            sys.exit(1)
        if len(ill_keys) > 0:
            for k in ill_keys:
                log(logger.error,"Cannot initialize Sample instance. %s is an illegal keyword." % k)
            sys.exit(1)

        # Start initialisation
        self.number_of_images = kwargs["number_of_images"]
        self.number_of_particles_mean = kwargs["number_of_particles"]
        self.set_number_of_particles_variation(kwargs["number_of_particles_variation"],kwargs.get("number_of_particles_spread",None),kwargs.get("number_of_particles_variation_n",None))
        self.particle_species = []

    def set_number_of_particles_variation(self,mode,spread,variation_n):
        self._number_of_particles_variation = Variation(mode,spread,variation_n)

    def _get_next_number_of_particles(self):
        N = self._number_of_particles_variation.get(self.number_of_particles_mean)
        # Non-random
        if self._number_of_particles_variation._mode in [None,"range"]:
            if N <= 0:
                log(logger.error,"Sample number of particles smaller-equals zero. Change your configuration.")
                sys.exit(0)
            else:
                return N
        # Random
        else:
            if N <= 0.:
                log(logger.info,"Sample number of particles smaller-equals zero. Trying again.")
                return self._get_next_number_of_particles()
            else:
                return N       
        
    def _next_particles(self):
        N = self._get_next_number_of_particles()
        if N > 1:
            if len(self.particle_species) == 1:
                self.particles = self.particle_species * N
            else:
                i_s = range(len(self.particle_species))
                c_s = [s.concentration for s in self.particle_species]
                dist = scipy.stats.rv_discrete(name='species distribution', values=(i_s, c_s))
                self.particles = self.particle_species[dist.rvs(size=self.number_of_particles)]
        else:
            self.particles = self.particle_species

    def get_next(self):
        self._next_particles()
        O = {}
        #O["particle_types"] = []
        O["particles"] = []
        for p in self.particles:
            O["particles"].append(p.get_next())
        O["number_of_particles"] = len(self.particles)
        return O

