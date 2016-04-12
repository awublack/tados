# -*- coding: utf-8 -*-
"""
Created on Thu Apr 07 19:23:20 2016

@author: Hambach
"""
import numpy as np
import matplotlib.pylab as plt
import logging


class AdaptiveMesh(object):
  """
  Implementation of an adaptive mesh for a given mapping f:domain->image.
  We start from a Delaunay triangulation in the domain of f. This grid
  will be distorted in the image space. We refine the mesh by subdividing
  large or broken triangles. This process can be iterated, e.g. wehn a 
  triangle is cut multiple times (use threshold for minimal size of triangle
  in domain space). Points outside of the domain (e.g. raytrace fails) 
  should be mapped to image point (np.nan,np.nan) and are handled separately.
  
  ToDo: add unit tests
  """
  
  def __init__(self,initial_domain,mapping):
    """
    Initialize mesh, mapping and image points.
      initial_domain ... 2d array of shape (nPoints,2)
      mapping        ... function image=mapping(domain) that accepts a list of  
                           domain points and returns corresponding image points
    """
    from scipy.spatial import Delaunay
     
    assert( initial_domain.ndim==2 and initial_domain.shape[1] == 2)
    self.initial_domain = initial_domain;
    self.mapping = mapping;
    # triangulation of initial domain
    self.__tri = Delaunay(initial_domain,incremental=True);
    self.simplices = self.__tri.simplices;
    # calculate distorted grid
    self.initial_image = self.mapping(self.initial_domain);
    assert( self.initial_image.ndim==2)
    assert( self.initial_image.shape==(self.initial_domain.shape[0],2))
    # current domain and image during refinement and for plotting
    self.domain = self.initial_domain;    
    self.image  = self.initial_image;   
    # initial domain area
    self.initial_domain_area = np.sum(self.get_area_in_domain());
    
          
  def get_mesh(self):
    """ 
    return triangles and points in domain and image space
       domain,image:  coordinate array of shape (nPoints,2)
       simplices:     index array for vertices of each triangle, shape (nTriangles,3)
    Returns: (domain,image,simplices)
    """
    return self.domain,self.image,self.simplices;

  
  def plot_triangulation(self,skip_triangle=None):
    """
    plot current triangulation of adaptive mesh in domain and image space
      skip_triangle... (opt) function mask=skip_triangle(simplices) that accepts a list of 
                     simplices of shape (nTriangles, 3) and returns a flag 
                     for each triangle indicating that it should not be drawn
    returns figure handle;
    """ 
    simplices = self.simplices.copy();
    if skip_triangle is not None:
      skip = skip_triangle(simplices);
      skipped_simplices=simplices[skip];
      simplices=simplices[~skip];
          
    fig,(ax1,ax2)= plt.subplots(2);
    ax1.set_title("Sampling + Triangulation in Domain");
    if skip_triangle is not None and np.sum(skip)>0:
      ax1.triplot(self.domain[:,0], self.domain[:,1], skipped_simplices,'k:');
    ax1.triplot(self.domain[:,0], self.domain[:,1], simplices,'b-');    
    ax1.plot(self.initial_domain[:,0],self.initial_domain[:,1],'r.')
    
    ax2.set_title("Sampling + Triangulation in Image")
    ax2.triplot(self.image[:,0], self.image[:,1], simplices,'b-');
    ax2.plot(self.initial_image[:,0],self.initial_image[:,1],'r.')

    return fig;


  def get_area_in_domain(self,simplices=None):
    """
    calculate signed area of given simplices in domain space
      simplices ... (opt) list of simplices, shape (nTriangles,3)
    Returns:
      1d vector of size nTriangles containing the signed area of each triangle
      (positive: ccw orientation, negative: cw orientation of vertices)
    """
    if simplices is None: simplices = self.simplices;    
    x,y = self.domain[simplices].T;
    # See http://geomalgorithms.com/a01-_area.html#2D%20Polygons
    return 0.5 * ( (x[1]-x[0])*(y[2]-y[0]) - (x[2]-x[0])*(y[1]-y[0]) );

  def get_area_in_image(self,simplices=None):
    """
    calculate signed area of given simplices in image space
    (see get_area_in_domain())
    """
    if simplices is None: simplices = self.simplices;    
    x,y = self.image[simplices].T;
    # See http://geomalgorithms.com/a01-_area.html#2D%20Polygons
    return 0.5 * ( (x[1]-x[0])*(y[2]-y[0]) - (x[2]-x[0])*(y[1]-y[0]) );
  
  
  def get_broken_triangles(self,simplices=None,lthresh=None):
    """
    identify triangles that are cut in image space or include invalid vertices
      simplices ... (opt) list of simplices, shape (nTriangles,3)  
      lthresh   ... (opt) threshold for longest side of broken triangle 
    Returns:
      1d vector of size nTriangles indicating if triangle is broken
    """
    if simplices is None: simplices = self.simplices;    
    # x and y coordinates for each vertex in each triangle 
    triangles = self.image[simplices]    
    # calculate maximum of (squared) length of two sides of each triangle 
    # (X[0]-X[1])**2 + (Y[0]-Y[1])**2; (X[1]-X[2])**2 + (Y[1]-Y[2])**2 
    max_lensq = np.max(np.sum(np.diff(triangles,axis=1)**2,axis=2),axis=1);
    # default: mark triangle as broken, if max side is 3 times larger than median value
    if lthresh is None: lthresh = 3*np.sqrt(np.median(max_lensq));
    # valid triangles: all sides smaller than lthresh, none of its vertices invalid (np.nan)
    bValid = max_lensq < lthresh**2; 
    return ~bValid;   # Note: differs from (max_lensq >= lthresh**2), if some vertices are invalid!

        
  def refine_large_triangles(self,is_large):
    """
    subdivide large triangles in the image mesh
      is_large ... function mask=is_large(triangles) that accepts a list of 
                     simplices of shape (nTriangles, 3) and returns a flag 
                     for each triangle indicating if it should be subdivided
    
    returns: number of new triangles                 
    Note: Additional points are added at the center of gravity of large triangles
          and the Delaunay triangulation is recalculated. Edge flips can occur.
    """
    # check if mesh is still a Delaunay mesh
    if self.__tri is None:
      raise RuntimeError('Mesh is no longer a Delaunay mesh. Subdivision not implemented for this case.');
    
    ind = is_large(self.simplices);
    if np.sum(ind)==0: return; # nothing to do
    
    # add center of gravity for critical triangles
    new_domain_points = np.sum(self.domain[self.simplices[ind]],axis=1)/3; # shape (nTriangles,2)
    # remove invalid points (coordinates are nan)    
    new_domain_points = new_domain_points[~np.any(np.isnan(new_domain_points),axis=1)]
    # update triangulation    
    self.__tri.add_points(new_domain_points);
    logging.info("refining_large_triangles(): adding %d points"%(new_domain_points.shape[0]))
    
    # calculate image points and update data
    new_image_points = self.mapping(new_domain_points);
    self.image = np.vstack((self.image,new_image_points));
    self.domain= np.vstack((self.domain,new_domain_points));
    self.simplices = self.__tri.simplices;
    
    return new_domain_points.shape[0];


  def refine_broken_triangles(self,is_broken,nDivide=10,bPlot=False,bPlotTriangles=[0]):
    """
    subdivide triangles which contain discontinuities in the image mesh or invalid vertices
      is_broken  ... function mask=is_broken(triangles) that accepts a list of 
                      simplices of shape (nTriangles, 3) and returns a flag 
                      for each triangle indicating if it should be subdivided
      nDivide    ... (opt) number of subdivisions of each side of broken triangle
      bPlot      ... (opt) plot sampling and selected points for debugging 
      bPlotTriangles (opt) list of triangle indices for which segmentation should be shown

    returns: number of new triangles
    Note: The resulting mesh will be no longer a Delaunay mesh (identical points 
          might be present, circumference rule not guaranteed). Mesh functions, 
          that need this property (like refine_large_triangles()) will not work
          after calling this function.
    """
    broken = is_broken(self.simplices);                    # shape (nSimplices)
    simplices = self.simplices[broken];                    # shape (nTriangles,3)
    triangles = self.image[simplices];                     # shape (nTriangles,3,2)
    
    # check if any of the triangles has an invalid vertex (x or y coordinate is np.nan)
    bInvalidVertex = np.any(np.isnan(triangles),axis=2);   # shape (nTriangles,3)
    if np.sum(bInvalidVertex)>0:
      # exclude triangles that have only invalid vertices      
      keep = ~np.all(bInvalidVertex,axis=1);               # shape (nTriangles,)
      broken[broken] = keep;                               # shape (nSimplices,)
      simplices=simplices[keep];
      triangles=triangles[keep];
      

    # check if subdivision is needed at all    
    nTriangles = np.sum(broken)
    if nTriangles==0: return 0;                 # noting to do!
    nPointsOrigMesh = self.image.shape[0];  
    
    # add new simplices:
    # segmentation of each broken triangle is generated in a cyclic manner,
    # starting with isolated point C and the two closest new sampling points
    # in image space, p1 + p2), continues with p3,p4,A,B.
    #    
    #             C
    #             /\
    #            /  \              \\\ largest segments of triangle in image space
    #        p1 *    *  p2          *  new sampling points
    #     ....///....\\\.............. discontinuity
    #      p3 *        * p4
    #        /          \          new triangles:
    #       /____________\           (C,p1,p2),             isolated point + closest two new points  
    #      A              B          (p1,p3,p2),(p2,p3,p4)  new broken triangles, only between new sampling points
    #                                (p4,p3,A), (p4,A,B):   rest
    # 
    # Note: one has to pay attention, that C,p1,p3,A are located on same side
    #       of the triangle, otherwise the partition will fail!     

    # identify the shortest edge of the triangle in image space (not cut)
    vertices = np.concatenate((triangles,triangles[:,[0],:]),axis=1); # shape (nTriangles,4,2)
    edge_len = np.sum( np.diff(vertices,axis=1)**2, axis=2); # shape (nTriangles,3)
    min_edge = np.argmin( edge_len,axis=1);                # shape (nTriangles)
 
    # find point as C (opposit to min_edge) and resample CA and CB
    indC = min_edge-1;
    A,B,C,domain_points,image_points = self.__resample_edges_of_triangle(simplices,indC,nDivide);
                                                           # shape (nDivide,2,nTriangles,2)
    # determine indices of broken segments (largest elements in CA and CB)
    len_segments = np.sum(np.diff(image_points,axis=0)**2,axis=-1); 
                                                    # shape (nDivide-1,2,nTriangle)
    largest_segments = np.argmax(len_segments,axis=0); # shape (2,nTriangle) 
    edge_points = np.asarray((largest_segments,largest_segments+1));
                                                    # shape (2,2,nTriangle)
 
    # set points p1 ... p4 for segmentation of triangle
    # see http://stackoverflow.com/questions/15660885/correctly-indexing-a-multidimensional-numpy-array-with-another-array-of-indices
    idx_tuple = (edge_points[...,np.newaxis],) + tuple(np.ogrid[:2,:nTriangles,:2]);
    new_domain_points = domain_points[idx_tuple];
    new_image_points  = image_points[idx_tuple];    
              # shape (2,2,nTriangle,2), indicating iDistance,iEdge,iTriangle,(x/y)
 
    # update points in mesh (points are no longer unique!)
    logging.info("refining_broken_triangles(): adding %d points"%(4*nTriangles));
    self.image = np.vstack((self.image,new_image_points.reshape(-1,2))); 
    self.domain= np.vstack((self.domain,new_domain_points.reshape(-1,2)));    
   
    if bPlot:   
      fig = self.plot_triangulation(skip_triangle=is_broken);
      ax1,ax2 = fig.axes;
      ax1.plot(domain_points[...,0].flat,domain_points[...,1].flat,'k.',label='test points');
      ax1.plot(new_domain_points[...,0].flat,new_domain_points[...,1].flat,'g.',label='selected points');
      ax1.legend(loc=0);      
      ax2.plot(image_points[...,0].flat,image_points[...,1].flat,'k.')
      ax2.plot(new_image_points[...,0].flat,new_image_points[...,1].flat,'g.',label='selected points');   
    
    # indices for points p1 ... p4 in new list of points self.domain 
    # (offset by number of points in the original mesh!)
    # Note: by construction, the order of p1 ... p4 corresponds exactly to the order
    #       shown above (first tuple contains points closest to C,
    #       first on CA, then on CB, second tuple beyond the discontinuity)
    (p1,p2),(p3,p4) = np.arange(4*nTriangles).reshape(2,2,nTriangles) + nPointsOrigMesh;
                                                    # shape (nTriangles,)
    # construct the five triangles from points
    t1=np.vstack((C,p1,p2));                        # shape (3,nTriangles)
    t2=np.vstack((p1,p3,p2));
    t3=np.vstack((p2,p3,p4));
    t4=np.vstack((p4,p3,A));
    t5=np.vstack((p4,A,B));
    new_simplices = np.hstack((t1,t2,t3,t4,t5)).T;  
       # shape (5*nTriangles,3), reshape as (5,nTriangles,3) to obtain subdivision of each triangle  

    # DEBUG subdivision of triangles
    if bPlot:
      for t in bPlotTriangles: # select index of triangle to look at
        BCA=[B[t],C[t],A[t]]; subdiv=new_simplices[t::nTriangles,:];
        pt=self.domain[BCA]; ax1.plot(pt[...,0],pt[...,1],'g')
        pt=self.image[BCA];  ax2.plot(pt[...,0],pt[...,1],'g')
        pt=self.domain[subdiv]; ax1.plot(pt[...,0],pt[...,1],'r')
        pt=self.image[subdiv];  ax2.plot(pt[...,0],pt[...,1],'r')

    # sanity check that total area did not change after segmentation
    old = np.sum(np.abs(self.get_area_in_domain(simplices)));
    new = np.sum(np.abs(self.get_area_in_domain(new_simplices)));
    assert(abs((old-new)/old)<1e-10) # segmentation of triangle has no holes/overlaps

    # update list of simplices
    return self.__add_new_simplices(new_simplices,broken);  
    
    
  def refine_invalid_triangles(self,nDivide=10,bPlot=False,bPlotTriangles=[0]):
    """
    subdivide triangles which have one or two invalid vertices (x or y coordinate are np.nan)
      nDivide    ... (opt) number of subdivisions of each side of triangle
      bPlot      ... (opt) plot sampling and selected points for debugging 
      bPlotTriangles (opt) list of triangle indices for which segmentation should be shown

    returns: number of new triangles
    Note: The resulting mesh will be no longer a Delaunay mesh (identical points 
          might be present, circumference rule not guaranteed). Mesh functions, 
          that need this property (like refine_large_triangles()) will not work
          after calling this function.
    """
    vertices = self.image[self.simplices];                 # shape (nSimplices,3,2)    
    bInvalidVertex = np.any(np.isnan(vertices),axis=2);    # shape (nSimplices,3)   
    if ~np.any(bInvalidVertex): return 0;                  # nothing to do
    
    # we only consider two cases: one vertex is invalid (generate two new triangles)
    #  or two vertices are invalid (generate one new triangle)
    #  all other triangles are unchanged
    nInvalidVertices = np.sum(bInvalidVertex,axis=1);      # shape (nSimplices)
    ind_case1 = nInvalidVertices==1;
    ind_case2 = nInvalidVertices==2;
    
    new_simplices=[];    
    if np.any(ind_case1):
      new_simplices.extend(self.__subdivide_triangles_with_one_invalid_vertex(ind_case1,nDivide));
    if np.any(ind_case2):
      new_simplices.extend(self.__subdivide_triangles_with_two_invalid_vertices(ind_case2,nDivide));
    new_simplices=np.reshape(new_simplices,(-1,3));    
    
    # update list of simplices
    bReplace=np.logical_or(ind_case1,ind_case1);
    return self.__add_new_simplices(new_simplices,bReplace);
    
    
  def __subdivide_triangles_with_one_invalid_vertex(self,bInvalid,nDivide=10):
    """
    case 1: one point is invalid (chosen as point C)
    adds new points p1 and p2 to mesh and returns new simplices
                 C
                 x
                x x              x invalid points 
               x   x             o new triangle vertices (first valid from C)
              x     x
          p1 o       o p2
            /         \          new triangles:
           /___________\           (p1,A,p2),(A,B,p2)
          A              B 
    """
    simplices = self.simplices[bInvalid];                  # shape (nTriangles,3)
    triangles = self.image[simplices];                     # shape (nTriangles,3,2)
    nTriangles= triangles.shape[0];
    nPointsOrigMesh = self.image.shape[0];  
    
    # find invalid point as C (index on first axis) and resample CA and CB
    indC = np.where(np.any(np.isnan(triangles),axis=-1))[1];
    A,B,C,domain_points,image_points = self.__resample_edges_of_triangle(simplices,indC,nDivide);
                                                           # shape (nDivide,2,nTriangles,2)
    assert(np.all(np.any(np.isnan(self.image[C]),axis=-1)));  # all points C should be invalid

    # iterate over all triangles and subdivide them
    new_domain_points=[];
    new_image_points=[];
    new_simplices=[];
    for k in xrange(nTriangles):    
      # find index of first valid point p1 on CA and p2 on CB
      ind = np.any(np.isnan(image_points[:,:,k]),axis=-1);  # shape (nDivide,2)
      p1=np.where(~ind[:,0])[0][0];                   # first valid point on CA
      p2=np.where(~ind[:,1])[0][0];                   # first valid ponit on CB
      new_domain_points.extend((domain_points[p1,0,k,:], domain_points[p2,1,k,:]));
      new_image_points.extend( ( image_points[p1,0,k,:],  image_points[p2,1,k,:]));
      # calculate index for points p1 and p2 in self.domain = [self.domain, new_domain_points]
      P1 = nPointsOrigMesh+2*k; P2=P1+1;
      new_simplices.extend(((P1,A[k],P2), (A[k],B[k],P2)));

    # update points in mesh (points are no longer unique!)
    logging.info("refine_invalid_triangles(case1): adding %d points"%(2*nTriangles));
    self.image = np.vstack((self.image,np.reshape(new_image_points,(2*nTriangles,2)))); 
    self.domain= np.vstack((self.domain,np.reshape(new_domain_points,(2*nTriangles,2))));  

    return np.reshape(new_simplices,(2*nTriangles,3));
    

  def __subdivide_triangles_with_two_invalid_vertices(self,bInvalid,nDivide=10):
    """
    case 2: two points are invalid (chosen as points A and B)
                 C
                 /\
                /  \              x invalid points 
               /    \             o new triangle vertices (last valid from C)
              /      \
          p1 o        o p2
            x          x          new triangle:
           xxxxxxxxxxxxxx           (p1,p2,C)
          A              B 
    """
    simplices = self.simplices[bInvalid];                  # shape (nTriangles,3)
    triangles = self.image[simplices];                     # shape (nTriangles,3,2)
    nTriangles= triangles.shape[0];
    nPointsOrigMesh = self.image.shape[0];  

    # find valid point as C (index on first axis) and resample CA and CB
    indC = np.where(~np.any(np.isnan(triangles),axis=-1))[1];
    A,B,C,domain_points,image_points = self.__resample_edges_of_triangle(simplices,indC,nDivide);
                                                           # shape (nDivide,2,nTriangles,2)
    assert(np.all(np.any(np.isnan(self.image[A]),axis=-1)));  # all points A should be invalid
    assert(np.all(np.any(np.isnan(self.image[B]),axis=-1)));  # all points B should be invalid
    
    # iterate over all triangles and subdivide them
    new_domain_points=[];
    new_image_points=[];
    new_simplices=[];
    for k in xrange(nTriangles):    
      # find index of first valid point p1 on CA and p2 on CB
      ind = np.any(np.isnan(image_points[:,:,k]),axis=-1);  # shape (nDivide,2)
      p1=np.where(~ind[:,0])[0][-1];                   # last valid point on CA
      p2=np.where(~ind[:,1])[0][-1];                   # last valid ponit on CB
      new_domain_points.extend((domain_points[p1,0,k,:], domain_points[p2,1,k,:]));
      new_image_points.extend( ( image_points[p1,0,k,:],  image_points[p2,1,k,:]));
      # calculate index for points p1 and p2 in self.domain = [self.domain, new_domain_points]
      P1 = nPointsOrigMesh+2*k; P2=P1+1;
      new_simplices.append((P1,P2,C[k]));
 
    # update points in mesh (points are no longer unique!)
    logging.info("refine_invalid_triangles(case2): adding %d points"%(2*nTriangles));
    self.image = np.vstack((self.image,np.reshape(new_image_points,(2*nTriangles,2)))); 
    self.domain= np.vstack((self.domain,np.reshape(new_domain_points,(2*nTriangles,2))));  

    return np.reshape(new_simplices,(nTriangles,3));
        


  def __resample_edges_of_triangle(self,simplices,indC,nDivide=10):
    """
    generate dense sampling on edges CA and CB on given simplices:
      simplices ... vertex indices of triangles to resample, shape (nTriangles,3)
      indC      ... vertex number (mod 3) that should be used as point C, shape (nTriangles)
      nDivide   ... number of sampling points on CA and CB
    returns: 
      A,B,C     ... indices of points A,B,C, shape (nTriangles,)
      domain_points(iPoint,iSide,iTriangle,xy) ... sampling points along CA,CB in domain
      image_points(iPoint,iSide,iTriangle,xy)  ... sampling points along CA,CB in image
    """    
    # get indices of points ABC as shown above (C is isolated point)
    nTriangles = simplices.shape[0];    
    ind_triangle = np.arange(nTriangles)
    C = simplices[ind_triangle,(indC)%3];
    A = simplices[ind_triangle,(indC+1)%3];
    B = simplices[ind_triangle,(indC-1)%3];
    # create dense sampling along C->B and C->A in domain space
    x = np.linspace(0,1,nDivide,endpoint=True);
    CA = np.outer(1-x,self.domain[C]) + np.outer(x,self.domain[A]);
    CB = np.outer(1-x,self.domain[C]) + np.outer(x,self.domain[B]);
    # map sampling on CA and CB to image space 
    domain_points= np.hstack((CA,CB)).reshape(nDivide,2,nTriangles,2);
    image_points = self.mapping(domain_points.reshape(-1,2)).reshape(nDivide,2,nTriangles,2);
    return A,B,C,domain_points,image_points;       


  def  __add_new_simplices(self,new_simplices,bReplace):
    """
      add list of new simplices to Mesh and Replace old simplices indicated by boolean array
      perform sanity checks beforehand
        new_simplices ... shape(nTriangles,3)
        bReplace      ... shape(self.simplices.shape[0])
      returns: number of added triangles
    """
    # remove degenerated triangles (p1,p2 identical to A or B) => area is 0 
    area = self.get_area_in_domain(new_simplices);    
    degenerated = np.abs(area/self.initial_domain_area)<1e-10;
    new_simplices = new_simplices[~degenerated];        # remove degenerate triangles
    assert(np.all(area[~degenerated]>0));               # by construction all triangles are oriented ccw
    # update simplices in mesh    
    self.__tri = None; # delete initial Delaunay triangulation        
    self.simplices=np.vstack((self.simplices[~bReplace], new_simplices)); # no longer Delaunay
    return new_simplices.shape[0];
