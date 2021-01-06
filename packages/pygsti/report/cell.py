""" Defines the Cell class """
from __future__ import division, print_function, absolute_import, unicode_literals

#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

from .formatters import formatDict  as _formatDict
from .convert    import convertDict as _convertDict


class Cell(object):
    '''
    Representation of a table cell, containing formatting and labeling info
    '''
    def __init__(self, data=None, formatterName=None, label=None):
        '''
        Creates Cell object 

        Parameters
        ----------
        data : ReportableQty 
            data to be reported
        formatterName : string
            name of the formatter to be used (ie 'Effect')
        label : string
            label of the cell
        '''
        self.data          = data
        self.formatterName = formatterName
        self.label         = label

    def __getstate__(self):
        state_dict = self.__dict__.copy()
        return state_dict 

    def __setstate__(self, d):
        self.__dict__.update(d)

    def _render_data(self, fmt, spec):
        '''
        Render self.data as a string

        Parameters
        ----------
        fmt : string
            name of format to be used
        spec: dict
            dictionary of formatting options
        Returns
        -------
        string
        '''
        if self.formatterName is not None:
            formatter = _formatDict[self.formatterName]
            formatted_item = formatter[fmt](self.data, spec)
            assert formatted_item is not None, ("Formatter " + str(type(formatter[fmt]))
                                              + " returned None for item = " + str(self.data))
            return formatted_item
        else:
            if self.data.get_value() is not None:
                return str(self.data)
            else:
                raise ValueError("Unformatted None in Cell")

    def render(self, fmt, spec):
        '''
        Render full cell as a string

        Parameters
        ----------
        fmt : string
            name of format to be used
        spec: dict
            dictionary of formatting options
        Returns
        -------
        string
        '''
        format_cell   = _convertDict[fmt]['cell'] # Function for rendering a cell in the format "fmt"
        formattedData = self._render_data(fmt, spec)

        return format_cell(formattedData, self.label, spec)
