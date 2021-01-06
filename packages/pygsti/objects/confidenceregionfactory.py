""" Classes for constructing confidence regions """
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

import numpy       as _np
import scipy.stats as _stats
import warnings    as _warnings
import itertools   as _itertools
import collections as _collections
from .. import optimize as _opt
from .. import tools as _tools

from .gatecalc import P_RANK_TOL
from ..baseobjs import VerbosityPrinter as _VerbosityPrinter

# NON-MARKOVIAN ERROR BARS
#Connection with Robin's notes:
#
# Robins notes: pg 21 : want to set radius delta'(alpha,r2)
#   via: lambda(G) = lambda(G_mle) + delta'
#
# Connecting with pyGSTi Hessian (H) calculations:
#   lambda(G) = 2(maxLogL - logL(G)) ~ chi2_k   (as defined in notes)
#   lambda(G_mle) = 2(maxLogL - logL(G_mle))
#
#  expand logL around max:
#    logL(G_mle + dx) ~= logL(G_mle) - 1/2 dx*H*dx (no first order term)
#
#  Thus, delta'
#    delta' = lambda(G) - lambda(G_mle) = -2(log(G)-log(G_mle))
#           = dx*H*dx ==> delta' is just like C1 or Ck scaling factors
#                         used for computing normal confidence regions
#    (recall delta' is computed as the alpha-th quantile of a
#     non-central chi^2_{K',r2} where K' = #of gateset params and
#     r2 = lambda(G_mle) - (K-K'), where K = #max-model params (~#gatestrings)
#     is the difference between the expected (mean) lambda (=K-K') and what
#     we actually observe (=lambda(G_mle)).
#

class ConfidenceRegionFactory(object):
    """
    An object which is capable of generating confidence intervals/regions.

    Often times, it does so by holding the Hessian of a fit function with
    respect to a `GateSet`'s parameters and related projections of it onto the
    non-gauge space.

    Alternative (non-Hessian-based) means of computing confidence intervals
    are also available, such as by using so-called "linear reponse error bars".
    """

    def __init__(self, parent, gateset_lbl, gatestring_list_lbl,
                 hessian=None, nonMarkRadiusSq=None):
        """
        Initializes a new ConfidenceRegionFactory.

        Parameters
        ----------
        parent : Estimate
            the parent estimate object, needed to resolve gate set and gate
            string list labels.

        gateset_lbl : str
            The key into the parent `Estimate`'s `.gatesets` dictionary that
            gives the `GateSet` about which confidence regions will be 
            constructed.

        gatestring_list_lbl : str
            The key into the parent `Results`'s `.gatestring_lists` dictionary
            that specifies which gate sequences should be or were included 
            when computing fit functions (the log-likelihood or chi2).

        hessian : numpy array, optional
            A pre-computed nParams x nParams Hessian matrix, where nParams is
            the number of dimensions of gateset space, i.e. gateset.num_params().

        nonMarkRadiusSq : float, optional
            The non-Markovian radius associated with the goodness of fit found
            at the point where `hessian` was computed.  This must be specified
            whenver `hessian` is, and should be left as `None` when `hessian`
            is not specified.
        """

        #May be specified (together) whey hessian has already been computed
        assert(hessian is None or nonMarkRadiusSq is not None), \
            "'nonMarkRadiusSq' must be non-None when 'hessian' is specified"
        self.hessian = hessian
        self.nonMarkRadiusSq = nonMarkRadiusSq
                
        self.hessian_projection_parameters = _collections.OrderedDict()
        self.inv_hessian_projections = _collections.OrderedDict()
        self.linresponse_mlgst_params = None
        self.nNonGaugeParams = self.nGaugeParams = None

        self.gateset_lbl = gateset_lbl
        self.gatestring_list_lbl = gatestring_list_lbl
        self.set_parent( parent )

    def __getstate__(self):
        # don't pickle parent (will create circular reference)
        to_pickle = self.__dict__.copy()
        del to_pickle['parent']

        # *don't* pickle any Comm objects
        if self.linresponse_mlgst_params and self.linresponse_mlgst_params.has_key("comm"):
            del self.linresponse_mlgst_params['comm'] # one *cannot* pickle Comm objects

        return to_pickle

    def __setstate__(self, stateDict):
        self.__dict__.update(stateDict)
        self.parent = None # initialize to None upon unpickling
        
    def set_parent(self, parent):
        """
        Sets the parent Estimate object of this ConfidenceRegionFactory.
        """
        self.parent = parent        
        
    def has_hessian(self):
        """
        Returns whether or not the Hessian has already been computed.

        When True, :func:`project_hessian` can be used to project the
        Hessian for use in creating confidence intervals.  When False,
        either :func:`compute_hessian` can be called to compute the 
        Hessian or slower methods must be used to estimate the necessary
        portion of the Hessian.  The result of this function is often used
        to decide whether or not to proceed with an error-bar computation.

        Returns
        -------
        bool
        """
        #return bool(self.invRegionQuadcForm is not None)
        return bool(self.hessian is not None)

    def can_construct_views(self):
        """
        Checks whether this factory has enough information to construct
        'views' of itself (`ConfidenceRegionFactoryView` objects via the
        :method:`view` method), which can then be used to construct 
        confidence intervals.

        Returns
        -------
        bool
        """
        try:
            self.view(95) #will raise assertion errors
            return True
        except:
            return False

        
    def get_gateset(self):
        """
        Retrieve the associated gate set.

        Returns
        -------
        GateSet
            the gate set marking the center location of this confidence region.
        """
        assert(self.parent is not None) # Estimate
        return self.parent.gatesets[self.gateset_lbl]

        
    def compute_hessian(self, comm=None, memLimit=None):
        """
        Computes the Hessian for this factory.

        Parameters
        ----------
        comm : mpi4py.MPI.Comm, optional
            When not None, an MPI communicator for distributing the computation
            across multiple processors.

        memLimit : int, optional
            A rough memory limit in bytes which restricts the amount of intermediate
            values that are computed and stored.

        Returns
        -------
        numpy.ndarray
            The Hessian matrix (also stored internally)
        """
        assert(self.parent is not None) # Estimate
        assert(self.parent.parent is not None) # Results

        gateset = self.parent.gatesets[self.gateset_lbl]
        gatestring_list = self.parent.parent.gatestring_lists[self.gatestring_list_lbl]
        dataset = self.parent.parent.dataset

        #extract any parameters we can get from the Estimate
        parameters = self.parent.parameters
        obj = parameters.get('objective','logl')
        minProbClip = parameters.get('minProbClip', 1e-4)
        minProbClipForWeighting = parameters.get('minProbClipForWeighting',1e-4)
        probClipInterval = parameters.get('probClipInterval',(-1e6,1e6))
        radius = parameters.get('radius',1e-4)
        cptp_penalty_factor = parameters.get('cptpPenaltyFactor',0)
        spam_penalty_factor = parameters.get('spamPenaltyFactor',0)
        useFreqWt = parameters.get('useFreqWeightedChiSq',False)
        aliases = parameters.get('gateLabelAliases',None)
        if memLimit is None:
            memLimit = parameters.get('memLimit',None)

        vb = 3 if memLimit else 0 #only show details of hessian comp when there's a mem limit (a heuristic)

        assert(cptp_penalty_factor == 0), 'cptp_penalty_factor unsupported in hessian computation'
        assert(spam_penalty_factor == 0), 'spam_penalty_factor unsupported in hessian computation'
        assert(useFreqWt == False), 'useFreqWeightedChiSq unsupported in hessian computation'

        #Expand gate label aliases used in DataSet lookups
        ds_gatestring_list = _tools.find_replace_tuple_list(
            gatestring_list, aliases)

        nGateStrings = len(gatestring_list)
        nModelParams = gateset.num_nongauge_params()        
        nDataParams  = dataset.get_degrees_of_freedom(ds_gatestring_list)
          #number of independent parameters in dataset (max. model # of params)

        #OLD nDataParams  = nGateStrings*(len(dataset.get_spam_labels())-1)

        
        MIN_NON_MARK_RADIUS = 1e-8 #must be >= 0

        if obj == 'logl':
            hessian = _tools.logl_hessian(gateset, dataset, gatestring_list,
                                          minProbClip, probClipInterval, radius,
                                          comm=comm, memLimit=memLimit, verbosity=vb,
                                          gateLabelAliases=aliases)

            nonMarkRadiusSq = max( 2*(_tools.logl_max(gateset, dataset)
                                      - _tools.logl(gateset, dataset,
                                                    gateLabelAliases=aliases)) \
                                   - (nDataParams-nModelParams), MIN_NON_MARK_RADIUS )

        elif obj == 'chi2':
            chi2, hessian = _tools.chi2(gateset, dataset, gatestring_list,
                                False, True, minProbClipForWeighting,
                                probClipInterval, memLimit=memLimit,
                                gateLabelAliases=aliases)
            
            nonMarkRadiusSq = max(chi2 - (nDataParams-nModelParams), MIN_NON_MARK_RADIUS)
        else:
            raise ValueError("Invalid objective '%s'" % obj)
        
        self.hessian = hessian
        self.nonMarkRadiusSq = nonMarkRadiusSq
        return hessian



    def project_hessian(self, projection_type, label=None, tol=1e-7, maxiter=10000):
        """
        Projects the Hessian onto the non-gauge space.

        This is a necessary step before confidence regions/intervals can be
        computed via Hessian-based methods.

        Parameters
        ----------
        projection_type : string
            Specifies how (and whether) to project the given hessian matrix
            onto a non-gauge space.  Allowed values are:

            - 'std' -- standard projection onto the space perpendicular to the
              gauge space.
            - 'none' -- no projection is performed.  Useful if the supplied
              hessian has already been projected.
            - 'optimal gate CIs' -- a lengthier projection process in which a
              numerical optimization is performed to find the non-gauge space
              which minimizes the (average) size of the confidence intervals
              corresponding to gate (as opposed to SPAM vector) parameters.
            - 'intrinsic error' -- compute separately the intrinsic error
              in the gate and spam GateSet parameters and set weighting metric
              based on their ratio.

        label : str, optional
            The internal label to use for this projection.  If None, then
            `projection_type` is used, which is usually fine.

        tol : float, optional
            Tolerance for optimal Hessian projection.  Only used when
            `projection_type == 'optimal gate CIs'`.

        maxiter : int, optional
            Maximum iterations for optimal Hessian projection.  Only used when
            `projection_type == 'optimal gate CIs'`.
        
        Returns
        -------
        numpy.ndarray
            The *inverse* of the projected Hessian matrix (also stored internally)
        """
        assert(self.hessian is not None), "No hessian! Compute it using 'compute_hessian'"
        
        if label is None:
            label = projection_type 
        
        gateset = self.parent.gatesets[self.gateset_lbl]
        proj_non_gauge = gateset.get_nongauge_projector()
        self.nNonGaugeParams = _np.linalg.matrix_rank(proj_non_gauge, P_RANK_TOL)
        self.nGaugeParams = gateset.num_params() - self.nNonGaugeParams

        #Project Hessian onto non-gauge space
        if projection_type == 'none':
            projected_hessian = self.hessian
        elif projection_type == 'std':
            projected_hessian = _np.dot(proj_non_gauge, _np.dot(self.hessian, proj_non_gauge))
        elif projection_type == 'optimal gate CIs':
            projected_hessian = self._optProjectionForGateCIs("L-BFGS-B", maxiter, maxiter,
                                                              tol, verbosity=3) #verbosity for DEBUG
        elif projection_type == 'intrinsic error':
            projected_hessian = self._optProjectionFromSplit(verbosity=3) #verbosity for DEBUG
        else:
            raise ValueError("Invalid value of projection_type argument: %s" % projection_type)

        #Invert *non-gauge-part* of quadratic 'projected_hessian' by eigen-decomposing ->
        #   inverting the non-gauge eigenvalues -> re-constructing via eigenvectors.
        # (Note that Hessian & quadc form mxs are symmetric so eigenvalues == singular values)
        evals,U = _np.linalg.eigh(projected_hessian)  # regionQuadcForm = U * diag(evals) * U.dag (b/c U.dag == inv(U) )
        Udag = _np.conjugate(_np.transpose(U))
    
          #invert only the non-gauge eigenvalues (those with ordering index >= nGaugeParams)
        orderInds = [ el[0] for el in sorted( enumerate(evals), key=lambda x: abs(x[1])) ] # ordering index of each eigenvalue
        invEvals = _np.zeros( evals.shape, evals.dtype )
        for i in orderInds[self.nGaugeParams:]:
            invEvals[i] = 1.0/evals[i]
    
          #re-construct "inverted" quadratic form
        inv_projected_hessian = _np.diag( invEvals )
        inv_projected_hessian = _np.dot(U, _np.dot(inv_projected_hessian, Udag))
        
        #save input args for copying object
        self.inv_hessian_projections[label] = inv_projected_hessian
        self.hessian_projection_parameters[label] = {
            'projection_type': projection_type,
            'tol': tol,
            'maxiter': maxiter
        }
        return inv_projected_hessian



    def enable_linear_response_errorbars(self):
        """
        Stores the parameters needed to run (on-demand) the ML-GST
        optimizations needed to compute error bars on quantities.

        'linear response' mode obtains elements of the Hessian via the
        linear response of a "forcing term".  This requres a likelihood
        optimization for *every* computed error bar, but avoids pre-
        computation of the entire Hessian matrix, which can be 
        prohibitively costly on large parameter spaces.

        Returns
        -------
        None
        """
        assert(self.parent is not None) # Estimate
        assert(self.parent.parent is not None) # Results

        gatestring_list = self.parent.parent.gatestring_lists[self.gatestring_list_lbl]
        dataset = self.parent.parent.dataset

        parameters = self.parent.parameters
        minProbClip = parameters.get('minProbClip', 1e-4)
        #minProbClipForWeighting = parameters.get('minProbClipForWeighting',1e-4)
        probClipInterval = parameters.get('probClipInterval',(-1e6,1e6))
        radius = parameters.get('radius',1e-4)
        cptp_penalty_factor = parameters.get('cptpPenaltyFactor',0)
        spam_penalty_factor = parameters.get('spamPenaltyFactor',0)
        aliases = parameters.get('gateLabelAliases',None)
        distributeMethod = parameters.get('distributeMethod','deriv')
        memLimit = parameters.get('memLimit',None)
        comm = parameters.get('comm',None)
        
        self.linresponse_mlgst_params = {
            'dataset': dataset,
            'gateStringsToUse': gatestring_list,
            'maxiter': 10000, 'tol': 1e-10,
            'cptp_penalty_factor': cptp_penalty_factor,
            'spam_penalty_factor': spam_penalty_factor,
            'minProbClip': minProbClip, 
            'probClipInterval': probClipInterval,
            'radius': radius,
            'poissonPicture': True, 'verbosity': 2, #NOTE: HARDCODED
            'memLimit': memLimit, 'comm': comm,
            'distributeMethod': distributeMethod, 'profiler': None,
            'gateLabelAliases': aliases
            }


    def view(self, confidenceLevel, regionType='normal',
             hessian_projection_label=None):
        """
        Constructs a "view" of this ConfidenceRegionFactory for a particular
        type and confidence level.  The returned view object can then be used to 
        construct confidence intervals/regions.

        Parameters
        ----------
        confidenceLevel : float
            The confidence level as a percentage, i.e. between 0 and 100.

        regionType : {'normal', 'non-markovian'}
            The type of confidence regions.  `'normal'` constructs standard
            intervals based on the inverted Hessian matrix or linear-response
            optimizations.  `'non-markovian'` attempts to enlarge the intervals
            to account for the badness-of-fit at the current location.

        hessian_projection_label : str, optional
            A label specifying which Hessian projection to use (only useful
            when there are multiple).  These labels are either the 
            `projection_type` values of :func:`project_hessian` or the
            custom `label` argument provided to that function.  If None,
            then the most recent (perhaps the only) projection is used.

        Returns
        -------
        ConfidenceRegionFactoryView
        """
        inv_hessian_projection = None
        linresponse_mlgst_params = None

        assert(self.parent is not None) # Estimate
        gateset = self.parent.gatesets[self.gateset_lbl]
        
        if self.hessian is not None:
            assert(len(self.inv_hessian_projections) > 0), \
                "No Hessian projections!  Use 'project_hessian' to create at least one."
            if hessian_projection_label is None:
                hessian_projection_label = list(self.inv_hessian_projections.keys())[-1]
            assert(hessian_projection_label in self.inv_hessian_projections.keys()), \
                "Hessian projection '%s' does not exist!" % hessian_projection_label
            inv_hessian_projection = self.inv_hessian_projections[hessian_projection_label]
        else:
            assert(self.linresponse_mlgst_params is not None), \
            "Must either compute & project a Hessian matrix or enable linear response parameters"
            linresponse_mlgst_params = self.linresponse_mlgst_params

        #Compute the non-Markovian "radius" if required
        if regionType == "normal":
            nonMarkRadiusSq = 0.0
        elif regionType == "non-markovian":
            nonMarkRadiusSq = self.nonMarkRadiusSq
        else:
            raise ValueError("Invalid confidence region type: %s" % regionType)

        return ConfidenceRegionFactoryView(gateset, inv_hessian_projection, linresponse_mlgst_params,
                                           confidenceLevel, nonMarkRadiusSq,
                                           self.nNonGaugeParams, self.nGaugeParams)
        
        #TODO: where to move this?
        ##Check that number of gauge parameters reported by gateset is consistent with confidence region
        ## since the parameter number computed this way is used in chi2 or logl progress tables
        #Np_check =  gateset.num_nongauge_params()
        #if(Np_check != cri.nNonGaugeParams):
        #    _warnings.warn("Number of non-gauge parameters in gateset and confidence region do "
        #                   + " not match.  This indicates an internal logic error.")

    def _optProjectionForGateCIs(self, method="L-BFGS-B", maxiter=10000,
                                 maxfev = 10000, tol=1e-6, verbosity=0):
        printer = _VerbosityPrinter.build_printer(verbosity)
        gateset = self.parent.gatesets[self.gateset_lbl]
        base_hessian = self.hessian
        level = 95 # or 50, or whatever - the scale factory doesn't matter for the optimization
    
        printer.log('', 3)
        printer.log("--- Hessian Projector Optimization for gate CIs (%s) ---" % method, 2, indentOffset=-1)
    
        def _objective_func(vectorM):
            matM = vectorM.reshape( (self.nNonGaugeParams,self.nGaugeParams) )
            proj_extra = gateset.get_nongauge_projector(nonGaugeMixMx=matM)
            projected_hessian_ex = _np.dot(proj_extra, _np.dot(base_hessian, proj_extra))
    
            sub_crf = ConfidenceRegionFactory(self.parent, self.gateset_lbl, self.gatestring_list_lbl,
                                              projected_hessian_ex, 0.0)
            sub_crf.project_hessian('none')
            crfv = sub_crf.view(level)

            gateCIs = _np.concatenate( [ crfv.get_profile_likelihood_confidence_intervals(gl).flatten()
                                         for gl in gateset.gates] )
            return _np.sqrt( _np.sum(gateCIs**2) )
    
        #Run Minimization Algorithm
        startM = _np.zeros( (self.nNonGaugeParams,self.nGaugeParams), 'd')
        x0 = startM.flatten()
        print_obj_func = _opt.create_obj_func_printer(_objective_func)
        minSol = _opt.minimize(_objective_func, x0,
                               method=method, maxiter=maxiter,
                               maxfev=maxfev, tol=tol,
                               callback = print_obj_func if verbosity > 2 else None)
    
        mixMx = minSol.x.reshape( (self.nNonGaugeParams,self.nGaugeParams) )
        proj_extra = gateset.get_nongauge_projector(nonGaugeMixMx=mixMx)
        projected_hessian_ex = _np.dot(proj_extra, _np.dot(base_hessian, proj_extra))
    
        printer.log('The resulting min sqrt(sum(gateCIs**2)): %g' % minSol.fun, 2)
        return projected_hessian_ex
    
    
    def _optProjectionFromSplit(self, verbosity=0):
        printer = _VerbosityPrinter.build_printer(verbosity)
        gateset = self.parent.gatesets[self.gateset_lbl]
        base_hessian = self.hessian
        level = 95 # or 50, or whatever - the scale factory doesn't matter for the optimization
    
        printer.log('', 3)
        printer.log("--- Hessian Projector Optimization from separate SPAM and Gate weighting ---", 2, indentOffset=-1)
        
        #get gate-intrinsic-error
        proj = gateset.get_nongauge_projector(itemWeights={'gates':1.0,'spam': 0.0})
        projected_hessian = _np.dot(proj, _np.dot(base_hessian, proj))
        sub_crf = ConfidenceRegionFactory(self.parent, self.gateset_lbl,
                                          self.gatestring_list_lbl, projected_hessian, 0.0)
        sub_crf.project_hessian('none')
        crfv = sub_crf.view(level)
        gateCIs = _np.concatenate( [ crfv.get_profile_likelihood_confidence_intervals(gl).flatten()
                                         for gl in gateset.gates] )
        gate_intrinsic_err = _np.sqrt( _np.mean(gateCIs**2) )
    
        #get spam-intrinsic-error
        proj = gateset.get_nongauge_projector(itemWeights={'gates':0.0,'spam': 1.0})
        projected_hessian = _np.dot(proj, _np.dot(base_hessian, proj))
        sub_crf = ConfidenceRegionFactory(self.parent, self.gateset_lbl,
                                          self.gatestring_list_lbl, projected_hessian, 0.0)
        sub_crf.project_hessian('none')
        crfv = sub_crf.view(level)
        spamCIs = _np.concatenate( [ crfv.get_profile_likelihood_confidence_intervals(sl).flatten()
                                         for sl in _itertools.chain(iter(gateset.preps),
                                                                    iter(gateset.povms))] )
        spam_intrinsic_err = _np.sqrt( _np.mean(spamCIs**2) )
    
        ratio = gate_intrinsic_err / spam_intrinsic_err
        proj = gateset.get_nongauge_projector(itemWeights={'gates':1.0,'spam': ratio})
        projected_hessian = _np.dot(proj, _np.dot(base_hessian, proj))
    
        if printer.verbosity >= 2:
            #Create crfv here just to extract #'s for print stmts
            sub_crf = ConfidenceRegionFactory(self.parent, self.gateset_lbl,
                                              self.gatestring_list_lbl, projected_hessian, 0.0)
            sub_crf.project_hessian('none')
            crfv = sub_crf.view(level)

            gateCIs = _np.concatenate( [ crfv.get_profile_likelihood_confidence_intervals(gl).flatten()
                                             for gl in gateset.gates] )
            spamCIs = _np.concatenate( [ crfv.get_profile_likelihood_confidence_intervals(sl).flatten()
                                             for sl in _itertools.chain(iter(gateset.preps),
                                                                        iter(gateset.povms))] )
            gate_err = _np.sqrt( _np.mean(gateCIs**2) )
            spam_err = _np.sqrt( _np.mean(spamCIs**2) )
            printer.log('Resulting intrinsic errors: %g (gates), %g (spam)' %
                        (gate_intrinsic_err, spam_intrinsic_err), 2)
            printer.log('Resulting sqrt(mean(gateCIs**2)): %g' % gate_err, 2)
            printer.log('Resulting sqrt(mean(spamCIs**2)): %g' % spam_err, 2)
    
        return projected_hessian

            


class ConfidenceRegionFactoryView(object):
    """ 
    Encapsulates a lightweight "view" of a ConfidenceRegionFactory,
    which is principally defined by it's having a fixed confidence-level.
    Thus, a "view" is like a factory that generates confidence intervals for
    just a single confidence level.  As such, it is a useful object to pass
    around to routines which compute and display error bars, as these routines
    typically don't depend on what confidence-level is being used.
    """

    def __init__(self, gateset, inv_projected_hessian, mlgst_params, confidenceLevel,
                 nonMarkRadiusSq, nNonGaugeParams, nGaugeParams):
        """
        Creates a new ConfidenceRegionFactoryView.

        Usually this constructor is not called directly, and objects of
        this type are obtained by calling the :method:`view` method of
        a `ConfidenceRegionFactory` object.

        Parameters
        ----------
        gateset : GateSet
            The gateset at the center of this confidence region.

        inv_projected_hessian : numpy.ndarray
            The computed inverse of the non-gauge-projected Hessian.

        mlgst_params : dict
            A dictionary of ML-GST parameters only used for linear-response
            error bars.

        confidenceLevel : float
            the confidence level (between 0 and 100) used in
            the computation of confidence regions/intervals.

        nonMarkRadiusSq : float, optional
            When non-zero, "a non-Markovian error region" is constructed using
            this value as the squared "non-markovian radius". This specifies the
            portion of 2*(max-log-likelihood - gateset-log-likelihood) that we
            attribute to non-Markovian errors (typically the previous
            difference minus it's expected value, the difference in number of
            parameters between the maximal and gateset models).  If set to
            zero (the default), a standard and thereby statistically rigorous
            conficence region is created.  Non-zero values should only be
            supplied if you really know what you're doing.

        nNonGaugeParams, nGaugeParams : int
            The numbers of non-gauge and gauge parameters, respectively.  These could be
            computed from `gateset` but they're passed in to save compuational time.
        """
    
        #Scale projected Hessian for desired confidence level => quadratic form for confidence region
        # assume hessian gives Fisher info, so asymptotically normal => confidence interval = +/- seScaleFctr * 1/sqrt(hessian)
        # where seScaleFctr gives the scaling factor for a normal distribution, i.e. integrating the
        # std normal distribution between -seScaleFctr and seScaleFctr == confidenceLevel/100 (as a percentage)
        assert(confidenceLevel > 0.0 and confidenceLevel < 100.0)
        if confidenceLevel < 1.0:
            _warnings.warn("You've specified a %f%% confidence interval, " % confidenceLevel \
                               + "which is usually small.  Be sure to specify this" \
                               + "number as a percentage in (0,100) and not a fraction in (0,1)." )

        # Get constants C such that xT*Hessian*x = C gives contour for the desired confidence region.
        #  C1 == Single DOF case: constant for a single-DOF likelihood, (or a profile likelihood in our case)
        #  Ck == Total DOF case: constant for a region of the likelihood as a function of *all non-gauge* gateset parameters
        self.nonMarkRadiusSq = nonMarkRadiusSq
        if nonMarkRadiusSq == 0.0: #use == to test for *exact* zero floating pt value as herald
            C1 = _stats.chi2.ppf(confidenceLevel/100.0, 1)
            Ck = _stats.chi2.ppf(confidenceLevel/100.0, nNonGaugeParams)

              # Alt. method to get C1: square the result of a single gaussian (normal distribution)
              #Note: scipy's ppf gives inverse of cdf, so want to know where cdf == the leftover probability on left side
            seScaleFctr = -_stats.norm.ppf((1.0 - confidenceLevel/100.0)/2.0) #std error scaling factor for desired confidence region
            assert(_np.isclose(C1, seScaleFctr**2))

            # save quadratic form Q s.t. xT*Q*x = 1 gives confidence region using C1, i.e. a
            #  region appropriate for generating 1-D confidence intervals.
            if inv_projected_hessian is not None:
                self.invRegionQuadcForm = inv_projected_hessian * C1
            else:
                self.invRegionQuadcForm = None

            self.intervalScaling = _np.sqrt( Ck / C1 ) # multiplicative scaling required to convert intervals
                                                       # to those obtained using a full (using Ck) confidence region.
            self.stdIntervalScaling = 1.0 # multiplicative scaling required to convert intervals
                                          # to *standard* (e.g. not non-Mark.) intervals.
            self.stdRegionScaling = self.intervalScaling # multiplicative scaling required to convert intervals
                                                  # to those obtained using a full *standard* confidence region.

        else:
            C1 = _stats.ncx2.ppf(confidenceLevel/100.0, 1, nonMarkRadiusSq)
            Ck = _stats.ncx2.ppf(confidenceLevel/100.0, nNonGaugeParams, nonMarkRadiusSq)

            # save quadratic form Q s.t. xT*Q*x = 1 gives confidence region using C1, i.e. a
            #  region appropriate for generating 1-D confidence intervals.
            if inv_projected_hessian is not None:
                self.invRegionQuadcForm  = inv_projected_hessian * C1
                self.invRegionQuadcForm /= _np.sqrt(nNonGaugeParams) #make a *worst case* non-mark. region...
            else:
                self.invRegionQuadcForm = None

            self.intervalScaling = _np.sqrt( Ck / C1 ) # multiplicative scaling required to convert intervals
                                                   # to those obtained using a full (using Ck) confidence region.

            stdC1 = _stats.chi2.ppf(confidenceLevel/100.0, 1)
            stdCk = _stats.chi2.ppf(confidenceLevel/100.0, nNonGaugeParams)
            self.stdIntervalScaling = _np.sqrt( stdC1 / C1 ) # see above description
            self.stdRegionScaling = _np.sqrt( stdCk / C1 ) # see above description

            _warnings.warn("Non-Markovian error bars are experimental and" +
                           " cannot be interpreted as standard error bars." +
                           " Proceed with caution!")

        #Store list of profile-likelihood confidence intervals
        #  which == sqrt(diagonal els) of invRegionQuadcForm
        if self.invRegionQuadcForm is not None:
            dim = self.invRegionQuadcForm.shape[0]
            self.profLCI = [ _np.sqrt(abs(self.invRegionQuadcForm[k,k])) for k in range(dim)]
            self.profLCI = _np.array( self.profLCI, 'd' )
        else:
            self.profLCI = None

        self.gateset = gateset
        self.level = confidenceLevel #a percentage, i.e. btwn 0 and 100
        self.nNonGaugeParams = nNonGaugeParams
        self.nGaugeParams = nGaugeParams

        self.mlgst_params = mlgst_params
        self._C1 = C1 #save for linear response scaling
        self.mlgst_evaltree_cache = {} #for _do_mlgst_base speedup

    def __getstate__(self):
        # *don't* pickle any Comm objects
        to_pickle = self.__dict__.copy()
        if self.mlgst_params and self.mlgst_params.has_key("comm"):
            del self.mlgst_params['comm'] # one *cannot* pickle Comm objects
        return to_pickle
        
    def get_errobar_type(self):
        """
        Return the type of error bars this view will generate, either
        "standard" or "non-markovian".

        Returns
        -------
        str
        """
        if self.nonMarkRadiusSq > 0:
            return "non-markovian"
        else:
            return "standard"

    def get_profile_likelihood_confidence_intervals(self, label=None):
        """
        Retrieve the profile-likelihood confidence intervals for a specified
        gate set object (or all such intervals).

        Parameters
        ----------
        label : string, optional
            If not None, can be either a gate or SPAM vector label
            to specify the confidence intervals corresponding to gate, rhoVec,
            or EVec parameters respectively.  If None, then intervals corresponding
            to all of the gateset's parameters are returned.

        Returns
        -------
        numpy array
            One-dimensional array of (positive) interval half-widths which specify
            a symmetric confidence interval.
        """
        if self.profLCI is None:
            raise NotImplementedError("Profile-likelihood confidence intervals" + \
                                      "are not implemented for this type of confidence region")
        if label is None:
            return self.profLCI
        
        elif label in self.gateset.gates:
            return self.profLCI[self.gateset.gates[label].gpindices]

        elif label in self.gateset.preps:
            return self.profLCI[self.gateset.preps[label].gpindices]

        elif label in self.gateset.povms:
            return self.profLCI[self.gateset.povms[label].gpindices]

        else:
            raise ValueError(("Invalid item label (%s) for computing" % label)
                             + "profile likelihood confidence intervals")


    def get_fn_confidence_interval(self, fnObj, eps=1e-7,
                                   returnFnVal=False, verbosity=0):
        """
        Compute the confidence interval for an arbitrary function.

        This "function", however, must be encapsulated as a 
        `GateSetFunction` object, which allows it to neatly specify
        what its dependencies are and allows it to compaute finite-
        different derivatives more efficiently.

        Parameters
        ----------
        fnObj : GateSetFunction
            An object representing the function to evaluate. The
            returned confidence interval is based on linearizing this function
            and propagating the gateset-space confidence region.

        eps : float, optional
            Step size used when taking finite-difference derivatives of fnOfGate.

        returnFnVal : bool, optional
            If True, return the value of fnOfGate along with it's confidence
            region half-widths.

        verbosity : int, optional
            Specifies level of detail in standard output.

        Returns
        -------
        df : float or numpy array
            Half-widths of confidence intervals for each of the elements
            in the float or array returned by fnOfGate.  Thus, shape of
            df matches that returned by fnOfGate.

        f0 : float or numpy array
            Only returned when returnFnVal == True. Value of fnOfGate
            at the gate specified by gateLabel.
        """

        nParams = self.gateset.num_params()
        f0 = fnObj.evaluate(self.gateset) #function value at "base point"

        #Get finite difference derivative gradF that is shape (nParams, <shape of f0>)
        gradF = _create_empty_gradF(f0, nParams)

        fn_dependencies = fnObj.get_dependencies()
        if 'all' in fn_dependencies:
            fn_dependencies = ['all'] #no need to do anything else
        if 'spam' in fn_dependencies:
            fn_dependencies = ["prep:%s"%l for l in self.gateset.preps.keys()] + \
                              ["povm:%s"%l for l in self.gateset.povms.keys()]

        #elements of fn_dependencies are either 'all', 'spam', or
        # the "type:label" of a specific gate or spam vector.
        all_gpindices = []
        for dependency in fn_dependencies:
            gs = self.gateset.copy() #copy that will contain the "+eps" gate set
            
            if dependency == 'all':
                all_gpindices.extend( range(gs.num_params()) )
            else:
                # copy objects because we add eps to them below
                typ,lbl = dependency.split(":")
                if typ == "gate":     gatesetObj = gs.gates[lbl]
                elif typ == "prep":   gatesetObj = gs.preps[lbl]
                elif typ == "povm":   gatesetObj = gs.povms[lbl]
                elif typ == "instrument": gatesetObj = gs.instruments[lbl]
                else: raise ValueError("Invalid dependency type: %s" % typ)
                all_gpindices.extend( gatesetObj.gpindices_as_array() )

        vec0 = gs.to_vector()
        all_gpindices = sorted(list(set(all_gpindices))) #remove duplicates
        
        for igp in all_gpindices: #iterate over "global" GateSet-parameter indices
            vec = vec0.copy(); vec[igp] += eps;
            gs.from_vector(vec)
            gs.basis = self.gateset.basis #we're still in the same basis (maybe needed by fnObj)
            
            f = fnObj.evaluate_nearby( gs )
            if isinstance(f0, dict): #special behavior for dict: process each item separately
                for ky in gradF:
                    gradF[ky][igp] = ( f[ky] - f0[ky] ) / eps
            else:
                assert( _np.linalg.norm(_np.imag(f-f0)) < 1e-12 or _np.iscomplexobj(gradF) ), "gradF seems to be the wrong type!"
                gradF[igp] = _np.real_if_close( f - f0 ) / eps

        return self._compute_return_from_gradF(gradF, f0, returnFnVal, verbosity)

    
    def _compute_return_from_gradF(self, gradF, f0, returnFnVal, verbosity):
        """ Just adds logic for special behavior when f0 is a dict """
        if isinstance(f0, dict):
            df_dict = { ky: self._compute_df_from_gradF(
                               gradF[ky], f0[ky], False, verbosity)
                        for ky in gradF }
            return (df_dict, f0) if returnFnVal else df_dict
        else:
            return self._compute_df_from_gradF(gradF, f0, returnFnVal, verbosity)

        
    def _compute_df_from_gradF(self, gradF, f0, returnFnVal, verbosity):
        if self.invRegionQuadcForm is None:
            df = self._compute_df_from_gradF_linresponse(
                gradF, f0, verbosity)
        else:
            df = self._compute_df_from_gradF_hessian(
                gradF, f0, verbosity)
        return (df, f0) if returnFnVal else df


    def _compute_df_from_gradF_linresponse(self, gradF, f0, verbosity):
        from .. import algorithms as _alg
        assert(self.mlgst_params is not None)

        if hasattr(f0,'dtype') and f0.dtype == _np.dtype("complex"):
            raise NotImplementedError("Can't handle complex-valued functions yet")

        if hasattr(f0,'shape') and len(f0.shape) > 2:
            raise ValueError("Unsupported number of dimensions returned by fnOfGate or fnOfGateset: %d" % len(f0.shape))
              #May not be needed here, but gives uniformity with Hessian case

        #massage gradF, which has shape (nParams,) + f0.shape
        # to that expected by _do_mlgst_base, which is
        # (flat_f0_size, nParams)
        if len(gradF.shape) == 1:
            gradF.shape = (1,gradF.shape[0])
        else:
            flatDim = _np.prod(f0.shape)
            gradF.shape = (gradF.shape[0], flatDim)
            gradF = _np.transpose(gradF) #now shape == (flatDim, nParams)
        assert(len(gradF.shape) == 2)

        mlgst_args = self.mlgst_params.copy()
        mlgst_args['startGateset'] = self.gateset
        mlgst_args['forcefn_grad'] = gradF
        mlgst_args['shiftFctr'] = 100.0
        mlgst_args['evaltree_cache'] = self.mlgst_evaltree_cache
        _, bestGS = _alg.core._do_mlgst_base(**mlgst_args)
        bestGS = _alg.gaugeopt_to_target(bestGS, self.gateset) #maybe more params here?
        norms = _np.array([_np.dot(gradF[i],gradF[i]) for i in range(gradF.shape[0])])
        delta2 = _np.abs(_np.dot(gradF, bestGS.to_vector() - self.gateset.to_vector()) \
            * _np.where(norms > 1e-10, 1.0/norms, 0.0))
        delta2 *= self._C1 #scaling appropriate for confidence level
        delta = _np.sqrt(delta2) # error^2 -> error

        if hasattr(f0,'shape'):
            delta.shape = f0.shape #reshape to un-flattened
        else:
            assert(isinstance(f0,float))
            delta = float(delta)

        return delta
        

    def _compute_df_from_gradF_hessian(self, gradF, f0, verbosity):
        """
        Internal function which computes error bars given an function value
        and gradient (using linear approx. to function)
        """

        #Compute df = sqrt( gradFu.dag * 1/D * gradFu )
        #  where regionQuadcForm = U * D * U.dag and gradFu = U.dag * gradF
        #  so df = sqrt( gradF.dag * U * 1/D * U.dag * gradF )
        #        = sqrt( gradF.dag * invRegionQuadcForm * gradF )

        printer = _VerbosityPrinter.build_printer(verbosity)

        printer.log("gradF = %s" % gradF)

        if isinstance(f0,float) or isinstance(f0,int):
            gradFdag = _np.conjugate(_np.transpose(gradF))

            #DEBUG
            #arg = _np.dot(gradFdag, _np.dot(self.invRegionQuadcForm, gradF))
            #print "HERE: taking sqrt(abs(%s))" % arg

            df = _np.sqrt( abs(_np.dot(gradFdag, _np.dot(self.invRegionQuadcForm, gradF))) )
        else:
            fDims = len(f0.shape)
            gradF = _np.rollaxis(gradF, 0, 1+fDims) # roll parameter axis to be the last index, preceded by f-shape
            df = _np.empty( f0.shape, f0.dtype)

            if f0.dtype == _np.dtype("complex"): #real and imaginary parts separately
                if fDims == 0: #same as float case above
                    gradFdag = _np.transpose(gradF)
                    df = _np.sqrt( abs( _np.dot(gradFdag.real, _np.dot(self.invRegionQuadcForm, gradF.real))) ) \
                        + 1j * _np.sqrt( abs( _np.dot(gradFdag.imag, _np.dot(self.invRegionQuadcForm, gradF.imag))) )
                elif fDims == 1:
                    for i in range(f0.shape[0]):
                        gradFdag = _np.transpose(gradF[i])
                        df[i] = _np.sqrt( abs( _np.dot(gradFdag.real, _np.dot(self.invRegionQuadcForm, gradF[i].real))) ) \
                            + 1j * _np.sqrt( abs( _np.dot(gradFdag.imag, _np.dot(self.invRegionQuadcForm, gradF[i].imag))) )
                elif fDims == 2:
                    for i in range(f0.shape[0]):
                        for j in range(f0.shape[1]):
                            gradFdag = _np.transpose(gradF[i,j])
                            df[i,j] = _np.sqrt( abs( _np.dot(gradFdag.real, _np.dot(self.invRegionQuadcForm, gradF[i,j].real))) ) \
                                + 1j * _np.sqrt( abs( _np.dot(gradFdag.imag, _np.dot(self.invRegionQuadcForm, gradF[i,j].imag))) )
                else:
                    raise ValueError("Unsupported number of dimensions returned by fnOfGate or fnOfGateset: %d" % fDims)

            else: #assume real -- so really don't need conjugate calls below
                if fDims == 0: #same as float case above
                    gradFdag = _np.conjugate(_np.transpose(gradF))

                    #DEBUG
                    #arg = _np.dot(gradFdag, _np.dot(self.invRegionQuadcForm, gradF))
                    #print "HERE2: taking sqrt(abs(%s))" % arg

                    df = _np.sqrt( abs( _np.dot(gradFdag, _np.dot(self.invRegionQuadcForm, gradF))) )
                elif fDims == 1:
                    for i in range(f0.shape[0]):
                        gradFdag = _np.conjugate(_np.transpose(gradF[i]))
                        df[i] = _np.sqrt( abs(_np.dot(gradFdag, _np.dot(self.invRegionQuadcForm, gradF[i]))) )
                elif fDims == 2:
                    for i in range(f0.shape[0]):
                        for j in range(f0.shape[1]):
                            gradFdag = _np.conjugate(_np.transpose(gradF[i,j]))
                            df[i,j] = _np.sqrt( abs(_np.dot(gradFdag, _np.dot(self.invRegionQuadcForm, gradF[i,j]))) )
                else:
                    raise ValueError("Unsupported number of dimensions returned by fnOfGate or fnOfGateset: %d" % fDims)

        printer.log("df = %s" % df)

        return df

#Helper functions
def _create_empty_grad(val, nParams):
    """ Get finite difference derivative gradF that is shape (nParams, <shape of val>) """
    if isinstance(val,float) or isinstance(val,int):
        gradVal = _np.zeros( nParams, 'd' )
    else:
        gradSize = (nParams,) + tuple(val.shape)
        gradVal = _np.zeros( gradSize, val.dtype )
    return gradVal #gradient of value (empty)

def _create_empty_gradF(f0, nParams):
    if isinstance(f0, dict): #special behavior for dict: process each item separately
        gradF = { ky: _create_empty_grad(val,nParams) for ky,val in f0.items() }
    else:
        gradF = _create_empty_grad(f0,nParams)
    return gradF




