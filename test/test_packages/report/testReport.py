import unittest
import warnings
import pickle
import pygsti
import os
from pygsti.construction import std1Q_XYI as std
from ..testutils import compare_files, temp_files

import numpy as np

# Inherit setup from here
from .reportBaseCase import ReportBaseCase

class TestReport(ReportBaseCase):

    def checkFile(self, fn):
        if 'PYGSTI_DEEP_TESTING' in os.environ and \
           os.environ['PYGSTI_DEEP_TESTING'].lower() in ("yes","1","true"):
            # Deep testing -- do latex comparison
            cmpFilenm = compare_files + "/%s" % fn
            if os.path.exists(cmpFilenm):
                linesToTest = open(temp_files + "/%s" % fn).readlines()
                linesOK = open(cmpFilenm).readlines()
                self.assertEqual(linesToTest,linesOK)
            else:
                print("WARNING! No reference file to compare against: %s" % cmpFilenm)
        else:
            # Normal testing -- no latex comparison
            pass

    def test_reports_chi2_noCIs(self):
        vs = self.versionsuffix
        pygsti.report.create_standard_report(self.results,temp_files + "/general_reportA",
                                            confidenceLevel=None, verbosity=3,  auto_open=False) # omit title as test
        #Compare the html files?
        #self.checkFile("general_reportA%s.html" % vs)


    def test_reports_chi2_wCIs(self):
        vs = self.versionsuffix
        crfact = self.results.estimates['default'].add_confidence_region_factory('go0', 'final')
        crfact.compute_hessian(comm=None)
        crfact.project_hessian('intrinsic error')

        pygsti.report.create_standard_report(self.results,temp_files + "/general_reportB",
                                            "Report B", confidenceLevel=95, verbosity=3,  auto_open=False)
        #Compare the html files?
        #self.checkFile("general_reportB%s.html" % vs)


    def test_reports_chi2_nonMarkCIs(self):
        vs = self.versionsuffix
        crfact = self.results.estimates['default'].add_confidence_region_factory('go0', 'final')
        crfact.compute_hessian(comm=None)
        crfact.project_hessian('std')

        #Note: Negative confidence levels no longer trigger non-mark error bars; this is done via "nm threshold"
        pygsti.report.create_standard_report(self.results,temp_files + "/general_reportE",
                                             "Report E", confidenceLevel=95, verbosity=3,  auto_open=False,
                                             advancedOptions={'nm threshold': -10})
        #Compare the html files?
        #self.checkFile("general_reportC%s.html" % vs)


    def test_reports_logL_TP_noCIs(self):
        vs = self.versionsuffix

        #Also test adding a model-test estimate to this report
        gs_guess = std.gs_target.depolarize(gate_noise=0.07,spam_noise=0.03)
        results = self.results_logL.copy()
        results.add_model_test(std.gs_target, gs_guess, estimate_key='Test', gauge_opt_keys="auto")

        
        #Note: this report will have (un-combined) Robust estimates too
        pygsti.report.create_standard_report(results,temp_files + "/general_reportC",
                                             "Report C", confidenceLevel=None, verbosity=3,  auto_open=False,
                                             advancedOptions={'combine_robust': False} )
        #Compare the html files?
        #self.checkFile("general_reportC%s.html" % vs)


    def test_reports_logL_TP_wCIs(self):
        vs = self.versionsuffix

        #Use propagation method instead of directly computing a factory for the go0 gauge-opt
        crfact = self.results.estimates['default'].add_confidence_region_factory('final iteration estimate', 'final')
        crfact.compute_hessian(comm=None)

        self.results.estimates['default'].gauge_propagate_confidence_region_factory('go0') #instead of computing one        
        crfact = self.results.estimates['default'].get_confidence_region_factory('go0') #was created by propagation
        crfact.project_hessian('optimal gate CIs')

        #Note: this report will have Robust estimates too
        pygsti.report.create_standard_report(self.results_logL,temp_files + "/general_reportD",
                                             "Report D", confidenceLevel=95, verbosity=3,  auto_open=False)
        #Compare the html files?
        #self.checkFile("general_reportD%s.html" % vs)

    def test_reports_multiple_ds(self):
        vs = self.versionsuffix
        
        #Note: this report will have (un-combined) Robust estimates too
        pygsti.report.create_standard_report({"chi2": self.results, "logl": self.results_logL},
                                             temp_files + "/general_reportF",
                                             "Report F", confidenceLevel=None, verbosity=3,  auto_open=False)
        #Compare the html files?
        #self.checkFile("general_reportC%s.html" % vs)


    def test_report_notebook(self):
        pygsti.report.create_report_notebook(self.results_logL, temp_files + "/report_notebook.ipynb", None,
                                             verbosity=3)


    def test_table_formatting(self):
        vec = np.array( [1.0,2.0,3.0] )
        mx = np.identity( 2, 'd' )
        rank3Tensor = np.zeros( (2,2,2), 'd')
        f = 10.0
        l = [10.0, 20.0]

        class weirdType:
            def __init__(self):
                pass
            def __str__(self):
                return "weird"
        w = weirdType()

        from pygsti.report.convert import converter
        specs = dict(longtables=False, tableID=None, tableclass=None,
               scratchDir=None, precision=6, polarprecision=3, sciprecision=0,
               resizable=False, autosize=False, fontsize=None, complexAsPolar=True,
               brackets=False)
        html  = converter('html')  # Retrieve low-level formatters
        latex = converter('latex')

        print("Float formatting")
        html(f, specs)
        latex(f, specs)

        print("List formatting")
        html(l, specs)
        latex(l, specs)

        print("Arbitrary class formatting")
        html(w, specs)
        latex(w, specs)

        print("Vector formatting")
        html(vec, specs)
        latex(vec, specs)

        print("Vector formatting (w/brackets)")
        specs['brackets'] = True
        html(vec, specs)
        latex(vec, specs)
        specs['brackets'] = False

        print("Matrix formatting")
        specs['fontsize'] = 8
        html(mx, specs)
        latex(mx, specs)
        specs['fontsize'] = None

        print("Value formatting")
        specs['precision'] = 2
        specs['complexAsPolar'] = True
        for complxAsPolar in (True,False):
            for x in (0.001,0.01,1.0,10.0,100.0,1000.0,10000.0,1.0+1.0j,10j,1.0+1e-10j,1e-10j,"N/A"):
                html(x, specs)
                latex(x, specs)

        with self.assertRaises(ValueError):
            html(rank3Tensor, specs)

        with self.assertRaises(ValueError):
            latex(rank3Tensor, specs)

#Test functions within reportables separately? This version of the test is outdated:
#    def test_reportables(self):
#        #Test that None is returned when qty cannot be computed
#        qty = pygsti.report.reportables.compute_dataset_qty("FooBar",self.ds)
#        self.assertIsNone(qty)
#        qty = pygsti.report.reportables.compute_gateset_qty("FooBar",self.gs_clgst)
#        self.assertIsNone(qty)
#        qty = pygsti.report.reportables.compute_gateset_dataset_qty("FooBar",self.gs_clgst, self.ds)
#        self.assertIsNone(qty)
#        qty = pygsti.report.reportables.compute_gateset_gateset_qty("FooBar",self.gs_clgst, self.gs_clgst)
#        self.assertIsNone(qty)
#
#        #test ignoring gate strings not in dataset
#        qty = pygsti.report.reportables.compute_dataset_qty("gate string length", self.ds,
#                                                            pygsti.construction.gatestring_list([('Gx','Gx'),('Gfoobar',)]) )
#        qty = pygsti.report.reportables.compute_gateset_dataset_qty("prob(0) diff", self.gs_clgst, self.ds,
#                                                            pygsti.construction.gatestring_list([('Gx','Gx'),('Gfoobar',)]) )
#        qty_str = str(qty) #test __str__
#
#        #Test gateset gates mismatch
#        from pygsti.construction import std1Q_XY as stdXY
#        with self.assertRaises(ValueError):
#            qty = pygsti.report.reportables.compute_gateset_gateset_qty(
#                "Gx fidelity",std.gs_target, stdXY.gs_target) #Gi missing from 2nd gateset
#        with self.assertRaises(ValueError):
#            qty = pygsti.report.reportables.compute_gateset_gateset_qty(
#                "Gx fidelity",stdXY.gs_target, std.gs_target) #Gi missing from 1st gateset



#def test_results_object(self):
#    results = pygsti.report.Results()
#    results.init_single("logl", self.targetGateset, self.ds, self.gs_clgst,
#                        self.lgstStrings, self.targetGateset)
#
#    results.parameters.update(
#        {'minProbClip': 1e-6, 'minProbClipForWeighting': 1e-4,
#         'probClipInterval': (-1e6,1e6), 'radius': 1e-4,
#         'weights': None, 'defaultDirectory': temp_files + "",
#         'defaultBasename': "MyDefaultReportName",
#         'hessianProjection': 'std'} )
#
#    results.create_full_report_pdf(
#        filename=temp_files + "/singleReport.pdf")
#    results.create_brief_report_pdf(
#        filename=temp_files + "/singleBrief.pdf")
#    results.create_presentation_pdf(
#        filename=temp_files + "/singleSlides.pdf")
#    if self.have_python_pptx:
#        results.create_presentation_ppt(
#            filename=temp_files + "/singleSlides.ppt", pptTables=True)
#
#    #test tree splitting of hessian
#    results.parameters['memLimit'] = 10*(1024)**2 #10MB
#    results.create_brief_report_pdf(confidenceLevel=95,
#        filename=temp_files + "/singleBriefMemLimit.pdf")
#    results.parameters['memLimit'] = 10 #10 bytes => too small
#    with self.assertRaises(MemoryError):
#        results.create_brief_report_pdf(confidenceLevel=90,
#           filename=temp_files + "/singleBriefMemLimit.pdf")
#
#
#    #similar test for chi2 hessian
#    results2 = pygsti.report.Results()
#    results2.init_single("chi2", self.targetGateset, self.ds, self.gs_clgst,
#                        self.lgstStrings, self.targetGateset)
#    results2.parameters.update(
#        {'minProbClip': 1e-6, 'minProbClipForWeighting': 1e-4,
#         'probClipInterval': (-1e6,1e6), 'radius': 1e-4,
#         'weights': None, 'defaultDirectory': temp_files + "",
#         'defaultBasename': "MyDefaultReportName",
#         'hessianProjection': "std"} )
#    results2.parameters['memLimit'] = 10*(1024)**2 #10MB
#    results2.create_brief_report_pdf(confidenceLevel=95,
#        filename=temp_files + "/singleBriefMemLimit2.pdf")
#    results2.parameters['memLimit'] = 10 #10 bytes => too small
#    with self.assertRaises(MemoryError):
#        results2.create_brief_report_pdf(confidenceLevel=90,
#           filename=temp_files + "/singleBriefMemLimit2.pdf")
#
#
#
#
#    results_str = str(results)
#    tableNames = list(results.tables.keys())
#    figNames = list(results.figures.keys())
#    for g in results.gatesets:
#        s = str(g)
#    for g in results.gatestring_lists:
#        s = str(g)
#    s = str(results.dataset)
#    s = str(results.options)
#
#    self.assertTrue(tableNames[0] in results.tables)
#
#    with self.assertRaises(KeyError):
#        x = results.tables.get('foobar')
#    with self.assertRaises(ValueError):
#        results.tables['newKey'] = "notAllowed"
#    with self.assertRaises(NotImplementedError):
#        for x in results.tables: # cannot __iter__
#            print(x)
#    with self.assertRaises(NotImplementedError):
#        for x in results.tables.iteritems(): # cannot iter
#            print(x)
#    with self.assertRaises(NotImplementedError):
#        for x in list(results.tables.values()): # cannot iter
#            print(x)
#
#    pkl = pickle.dumps(results)
#    results_copy = pickle.loads(pkl)
#    self.assertEqual(tableNames, list(results_copy.tables.keys()))
#    self.assertEqual(figNames, list(results_copy.figures.keys()))
#    #self.assertEqual(results.options, results_copy.options) #need to add equal test to ResultsOptions
#    self.assertEqual(results.parameters, results_copy.parameters)
#
#    results2 = pygsti.report.Results()
#    results2.options.template_path = "/some/path/to/templates"
#    results2.options.latex_cmd = "myCustomLatex"
#
#    #bad objective function name
#    results_badObjective = pygsti.report.Results()
#    #results_badObjective.init_single("foobar", self.targetGateset, self.ds, self.gs_clgst,
#    #                                 self.lgstStrings)
#    results_badObjective.init_Ls_and_germs("foobar", self.targetGateset, self.ds, self.gs_clgst, [0], self.germs,
#                                           [self.gs_clgst], [self.lgstStrings], self.fiducials, self.fiducials,
#                                           pygsti.construction.repeat_with_max_length, True)
#
#    with self.assertRaises(ValueError):
#        results_badObjective._get_confidence_region(95)
#    with self.assertRaises(ValueError):
#        results_badObjective._specials['DirectLongSeqGatesets']
#    with self.assertRaises(ValueError):
#        results_badObjective.create_full_report_pdf(filename=temp_files + "/badReport.pdf")
#    with self.assertRaises(ValueError):
#        results_badObjective.create_presentation_pdf(filename=temp_files + "/badSlides.pdf")
#    if self.have_python_pptx:
#        with self.assertRaises(ValueError):
#            results_badObjective.create_presentation_ppt(filename=temp_files + "/badSlides.pptx")


if __name__ == "__main__":
    unittest.main(verbosity=2)
