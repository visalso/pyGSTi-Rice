""" Routines for converting python objects to python. """
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

import collections as _collections
from ..objects.reportableqty import ReportableQty as _ReportableQty

'''
table() and cell() functions are used by table.py in table creation
everything else is used in creating formatters in formatters.py
'''

def table(customHeadings, colHeadingsFormatted, rows, spec):
    '''
    Create a "Python table" - really a pandas DataFrame

    Parameters
    ----------
    customHeadings : None, dict
        optional dictionary of custom table headings
    colHeadingsFormatted : list
        formatted column headings
    rows : list of lists of cell-strings
        Data in the table, pre-formatted
    spec : dict
        options for the formatter
    Returns
    -------
    dict : contains key 'python', which corresponds to a
           pandas.DataFrame object representing the table
    '''
    try:
        import pandas as _pd
    except ImportError:
        raise ValueError(("You must have the optional 'pandas' package "
                          "installed to render tables in the 'python' format"))
    
    if customHeadings is not None \
            and "python" in customHeadings:
        colLabels = customHeadings['python']
    else:
        colLabels = colHeadingsFormatted
    nCols = len(colLabels)

    if nCols == 0: return {'python': _pd.DataFrame() }

    #Add addition error-bar columns for any columns that have error bar info
    cols_containing_ebs = set()
    for formatted_rowData in rows:
        assert(len(formatted_rowData) == nCols)
        for i,formatted_cellData in enumerate(formatted_rowData):
            if isinstance(formatted_cellData, _ReportableQty) and \
               formatted_cellData.has_eb():
                cols_containing_ebs.add(i)

    n=0 # number of cols inserted
    for iCol in sorted(cols_containing_ebs):
        origLbl = colLabels[iCol+n]
        colLabels.insert(iCol+n+1, origLbl + " Error Bar")
        n += 1
        
    rowLabels = [ ]
    rowIndexName =  colLabels[0].value if isinstance(colLabels[0], _ReportableQty) else colLabels[0]
    if len(rowIndexName.strip()) == 0:
        rowIndexName = None

    dict_of_columns = _collections.OrderedDict()
    for colLabel in colLabels[1:]:
        dict_of_columns[colLabel] = []

    for formatted_rowData in rows:
        rowLabels.append(formatted_rowData[0]); n=0
        
        for i,formatted_cellData in enumerate(formatted_rowData[1:],start=1):
            if i in cols_containing_ebs:
                if isinstance(formatted_cellData, _ReportableQty):
                    val, eb = formatted_cellData.get_value_and_err_bar()
                else:
                    val, eb = formatted_cellData, None
                dict_of_columns[colLabels[i+n]].append( val )
                dict_of_columns[colLabels[i+n+1]].append( eb )
                n += 1
            else:
                dict_of_columns[colLabels[i+n]].append( formatted_cellData )

    indx = _pd.Index(rowLabels, name=rowIndexName)
    df = _pd.DataFrame(dict_of_columns,
                       columns=dict_of_columns.keys(),
                       index=indx)
    
    return {'python' : df}


def cell(data, label, spec):
    '''
    Format the cell of a python table 

    Parameters
    ----------
    data : string
        string representation of cell content
    label : string
        optional cell label, used for tooltips
    spec : dict
        options for the formatters

    Returns
    -------
    string
    '''
    return data

def list(l, specs):
    """
    Stub for conversion that isn't needed in python case.
    (Convert a python list to python.)

    Parameters
    ----------
    l : list
        list to convert into latex. sub-items pre formatted

    specs : dictionary
        Dictionary of user-specified and default parameters to formatting

    Returns
    -------
    list
    """
    return l


def vector(v, specs):
    """
    Stub for conversion that isn't needed in python case.
    (Convert a 1D numpy array to python.)

    Parameters
    ----------
    v : numpy array
        1D array to convert.

    specs : dictionary
        Dictionary of user-specified and default parameters to formatting

    Returns
    -------
    numpy array        
    """
    return v


def matrix(m, specs):
    """
    Stub for conversion that isn't needed in python case.
    Convert a 2D numpy array to python.

    Parameters
    ----------
    m : numpy array
        2D array to convert.

    specs : dictionary
        Dictionary of user-specified and default parameters to formatting

    Returns
    -------
    numpy array
    """
    return m

def value(el, specs):
    """
    Stub for conversion that isn't needed in python case.
    (this function would be for converting python to python).

    Parameters
    ----------
    el : float or complex
        Value to convert into latex.

    specs : dictionary
        Dictionary of user-specified and default parameters to formatting

    Returns
    -------
    float or complex
    """
    return el


def escaped(txt, specs):
    """
    Stub for conversion that isn't needed in python case.
    (Escape txt so it is python safe.)

    Parameters
    ----------
    txt : string
        value to escape

    specs : dictionary
        Dictionary of user-specified and default parameters to formatting

    Returns
    -------
    string
    """
    return txt
