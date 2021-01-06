""" Functions for reducing the number of required fiducial pairs for analysis."""
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************


import numpy      as _np
import itertools  as _itertools
import random     as _random
import scipy.misc as _spmisc
from ..construction import gatestringconstruction as _gsc
from ..tools        import remove_duplicates      as _remove_duplicates
from ..tools        import slicetools             as _slct

from ..             import objects as _objs

def _nCr(n,r):
    """Number of combinations of r items out of a set of n.  Equals n!/(r!(n-r)!)"""
    #f = _math.factorial; return f(n) / f(r) / f(n-r)
    return _spmisc.comb(n,r)

def _random_combination(indices_tuple, r):
    """
    Random selection from itertools.combinations(indices_tuple, r)
      from http://docs.python.org/2/library/itertools.html#recipes 
    """
    n = len(indices_tuple)
    iis = sorted(_random.sample(range(n), r))
    return tuple(indices_tuple[i] for i in iis)

def find_sufficient_fiducial_pairs(targetGateset, prepStrs, effectStrs, germList,
                                   testLs=(256,2048), prepovmTuples="first", tol=0.75,
                                   searchMode="sequential", nRandom=100, seed=None,
                                   verbosity=0, testPairList=None, memLimit=None,
                                   minimumPairs=1):
    """
    Finds a (global) set of fiducial pairs that are amplificationally complete.

    A "standard" set of GST gate sequences consists of all sequences of the form:

    statePrep + prepFiducial + germPower + measureFiducial + measurement
    
    This set is typically over-complete, and it is possible to restrict the 
    (prepFiducial, measureFiducial) pairs to a subset of all the possible 
    pairs given the separate `prepStrs` and `effectStrs` lists.  This function
    attempts to find a set of fiducial pairs that still amplify all of the
    gate set's parameters (i.e. is "amplificationally complete").  The test
    for amplification is performed using the two germ-power lengths given by
    `testLs`, and tests whether the magnitudes of the Jacobian's singular
    values scale linearly with the germ-power length.

    In the special case when `testPairList` is not None, the function *tests*
    the given set of fiducial pairs for amplificational completeness, and 
    does not perform any search.

    Parameters
    ----------
    targetGateset : GateSet
        The target gateset used to determine amplificational completeness.

    prepStrs, effectStrs, germList : list of GateStrings
        The (full) fiducial and germ gate sequences.

    testLs : (L1,L2) tuple of ints, optional
        A tuple of integers specifying the germ-power lengths to use when
        checking for amplificational completeness.

    prepovmTuples : list or "first", optional
        A list of `(prepLabel, povmLabel)` tuples to consider when
        checking for completeness.  Usually this should be left as the special
        (and default) value "first", which considers the first prep and POVM
        contained in `targetGateset`.

    tol : float, optional
        The tolerance for the fraction of the expected amplification that must
        be observed to call a parameter "amplified".

    searchMode : {"sequential","random"}, optional
        If "sequential", then all potential fiducial pair sets of a given length
        are considered in sequence before moving to sets of a larger size.  This
        can take a long time when there are many possible fiducial pairs.
        If "random", then only `nRandom` randomly chosen fiducial pair sets are
        considered for each set size before the set is enlarged.

    nRandom : int, optional
        The number of random-pair-sets to consider for a given set size.

    seed : int, optional
        The seed to use for generating random-pair-sets.
        
    verbosity : int, optional
        How much detail to print to stdout.

    testPairList : list or None, optional
        If not None, a list of (iRhoStr,iEffectStr) tuples of integers,
        specifying a list of fiducial pairs (indices are into `prepStrs` and
        `effectStrs`, respectively).  These pairs are then tested for 
        amplificational completeness and the number of amplified parameters
        is printed to stdout.  (This is a special debugging functionality.)

    memLimit : int, optional
        A memory limit in bytes.

    minimumPairs : int, optional
        The minimium number of fiducial pairs to try (default == 1).  Set this
        to integers larger than 1 to avoid trying pair sets that are known to 
        be too small.

    Returns
    -------
    list
        A list of (iRhoStr,iEffectStr) tuples of integers, specifying a list
        of fiducial pairs (indices are into `prepStrs` and `effectStrs`).
    """
    printer = _objs.VerbosityPrinter.build_printer(verbosity)
    #trim LSGST list of all f1+germ^exp+f2 strings to just those needed to get full rank jacobian. (compressed sensing like)

    #tol = 0.5 #fraction of expected amplification that must be observed to call a parameter "amplified"
    if prepovmTuples == "first":
        firstRho = list(targetGateset.preps.keys())[0]
        firstPOVM = list(targetGateset.povms.keys())[0]
        prepovmTuples = [ (firstRho, firstPOVM) ]
    prepovmTuples = [ (_objs.GateString((prepLbl,)), _objs.GateString((povmLbl,)))
                      for prepLbl,povmLbl in prepovmTuples ]

    nGatesetParams = targetGateset.num_params()

    def get_derivs(L):
        """ Compute all derivative info: get derivative of each <E_i|germ^exp|rho_j>
            where i = composite EVec & fiducial index and j similar """

        st=0 #running row count over to-be-concatenated dPall matrix
        elIndicesForPair = [ [] for i in range(len(prepStrs)*len(effectStrs))]
          #contains lists of final leading-dim indices corresponding to each fiducial pair
          
        dPall = [] # one element per germ, concatenate later

        for iGerm,germ in enumerate(germList):
            expGerm = _gsc.repeat_with_max_length(germ,L) # could pass exponent and set to germ**exp here
            lst = _gsc.create_gatestring_list(
                "pp[0]+f0+expGerm+f1+pp[1]", f0=prepStrs, f1=effectStrs,
                expGerm=expGerm, pp=prepovmTuples, order=('f0','f1','pp'))

            evTree,blkSz,_,lookup,_ = targetGateset.bulk_evaltree_from_resources(
                lst, memLimit=memLimit, distributeMethod="deriv",
                subcalls=['bulk_fill_dprobs'], verbosity=0)
            #FUTURE: assert that no instruments are allowed?

            dP = _np.empty( (evTree.num_final_elements(),targetGateset.num_params()), 'd' )
            targetGateset.bulk_fill_dprobs(dP, evTree, wrtBlockSize=blkSz) # num_els x num_params
            dPall.append(dP)

            #Add this germ's element indices for each fiducial pair (final gate string of evTree)
            nPrepPOVM = len(prepovmTuples)
            for k in range(len(prepStrs)*len(effectStrs)):
                for o in range(k*nPrepPOVM,(k+1)*nPrepPOVM): # "original" indices into lst for k-th fiducial pair
                    elArray = _slct.as_array(lookup[o]) + st
                    elIndicesForPair[k].extend( list(elArray) )
            st += evTree.num_final_elements() # b/c we'll concatenate tree's elements later
                
        return _np.concatenate( dPall, axis=0 ), elIndicesForPair
            #indexed by [iElement, iGatesetParam] : gives d(<SP|f0+exp_iGerm+f1|AM>)/d(iGatesetParam)
            # where iGerm, f0, f1, and SPAM are all bundled into iElement (but elIndicesForPair
            # provides the necessary indexing for picking out certain pairs)

    def get_number_amplified(M0,M1,L0,L1,verb):
        """ Return the number of amplified parameters """
        printer = _objs.VerbosityPrinter.build_printer(verb)
        L_ratio = float(L1)/float(L0)
        try:
            s0 = _np.linalg.svd(M0, compute_uv=False)
            s1 = _np.linalg.svd(M1, compute_uv=False)
        except:
            printer.warning("SVD error!!"); return 0
            #SVD did not converge -> just say no amplified params...

        numAmplified = 0
        printer.log("Amplified parameter test: matrices are %s and %s." % (M0.shape, M1.shape), 4)
        printer.log("Index : SV(L=%d)  SV(L=%d)  AmpTest ( > %g ?)" % (L0,L1,tol), 4)
        for i,(v0,v1) in enumerate(zip(sorted(s0,reverse=True),sorted(s1,reverse=True))):
            if abs(v0) > 0.1 and (v1/v0)/L_ratio > tol:
                numAmplified += 1
                printer.log("%d: %g  %g  %g YES" % (i,v0,v1, (v1/v0)/L_ratio ), 4)
            printer.log("%d: %g  %g  %g NO" % (i,v0,v1, (v1/v0)/L_ratio ), 4)
        return numAmplified

    #rank = len( [v for v in s if v > 0.001] )


    printer.log("------  Fiducial Pair Reduction --------")

    L0 = testLs[0]; dP0, elIndices0 = get_derivs(L0)
    L1 = testLs[1]; dP1, elIndices1 = get_derivs(L1)
    fullTestMx0 = dP0
    fullTestMx1 = dP1

    #Get number of amplified parameters in the "full" test matrix: the one we get when we use all possible fiducial pairs
    if testPairList is None:
        maxAmplified = get_number_amplified(fullTestMx0, fullTestMx1, L0, L1, verbosity+1)
        printer.log("maximum number of amplified parameters = %s" % maxAmplified)

    #Loop through fiducial pairs and add all derivative rows (1 x nGatesetParams) to test matrix
    # then check if testMatrix has full rank ( == nGatesetParams)

    nPossiblePairs = len(prepStrs)*len(effectStrs)
    allPairIndices = list(range(nPossiblePairs))
    nRhoStrs, nEStrs = len(prepStrs), len(effectStrs)

    if testPairList is not None: #special mode for testing/debugging single pairlist
        pairIndices0 = _np.concatenate( [ elIndices0[iRhoStr*nEStrs + iEStr]
                                         for iRhoStr,iEStr in testPairList ] )
        pairIndices1 = _np.concatenate( [ elIndices1[iRhoStr*nEStrs + iEStr]
                                         for iRhoStr,iEStr in testPairList ] )
        testMx0 = _np.take( fullTestMx0, pairIndices0, axis=0 )
        testMx1 = _np.take( fullTestMx1, pairIndices1, axis=0 )
        nAmplified = get_number_amplified(testMx0, testMx1, L0, L1, verbosity)
        printer.log("Number of amplified parameters = %s" % nAmplified)
        return None

    bestAmplified = 0
    for nNeededPairs in range(minimumPairs,nPossiblePairs):
        printer.log("Beginning search for a good set of %d pairs (%d pair lists to test)" % \
                (nNeededPairs,_nCr(nPossiblePairs,nNeededPairs)))

        bestAmplified = 0
        if searchMode == "sequential":
            pairIndicesToIterateOver = _itertools.combinations(allPairIndices, nNeededPairs)

        elif searchMode == "random":
            _random.seed(seed)  # ok if seed is None
            nTotalPairCombos = _nCr(len(allPairIndices), nNeededPairs)
            if nRandom < nTotalPairCombos:
                pairIndicesToIterateOver = [ _random_combination(allPairIndices, nNeededPairs) for i in range(nRandom) ]
            else:
                pairIndicesToIterateOver = _itertools.combinations(allPairIndices, nNeededPairs)

        for pairIndicesToTest in pairIndicesToIterateOver:
            pairIndices0 = _np.concatenate( [ elIndices0[i] for i in pairIndicesToTest ] )
            pairIndices1 = _np.concatenate( [ elIndices1[i] for i in pairIndicesToTest ] )            
            testMx0 = _np.take( fullTestMx0, pairIndices0, axis=0 )
            testMx1 = _np.take( fullTestMx1, pairIndices1, axis=0 )
            nAmplified = get_number_amplified(testMx0, testMx1, L0, L1, verbosity)
            bestAmplified = max(bestAmplified, nAmplified)
            if printer.verbosity > 1:
                ret = []
                for i in pairIndicesToTest:
                    iRhoStr = i // nEStrs
                    iEStr   = i - iRhoStr*nEStrs
                    ret.append( (iRhoStr,iEStr) )
                printer.log("Pair list %s ==> %d amplified parameters" % (" ".join(map(str,ret)), nAmplified))

            if nAmplified == maxAmplified:
                ret = []
                for i in pairIndicesToTest:
                    iRhoStr = i // nEStrs
                    iEStr   = i - iRhoStr*nEStrs
                    ret.append( (iRhoStr,iEStr) )
                return ret

    printer.log(" --> Highest number of amplified parameters was %d" % bestAmplified)

    #if we tried all the way to nPossiblePairs-1 and no success, just return all the pairs, which by definition will hit the "max-amplified" target
    listOfAllPairs = [ (iRhoStr,iEStr)
                       for iRhoStr in range(nRhoStrs)
                       for iEStr in range(nEStrs) ]
    return listOfAllPairs



def find_sufficient_fiducial_pairs_per_germ(targetGateset, prepStrs, effectStrs,
                                            germList, prepovmTuples="first",
                                            searchMode="sequential", constrainToTP=True,
                                            nRandom=100, seed=None, verbosity=0,
                                            memLimit=None):
    """
    Finds a per-germ set of fiducial pairs that are amplificationally complete.

    A "standard" set of GST gate sequences consists of all sequences of the form:

    statePrep + prepFiducial + germPower + measureFiducial + measurement
    
    This set is typically over-complete, and it is possible to restrict the 
    (prepFiducial, measureFiducial) pairs to a subset of all the possible 
    pairs given the separate `prepStrs` and `effectStrs` lists.  This function
    attempts to find sets of fiducial pairs, one set per germ, that still
    amplify all of the gate set's parameters (i.e. is "amplificationally
    complete").  For each germ, a fiducial pair set is found that amplifies
    all of the "parameters" (really linear combinations of them) that the
    particular germ amplifies.  

    To test whether a set of fiducial pairs satisfies this condition, the
    sum of projectors `P_i = dot(J_i,J_i^T)`, where `J_i` is a matrix of the
    derivatives of each of the selected (prepFiducial+germ+effectFiducial)
    sequence probabilities with respect to the i-th germ eigenvalue (or
    more generally, amplified parameter), is computed.  If the fiducial-pair
    set is sufficient, the rank of the resulting sum (an operator) will be
    equal to the total (maximal) number of parameters the germ can amplify.

    Parameters
    ----------
    targetGateset : GateSet
        The target gateset used to determine amplificational completeness.

    prepStrs, effectStrs, germList : list of GateStrings
        The (full) fiducial and germ gate sequences.

    prepovmTuples : list or "first", optional
        A list of `(prepLabel, povmLabel)` tuples to consider when
        checking for completeness.  Usually this should be left as the special
        (and default) value "first", which considers the first prep and POVM
        contained in `targetGateset`.

    searchMode : {"sequential","random"}, optional
        If "sequential", then all potential fiducial pair sets of a given length
        are considered in sequence (per germ) before moving to sets of a larger
        size.  This can take a long time when there are many possible fiducial
        pairs.  If "random", then only `nRandom` randomly chosen fiducial pair
        sets are considered for each set size before the set is enlarged.

    constrainToTP : bool, optional
        Whether or not to consider non-TP parameters the the germs amplify.  If
        the fiducal pairs will be used in a GST estimation where the gate set is
        constrained to being trace-preserving (TP), this should be set to True.

    nRandom : int, optional
        The number of random-pair-sets to consider for a given set size.

    seed : int, optional
        The seed to use for generating random-pair-sets.
        
    verbosity : int, optional
        How much detail to print to stdout.

    memLimit : int, optional
        A memory limit in bytes.

    Returns
    -------
    dict
        A dictionary whose keys are the germ gate strings and whose values are
        lists of (iRhoStr,iEffectStr) tuples of integers, each specifying the
        list of fiducial pairs for a particular germ (indices are into
        `prepStrs` and `effectStrs`).
    """

    printer = _objs.VerbosityPrinter.build_printer(verbosity)

    if prepovmTuples == "first":
        firstRho = list(targetGateset.preps.keys())[0]
        firstPOVM = list(targetGateset.povms.keys())[0]
        prepovmTuples = [ (firstRho, firstPOVM) ]
    prepovmTuples = [ (_objs.GateString((prepLbl,)), _objs.GateString((povmLbl,)))
                      for prepLbl,povmLbl in prepovmTuples ]
    

    pairListDict = {} # dict of lists of 2-tuples: one pair list per germ

    printer.log("------  Individual Fiducial Pair Reduction --------")
    with printer.progress_logging(1):
        for i,germ in enumerate(germList):

            #Create a new gateset containing static target gates and a
            # special "germ" gate that is parameterized only by it's 
            # eigenvalues (and relevant off-diagonal elements)
            gsGerm = targetGateset.copy()
            gsGerm.set_all_parameterizations("static")
            germMx = gsGerm.product(germ)
            gsGerm.gates["Ggerm"] = _objs.EigenvalueParameterizedGate(
                                                   germMx, True, constrainToTP)

            printer.show_progress(i, len(germList), 
                                  suffix='-- %s germ (%d params)' % 
                                  (germ, gsGerm.num_params()))
            #Debugging
            #print(gsGerm.gates["Ggerm"].evals)
            #print(gsGerm.gates["Ggerm"].params)

            #Get dP-matrix for full set of fiducials, where
            # P_ij = <E_i|germ^exp|rho_j>, i = composite EVec & fiducial index,
            #   j is similar, and derivs are wrt the "eigenvalues" of the germ
            #  (i.e. the parameters of the gsGerm gate set).
            lst = _gsc.create_gatestring_list(
                "pp[0]+f0+germ+f1+pp[1]", f0=prepStrs, f1=effectStrs,
                germ=_objs.GateString(("Ggerm",)), pp=prepovmTuples,
                order=('f0','f1','pp'))

            evTree,blkSz,_,lookup,_ = gsGerm.bulk_evaltree_from_resources(
                lst, memLimit=memLimit, distributeMethod="deriv",
                subcalls=['bulk_fill_dprobs'], verbosity=0)

            elIndicesForPair = [ [] for i in range(len(prepStrs)*len(effectStrs)) ]
            nPrepPOVM = len(prepovmTuples)
            for k in range(len(prepStrs)*len(effectStrs)):
                for o in range(k*nPrepPOVM,(k+1)*nPrepPOVM): # "original" indices into lst for k-th fiducial pair
                    elIndicesForPair[k].extend( list(_slct.indices(lookup[o])) )

            dPall = _np.empty( (evTree.num_final_elements(),gsGerm.num_params()), 'd' )
            gsGerm.bulk_fill_dprobs(dPall, evTree, wrtBlockSize=blkSz) # num_els x num_params

            # Construct sum of projectors onto the directions (1D spaces)
            # corresponding to varying each parameter (~eigenvalue) of the
            # germ.  If the set of fiducials is sufficient, then the rank of
            # the resulting operator will equal the number of parameters,
            # indicating that the P matrix is (independently) sensitive to
            # each of the germ parameters (~eigenvalues), which is *all* we
            # want sensitivity to.
            RANK_TOL = 1e-7
            rank = _np.linalg.matrix_rank( _np.dot(dPall, dPall.T), RANK_TOL )
            if rank < gsGerm.num_params(): # full fiducial set should work!
                raise ValueError("Incomplete fiducial-pair set!")

              #Below will take a *subset* of the rows in dPall
              # depending on which (of all possible) fiducial pairs
              # are being considered.

            nRhoStrs, nEStrs = len(prepStrs), len(effectStrs)
            nPossiblePairs = len(prepStrs)*len(effectStrs)
            allPairIndices = list(range(nPossiblePairs))

            #Determine which fiducial-pair indices to iterate over
            goodPairList = None; maxRank = 0
            for nNeededPairs in range(gsGerm.num_params(),nPossiblePairs):
                printer.log("Beginning search for a good set of %d pairs (%d pair lists to test)" % \
                                (nNeededPairs,_nCr(nPossiblePairs,nNeededPairs)),2)

                if searchMode == "sequential":
                    pairIndicesToIterateOver = _itertools.combinations(allPairIndices, nNeededPairs)

                elif searchMode == "random":
                    _random.seed(seed)  # ok if seed is None
                    nTotalPairCombos = _nCr(len(allPairIndices), nNeededPairs)
                    if nRandom < nTotalPairCombos:
                        pairIndicesToIterateOver = [ _random_combination(allPairIndices, nNeededPairs) for i in range(nRandom) ]
                    else:
                        pairIndicesToIterateOver = _itertools.combinations(allPairIndices, nNeededPairs)
                        
                for pairIndicesToTest in pairIndicesToIterateOver:
    
                    #Get list of pairs as tuples for printing & returning
                    pairList = []
                    for i in pairIndicesToTest:
                        iRhoStr = i // nEStrs; iEStr = i - iRhoStr*nEStrs
                        pairList.append( (iRhoStr,iEStr) )
    
                    # Same computation of rank as above, but with only a 
                    # subset of the total fiducial pairs.
                    elementIndicesToTest = _np.concatenate([ elIndicesForPair[i] for i in pairIndicesToTest])
                    dP = _np.take(dPall, elementIndicesToTest, axis=0) # subset_of_num_elements x num_params
                    rank = _np.linalg.matrix_rank( _np.dot(dP, dP.T), RANK_TOL )
                    maxRank = max(maxRank,rank)
    
                    printer.log("Pair list %s ==> %d of %d amplified parameters"
                                % (" ".join(map(str,pairList)), rank,
                                   gsGerm.num_params()), 3)
    
                    if rank == gsGerm.num_params():
                        printer.log("Found a good set of %d pairs: %s" % \
                                        (nNeededPairs," ".join(map(str,pairList))),2)
                        goodPairList = pairList
                        break

                if goodPairList is not None:
                    break #exit another loop level if a solution was found

            if goodPairList is not None:
                pairListDict[germ] = goodPairList # add to final list of per-germ pairs
            else:
                #we tried all the way to nPossiblePairs-1 and no success,
                # just return all the pairs
                printer.log(" --> Highest number amplified = %d of %d" %
                            (maxRank, gsGerms.num_params()))
                listOfAllPairs = [ (iRhoStr,iEStr)
                                   for iRhoStr in range(nRhoStrs)
                                   for iEStr in range(nEStrs) ]
                pairListDict[germ] = listOfAllPairs

    return pairListDict


def test_fiducial_pairs(fidPairs, targetGateset, prepStrs, effectStrs, germList,
                        testLs=(256,2048), prepovmTuples="first", tol=0.75,
                        verbosity=0, memLimit=None):
    """
    Tests a set of global or per-germ fiducial pairs.

    Determines how many gate set parameters (of `targetGateset`) are
    amplified by the fiducial pairs given by `fidPairs`, which can be
    either a list of 2-tuples (for global-FPR) or a dictionary (for
    per-germ FPR).

    Parameters
    ----------
    fidPairs : list or dict
        Either a single list of fiducial-index pairs (2-tuples) that is applied
        to every germ (global FPR) OR a per-germ dictionary of lists, each
        containing the fiducial-index pairs (2-tuples) for that germ (for
        per-germ FPR).

    targetGateset : GateSet
        The target gateset used to determine amplificational completeness.

    prepStrs, effectStrs, germList : list of GateStrings
        The (full) fiducial and germ gate sequences.

    testLs : (L1,L2) tuple of ints, optional
        A tuple of integers specifying the germ-power lengths to use when
        checking for amplificational completeness.

    prepovmTuples : list or "first", optional
        A list of `(prepLabel, povmLabel)` tuples to consider when
        checking for completeness.  Usually this should be left as the special
        (and default) value "first", which considers the first prep and POVM
        contained in `targetGateset`.

    tol : float, optional
        The tolerance for the fraction of the expected amplification that must
        be observed to call a parameter "amplified".

    verbosity : int, optional
        How much detail to print to stdout.

    memLimit : int, optional
        A memory limit in bytes.

    Returns
    -------
    numAmplified : int
    """
    printer = _objs.VerbosityPrinter.build_printer(verbosity)

    if prepovmTuples == "first":
        firstRho = list(targetGateset.preps.keys())[0]
        firstPOVM = list(targetGateset.povms.keys())[0]
        prepovmTuples = [ (firstRho, firstPOVM) ]
    prepovmTuples = [ (_objs.GateString((prepLbl,)), _objs.GateString((povmLbl,)))
                      for prepLbl,povmLbl in prepovmTuples ]


    nGatesetParams = targetGateset.num_params()

    def get_derivs(L):
        """ Compute all derivative info: get derivative of each <E_i|germ^exp|rho_j> 
            where i = composite EVec & fiducial index and j similar """

        gatestrings = []
        for germ in germList:
            expGerm = _gsc.repeat_with_max_length(germ,L) # could pass exponent and set to germ**exp here
            pairList = fidPairs[germ] if isinstance(fidPairs,dict) else fidPairs
            gatestrings += _gsc.create_gatestring_list("pp[0]+p[0]+expGerm+p[1]+pp[1]",
                                                       p=[ (prepStrs[i],effectStrs[j]) for i,j in pairList ],
                                                       pp=prepovmTuples, expGerm=expGerm, order=['p','pp'])
        gatestrings = _remove_duplicates(gatestrings)

        evTree,wrtSize,_,_,_ = targetGateset.bulk_evaltree_from_resources(
            gatestrings, memLimit=memLimit, distributeMethod="deriv",
            subcalls=['bulk_fill_dprobs'], verbosity=0)

        dP = _np.empty( (evTree.num_final_elements(), nGatesetParams) )
           #indexed by [iSpamLabel,iGateString,iGatesetParam] : gives d(<SP|GateString|AM>)/d(iGatesetParam)
        
        targetGateset.bulk_fill_dprobs(dP, evTree, wrtBlockSize=wrtSize)
        return dP

    def get_number_amplified(M0,M1,L0,L1):
        """ Return the number of amplified parameters """
        L_ratio = float(L1)/float(L0)
        try:
            s0 = _np.linalg.svd(M0, compute_uv=False)
            s1 = _np.linalg.svd(M1, compute_uv=False)
        except:
            printer.warning("SVD error!!"); return 0
            #SVD did not converge -> just say no amplified params...

        numAmplified = 0
        printer.log("Amplified parameter test: matrices are %s and %s." % (M0.shape, M1.shape), 4)
        printer.log("Index : SV(L=%d)  SV(L=%d)  AmpTest ( > %g ?)" % (L0,L1,tol), 4)
        for i,(v0,v1) in enumerate(zip(sorted(s0,reverse=True),sorted(s1,reverse=True))):
            if abs(v0) > 0.1 and (v1/v0)/L_ratio > tol:
                numAmplified += 1
                printer.log("%d: %g  %g  %g YES" % (i,v0,v1, (v1/v0)/L_ratio ), 4)
            printer.log("%d: %g  %g  %g NO" % (i,v0,v1, (v1/v0)/L_ratio ), 4)
        return numAmplified

    L0,L1 = testLs
    
    printer.log("----------  Testing Fiducial Pairs ----------")
    printer.log("Getting jacobian at L=%d" % L0,2)
    dP0 = get_derivs(L0)
    printer.log("Getting jacobian at L=%d" % L1,2)
    dP1 = get_derivs(L1)
    printer.log("Computing number amplified",2)
    nAmplified = get_number_amplified(dP0, dP1, L0, L1)
    printer.log("Number of amplified parameters = %s" % nAmplified)
    
    return nAmplified




#def _old_TestPair(targetGateset, fiducialList, germList, L, testPairList, spamLabels="all"):
#
#    if spamLabels == "all":
#        spamLabels = targetGateset.get_spam_labels()
#
#    dprobs = []
#    for iGerm,germ in enumerate(germList):
#        expGerm = _gsc.repeat_with_max_length(germ,L)
#        lst = _gsc.create_gatestring_list("f0+expGerm+f1", f0=fiducialList, f1=fiducialList,
#                                        expGerm=expGerm, order=('f0','f1'))
#        evTree = targetGateset.bulk_evaltree(lst)
#        dprobs.append( targetGateset.bulk_dprobs(evTree) )
#
#    nGatesetParams = targetGateset.num_params()
#    testMatrix = _np.empty( (0,nGatesetParams) )
#    for (i0,i1) in testPairList: #[(0,0),(1,0),(2,3),(4,5)]:
#        iCmp = i0*len(fiducialList) + i1 #composite index of (f0,f1) in dprobs[iGerm][spamLabel]
#
#        for iGerm,germ in enumerate(germList):
#            for spamLabel in spamLabels:
#                testMatrix = _np.concatenate( (testMatrix, dprobs[iGerm][spamLabel][iCmp:iCmp+1,:] ), axis=0 )
#
#        U,s,V = _np.linalg.svd(testMatrix)
#        rank = len( [v for v in s if v > 0.001] )
#        sorteds = sorted(s,reverse=True)
#        #print "DEBUG: added (%d,%d): testMx=%s, rank=%d, iCmp=%d, s =\n%s\n" % (i0,i1,testMatrix.shape,rank,iCmp,'\n'.join(map(str,enumerate(sorted(s,reverse=True)))))
#
#    print "Singular values:\n", '\n'.join(map(str,enumerate(sorteds)))
#    #print "normalized 34th singular val = ",sorteds[33]/len(pairList)
#    #print "normalized 35th singular val = ",sorteds[34]/len(pairList)
