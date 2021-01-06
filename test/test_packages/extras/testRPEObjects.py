from ..testutils import BaseTestCase, compare_files, temp_files
import unittest
import pygsti
import numpy as np

import pygsti.extras.rpe as rpe
import pygsti.extras.rpe.rpeconstruction as rc
from pygsti.extras.rpe.rpeconfig_GxPi2_GyPi2_UpDn import rpeconfig_GxPi2_GyPi2_UpDn

class TestRPEObjectMethods(BaseTestCase):

    def test_rpe_datasets(self):

        gateset = pygsti.construction.build_gateset( [2], [('Q0',)],['Gi','Gx','Gy','Gz'],
                                                     [ "I(Q0)","X(pi/8,Q0)", "Y(pi/8,Q0)", "Z(pi/2,Q0)"])

        depol_gateset = gateset.depolarize(gate_noise=0.1,spam_noise=0)

        #test RPE datasets
        rpeconfig_inst = rpeconfig_GxPi2_GyPi2_UpDn
        rpeGS  = rc.make_parameterized_rpe_gate_set(np.pi/2, np.pi/4, 0, 0.1, 0.1, True, rpeconfig_inst=rpeconfig_inst)
        rpeGS2 = rc.make_parameterized_rpe_gate_set(np.pi/2, np.pi/4, 0, 0.1, 0.1, False, rpeconfig_inst=rpeconfig_inst)
        rpeGS3 = rc.make_parameterized_rpe_gate_set(np.pi/2, np.pi/4, np.pi/4, 0.1, 0.1, False, rpeconfig_inst=rpeconfig_inst)

        kList = [0,1,2]
        lst1 = rc.make_rpe_angle_str_lists(kList, "alpha", rpeconfig_inst)
        lst2 = rc.make_rpe_angle_str_lists(kList, "epsilon", rpeconfig_inst)
        lst3 = rc.make_rpe_angle_str_lists(kList, "theta", rpeconfig_inst)
        lstDict = rc.make_rpe_angle_string_list_dict(2,rpeconfig_inst)

        rpeDS = rc.make_rpe_data_set(depol_gateset,lstDict,1000,
                                     sampleError='binomial',seed=1234)

        #Just make sure this runs:
        #Removed? rc.rpe_ensemble_test(np.pi/2, np.pi/4, 0, 0.1, 2, 1000, 2)

    def test_bad_rpeconfig(self):
        #Note: this doesn't actually raise an exception, it just prints a warning message to stdout
        with self.assertRaises(ValueError):
            badconfig = rpe.rpeconfig({'alpha': 0, 'epsilon': 1, 'theta': 2} ) #need lots more keys...


if __name__ == "__main__":
    unittest.main(verbosity=2)
