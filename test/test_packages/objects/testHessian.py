import unittest
import warnings
import pygsti
from pygsti.construction import std1Q_XYI as stdxyi
from pygsti.construction import std1Q_XY as stdxy
from pygsti.objects import gatesetfunction as gsf
from pygsti.objects.gatemapcalc import GateMapCalc

import numpy as np
import sys, os

from ..testutils import BaseTestCase, compare_files, temp_files


class TestHessianMethods(BaseTestCase):

    def setUp(self):
        super(TestHessianMethods, self).setUp()

        self.gateset = pygsti.io.load_gateset(compare_files + "/analysis.gateset")
        self.ds = pygsti.objects.DataSet(fileToLoadFrom=compare_files + "/analysis.dataset%s" % self.versionsuffix)


        fiducials = stdxyi.fiducials
        germs = stdxyi.germs
        gateLabels = list(self.gateset.gates.keys()) # also == std.gates
        self.maxLengthList = [1,2]
        self.gss = pygsti.construction.make_lsgst_structs(gateLabels, fiducials, fiducials, germs, self.maxLengthList)


    def test_parameter_counting(self):
        #XY Gateset: SPAM=True
        n = stdxy.gs_target.num_params()
        self.assertEqual(n,44) # 2*16 + 3*4 = 44

        n = stdxy.gs_target.num_nongauge_params()
        self.assertEqual(n,28) # full 16 gauge params

        #XY Gateset: SPAM=False
        tst = stdxy.gs_target.copy()
        del tst.preps['rho0']
        del tst.povms['Mdefault']
        n = tst.num_params()
        self.assertEqual(n,32) # 2*16 = 32

        n = tst.num_nongauge_params()
        self.assertEqual(n,18) # gates are all unital & TP => only 14 gauge params (2 casimirs)


        #XYI Gateset: SPAM=True
        n = stdxyi.gs_target.num_params()
        self.assertEqual(n,60) # 3*16 + 3*4 = 60

        n = stdxyi.gs_target.num_nongauge_params()
        self.assertEqual(n,44) # full 16 gauge params: SPAM gate + 3 others

        #XYI Gateset: SPAM=False
        tst = stdxyi.gs_target.copy()
        del tst.preps['rho0']
        del tst.povms['Mdefault']
        n = tst.num_params()
        self.assertEqual(n,48) # 3*16 = 48

        n = tst.num_nongauge_params()
        self.assertEqual(n,34) # gates are all unital & TP => only 14 gauge params (2 casimirs)

        #XYI Gateset: SP0=False
        tst = stdxyi.gs_target.copy()
        tst.preps['rho0'] = pygsti.obj.TPParameterizedSPAMVec(tst.preps['rho0'])
        n = tst.num_params()
        self.assertEqual(n,59) # 3*16 + 2*4 + 3 = 59

        n = tst.num_nongauge_params()
        self.assertEqual(n,44) # 15 gauge params (minus one b/c can't change rho?)

        #XYI Gateset: G0=SP0=False
        tst.gates['Gi'] = pygsti.obj.TPParameterizedGate(tst.gates['Gi'])
        tst.gates['Gx'] = pygsti.obj.TPParameterizedGate(tst.gates['Gx'])
        tst.gates['Gy'] = pygsti.obj.TPParameterizedGate(tst.gates['Gy'])
        n = tst.num_params()
        self.assertEqual(n,47) # 3*12 + 2*4 + 3 = 47

        n = tst.num_nongauge_params()
        self.assertEqual(n,35) # full 12 gauge params of single 4x3 gate


    def test_hessian_projection(self):

        chi2, chi2Grad, chi2Hessian = pygsti.chi2(self.gateset, self.ds,
                                                  returnGradient=True,
                                                  returnHessian=True)

        proj_non_gauge = self.gateset.get_nongauge_projector()
        projectedHessian = np.dot(proj_non_gauge,
                                  np.dot(chi2Hessian, proj_non_gauge))

        print(self.gateset.num_params())
        print(proj_non_gauge.shape)
        self.assertEqual( projectedHessian.shape, (60,60) )
        #print("Evals = ")
        #print("\n".join( [ "%d: %g" % (i,ev) for i,ev in enumerate(np.linalg.eigvals(projectedHessian))] ))
        self.assertEqual( np.linalg.matrix_rank(proj_non_gauge), 44)
        self.assertEqual( np.linalg.matrix_rank(projectedHessian), 44)

        eigvals = np.sort(abs(np.linalg.eigvals(projectedHessian)))

        print("eigvals = ",eigvals)

        eigvals_chk =  np.array(
            [  1.06310603e-10,   2.65635664e-10,   6.50301005e-10,   7.97927477e-10,
               7.97927477e-10,   1.00960481e-09,   1.20668922e-09,   1.60395671e-09,
               1.60395671e-09,   2.10414039e-09,   2.40422523e-09,   2.66328705e-09,
               2.66328705e-09,   3.78157418e-09,   4.97929640e-09,   1.69073771e-08,
               9.22542920e+05,   1.05940963e+06,   1.16240250e+06,   1.39506940e+06,
               1.83925308e+06,   2.11037916e+06,   2.39385711e+06,   2.47432236e+06,
               2.63561759e+06,   2.68157105e+06,   2.81568070e+06,   2.86569765e+06,
               2.94543146e+06,   2.95039566e+06,   3.08684833e+06,   3.28869042e+06,
               3.66558726e+06,   3.76232707e+06,   3.82389736e+06,   3.86638791e+06,
               3.88874028e+06,   4.73808468e+06,   4.96550964e+06,   6.53177028e+06,
               1.01544928e+07,   1.11525472e+07,   1.25572253e+07,   1.30411488e+07,
               1.36881398e+07,   1.49309288e+07,   1.57790471e+07,   1.81263731e+07,
               2.08276405e+07,   2.18675949e+07,   2.46968548e+07,   2.64099665e+07,
               2.72117335e+07,   3.35172152e+07,   3.45138716e+07,   3.68918207e+07,
               5.09742531e+07,   9.43260992e+07,   1.36044734e+08,   6.30355637e+08])
            
            #OLD
            #[  2.53636344e-10,   3.87263955e-10,   4.49523968e-10,
            #   8.17955744e-10,   8.17955744e-10,   1.22910388e-09,
            #   1.23803907e-09,   1.67547571e-09,   1.67547571e-09,
            #   1.75147770e-09,   2.20582127e-09,   2.20582127e-09,
            #   2.84333714e-09,   4.43169431e-09,   4.43169431e-09,
            #   1.75164250e-08,   9.38919779e+05,   9.57169426e+05,
            #   9.69271265e+05,   1.41963844e+06,   1.52443387e+06,
            #   1.89627852e+06,   1.97543819e+06,   2.05177386e+06,
            #   2.18333142e+06,   2.30078215e+06,   2.31036461e+06,
            #   2.40108194e+06,   2.63301339e+06,   2.72062783e+06,
            #   2.73970548e+06,   2.90332118e+06,   3.15705184e+06,
            #   3.86079309e+06,   3.87209620e+06,   4.70586582e+06,
            #   8.76738379e+06,   9.73067464e+06,   1.04062266e+07,
            #   1.15408214e+07,   1.21868610e+07,   1.33524791e+07,
            #   1.34516720e+07,   1.50757108e+07,   1.74290255e+07,
            #   1.83023511e+07,   2.15141700e+07,   2.22614418e+07,
            #   2.32690752e+07,   2.88149432e+07,   3.04306844e+07,
            #   3.10300863e+07,   4.25290585e+07,   8.95794195e+07,
            #   1.29723323e+08,   5.69560469e+08])

        TOL = 1e-7
        for val,chk in zip(eigvals,eigvals_chk):
            if abs(val) > TOL or abs(chk) > TOL:
                self.assertAlmostEqual(abs(val-chk)/(abs(chk)+TOL), 0.0, places=3)
            # (else both chk and val are <= TOL, so both == 0 for our purposes)
        #print "eigvals = ",eigvals

    def test_confidenceRegion(self):

        res = pygsti.obj.Results()
        res.init_dataset(self.ds)
        res.init_gatestrings(self.gss)
        res.add_estimate(stdxyi.gs_target.copy(), stdxyi.gs_target.copy(),
                         [self.gateset]*len(self.maxLengthList), parameters={'objective': 'logl'},
                         estimate_key="default")
        
        est = res.estimates['default']
        est.add_confidence_region_factory('final iteration estimate', 'final')
        self.assertTrue( est.has_confidence_region_factory('final iteration estimate', 'final'))

        cfctry = est.get_confidence_region_factory('final iteration estimate', 'final')
        cfctry.compute_hessian()
        self.assertTrue( cfctry.has_hessian() )

        cfctry.project_hessian('std')
        cfctry.project_hessian('none')
        cfctry.project_hessian('optimal gate CIs')
        cfctry.project_hessian('intrinsic error')

        cfctry.enable_linear_response_errorbars()
        #{'dataset': self.ds, 'gateStringsToUse': list(self.ds.keys())})

        ci_std = cfctry.view( 95.0, 'normal', 'std')
        ci_noproj = cfctry.view( 95.0, 'normal', 'none')
        ci_intrinsic = cfctry.view( 95.0, 'normal', 'intrinsic error')
        ci_opt = cfctry.view( 95.0, 'normal', 'optimal gate CIs')
        #ci_linresponse = ??
        
        with self.assertRaises(ValueError):
            cfctry.project_hessian(95.0, 'normal', 'FooBar') #bad hessianProjection

        self.assertWarns(cfctry.view, 0.95, 'normal', 'none') # percentage < 1.0

        for ci_cur in (ci_std, ci_noproj, ci_opt, ci_intrinsic): # , ci_linresponse
            try: 
                ar_of_intervals_Gx = ci_cur.get_profile_likelihood_confidence_intervals("Gx")
                ar_of_intervals_rho0 = ci_cur.get_profile_likelihood_confidence_intervals("rho0")
                ar_of_intervals_M0 = ci_cur.get_profile_likelihood_confidence_intervals("Mdefault")
                ar_of_intervals = ci_cur.get_profile_likelihood_confidence_intervals()
            except NotImplementedError: 
                pass #linear response CI doesn't support profile likelihood intervals
    
            def fnOfGate_float(mx,b):
                return float(mx[0,0])
            def fnOfGate_0D(mx,b):
                return np.array( float(mx[0,0]) )
            def fnOfGate_1D(mx,b):
                return mx[0,:]
            def fnOfGate_2D(mx,b):
                return mx[:,:]
            def fnOfGate_3D(mx,b):
                return np.zeros( (2,2,2), 'd') #just to test for error

            for fnOfGate in (fnOfGate_float, fnOfGate_0D, fnOfGate_1D, fnOfGate_2D, fnOfGate_3D):
                FnClass = gsf.gatefn_factory(fnOfGate)
                FnObj = FnClass(self.gateset, 'Gx')
                if fnOfGate is fnOfGate_3D:
                    with self.assertRaises(ValueError):
                        df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                else:
                    df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                    df, f0 = self.runSilent(ci_cur.get_fn_confidence_interval,
                                            FnObj, returnFnVal=True, verbosity=4)

            ##SHORT-CIRCUIT linear reponse here to reduce run time
            #if ci_cur is ci_linresponse: continue
    
            def fnOfVec_float(v,b):
                return float(v[0])
            def fnOfVec_0D(v,b):
                return np.array( float(v[0]) )
            def fnOfVec_1D(v,b):
                return np.array(v[:])
            def fnOfVec_2D(v,b):
                return np.dot(v.T,v)
            def fnOfVec_3D(v,b):
                return np.zeros( (2,2,2), 'd') #just to test for error
    
            for fnOfVec in (fnOfVec_float, fnOfVec_0D, fnOfVec_1D, fnOfVec_2D, fnOfVec_3D):
                FnClass = gsf.vecfn_factory(fnOfVec)
                FnObj = FnClass(self.gateset, 'rho0', 'prep')
                if fnOfVec is fnOfVec_3D:
                    with self.assertRaises(ValueError):
                        df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                else:
                    df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                    df, f0 = self.runSilent(ci_cur.get_fn_confidence_interval,
                                            FnObj, returnFnVal=True, verbosity=4)

            for fnOfVec in (fnOfVec_float, fnOfVec_0D, fnOfVec_1D, fnOfVec_2D, fnOfVec_3D):
                FnClass = gsf.vecfn_factory(fnOfVec)
                FnObj = FnClass(self.gateset, 'Mdefault:0', 'effect')
                if fnOfVec is fnOfVec_3D:
                    with self.assertRaises(ValueError):
                        df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                else:
                    df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                    df, f0 = self.runSilent(ci_cur.get_fn_confidence_interval,
                                            FnObj, returnFnVal=True, verbosity=4)
    
    
            def fnOfSpam_float(rhoVecs, povms):
                lbls = list(povms[0].keys())
                return float( np.dot( rhoVecs[0].T, povms[0][lbls[0]] ) )
            def fnOfSpam_0D(rhoVecs, povms):
                lbls = list(povms[0].keys())
                return np.array( float( np.dot( rhoVecs[0].T, povms[0][lbls[0]] ) ) )
            def fnOfSpam_1D(rhoVecs, povms):
                lbls = list(povms[0].keys())
                return np.array( [ np.dot( rhoVecs[0].T, povms[0][lbls[0]] ), 0] )
            def fnOfSpam_2D(rhoVecs, povms):
                lbls = list(povms[0].keys())
                return np.array( [[ np.dot( rhoVecs[0].T, povms[0][lbls[0]] ), 0],[0,0]] )
            def fnOfSpam_3D(rhoVecs, povms):
                return np.zeros( (2,2,2), 'd') #just to test for error

            for fnOfSpam in (fnOfSpam_float, fnOfSpam_0D, fnOfSpam_1D, fnOfSpam_2D, fnOfSpam_3D):
                FnClass = gsf.spamfn_factory(fnOfSpam)
                FnObj = FnClass(self.gateset)
                if fnOfSpam is fnOfSpam_3D:
                    with self.assertRaises(ValueError):
                        df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                else:
                    df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                    df, f0 = self.runSilent(ci_cur.get_fn_confidence_interval,
                                            FnObj, returnFnVal=True, verbosity=4)

    
            def fnOfGateSet_float(gs):
                return float( gs.gates['Gx'][0,0] )
            def fnOfGateSet_0D(gs):
                return np.array( gs.gates['Gx'][0,0]  )
            def fnOfGateSet_1D(gs):
                return np.array( gs.gates['Gx'][0,:] )
            def fnOfGateSet_2D(gs):
                return np.array( gs.gates['Gx'] )
            def fnOfGateSet_3D(gs):
                return np.zeros( (2,2,2), 'd') #just to test for error

            for fnOfGateSet in (fnOfGateSet_float, fnOfGateSet_0D, fnOfGateSet_1D, fnOfGateSet_2D, fnOfGateSet_3D):
                FnClass = gsf.gatesetfn_factory(fnOfGateSet)
                FnObj = FnClass(self.gateset)
                if fnOfGateSet is fnOfGateSet_3D:
                    with self.assertRaises(ValueError):
                        df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                else:
                    df = ci_cur.get_fn_confidence_interval(FnObj, verbosity=0)
                    df, f0 = self.runSilent(ci_cur.get_fn_confidence_interval,
                                            FnObj, returnFnVal=True, verbosity=4)

        #TODO: assert values of df & f0 ??

    def tets_pickle_ConfidenceRegion(self):
        res = pygsti.obj.Results()
        res.init_dataset(self.ds)
        res.init_gatestrings(self.gss)
        res.add_estimate(stdxyi.gs_target.copy(), stdxyi.gs_target.copy(),
                         [self.gateset]*len(self.maxLengthList), parameters={'objective': 'logl'},
                         estimate_key="default")
        
        res.add_confidence_region_factory('final iteration estimate', 'final')
        self.assertTrue( res.has_confidence_region_factory('final iteration estimate', 'final'))

        cfctry = res.get_confidence_region_factory('final iteration estimate', 'final')
        cfctry.compute_hessian()
        self.assertTrue( cfctry.has_hessian() )

        cfctry.project_hessian('std')
        ci_std = cfctry.view( 95.0, 'normal', 'std')

        import pickle
        s = pickle.dumps(cfctry)
        cifctry2 = pickle.loads(s)
        
        s = pickle.dumps(ci_std)
        ci_std2 = pickle.loads(s)
        
        #TODO: make sure ci_std and ci_std2 are the same


    def test_mapcalc_hessian(self):
        chi2, chi2Hessian = pygsti.chi2(self.gateset, self.ds, 
                                        returnHessian=True)
        
        gs_mapcalc = self.gateset.copy()
        gs_mapcalc._calcClass = GateMapCalc
        chi2, chi2Hessian_mapcalc = pygsti.chi2(self.gateset, self.ds, 
                                        returnHessian=True)

        self.assertArraysAlmostEqual(chi2Hessian, chi2Hessian_mapcalc)



if __name__ == "__main__":
    unittest.main(verbosity=2)
