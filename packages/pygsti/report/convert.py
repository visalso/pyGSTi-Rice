'''
This module defines type-differentiation for low level formatting types
Its main function, convert, takes any item x, a specs dictionary, and a format (ie 'html')
and returns a formatted version of x using the format
'''
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************
from . import html
from . import latex
from . import python

import numpy as _np
import functools
from .. import objects as _objs
from ..tools import compattools as _compat
from ..objects.reportableqty import ReportableQty as _ReportableQty


def functions_in(module):
    '''
    Create a dictionary of the functions in a module
    '''
    return { name : f for name, f in module.__dict__.items() if callable(f)}

convertDict = {
        'html'  : functions_in(html),
        'latex' : functions_in(latex),
        'python' : functions_in(python)}

def calc_dim(x):
    '''
    Calculate the dimension of some matrix-like type
    '''
    d = 0
    for l in x.shape:
        if l > 1: d += 1
    return d

def item_type(x):
    """
    Differentiate an item's type

    Parameters
    ----------
    x : anything
        Value to convert.
    Returns
    -------
    string
        name of low-level formatter to use (i.e. value or matrix)
    """
    if isinstance(x, _ReportableQty):
        return 'reportable'
    if isinstance(x,_np.ndarray) or \
       isinstance(x,_objs.Gate) or \
       isinstance(x,_objs.SPAMVec):
        d = calc_dim(x)
        if d == 0: return 'value' 
        if d == 1: return 'vector' 
        if d == 2: return 'matrix' 
        raise ValueError("I don't know how to render a rank %d numpy array as html" % d)
    elif type(x) in (float,int,complex,_np.float64,_np.int64):
        return 'value'
    elif type(x) in (list,tuple):
        return 'list'
    elif _compat.isstr(x):
        return 'escaped'
    else:
        return 'raw'

def convert(x, specs, fmt):
    '''
    Convert any item to a format
    '''

    #Squeeze arrays before formatting
    if isinstance(x,_np.ndarray) or \
       isinstance(x,_objs.Gate) or \
       isinstance(x,_objs.SPAMVec):
        x = _np.squeeze(x)
    
    t = item_type(x)
    if t == 'raw':
        print('WARNING: {} not explicitly converted to {}'.format(x, fmt))
        return str(x)
    if t == 'reportable':
        return x.render_with(lambda a,specz : convert(a, specz, fmt))
    if t == 'list':
        return convertDict[fmt][t]([convert(xi, specs, fmt) for xi in x], specs)
    return convertDict[fmt][t](x, specs)

def converter(fmt):
    '''
    Create a converter function for some specific format
    '''
    return functools.partial(convert, fmt=fmt)
