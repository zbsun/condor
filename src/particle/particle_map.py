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

import sys
import numpy
import scipy.stats

import condor
import condor.utils.log
from condor.utils.log import log 

from condor.utils.variation import Variation
import condor.utils.spheroid_diffraction
import condor.utils.diffraction
import condor.utils.bodies

from particle_abstract import AbstractContinuousParticle

class ParticleMap(AbstractContinuousParticle):
    def __init__(self,
                 geometry, diameter,
                 diameter_variation = None, diameter_spread = None, diameter_variation_n = None,
                 map3d = None, dx = None, filename = None,
                 flattening = 1., flattening_variation = None, flattening_spread = None, flattening_variation_n = None,
                 alignment = None, euler_angle_0 = None, euler_angle_1 = None, euler_angle_2 = None,
                 concentration = 1.,
                 position = None, position_variation = None, position_spread = None, position_variation_n = None,
                 material_type = None, massdensity = None, **atomic_composition):
        """
        Function initializes ParticleMap object:
        =============================================

        Arguments:

        Keyword arguments (if not given variable \'X\' is set to default value \'[X_default]\'):
        
        EITHER (default):

        - N_fine: Edge length in number of voxels [1]

        OR:
        - map3d_fine: Cubic 3d map.
          EITHER:

          - dx_fine: Real space sampling distance.
          OR:
          - oversampling_fine: Real space oversampling in relation to detector/source configuration. [1]
        
        OR:
        - geometry: Geometry that shall be generated (icosahedron, sphere, spheroid, cube)
          - oversampling_fine: Additional oversampling for the initial map self.map3d_fine [1.]
          ADDITIONAL (spheroid):
          - flattening

        ADDITIONAL:
        - euler_angle_0, euler_angle_1, euler_angle_2: Euler angles defining orientation of 3D grid in the experimental reference frame (beam axis). [0.0,0.0,0.0]
        - size: Characteristic size of the object in meters. [1]
        - parent: Input object that this SampleMap object shall be linked to. [None]
        - SAMPLING:
          EITHER:
          - dX_fine: Real space sampling distance.
          OR:
          - oversampling_fine: Real space oversampling in relation to detector/source configuration. [1]
        - MATERIAL:
          (For more documentation look at the help of the Material class.)
          - material_type: predefined material type. 
          OR
          - massdensity: massdensity of the component
          - cX, cY, ... : atomic composition

        """
        # Initialise base class
        AbstractContinuousParticle.__init__(self,
                                                 diameter=diameter, diameter_variation=diameter_variation, diameter_spread=diameter_spread, diameter_variation_n=diameter_variation_n,
                                                 alignment=alignment, euler_angle_0=euler_angle_0, euler_angle_1=euler_angle_1, euler_angle_2=euler_angle_2,
                                                 concentration=concentration,
                                                 position=position, position_variation=position_variation, position_spread=position_spread, position_variation_n=position_variation_n,
                                                 material_type=material_type, massdensity=massdensity, **atomic_composition)
        
        # Check for valid geometry
        if geometry not in ["icosahedron", "cube", "sphere", "spheroid", "custom"]:
            log(condor.CONDOR_logger.error,"Cannot initialize %s because \'%s\' is not a valid argument for \'geometry\'." % (kwargs["geometry"], self.__class__.__name__))
            sys.exit(1)
        self.geometry = geometry

        if geometry != "spheroid":
            if flattening != 1. or flattening_variation is not None or flattening_spread is not None or flattening_variation_n is not None:
                log(condor.CONDOR_logger.warning, "At least one flattening keyword argument is not None - although geometry != \"spheroid\". The flattening keywords will have no effect.")
        # Has effect only for spheroids
        self.flattening_mean = flattening
        self.set_flattening_variation(flattening_variation=flattening_variation, flattening_spread=flattening_spread, flattening_variation_n=flattening_variation_n)

                
        if geometry == "custom":
            if filename is not None and map3d is not None:
                log(condor.CONDOR_logger.error, "Cannot initialize geometry because the keyword arguments for both \'filename\' and \'map3d\' are not None.")
                sys.exit(1)
            elif filename is None and map3d is None:
                log(condor.CONDOR_logger.error, "Cannot initialize geometry because the keyword arguments for both \'filename\' and \'map3d\' are None.")
                sys.exit(1)
            elif dx is None:
                log(condor.CONDOR_logger.error, "Cannot initialize geometry because the keyword argument \'dx\' is None.")
                sys.exit(1)                
            elif map3d is not None:
                self.set_custom_geometry_by_array(map3d, dx)
            elif filename is not None:
                self.set_custom_geometry_by_file(filename, dx)
                    
        # Init chache
        self._old_map3d_diameter               = None
        self._old_map3d_geometry               = None
        self._old_map3d_dx                     = None
        self._old_map3d                        = None

    def get_conf(self):
        conf = {}
        conf.update(AbstractContinuousParticle.get_conf(self))
        m,dx = self.get_map3d()
        conf["map3d"] = m
        conf["dx"] = dx
        conf["flattening"] = self.flattening_mean
        fvar = self._flattening_variation.get_conf()
        conf["flattening_variation"] = fvar["mode"]
        conf["flattening_spread"] = fvar["spread"]
        conf["flattening_variation_n"] = fvar["n"]
        return conf

    def get_next(self):
        O = AbstractContinuousParticle.get_next(self)
        O["geometry"]   = self.geometry
        O["flattening"] = self._get_next_flattening()
        return O

    def set_custom_geometry_by_array(self, map3d, dx):
        s = numpy.array(map3d.shape)
        if not numpy.all(s==s[0]):
            log(condor.CONDOR_logger.error,"Condor only accepts maps with equal dimensions.")
            return
        self._old_map3d = map3d
        self._old_map3d_dx = dx
        
    def set_custom_geometry_by_h5file(self, filename, dx):
        import h5py
        with h5py.File(O["filename"],"r") as f:
            if len(f.items()) == 1:
                map3d = numpy.array(f.items()[0][1][:,:,:], dtype="float")
            else:
                map3d = numpy.array(f["data"][:,:,:], dtype="float")
        self.set_custom_geometry_by_array(map3d, dx)                
    
    def set_flattening_variation(self, flattening_variation=None, flattening_spread=None, flattening_variation_n=None):
        self._flattening_variation = Variation(flattening_variation,flattening_spread,flattening_variation_n,name="spheroid flattening")       

    def _get_next_flattening(self):
        f = self._flattening_variation.get(self.flattening_mean)
        # Non-random 
        if self._flattening_variation._mode in [None, "range"]:
            if f <= 0:
                log(condor.CONDOR_logger.error, "Spheroid flattening smaller-equals zero. Change your configuration.")
            else:
                return f
        # Random 
        else:
            if f <= 0.:
                log(condor.CONDOR_logger.warning, "Spheroid flattening smaller-equals zero. Try again.")
                return self._get_next_flattening()
            else:
                return f

    def get_map3d(self, O = None, dx_required = None, dx_suggested = None, dn = None):
        if O is not None:
            self._build_map(O, dx_required, dx_suggested, dn)
        dx = self._old_map3d_dx
        m = self._old_map3d
        return m, dx
            
    def _build_map(self, O, dx_required, dx_suggested, dn):
        build_map = False
        if self._old_map3d is None:
            build_map = True
        if self._old_map3d_diameter is None:
            build_map = True
        else:
            if abs(self._old_map3d_diameter - O["diameter"]) > 1E-10:
                build_map = True
        if self._old_map3d_dx > dx_required:
            build_map = True
            self._old_map3d = None
        if not build_map:
            return

        self._old_map3d = None
        self._old_map3d_dx = dx_suggested
        self._old_map3d_diameter = O["diameter"]
        
        if O["geometry"] is not "custom":
            if O["geometry"] == "icosahedron":
                self._put_icosahedron(O["diameter"]/2., dn)
            elif O["geometry"] == "spheroid":
                a = condor.utils.spheroid_diffraction.to_spheroid_semi_diameter_a(O["diameter"],O["flattening"])
                c = condor.utils.spheroid_diffraction.to_spheroid_semi_diameter_c(O["diameter"],O["flattening"])
                self._put_spheroid(a, c, dn)
            elif O["geometry"] == "sphere":
                self._put_sphere(O["diameter"]/2., dn)
            elif O["geometry"] == "cube":
                self._put_cube(O["diameter"]/2., dn)
            else:
                log(condor.CONDOR_logger.error,"Particle map geometry \"%s\" is not implemented. Change your configuration and try again." % O["geometry"])
                sys.exit(1)
        else:
            s = numpy.array(self._old_map3d.shape)
            self._old_map3d_dx = O["diameter"]/float(s[0])

    def _put_custom_map(self, map_add, n):
        self._old_map3d = numpy.array(map_add, dtype=numpy.complex128) * n
    
    def _put_sphere(self, radius, n):
        nR = radius/self._old_map3d_dx
        N = int(round((nR*1.2)*2))
        spheremap = condor.utils.bodies.make_sphere_map(N,nR)
        self._put_custom_map(spheremap, n)
 
    def _put_spheroid(self, a, c, n, e0=0., e1=0., e2=0.):
        # maximum radius
        Rmax = max([a,c])
        # maximum radius in pixel
        nRmax = Rmax/self._old_map3d_dx
        # dimensions in pixel
        nA = a/self._old_map3d_dx
        nC = c/self._old_map3d_dx
        # leaving a bit of free space around spheroid
        N = int(round((nRmax*1.2)*2))
        spheromap = condor.utils.bodies.make_spheroid_map(N,nA,nC,e0,e1,e2)
        self._put_custom_map(spheromap, n)

    def _put_icosahedron(self, radius, n, e0=0., e1=0., e2=0.):
        # icosahedon size parameter
        a = radius*(16*numpy.pi/5.0/(3+numpy.sqrt(5)))**(1/3.0)
        # radius at corners in meter
        Rmax = numpy.sqrt(10.0+2*numpy.sqrt(5))*a/4.0 
        # radius at corners in pixel
        nRmax = Rmax/self._old_map3d_dx 
        # leaving a bit of free space around icosahedron 
        N = int(numpy.ceil(2.3*(nRmax)))
        log(condor.CONDOR_logger.info,"Building icosahedron with radius %e (%i pixel) in %i x %i x %i voxel cube." % (radius,nRmax,N,N,N))
        icomap = condor.utils.bodies.make_icosahedron_map(N,nRmax,e0,e1,e2)
        self._put_custom_map(icomap, n)

    def _put_cube(self, a, n, e0=0., e1=0., e2=0.):
        # edge_length in pixels
        nel = a/self._old_map3d_dx 
        # leaving a bit of free space around
        N = int(numpy.ceil(2.3*nel))
        # make map
        X,Y,Z = 1.0*numpy.mgrid[0:N,0:N,0:N]
        X = X - (N-1)/2.
        Y = Y - (N-1)/2.
        Z = Z - (N-1)/2.
        DX = abs(X)-nel/2.
        DY = abs(Y)-nel/2.
        DZ = abs(Z)-nel/2.
        D = numpy.array([DZ,DY,DX])
        cubemap = numpy.zeros(shape=(N,N,N))
        Dmax = D.max(0)
        cubemap[Dmax<-0.5] = 1.
        temp = (Dmax<0.5)*(cubemap==0.)
        d = Dmax[temp]
        cubemap[temp] = 0.5-d
        self._put_custom_map(cubemap, n)        

    def plot_map3d(self,mode='surface'):
        try:
            from enthought.mayavi import mlab
        except:
            from mayavi import mlab
        if mode=='planes':
            s = mlab.pipeline.scalar_field(abs(self._old_map3d))
            plane_1 = mlab.pipeline.image_plane_widget(s,plane_orientation='x_axes',
                                                       slice_index=self._old_map3d.shape[2]/2)
            plane_2 = mlab.pipeline.image_plane_widget(s,plane_orientation='y_axes',
                                                       slice_index=self._old_map3d.shape[1]/2)
            mlab.show()
        elif mode=='surface':
            mlab.contour3d(abs(self._old_map3d))
        else:
            log(condor.CONDOR_logger.error,"No valid mode given.")
            
    def plot_fmap3d(self):
        from enthought.mayavi import mlab
        import spimage
        M = spimage.sp_image_alloc(self._old_map3d.shape[0],self._old_map3d.shape[1],self._old_map3d.shape[2])
        M.image[:,:,:] = self._old_map3d[:,:,:]
        M.mask[:,:,:] = 1
        fM = spimage.sp_image_fftw3(M)
        fM.mask[:,:,:] = 1
        fsM = spimage.sp_image_shift(fM)
        self.fmap3d = abs(fsM.image).copy()
        self.fmap3d[self.fmap3d!=0] = numpy.log10(self.fmap3d[self.fmap3d!=0])
        
        s = mlab.pipeline.scalar_field(self.fmap3d)
        plane_1 = mlab.pipeline.image_plane_widget(s,plane_orientation='x_axes',
                                                   slice_index=self.fmap3d.shape[2]/2)
        plane_2 = mlab.pipeline.image_plane_widget(s,plane_orientation='y_axes',
                                                   slice_index=self.fmap3d.shape[1]/2)
        mlab.show()


    def save_map3d(self,filename):
        """
        Function saves the current refractive index map to an hdf5 file:
        ================================================================
        
        Arguments:
        
        - filename: Filename.

        """
        if filename[-3:] == '.h5':
            import h5py
            f = h5py.File(filename,'w')
            map3d = f.create_dataset('data', self._old_map3d.shape, self._old_map3d.dtype)
            map3d[:,:,:] = self._old_map3d[:,:,:]
            f['voxel_dimensions_in_m'] = self._old_map3d_dx
            f.close()
        else:
            log(condor.CONDOR_logger.error,"Invalid filename extension, has to be \'.h5\'.")

 