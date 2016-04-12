# -*- coding: utf-8 -*-
"""
Created on Tue Apr 12 11:45:06 2016

@author: Hambach
"""


import numpy as np
import matplotlib.pylab as plt
import logging
from tolerancing import *
from transmission import *
from zemax_dde_link import *


def __test_tolerancing(tol):  
  
  # raytrace parameters for image intensity before aperture
  image_surface = 22;
  wavenum  = 3;
  def raytrace(params, pupil_points):      # local function for raytrace
    x,y   = params;      
    px,py = pupil_points.T;                # shape (nPoints,)
    ret   = tol.hDDE.trace_rays(x,y,px,py,wavenum,surf=image_surface);
    error = ret[:,0];
    vigcode= ret[:,[1]];     
    xy    = ret[:,[2,3]];    
    # return (x,y) coordinates in image space    
    xy   += image_size*(vigcode<>0);       # include vignetting by shifting ray outside image
    xy[error<>0]=np.nan;                   # rays that could not be traced
    return xy;                             

  # field sampling (octagonal fiber)
  xx,yy=cartesian_sampling(3,3,rmax=2);   # low: 7x7, high: 11x11
  ind = (np.abs(xx)<=1) & (np.abs(yy)<=1) & \
              (np.abs(xx+yy)<=np.sqrt(2)) & (np.abs(xx-yy)<=np.sqrt(2));
  field_sampling = np.vstack((xx[ind],yy[ind])).T;       # size (nFieldPoints,2)
  plt.figure(); plt.title("field sampling (normalized coordinates)");
  plt.plot(xx[ind].flat,yy[ind].flat,'.')
  plt.xlabel('x'); plt.ylabel('y');
  
  # pupil sampling (circular, adaptive mesh)
  px,py=fibonacci_sampling_with_circular_boundary(50,30) # low: (50,20), high: (200,50)
  pupil_sampling = np.vstack((px,py)).T;                 # size (nPoints,2)
  
  # set up image detector
  image_size=(0.2,0.05);  # [mm]
  img = RectImageDetector(extent=image_size,pixels=(201,401));
  dbg = CheckTriangulationDetector();

  # disturb system (tolerancing)
  tol.change_thickness(5,12,value=2); # shift of pupil slicer
  
  # run Transmission calculation
  T = Transmission(field_sampling,pupil_sampling,raytrace,[dbg,img]);
  lthresh = 0.5*image_size[1];  
  T.total_transmission(lthresh)
  
  # plotting
  img.show();

  # analyze img detector in detail (left and right sight separately)
  img.show(fMask = lambda x,y: np.logical_or(2*x+y<0, x>0.07))  
  img.show(fMask = lambda x,y: 2*x+y>=0)
  

if __name__ == '__main__':
  import os as os
  import sys as sys
  logging.basicConfig(level=logging.INFO);
  
  with DDElinkHandler() as hDDE:
  
    ln = hDDE.link;
    # load example file
    #filename = os.path.join(ln.zGetPath()[1], 'Sequential', 'Objectives', 
    #                        'Cooke 40 degree field.zmx')
    filename= os.path.realpath('./tests/pupil_slicer.ZMX');
    tol=ToleranceSystem(hDDE,filename)
    __test_tolerancing(tol);
    