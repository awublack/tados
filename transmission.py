# -*- coding: utf-8 -*-
"""

Provides several classes for calculation of transmission through an optical system

Transmission: perform the transmission calculation (iterate over discrete set of
  parameters (e.g. field points) and evaluate the transmission on an adaptive mesh
  (e.g. pupil coordinates) using a given raytrace function
Detectors: analyze the raytrace results

ToDo: add unit tests

@author: Hambach
"""

from __future__ import division
import abc
import logging
import numpy as np
import matplotlib.pylab as plt
from point_in_triangle import point_in_triangle
from adaptive_mesh import *
from zemax_dde_link import *

class Detector(object):
  __metaclass__ = abc.ABCMeta
  @abc.abstractmethod
  def add(self,mesh,skip=None,weight=1): return;
  @abc.abstractmethod  
  def show(self): return;


class CheckTriangulationDetector(Detector):
  " Detector class for testing completeness of triangulation in domain"

  def __init__(self, ref_area=np.pi):
    """
    ref_area ... (opt) theoretical area of domain space, default: area of unit circle
    """
    self.ref_domain_area=ref_area;
  
  def add(self,mesh,skip=None,weight=1):
    """
    calculate total domain area of mesh and print logging info 
      mesh ... instance of AdaptiveMesh 
      skip ... indices which simplices should be skipped
      weight.. ignored
    """
    triangle_area  = mesh.get_area_in_domain(); 
    assert(all(triangle_area>0));  # triangles should be oriented ccw in mesh    
    mesh_domain_area= np.sum(np.abs(triangle_area));
    err_boundary= 1-mesh_domain_area/self.ref_domain_area;
    out = 'error of triangulation of mesh: \n' + \
     '  %5.3f%% due to approx. of mesh boundary \n'%(err_boundary*100);
    if skip is not None:
      err_skip  = np.sum(triangle_area[skip])/mesh_domain_area;
      out += '  %5.3f%% due to skipped triangles' %(err_skip*100);
    logging.info(out);
    #image_area = Mesh.get_area_in_image();
    #if any(image_area<0) and any(image_area>0):
    #  logging.warning('scambling of rays, triangulation may not be working')
       
  def show(self): 
    raise NotImplemented();


     
class RectImageDetector(Detector):    
  " 2D Image Detector with cartesian coordinates "

  def __init__(self, extent=(1,1), pixels=(100,100)):
    """
     extent ... size of detector in image space (xwidth, ywidth)
     pixels ... number of pixels in x and y (xnum,ynum)
    """
    self.extent = np.asarray(extent);
    self.pixels = np.asarray(pixels);
    self.points = cartesian_sampling(*pixels,rmax=2); # shape: (2,nPixels)
    self.points *= self.extent[:,np.newaxis]/2;
    self.intensity = np.zeros(np.prod(self.pixels));  # 1d array

  def add(self,mesh,skip=None,weight=1):
    """
    calculate footprint in image plane
      mesh ... instance of AdaptiveMesh 
      skip ... indices which simplices should be skipped
      weight.. weight of contribution (intensity in Watt)
    """
    domain_area = mesh.get_area_in_domain(); 
    domain_area /= np.sum(np.abs(domain_area));   # normalized weight in domain
    image_area  = mesh.get_area_in_image();       # size of triangle in image
    density = weight * abs( domain_area / image_area);
    for s in np.where(~skip)[0]:
      triangle = mesh.image[mesh.simplices[s]];
      mask = point_in_triangle(self.points,triangle);
      self.intensity += density[s]*mask;

  def show(self):
    " plotting 2D footprint in image plane, returns figure handle"
    Nx,Ny = self.pixels;
    img_pixels_2d = self.points.reshape(2,Ny,Nx);
    image_intensity = self.intensity.reshape(Ny,Nx);
    xaxis = img_pixels_2d[1,:,0]; dx=xaxis[1]-xaxis[0];
    yaxis = img_pixels_2d[0,0,:]; dy=yaxis[1]-yaxis[0];
  
    fig,(ax1,ax2)= plt.subplots(2);
    ax1.set_title("footprint in image plane");
    ax1.imshow(image_intensity,origin='lower',aspect='auto',interpolation='hanning',
             extent=[xaxis[0],xaxis[-1],yaxis[0],yaxis[-1]]);
    ax2.set_title("integrated intensity in image plane");    
    ax2.plot(xaxis,np.sum(image_intensity,axis=1)*dy,label="along y");
    ax2.plot(yaxis,np.sum(image_intensity,axis=0)*dx,label="along x");
    ax2.legend(loc=0)
  
    logging.info('total intensity: %5.3f W'%(np.sum(image_intensity)*dx*dy)); 
    return fig
    
    
class PolarImageDetector(Detector):    
  "2D Image Detector with polar coordinates"

  def __init__(self, rmax=1, nrings=100):
    """
     rmax ... radial size of detector in image space
     nrings.. number of rings
    """
    self.rmax = rmax;
    self.nrings = nrings;
    ret = polar_sampling(nrings,rmax=rmax,ind=True); 
    self.points = np.asarray(ret[0:2]);     # shape: (2,nPixels)
    self.points_per_ring = ret[2];          # shape: (nrings,)
    self.weight_of_ring  = ret[3];          # shape: (nrings,)
    self.intensity = np.zeros(self.points.shape[1]);  # 1d array

  def add(self,mesh,skip=None,weight=1):
    """
    calculate footprint in image plane
      mesh ... instance of AdaptiveMesh 
      skip ... indices which simplices should be skipped
      weight.. weight of contribution (intensity in Watt)
    """
    domain_area = mesh.get_area_in_domain(); 
    domain_area /= np.sum(np.abs(domain_area));   # normalized weight in domain
    image_area  = mesh.get_area_in_image();       # size of triangle in image
    density = weight * abs( domain_area / image_area);
    for s in np.where(~skip)[0]:
      triangle = mesh.image[mesh.simplices[s]];
      mask = point_in_triangle(self.points,triangle);
      self.intensity += density[s]*mask;

  def show(self):
    " plotting 2D footprint in image plane, returns figure handle"
    x,y=self.points;    
    fig,(ax1,ax2)= plt.subplots(2);
    ax1.set_title("footprint in image plane");
    ax1.tripcolor(x,y,self.intensity);
    # radial profile
    ax2.set_title("radial profile");    
    Nr=np.insert(np.cumsum(self.points_per_ring),0,0); # index array for rings, size (nrings+1,)
    radial_profile = np.empty(self.nrings);
    r = np.empty(self.nrings);
    for i in xrange(self.nrings):
      radial_profile[i] = np.sum(self.intensity[Nr[i]:Nr[i+1]]) / self.points_per_ring[i];
      r2 = np.sum(self.points[:,Nr[i]:Nr[i+1]]**2,axis=0)
      assert np.allclose(r2[0],r2);
      r[i] = np.sqrt(r2[0]);
    ax2.plot(r,radial_profile,label='radial profile');
    
    # encircled energy (area of ring = weight of ring x total area of detector)
    encircled_energy = np.cumsum(radial_profile*self.weight_of_ring*np.pi*self.rmax**2);
    ax2.plot(r,encircled_energy,label='encircled energy');
    ax2.legend(loc=0)
    logging.info('total intensity: %5.3f W'%(encircled_energy[-1])); 
    return fig
    
    
    
      

class Transmission(object):
  def __init__(self, parameters, mesh_points, raytrace, detectors, weights=None):
    """
    Transmission for rays defined by a set of discrete parameters and a mesh, 
    which can be refined iteratively. The results are recorded by a set of
    given detectors, which are called for each parameter sequentially.
    
      parameters ... list of Np discrete parameters for each raytrace, shape (nParams,Np)
      mesh_points... list of initial points for the adaptive mesh, shape (nMeshPoints,2)
      raytrace   ... function mask=raytrace(para,mesh_points) that performs a raytrace
                       with the given Np parameters for a list of points of shape (nPoints,2)
                       returns list of points in image space, shape (nPoints,2)
      detectors  ... list of instances of Detector class for analyzing raytrace results
      weights    ... (opt) weights of contribution for each parameter set (default: constant)
    """
    self.parameters  = parameters;
    self.mesh_points = mesh_points;
    self.raytrace = raytrace;
    self.detectors = detectors;    
    nParams,Np = self.parameters.shape;
    if weights is None: weights = np.ones(nParams)/nParams;
    self.weights = weights;   
   
    
  def total_transmission(self, lthresh, Athresh=np.pi/1000):
    
    def is_broken(simplices):
        " local help function for defining which simplices should be subdivided"
        broken = Mesh.get_broken_triangles(simplices=simplices,lthresh=lthresh);
        area_broken = Mesh.get_area_in_domain(simplices=simplices[broken]);
        broken[broken] = (area_broken>Athresh);  # only consider triangles > Athresh as broken
        return broken;
        
    # incoherent sum on detector over all raytrace parameters
    for ip,p in enumerate(self.parameters):
      logging.info("Transmission for parameter: "+str(p));      
      
      # initialize adaptive grid for 
      mapping = lambda(mesh_points): self.raytrace(p,mesh_points);
      Mesh=AdaptiveMesh(self.mesh_points, mapping);  
      
      # iterative mesh refinement (subdivision of broken triangles)
      while True:  
        if ip==0: # plot mesh for first set of parameters
          skip = lambda(simplices): Mesh.get_broken_triangles(simplices=simplices,lthresh=lthresh)        
          Mesh.plot_triangulation(skip_triangle=skip);
        # refine mesh until nothing changes
        nNew = Mesh.refine_broken_triangles(is_broken,nDivide=100,bPlot=(ip==0));        
        if nNew==0: break 
          
      # update detectors
      broken = Mesh.get_broken_triangles(lthresh=lthresh);
      for d in self.detectors:
        d.add(Mesh,skip=broken,weight=self.weights[ip]);

