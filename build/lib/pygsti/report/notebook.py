""" Defines the Notebook class """
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

from .notebookcell import NotebookCell

import os   as _os
import json as _json
import webbrowser as _browser
import textwrap as _textwrap

from subprocess import call as _call

class Notebook(object):
    '''
    Python representation of an IPython notebook
    '''
    DefaultTemplate = 'Empty.ipynb'

    def __init__(self, cells=None, notebookTextFiles=None):
        '''
        Create an IPython notebook from a list of cells, list of notebookTextFiles, or both.
        
        Parameters
        ----------
        cells : list, optional
            List of NotebookCell objects
        notebookTextFiles : list, optional
            List of filenames (text files with '@@markdown' or '@@code' designating cells)
        '''
        if cells is None:
            cells = []
        self.cells = cells
        if notebookTextFiles is not None:
            for filename in notebookTextFiles:
                self.add_notebook_text_file(filename)

    def to_json_dict(self, templateFilename=DefaultTemplate):
        '''
        Using an existing (usually empty) notebook as a template, generate the json for a new notebook.

        Parameters
        ----------
        templateFilename : str, optional
            Name of an existing notebook file to build from
        '''
        templateFilename = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)),
                                          'templates', templateFilename )
        with open(templateFilename, 'r') as infile:
            notebookDict = _json.load(infile)
        notebookDict['cells'].extend([c.to_json_dict() for c in self.cells])
        return notebookDict

    def save_to(self, outputFilename, templateFilename=DefaultTemplate):
        '''
        Save this class to a file as a jupyter notebook

        Parameters
        ----------
        outputFilename : str
            File to save the output jupyter notebook to

        templateFilename : str, optional
            Name of an existing notebook file to build from
        '''
        jsonDict = self.to_json_dict(templateFilename)
        with open(outputFilename, 'w') as outfile:
            _json.dump(jsonDict, outfile)

    def add(self, cell):
        '''
        Add a cell to the notebook

        Parameters
        ----------
        cell : NotebookCell object
        '''
        self.cells.append(cell)

    def add_block(self, block, cellType):
        '''
        Add a block to the notebook

        Parameters
        ----------
        block : str
            block of either code or markdown
        cellType : str
            tag for the cell. Either 'code' or 'markdown'
        '''
        lines = block.splitlines(True)
        self.cells.append(NotebookCell(cellType, lines))

    def add_file(self, filename, cellType):
        '''
        Read in a cell block from a file

        Parameters
        ----------
        filename: str
            filename containing either code or markdown
        cellType : str
            tag for the cell. Either 'code' or 'markdown'
        '''
        with open(filename, 'r') as infile:
            block = infile.read()
        self.add_block(block, cellType)

    def add_code(self, block):
        '''
        Add code to notebook

        Parameters
        ----------
        block : str
            Block of python code
        '''
        self.add_block(_textwrap.dedent(block), 'code')

    def add_markdown(self, block):
        '''
        Add markdown to notebook

        Parameters
        ----------
        block : str
            Block of markdown (or HTML) 
        '''
        self.add_block(block, 'markdown')

    def add_code_file(self, filename):
        '''
        Add a code file to the notebook 

        Parameters
        ----------
        filename : str
            name of file containing python code
        '''
        self.add_file(filename, 'code')

    def add_markdown_file(self, filename):
        '''
        Add a markdown file to the notebook 

        Parameters
        ----------
        filename : str
            name of file containing markdown 
        '''
        self.add_file(filename, 'markdown')

    def add_notebook_text(self, text):
        '''
        Add custom formatted text to the notebook
        Text contains both python and markdown, with
        cells differentiated by @@code and @@markdown tags.
        At least one cell tag must be present for the file to be correctly parsed

        Parameters
        ----------
        text : str
            notebook formatted text 
        '''
        assert '@@' in text, 'At least one cell tag must be present for the file to be correctly parsed'
        for block in text.split('@@'):
            if block == '':
                continue
            if block.startswith('code'):
                block = block.replace('code', '', 1)
                block = block.strip('\n')
                '''
                TODO: Auto-move comments to markdown
                lines = []
                for line in block.splitlines():
                    if '#' in line:
                        i = line.index('#')
                '''
                self.add_code(block)
            elif block.startswith('markdown'):
                block = block.replace('markdown', '', 1)
                block = block.strip('\n')
                self.add_markdown(block)
            else:
                raise ValueError('Invalid notebook text block heading:\n{}'.format(block))

    def add_notebook_text_file(self, filename):
        '''
        Add a custom formatted text file to the notebook
        Text file contains both python and markdown, with
        cells differentiated by @@code and @@markdown tags.
        At least one cell tag must be present for the file to be correctly parsed

        Parameters
        ----------
        filename : str
            name of file containing notebook formatted text 
        '''
        with open(filename, 'r') as infile:
            self.add_notebook_text(infile.read())

    def add_notebook_text_files(self, filenames):
        '''
        Add multiple notebook text files to the notebook, in order

        Parameters
        ----------
        filenames : list(str)
            names of file containing notebook formatted text 
        '''
        for filename in filenames:
            self.add_notebook_text_file(filename)

    def add_notebook_file(self, filename):
        '''
        Append an .ipynb file to this notebook

        Parameters
        ----------
        filename : str
            ipynb file to append 
        '''
        with open(filename, 'r') as infile:
            notebookDict = _json.load(infile)
        for cell in notebookDict['cells']:
            self.cells.append(NotebookCell(cell['cell_type'], cell['source']))

    def add_notebook_files(self, filenames):
        '''
        Add multiple notebook files to the notebook, in order

        Parameters
        ----------
        filenames : list(str)
            names of file containing ipynb json
        '''
        for filename in filenames:
            self.add_notebook_file(filename)

    def launch_new(self, outputFilename, templateFilename=DefaultTemplate):
        '''
        Save and then launch this notebook with a new jupyter server.  Note that
        this function waits to return until the notebook server exists, and so
        is difficult to work with.

        Parameters
        ----------
        outputFilename : str
            filename to save this notebook to
        templateFilename : str, optional
            filename to build this notebook from (see save_to)
        '''
        self.save_to(outputFilename, templateFilename)
        _call('jupyter notebook {}'.format(outputFilename), shell=True) #this waits for notebook to complete
        #_os.system('jupyter notebook {}'.format(outputFilename)) # same behavior as above
        #processid = _os.spawnlp(_os.P_NOWAIT, 'jupyter', 'notebook', _os.path.abspath(outputFilename)) #DOESN'T WORK
        #print("DB: spawned notebook %d!" % processid)

    def launch(self, outputFilename, templateFilename=DefaultTemplate, port='auto'):
        '''
        Save and then launch this notebook

        Parameters
        ----------
        outputFilename : str
            filename to save this notebook to
        templateFilename : str, optional
            filename to build this notebook from (see save_to)
        '''
        self.save_to(outputFilename, templateFilename)
        outputFilename = _os.path.abspath(outputFilename) #for path manips below

        from notebook import notebookapp
        servers = list(notebookapp.list_running_servers())
        for serverinfo in servers:
            rel = _os.path.relpath(outputFilename, serverinfo['notebook_dir'])
            if ".." not in rel: # notebook servers don't allow moving up directories
                if port == 'auto'or int(serverinfo['port']) == port:
                    url = _os.path.join( serverinfo['url'], 'notebooks', rel)
                    _browser.open(url); break
        else:
            print("No running notebook server found that is rooted above %s" %
                  outputFilename)
