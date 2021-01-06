#!/usr/bin/env python3
import pygsti
from pygsti.algorithms.gaugeopt import create_objective_fn
from pygsti.tools.opttools      import timed_block

import pickle
from functools  import partial

def test_options(gs, gs_target, options, iterations=100):
    objective_fn = create_objective_fn(gs, gs_target, **options)

    with timed_block('Objective function'):
        for i in range(iterations):
            objective_fn(gs)
    print('({} iterations)'.format(iterations))

def main():
    with open('2qbit_results.pkl', 'rb') as infile:
        results = pickle.load(infile)

    est       = results.estimates['default']
    gs_target = est.gatesets['target']
    gs        = est.gatesets['final iteration estimate']

    test = partial(test_options, gs, gs_target)

    defaultOptions = {
            'itemWeights' : {'spam' : 0.0001, 'gates' : 1.0},
            'spamMetric'  : 'frobenius',
            'gatesMetric' : 'frobenius'}

    test(defaultOptions, iterations=10000)

main()
