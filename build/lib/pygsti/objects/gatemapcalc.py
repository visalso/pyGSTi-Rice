""" Defines the GateMapCalc calculator class"""
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

import warnings as _warnings
import numpy as _np
import time as _time
import itertools as _itertools

from ..tools import mpitools as _mpit
from ..tools import slicetools as _slct
from ..tools import compattools as _compat
from ..tools.matrixtools import _fas
from ..baseobjs import DummyProfiler as _DummyProfiler
from .mapevaltree import MapEvalTree as _MapEvalTree
from .gatecalc import GateCalc

_dummy_profiler = _DummyProfiler()

#TODO:
# Gate -> GateMatrix
# New "Gate" base class, new "GateMap" class
class GateMapCalc(GateCalc):
    """
    Encapsulates a calculation tool used by gate set objects to perform product
    and derivatives-of-product calculations.

    This is contained in a class separate from GateSet to allow for additional
    gate set classes (e.g. ones which use entirely different -- non-gate-local
    -- parameterizations of gate matrices and SPAM vectors) access to these
    fundamental operations.
    """

    def __init__(self, dim, gates, preps, effects, paramvec):
        """
        Construct a new GateMapCalc object.

        Parameters
        ----------
        dim : int
            The gate-dimension.  All gate matrices should be dim x dim, and all
            SPAM vectors should be dim x 1.

        gates, preps, effects : OrderedDict
            Ordered dictionaries of Gate, SPAMVec, and SPAMVec objects,
            respectively.  Must be *ordered* dictionaries to specify a
            well-defined column ordering when taking derivatives.

        spamdefs : OrderedDict
            A dictionary whose keys are the allowed SPAM labels, and whose
            values are 2-tuples comprised of a state preparation label
            followed by a POVM effect label (both of which are strings,
            and keys of preps and effects, respectively, except for the
            special case when both are set to "remainder").

        paramvec : ndarray
            The parameter vector of the GateSet.
        """
        super(GateMapCalc, self).__init__(
            dim, gates, preps, effects, paramvec)

        
    def copy(self):
        """ Return a shallow copy of this GateMatrixCalc """
        return GateMapCalc(self.dim, self.gates, self.preps,
                              self.effects, self.paramvec)

        
    #Same as GateMatrixCalc, but not general enough to be in base class
    def _rhoE_from_spamTuple(self, spamTuple):
        if len(spamTuple) == 2:
            rholabel,elabel = spamTuple
            rho = self.preps[rholabel]
            E   = _np.conjugate(_np.transpose(self.effects[elabel]))
        else:
            # a "custom" spamLabel consisting of a pair of SPAMVec (or array)
            #  objects: (prepVec, effectVec)
            rho, Eraw = spamTuple
            E   = _np.conjugate(_np.transpose(Eraw))
        return rho,E

    def propagate_state(self, rho, gatestring):
        """ 
        State propagation by GateMap objects which have 'acton'
        methods.  This function could easily be overridden to 
        perform some more sophisticated state propagation
        (i.e. Monte Carlo) in the future.

        Parameters
        ----------
        rho : SPAMVec
           The spam vector representing the initial state.

        gatestring : GateString or tuple
           A tuple of labels specifying the gate sequence to apply.

        Returns
        -------
        SPAMVec
        """
        for lbl in gatestring:
            rho = self.gates[lbl].acton(rho) # LEXICOGRAPHICAL VS MATRIX ORDER
        return rho


    def pr(self, spamTuple, gatestring, clipTo, bUseScaling=False):
        """
        Compute probability of a single "outcome" (spam-tuple) for a single
        gate string.

        Parameters
        ----------
        spamTuple : (rho_label, compiled_effect_label)
            Specifies the prep and POVM effect used to compute the probability.

        gatestring : GateString or tuple
            A tuple-like object of *compiled* gates (e.g. may include
            instrument elements like 'Imyinst_0')

        clipTo : 2-tuple
          (min,max) to clip returned probability to if not None.
          Only relevant when prMxToFill is not None.

        bUseScaling : bool, optional
          Whether to use a post-scaled product internally.  If False, this
          routine will run slightly faster, but with a chance that the
          product will overflow and the subsequent trace operation will
          yield nan as the returned probability.

        Returns
        -------
        probability: float
        """
        rho,E = self._rhoE_from_spamTuple(spamTuple)
        rho = self.propagate_state(rho, gatestring)
        p = _np.dot(E,rho)

        if _np.isnan(p):
            if len(gatestring) < 10:
                strToPrint = str(gatestring)
            else:
                strToPrint = str(gatestring[0:10]) + " ... (len %d)" % len(gatestring)
            _warnings.warn("pr(%s) == nan" % strToPrint)

        if clipTo is not None:
            return _np.clip(p,clipTo[0],clipTo[1])
        else: return p

        
    def dpr(self, spamTuple, gatestring, returnPr, clipTo):
        """
        Compute the derivative of a probability generated by a gate string and
        spam tuple as a 1 x M numpy array, where M is the number of gateset
        parameters.

        Parameters
        ----------
        spamTuple : (rho_label, compiled_effect_label)
            Specifies the prep and POVM effect used to compute the probability.

        gatestring : GateString or tuple
            A tuple-like object of *compiled* gates (e.g. may include
            instrument elements like 'Imyinst_0')

        returnPr : bool
          when set to True, additionally return the probability itself.

        clipTo : 2-tuple
          (min,max) to clip returned probability to if not None.
          Only relevant when prMxToFill is not None.

        Returns
        -------
        derivative : numpy array
            a 1 x M numpy array of derivatives of the probability w.r.t.
            each gateset parameter (M is the length of the vectorized gateset).

        probability : float
            only returned if returnPr == True.
        """
        
        #Finite difference derivative
        eps = 1e-7 #hardcoded?
        p = self.pr(spamTuple, gatestring, clipTo)
        dp = _np.empty( (1,self.Np), 'd' )

        orig_vec = self.to_vector().copy()
        for i in range(self.Np):
            vec = orig_vec.copy(); vec[i] += eps
            self.from_vector(vec)
            dp[0,i] = (self.pr(spamTuple, gatestring, clipTo)-p)/eps
        self.from_vector(orig_vec)
                
        if returnPr:
            if clipTo is not None:  p = _np.clip( p, clipTo[0], clipTo[1] )
            return dp, p
        else: return dp


    def hpr(self, spamTuple, gatestring, returnPr, returnDeriv, clipTo):
        """
        Compute the Hessian of a probability generated by a gate string and
        spam tuple as a 1 x M x M array, where M is the number of gateset
        parameters.

        Parameters
        ----------
        spamTuple : (rho_label, compiled_effect_label)
            Specifies the prep and POVM effect used to compute the probability.

        gatestring : GateString or tuple
            A tuple-like object of *compiled* gates (e.g. may include
            instrument elements like 'Imyinst_0')

        returnPr : bool
          when set to True, additionally return the probability itself.

        returnDeriv : bool
          when set to True, additionally return the derivative of the
          probability.

        clipTo : 2-tuple
          (min,max) to clip returned probability to if not None.
          Only relevant when prMxToFill is not None.

        Returns
        -------
        hessian : numpy array
            a 1 x M x M array, where M is the number of gateset parameters.
            hessian[0,j,k] is the derivative of the probability w.r.t. the
            k-th then the j-th gateset parameter.

        derivative : numpy array
            only returned if returnDeriv == True. A 1 x M numpy array of
            derivatives of the probability w.r.t. each gateset parameter.

        probability : float
            only returned if returnPr == True.
        """
        
        #Finite difference hessian
        eps = 1e-4 #hardcoded?
        if returnPr:
            dp,p = self.dpr(spamTuple, gatestring, returnPr, clipTo)
        else:
            dp = self.dpr(spamTuple, gatestring, returnPr, clipTo)
        hp = _np.empty( (1,self.Np, self.Np), 'd' )

        orig_vec = self.to_vector().copy()
        for i in range(self.Np):
            vec = orig_vec.copy(); vec[i] += eps
            self.from_vector(vec)
            hp[0,i,:] = (self.dpr(spamTuple, gatestring, False, clipTo)-dp)/eps
        self.from_vector(orig_vec)
                
        if returnPr and clipTo is not None:
            p = _np.clip( p, clipTo[0], clipTo[1] )

        if returnDeriv:
            if returnPr: return hp, dp, p
            else:        return hp, dp
        else:
            if returnPr: return hp, p
            else:        return hp


    def _compute_pr_cache(self, spamTuple, evalTree, comm, scratch=None):
        dim = self.dim
        cacheSize = len(evalTree)
        rho,E = self._rhoE_from_spamTuple(spamTuple)
        
        if scratch is None:
            rho_cache = _np.zeros((cacheSize, dim), 'd')
        else:
            assert(scratch.shape == (cacheSize,dim))
            rho_cache = scratch #to avoid recomputation

        #comm is currently ignored
        #TODO: if evalTree is split, distribute among processors
        
        for i in evalTree.get_evaluation_order():
            iStart,remainder = evalTree[i]
            if iStart is None:  init_state = rho[:,0]
            else:               init_state = rho_cache[iStart]
            rho_cache[i] = self.propagate_state(init_state, remainder)

        pCache = _np.dot(E,rho_cache.T) # (1,cacheSize)
        return _np.squeeze(pCache, axis=0) # shape (cacheSize,)
    
    def _compute_dpr_cache(self, spamTuple, evalTree, wrtSlice, comm, scratch=None):
        #Compute finite difference derivatives, one parameter at a time.

        param_indices = range(self.Np) if (wrtSlice is None) else _slct.indices(wrtSlice)
        nDerivCols = len(param_indices) # *all*, not just locally computed ones
        
        dim = self.dim
        cacheSize  = len(evalTree)
        if scratch is None:
            rho_cache  = _np.zeros((cacheSize, dim), 'd')
            dpr_cache  = _np.zeros((cacheSize, nDerivCols),'d')
        else:
            assert(scratch.shape == (cacheSize,nDerivCols + dim))
            rho_cache  = scratch[:,nDerivCols:nDerivCols+dim]
            dpr_cache  = scratch[:,0:nDerivCols]
            
        eps = 1e-7 #hardcoded?
        pCache = self._compute_pr_cache(spamTuple,evalTree,comm,rho_cache)

        all_slices, my_slice, owners, subComm = \
                _mpit.distribute_slice(slice(0,len(param_indices)), comm)

        my_param_indices = param_indices[my_slice]
        st = my_slice.start #beginning of where my_param_indices results
                            # get placed into dpr_cache
        
        #Get a map from global parameter indices to the desired
        # final index within dpr_cache
        iParamToFinal = { i: st+ii for ii,i in enumerate(my_param_indices) }

        orig_vec = self.to_vector().copy()
        for i in range(self.Np):
            if i in iParamToFinal:
                iFinal = iParamToFinal[i]
                vec = orig_vec.copy(); vec[i] += eps
                self.from_vector(vec)
                dpr_cache[:,iFinal] = ( self._compute_pr_cache(
                            spamTuple,evalTree,subComm,rho_cache) - pCache)/eps
        self.from_vector(orig_vec)

        #Now each processor has filled the relavant parts of dpr_cache,
        # so gather together:
        _mpit.gather_slices(all_slices, owners, dpr_cache,[], axes=1, comm=comm)

        return dpr_cache

    def _compute_hpr_cache(self, spamTuple, evalTree, wrtSlice1, wrtSlice2, comm):
        #Compute finite difference hessians, one parameter at a time.

        param_indices1 = range(self.Np) if (wrtSlice1 is None) else _slct.indices(wrtSlice1)
        param_indices2 = range(self.Np) if (wrtSlice2 is None) else _slct.indices(wrtSlice2)
        nDerivCols1 = len(param_indices1) # *all*, not just locally computed ones
        nDerivCols2 = len(param_indices2) # *all*, not just locally computed ones
        
        dim = self.dim
        cacheSize  = len(evalTree)
        dpr_scratch = _np.zeros((cacheSize,nDerivCols2 + dim), 'd')
        hpr_cache  = _np.zeros((cacheSize, nDerivCols1, nDerivCols2),'d')
            
        eps = 1e-4 #hardcoded?
        dpCache = self._compute_dpr_cache(spamTuple,evalTree,wrtSlice2,comm,
                                          dpr_scratch).copy()
           #need copy here b/c scratch space is used by sub-calls to
           # _compute_dpr_cache below in finite difference computation.
           
        all_slices, my_slice, owners, subComm = \
                _mpit.distribute_slice(slice(0,len(param_indices1)), comm)

        my_param_indices = param_indices1[my_slice]
        st = my_slice.start #beginning of where my_param_indices results
                            # get placed into dpr_cache
        
        #Get a map from global parameter indices to the desired
        # final index within dpr_cache
        iParamToFinal = { i: st+ii for ii,i in enumerate(my_param_indices) }

        orig_vec = self.to_vector().copy()
        for i in range(self.Np):
            if i in iParamToFinal:
                iFinal = iParamToFinal[i]
                vec = orig_vec.copy(); vec[i] += eps
                self.from_vector(vec)
                hpr_cache[:,iFinal,:] = ( self._compute_dpr_cache(
                    spamTuple,evalTree,wrtSlice2,subComm,dpr_scratch) - dpCache)/eps
        self.from_vector(orig_vec)

        #Now each processor has filled the relavant parts of dpr_cache,
        # so gather together:
        _mpit.gather_slices(all_slices, owners, hpr_cache,[], axes=1, comm=comm)

        return hpr_cache

    
    def construct_evaltree(self):
        """
        Constructs an EvalTree object appropriate for this calculator.
        """
        return _MapEvalTree()


    def estimate_mem_usage(self, subcalls, cache_size, num_subtrees,
                           num_subtree_proc_groups, num_param1_groups,
                           num_param2_groups):
        """
        Estimate the memory required by a given set of subcalls to computation functions.

        Parameters
        ----------
        subcalls : list of strs
            A list of the names of the subcalls to estimate memory usage for.

        cache_size : int
            The size of the evaluation tree that will be passed to the
            functions named by `subcalls`.

        num_subtrees : int
            The number of subtrees to split the full evaluation tree into.

        num_subtree_proc_groups : int
            The number of processor groups used to (in parallel) iterate through
            the subtrees.  It can often be useful to have fewer processor groups
            then subtrees (even == 1) in order to perform the parallelization
            over the parameter groups.
        
        num_param1_groups : int
            The number of groups to divide the first-derivative parameters into.
            Computation will be automatically parallelized over these groups.

        num_param2_groups : int
            The number of groups to divide the second-derivative parameters into.
            Computation will be automatically parallelized over these groups.
        
        Returns
        -------
        int
            The memory estimate in bytes.
        """
        np1,np2 = num_param1_groups, num_param2_groups
        FLOATSIZE = 8 # in bytes: TODO: a better way

        dim = self.dim
        wrtLen1 = (self.Np+np1-1) // np1 # ceiling(num_params / np1)
        wrtLen2 = (self.Np+np2-1) // np2 # ceiling(num_params / np2)

        mem = 0
        for fnName in subcalls:
            if fnName == "bulk_fill_probs":
                mem += cache_size * dim # pr cache intermediate
                mem += cache_size # pr cache final

            elif fnName == "bulk_fill_dprobs":
                mem += cache_size * (wrtLen1 + dim) # dpr cache
                mem += cache_size * dim # pr cache intermediate
                mem += cache_size # pr cache final

            elif fnName == "bulk_fill_hprobs":
                mem += cache_size * (wrtLen2 + dim) # hproduct cache intermediate
                mem += cache_size * wrtLen1 * wrtLen2 # hproduct cache final
                mem += cache_size * (wrtLen1 + dim) * 2 # dpr cache (x2)
                mem += cache_size * dim # pr cache intermediate
                mem += cache_size # pr cache final
                
            else:
                raise ValueError("Unknown subcall name: %s" % fnName)
        
        return mem * FLOATSIZE


    
    def bulk_fill_probs(self, mxToFill, evalTree, clipTo=None, check=False,
                        comm=None):

        """
        Identical to bulk_probs(...) except results are
        placed into rows of a pre-allocated array instead
        of being returned in a dictionary.

        Specifically, the probabilities for all gate strings
        and a given SPAM label are placed into the row of
        mxToFill specified by spam_label_rows[spamLabel].

        Parameters
        ----------
        mxToFill : numpy ndarray
          an already-allocated KxS numpy array, where K is larger
          than the maximum value in spam_label_rows and S is equal
          to the number of gate strings (i.e. evalTree.num_final_strings())

        spam_label_rows : dictionary
          a dictionary with keys == spam labels and values which
          are integer row indices into mxToFill, specifying the
          correspondence between rows of mxToFill and spam labels.

        evalTree : EvalTree
           given by a prior call to bulk_evaltree.  Specifies the gate strings
           to compute the bulk operation on.

        clipTo : 2-tuple, optional
           (min,max) to clip return value if not None.

        check : boolean, optional
          If True, perform extra checks within code to verify correctness,
          generating warnings when checks fail.  Used for testing, and runs
          much slower when True.

        comm : mpi4py.MPI.Comm, optional
           When not None, an MPI communicator for distributing the computation
           across multiple processors.  Distribution is performed over
           subtrees of evalTree (if it is split).

        Returns
        -------
        None
        """
        #get distribution across subtrees (groups if needed)
        subtrees = evalTree.get_sub_trees()
        mySubTreeIndices, subTreeOwners, mySubComm = evalTree.distribute(comm)

        #eval on each local subtree
        for iSubTree in mySubTreeIndices:
            evalSubTree = subtrees[iSubTree]

            def calc_and_fill(spamTuple, fInds, gInds, pslc1, pslc2, sumInto):
                """ Compute and fill result quantities for given arguments """
                #Fill cache info
                prCache = self._compute_pr_cache(spamTuple, evalSubTree, mySubComm)

                #use cached data to final values
                ps = evalSubTree.final_view( prCache, axis=0) # ( nGateStrings, )
                _fas(mxToFill, [fInds], ps[gInds], add=sumInto)

            self._fill_result_tuple( (mxToFill,), evalSubTree,
                                     slice(None), slice(None), calc_and_fill )

        #collect/gather results
        subtreeElementIndices = [ t.final_element_indices(evalTree) for t in subtrees]
        _mpit.gather_indices(subtreeElementIndices, subTreeOwners,
                             mxToFill,[], 0, comm)
        #note: pass mxToFill, dim=(KS,), so gather mxToFill[felInds] (axis=0)

        if clipTo is not None:
            _np.clip( mxToFill, clipTo[0], clipTo[1], out=mxToFill ) # in-place clip

#Will this work?? TODO
#        if check:
#            self._check(evalTree, spam_label_rows, mxToFill, clipTo=clipTo)


    def bulk_fill_dprobs(self, mxToFill, evalTree,
                         prMxToFill=None,clipTo=None,check=False,
                         comm=None, wrtFilter=None, wrtBlockSize=None,
                         profiler=None, gatherMemLimit=None):

        """
        Identical to bulk_dprobs(...) except results are
        placed into rows of a pre-allocated array instead
        of being returned in a dictionary.

        Specifically, the probability derivatives for all gate
        strings and a given SPAM label are placed into
        mxToFill[ spam_label_rows[spamLabel] ].
        Optionally, probabilities can be placed into
        prMxToFill[ spam_label_rows[spamLabel] ]

        Parameters
        ----------
        mxToFill : numpy array
          an already-allocated KxSxM numpy array, where K is larger
          than the maximum value in spam_label_rows, S is equal
          to the number of gate strings (i.e. evalTree.num_final_strings()),
          and M is the length of the vectorized gateset.

        spam_label_rows : dictionary
          a dictionary with keys == spam labels and values which
          are integer row indices into mxToFill, specifying the
          correspondence between rows of mxToFill and spam labels.

        evalTree : EvalTree
           given by a prior call to bulk_evaltree.  Specifies the gate strings
           to compute the bulk operation on.

        prMxToFill : numpy array, optional
          when not None, an already-allocated KxS numpy array that is filled
          with the probabilities as per spam_label_rows, similar to
          bulk_fill_probs(...).

        clipTo : 2-tuple, optional
          (min,max) to clip returned probability to if not None.
          Only relevant when prMxToFill is not None.

        check : boolean, optional
          If True, perform extra checks within code to verify correctness,
          generating warnings when checks fail.  Used for testing, and runs
          much slower when True.

        comm : mpi4py.MPI.Comm, optional
           When not None, an MPI communicator for distributing the computation
           across multiple processors.  Distribution is first performed over
           subtrees of evalTree (if it is split), and then over blocks (subsets)
           of the parameters being differentiated with respect to (see
           wrtBlockSize).

        wrtFilter : list of ints, optional
          If not None, a list of integers specifying which parameters
          to include in the derivative dimension. This argument is used
          internally for distributing calculations across multiple
          processors and to control memory usage.  Cannot be specified
          in conjuction with wrtBlockSize.

        wrtBlockSize : int or float, optional
          The maximum number of derivative columns to compute *products*
          for simultaneously.  None means compute all requested columns
          at once.  The  minimum of wrtBlockSize and the size that makes
          maximal use of available processors is used as the final block size.
          This argument must be None if wrtFilter is not None.  Set this to
          non-None to reduce amount of intermediate memory required.

        profiler : Profiler, optional
          A profiler object used for to track timing and memory usage.

        gatherMemLimit : int, optional
          A memory limit in bytes to impose upon the "gather" operations
          performed as a part of MPI processor syncronization.

        Returns
        -------
        None
        """

        tStart = _time.time()
        if profiler is None: profiler = _dummy_profiler

        if wrtFilter is not None:
            assert(wrtBlockSize is None) #Cannot specify both wrtFilter and wrtBlockSize
            wrtSlice = _slct.list_to_slice(wrtFilter) #for now, require the filter specify a slice
        else:
            wrtSlice = None

        profiler.mem_check("bulk_fill_dprobs: begin (expect ~ %.2fGB)" 
                           % (mxToFill.nbytes/(1024.0**3)) )

        #get distribution across subtrees (groups if needed)
        subtrees = evalTree.get_sub_trees()
        mySubTreeIndices, subTreeOwners, mySubComm = evalTree.distribute(comm)

        #eval on each local subtree
        for iSubTree in mySubTreeIndices:
            evalSubTree = subtrees[iSubTree]
            felInds = evalSubTree.final_element_indices(evalTree)

            #Free memory from previous subtree iteration before computing caches
            paramSlice = slice(None)
            fillComm = mySubComm #comm used by calc_and_fill

            def calc_and_fill(spamTuple, fInds, gInds, pslc1, pslc2, sumInto):
                """ Compute and fill result quantities for given arguments """
                tm = _time.time()
                
                if prMxToFill is not None:
                    prCache = self._compute_pr_cache(spamTuple, evalSubTree, fillComm)
                    ps = evalSubTree.final_view( prCache, axis=0) # ( nGateStrings, )
                    _fas(prMxToFill, [fInds], ps[gInds], add=sumInto)

                #Fill cache info
                dprCache = self._compute_dpr_cache(spamTuple, evalSubTree, paramSlice, fillComm)
                dps = evalSubTree.final_view( dprCache, axis=0) # ( nGateStrings, )
                _fas(mxToFill, [fInds, pslc1], dps[gInds], add=sumInto)
                profiler.add_time("bulk_fill_dprobs: calc_and_fill", tm)

                
            #Set wrtBlockSize to use available processors if it isn't specified
            if wrtFilter is None:
                blkSize = wrtBlockSize #could be None
                if (mySubComm is not None) and (mySubComm.Get_size() > 1):
                    comm_blkSize = self.Np / mySubComm.Get_size()
                    blkSize = comm_blkSize if (blkSize is None) \
                        else min(comm_blkSize, blkSize) #override with smaller comm_blkSize
            else:
                blkSize = None # wrtFilter dictates block


            if blkSize is None:
                #Fill derivative cache info
                paramSlice = wrtSlice #specifies which deriv cols calc_and_fill computes
                
                #Compute all requested derivative columns at once
                self._fill_result_tuple( (prMxToFill, mxToFill), evalSubTree,
                                         slice(None), slice(None), calc_and_fill )
                profiler.mem_check("bulk_fill_dprobs: post fill")

            else: # Divide columns into blocks of at most blkSize
                assert(wrtFilter is None) #cannot specify both wrtFilter and blkSize
                nBlks = int(_np.ceil(self.Np / blkSize))
                  # num blocks required to achieve desired average size == blkSize
                blocks = _mpit.slice_up_range(self.Np, nBlks)

                #distribute derivative computation across blocks
                myBlkIndices, blkOwners, blkComm = \
                    _mpit.distribute_indices(list(range(nBlks)), mySubComm)
                if blkComm is not None:
                    _warnings.warn("Note: more CPUs(%d)" % mySubComm.Get_size()
                       +" than derivative columns(%d)!" % self.Np
                       +" [blkSize = %.1f, nBlks=%d]" % (blkSize,nBlks))
                fillComm = blkComm #comm used by calc_and_fill

                for iBlk in myBlkIndices:
                    paramSlice = blocks[iBlk] #specifies which deriv cols calc_and_fill computes
                    self._fill_result_tuple( 
                        (mxToFill,), evalSubTree,
                        blocks[iBlk], slice(None), calc_and_fill )
                    profiler.mem_check("bulk_fill_dprobs: post fill blk")

                #gather results
                tm = _time.time()
                _mpit.gather_slices(blocks, blkOwners, mxToFill,[felInds],
                                    1, mySubComm, gatherMemLimit)
                #note: gathering axis 1 of mxToFill[:,fslc], dim=(ks,M)
                profiler.add_time("MPI IPC", tm)
                profiler.mem_check("bulk_fill_dprobs: post gather blocks")

        #collect/gather results
        tm = _time.time()
        subtreeElementIndices = [ t.final_element_indices(evalTree) for t in subtrees]
        _mpit.gather_indices(subtreeElementIndices, subTreeOwners,
                             mxToFill,[], 0, comm, gatherMemLimit)
        #note: pass mxToFill, dim=(KS,M), so gather mxToFill[felInds] (axis=0)

        if prMxToFill is not None:
            _mpit.gather_indices(subtreeElementIndices, subTreeOwners,
                             prMxToFill,[], 0, comm)
            #note: pass prMxToFill, dim=(KS,), so gather prMxToFill[felInds] (axis=0)

        profiler.add_time("MPI IPC", tm)
        profiler.mem_check("bulk_fill_dprobs: post gather subtrees")

        if clipTo is not None and prMxToFill is not None:
            _np.clip( prMxToFill, clipTo[0], clipTo[1], out=prMxToFill ) # in-place clip

        #TODO: will this work?
        #if check:
        #    self._check(evalTree, spam_label_rows, prMxToFill, mxToFill,
        #                clipTo=clipTo)
        profiler.add_time("bulk_fill_dprobs: total", tStart)
        profiler.add_count("bulk_fill_dprobs count")
        profiler.mem_check("bulk_fill_dprobs: end")



    def bulk_fill_hprobs(self, mxToFill, evalTree,
                         prMxToFill=None, deriv1MxToFill=None, deriv2MxToFill=None, 
                         clipTo=None, check=False,comm=None, wrtFilter1=None, wrtFilter2=None,
                         wrtBlockSize1=None, wrtBlockSize2=None, gatherMemLimit=None):

        """
        Identical to bulk_hprobs(...) except results are
        placed into rows of a pre-allocated array instead
        of being returned in a dictionary.

        Specifically, the probability hessians for all gate
        strings and a given SPAM label are placed into
        mxToFill[ spam_label_rows[spamLabel] ].
        Optionally, probabilities and/or derivatives can be placed into
        prMxToFill[ spam_label_rows[spamLabel] ] and
        derivMxToFill[ spam_label_rows[spamLabel] ] respectively.

        Parameters
        ----------
        mxToFill : numpy array
          an already-allocated KxSxMxM numpy array, where K is larger
          than the maximum value in spam_label_rows, S is equal
          to the number of gate strings (i.e. evalTree.num_final_strings()),
          and M is the length of the vectorized gateset.

        spam_label_rows : dictionary
          a dictionary with keys == spam labels and values which
          are integer row indices into mxToFill, specifying the
          correspondence between rows of mxToFill and spam labels.

        evalTree : EvalTree
           given by a prior call to bulk_evaltree.  Specifies the gate strings
           to compute the bulk operation on.

        prMxToFill : numpy array, optional
          when not None, an already-allocated KxS numpy array that is filled
          with the probabilities as per spam_label_rows, similar to
          bulk_fill_probs(...).

        deriv1MxToFill, deriv2MxToFill : numpy array, optional
          when not None, an already-allocated KxSxM numpy array that is filled
          with the probability derivatives as per spam_label_rows, similar to
          bulk_fill_dprobs(...), but where M is the number of gateset parameters
          selected for the 1st and 2nd differentiation, respectively (i.e. by
          wrtFilter1 and wrtFilter2).

        clipTo : 2-tuple
          (min,max) to clip returned probability to if not None.
          Only relevant when prMxToFill is not None.

        check : boolean, optional
          If True, perform extra checks within code to verify correctness,
          generating warnings when checks fail.  Used for testing, and runs
          much slower when True.

        comm : mpi4py.MPI.Comm, optional
           When not None, an MPI communicator for distributing the computation
           across multiple processors.  Distribution is first performed over
           subtrees of evalTree (if it is split), and then over blocks (subsets)
           of the parameters being differentiated with respect to (see
           wrtBlockSize).

        wrtFilter1, wrtFilter2 : list of ints, optional
          If not None, a list of integers specifying which gate set parameters
          to differentiate with respect to in the first (row) and second (col)
          derivative operations, respectively.

        wrtBlockSize2, wrtBlockSize2 : int or float, optional
          The maximum number of 1st (row) and 2nd (col) derivatives to compute
          *products* for simultaneously.  None means compute all requested
          rows or columns at once.  The  minimum of wrtBlockSize and the size
          that makes maximal use of available processors is used as the final
          block size.  These arguments must be None if the corresponding
          wrtFilter is not None.  Set this to non-None to reduce amount of
          intermediate memory required.

        gatherMemLimit : int, optional
          A memory limit in bytes to impose upon the "gather" operations
          performed as a part of MPI processor syncronization.


        Returns
        -------
        None
        """
        if wrtFilter1 is not None:
            assert(wrtBlockSize1 is None and wrtBlockSize2 is None) #Cannot specify both wrtFilter and wrtBlockSize
            wrtSlice1 = _slct.list_to_slice(wrtFilter1) #for now, require the filter specify a slice
        else:
            wrtSlice1 = None

        if wrtFilter2 is not None:
            assert(wrtBlockSize1 is None and wrtBlockSize2 is None) #Cannot specify both wrtFilter and wrtBlockSize
            wrtSlice2 = _slct.list_to_slice(wrtFilter2) #for now, require the filter specify a slice
        else:
            wrtSlice2 = None

        #get distribution across subtrees (groups if needed)
        subtrees = evalTree.get_sub_trees()
        mySubTreeIndices, subTreeOwners, mySubComm = evalTree.distribute(comm)

        #eval on each local subtree
        for iSubTree in mySubTreeIndices:
            evalSubTree = subtrees[iSubTree]
            felInds = evalSubTree.final_element_indices(evalTree)
            fillComm = mySubComm

            #Free memory from previous subtree iteration before computing caches
            paramSlice1 = slice(None)
            paramSlice2 = slice(None)

            def calc_and_fill(spamTuple, fInds, gInds, pslc1, pslc2, sumInto):
                """ Compute and fill result quantities for given arguments """
                
                if prMxToFill is not None:
                    prCache = self._compute_pr_cache(spamTuple, evalSubTree, fillComm)
                    ps = evalSubTree.final_view( prCache, axis=0) # ( nGateStrings, )
                    _fas(prMxToFill, [fInds], ps[gInds], add=sumInto)

                if deriv1MxToFill is not None:
                    dprCache = self._compute_dpr_cache(spamTuple, evalSubTree, paramSlice1, fillComm)
                    dps1 = evalSubTree.final_view( dprCache, axis=0) # ( nGateStrings, )
                    _fas(deriv1MxToFill, [fInds,pslc1], dps1[gInds], add=sumInto)

                if deriv2MxToFill is not None:
                    if deriv1MxToFill is not None and paramSlice1 == paramSlice2:
                        dps2 = dps1
                    else:
                        dprCache = self._compute_dpr_cache(spamTuple, evalSubTree, paramSlice2, fillComm)
                        dps2 = evalSubTree.final_view( dprCache, axis=0) # ( nGateStrings, )

                    _fas(deriv2MxToFill, [fInds,pslc2], dps2[gInds], add=sumInto)

                #Fill cache info
                hprCache = self._compute_hpr_cache(spamTuple, evalSubTree, paramSlice1, paramSlice2, fillComm)
                hps = evalSubTree.final_view( hprCache, axis=0) # ( nGateStrings, )
                
                _fas(mxToFill, [fInds,pslc1,pslc2], hps[gInds], add=sumInto)


            #Set wrtBlockSize to use available processors if it isn't specified
            if wrtFilter1 is None and wrtFilter2 is None:
                blkSize1 = wrtBlockSize1 #could be None
                blkSize2 = wrtBlockSize2 #could be None
                if (mySubComm is not None) and (mySubComm.Get_size() > 1):
                    comm_blkSize = self.Np / mySubComm.Get_size()
                    blkSize1 = comm_blkSize if (blkSize1 is None) \
                        else min(comm_blkSize, blkSize1) #override with smaller comm_blkSize
                    blkSize2 = comm_blkSize if (blkSize2 is None) \
                        else min(comm_blkSize, blkSize2) #override with smaller comm_blkSize
            else:
                blkSize1 = blkSize2 = None # wrtFilter1 & wrtFilter2 dictates block


            if blkSize1 is None and blkSize2 is None:
                #Fill hessian cache info
                paramSlice1 = wrtSlice1 #specifies which deriv cols calc_and_fill computes
                paramSlice2 = wrtSlice2 #specifies which deriv cols calc_and_fill computes

                #Compute all requested derivative columns at once
                self._fill_result_tuple((prMxToFill, deriv1MxToFill, deriv2MxToFill, mxToFill),
                                        evalSubTree, slice(None), slice(None), calc_and_fill)

            else: # Divide columns into blocks of at most blkSize
                assert(wrtFilter1 is None and wrtFilter2 is None) #cannot specify both wrtFilter and blkSize
                nBlks1 = int(_np.ceil(self.Np / blkSize1))
                nBlks2 = int(_np.ceil(self.Np / blkSize2))
                  # num blocks required to achieve desired average size == blkSize1 or blkSize2
                blocks1 = _mpit.slice_up_range(self.Np, nBlks1)
                blocks2 = _mpit.slice_up_range(self.Np, nBlks2)

                #distribute derivative computation across blocks
                myBlk1Indices, blk1Owners, blk1Comm = \
                    _mpit.distribute_indices(list(range(nBlks1)), mySubComm)

                myBlk2Indices, blk2Owners, blk2Comm = \
                    _mpit.distribute_indices(list(range(nBlks2)), blk1Comm)

                if blk2Comm is not None:
                    _warnings.warn("Note: more CPUs(%d)" % mySubComm.Get_size()
                       +" than hessian elements(%d)!" % (self.Np**2)
                       +" [blkSize = {%.1f,%.1f}, nBlks={%d,%d}]" % (blkSize1,blkSize2,nBlks1,nBlks2))
                fillComm = blk2Comm #comm used by calc_and_fill

                for iBlk1 in myBlk1Indices:
                    paramSlice1 = blocks1[iBlk1]

                    for iBlk2 in myBlk2Indices:
                        paramSlice2 = blocks2[iBlk2]
                        self._fill_result_tuple((prMxToFill, deriv1MxToFill, deriv2MxToFill, mxToFill),
                                                evalSubTree, blocks1[iBlk1], blocks2[iBlk2], calc_and_fill)
    
                    #gather column results: gather axis 2 of mxToFill[felInds,blocks1[iBlk1]], dim=(ks,blk1,M)
                    _mpit.gather_slices(blocks2, blk2Owners, mxToFill,[felInds,blocks1[iBlk1]],
                                        2, blk1Comm, gatherMemLimit)

                #gather row results; gather axis 1 of mxToFill[felInds], dim=(ks,M,M)
                _mpit.gather_slices(blocks1, blk1Owners, mxToFill,[felInds],
                                    1, mySubComm, gatherMemLimit)
                if deriv1MxToFill is not None:
                    _mpit.gather_slices(blocks1, blk1Owners, deriv1MxToFill,[felInds],
                                        1, mySubComm, gatherMemLimit)
                if deriv2MxToFill is not None:
                    _mpit.gather_slices(blocks2, blk2Owners, deriv2MxToFill,[felInds],
                                        1, blk1Comm, gatherMemLimit) 
                   #Note: deriv2MxToFill gets computed on every inner loop completion
                   # (to save mem) but isn't gathered until now (but using blk1Comm).
                   # (just as prMxToFill is computed fully on each inner loop *iteration*!)
            
        #collect/gather results
        subtreeElementIndices = [ t.final_element_indices(evalTree) for t in subtrees]
        _mpit.gather_indices(subtreeElementIndices, subTreeOwners,
                             mxToFill,[], 0, comm, gatherMemLimit)
        if deriv1MxToFill is not None:
            _mpit.gather_indices(subtreeElementIndices, subTreeOwners,
                                 deriv1MxToFill,[], 0, comm, gatherMemLimit)
        if deriv2MxToFill is not None:
            _mpit.gather_indices(subtreeElementIndices, subTreeOwners,
                                 deriv2MxToFill,[], 0, comm, gatherMemLimit)
        if prMxToFill is not None:
            _mpit.gather_indices(subtreeElementIndices, subTreeOwners,
                                 prMxToFill,[], 0, comm)


        if clipTo is not None and prMxToFill is not None:
            _np.clip( prMxToFill, clipTo[0], clipTo[1], out=prMxToFill ) # in-place clip

        #TODO: check if this works
        #if check:
        #    self._check(evalTree, spam_label_rows,
        #                prMxToFill, deriv1MxToFill, mxToFill, clipTo)
