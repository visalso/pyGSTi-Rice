""" Colormap and derived class definitions """
from __future__ import division, print_function, absolute_import, unicode_literals
#*****************************************************************
#    pyGSTi 0.9:  Copyright 2015 Sandia Corporation
#    This Software is released under the GPL license detailed
#    in the file "license.txt" in the top-level pyGSTi directory
#*****************************************************************

import numpy as _np
from scipy.stats import chi2 as _chi2

from ..baseobjs import smart_cached

@smart_cached
def _vnorm(x, vmin, vmax):
    #Perform linear mapping from [vmin,vmax] to [0,1]
    # (which is just a *part* of the full mapping performed)
    if _np.isclose(vmin,vmax): return _np.ma.zeros(x.shape,'d')
    return _np.clip( (x-vmin)/ (vmax-vmin), 0.0, 1.0)

@smart_cached
def as_rgb_array(colorStr):
    """ 
    Convert a color string, such as `"rgb(0,255,128)"` or `"#00FF88"`
    to a numpy array of length 3.
    """
    colorStr = colorStr.strip() #remove any whitespace                                                                           
    if colorStr.startswith('#') and len(colorStr) >= 7:
        r,g,b = colorStr[1:3], colorStr[3:5], colorStr[5:7]
        r = float(int(r,16))
        g = float(int(r,16))
        b = float(int(r,16))
        rgb = r,g,b                                                                          
    elif colorStr.startswith('rgb(') and colorStr.endswith(')'):
        tupstr = colorStr[len('rgb('):-1]
        rgb = [float(x) for x in tupstr.split(',')]
    elif colorStr.startswith('rgba(') and colorStr.endswith(')'):
        tupstr = colorStr[len('rgba('):-1]
        rgba = tupstr.split(',')
        rgb = [float(x)/256.0 for x in rgba[0:3]] + [float(rgba[3])]
    else:
        raise ValueError("Cannot convert colorStr = ", colorStr)
    return _np.array(rgb)


def interpolate_plotly_colorscale(plotly_colorscale, normalized_value):
    """
    Evaluates plotly colorscale at a particular value.

    This function linearly interpolates between the colors of a 
    Plotly colorscale.

    Parameters
    ----------
    plotly_colorscale : list
        A Plotly colorscale (list of `[val, color]`) elements where
        `val` is a float between 0 and 1, and `color` is any acceptable
        Plotly color value (e.g. `rgb(0,100,255)`, `#0033FF`, etc.).

    normalized_value : float
        The value (between 0 and 1) to compute the color for.
    
    Returns
    -------
    str
        A string representation of the plotly color of the form `"rgb(R,G,B)"`.
    """
    for i,(val,color) in enumerate(plotly_colorscale[:-1]):
        next_val, next_color = plotly_colorscale[i+1]
        if val <= normalized_value < next_val:
            rgb = as_rgb_array(color)
            next_rgb = as_rgb_array(next_color)
            v = (normalized_value - val) / (next_val - val)
            interp_rgb = (1.0-v)*rgb + v*next_rgb
            break
    else:
        val,color = plotly_colorscale[-1]
        assert(val <= normalized_val)
        interp_rgb = as_rgb_array(color)
    return 'rgb(%d,%d,%d)' % ( int(round(interp_rgb[0])),
                               int(round(interp_rgb[1])),
                               int(round(interp_rgb[2])) )



class Colormap(object):
    """ 
    A color map which encapsulates a plotly colorscale with a normalization,
    and contains additional functionality such as the ability to compute the
    color corresponding to a particular value and extract matplotlib
    colormap and normalization objects.
    """
    def __init__(self, rgb_colors, hmin, hmax):
        """
        Create a new Colormap.

        Parameters
        ----------
        rgb_colors : list
            A list of `[val, (R,G,B)]` elements where `val` is a floating point
            number between 0 and 1 (plotly maps the post-'normalized' data linearly
            onto the interval [0,1] before mapping to a color), and `R`,`G`,and `B`
            are red, green, and blue floating point values in [0,1].  The color will
            be interpolated between the different "point" elements in this list.

        hmin, hmax : float
            The minimum and maximum post-normalized values to be used for the
            heatmap.  That is, `hmin` is the value (after `normalize` has been
            called) assigned the "0.0"-valued color in `rgb_colors` and `hmax`
            similarly for the "1.0"-valued color.
        """

        self.rgb_colors = rgb_colors
        self.hmin = hmin
        self.hmax = hmax
        
    def _brightness(self,R,G,B):
        # Perceived brightness calculation from http://alienryderflex.com/hsp.html
        return _np.sqrt(0.299*R**2 + 0.587*G**2 + 0.114*B**2)

    def normalize(self, value):
        """ 
        Normalize value as it would be prior to linearly interpolating
        onto the [0,1] range of the color map.

        In this case, no additional normalization is performed, so this 
        function just returns `value`.
        """
        #Default behavior for derived classes: no "normalization" is done
        # here because plotly automatically maps (linearly) the interval
        # between a heatmap's zmin and zmax to [0,1].
        return value


    def besttxtcolor(self, value):
        """ 
        Return the better text color, "black" or "white", given an
        un-normalized `value`.

        Parameters
        ----------
        value : float
            An un-normalized value.

        Returns
        -------
        str
        """
        z = _vnorm( self.normalize(value), self.hmin, self.hmax) # norm_value <=> color
        for i in range(1,len(self.rgb_colors)):
            if z < self.rgb_colors[i][0]:
                z1,rgb1 = self.rgb_colors[i-1]
                z2,rgb2 = self.rgb_colors[i]
                alpha = (z-z1)/(z2-z1)
                R,G,B = [rgb1[i] + alpha*(rgb2[i]-rgb1[i]) for i in range(3)]
                break
        else: R,G,B = self.rgb_colors[-1][1] #just take the final color

        # Perceived brightness calculation from http://alienryderflex.com/hsp.html
        P = self._brightness(R,G,B)
        #print("DB: value = %f (%s), RGB = %f,%f,%f, P=%f (%s)" % (value,z,R,G,B,P,"black" if 0.5 <= P else "white"))
        return "black" if 0.5 <= P else "white"

    def get_colorscale(self):
        """
        Construct and return the plotly colorscale of this color map.
        
        Returns
        -------
        list 
            A list of `[float_value, "rgb(R,G,B)"]` items.
        """
        plotly_colorscale = [ [z, 'rgb(%d,%d,%d)' %
                               (round(r*255),round(g*255),round(b*255))]
                              for z,(r,g,b) in self.rgb_colors ]
        return plotly_colorscale

    def get_color(self, value):
        """
        Retrieves the color at a particular colormap value.
    
        This function linearly interpolates between the colors of a 
        this colormap's color scale
    
        Parameters
        ----------
        value : float
            The value (before normalization) to compute the color for.
        
        Returns
        -------
        str
            A string representation of the plotly color of the form `"rgb(R,G,B)"`.
        """
        normalized_value = self.normalize(value)

        for i,(val,color) in enumerate(self.rgb_colors[:-1]):
            next_val, next_color = self.rgb_colors[i+1]
            if val <= normalized_value < next_val:
                rgb = _np.array( color ) # r,g,b values as array
                next_rgb = _np.array(next_color)
                v = (normalized_value - val) / (next_val - val)
                interp_rgb = (1.0-v)*rgb + v*next_rgb
                break
        else:
            val,color = self.rgb_colors[-1]
            assert(val <= normalized_value)
            interp_rgb = _np.array(color)
        return 'rgb(%d,%d,%d)' % ( int(round(interp_rgb[0]*255)),
                                   int(round(interp_rgb[1]*255)),
                                   int(round(interp_rgb[2]*255)) )



    def get_matplotlib_norm_and_cmap(self):
        """
        Creates and returns normalization and colormap 
        classes for matplotlib heatmap plots.

        Returns
        -------
        norm, cmap
        """
        from .mpl_colormaps import mpl_make_linear_norm as _mpl_make_linear_norm
        from .mpl_colormaps import mpl_make_linear_cmap as _mpl_make_linear_cmap
        norm = _mpl_make_linear_norm(self.hmin, self.hmax)
        cmap = _mpl_make_linear_cmap(self.rgb_colors)
        return norm, cmap


    

class LinlogColormap(Colormap):
    """
    Colormap which combines a linear grayscale portion with a logarithmic
    color (by default red) portion.  The transition between these occurs
    at a point based on a percentile of chi^2 distribution.
    """
    def __init__(self, vmin, vmax, n_boxes, pcntle, dof_per_box, color="red"):
        """
        Create a new LinlogColormap.

        Parameters
        ----------
        vmin, vmax : float
            The min and max values of the data being colormapped.

        n_boxes : int
            The number of boxes in the plot this colormap is being used with,
            so that `pcntle` gives a percentage of the *worst* box being "red".
        
        pcntle : float
            A number between 0 and 1 giving the probability that the worst box
            in the plot will be red.  Typically a value of 0.05 is used.

        dof_per_box : int
            The number of degrees of freedom represented by each box, so the
            expected distribution of each box's values is chi^2_[dof_per_box].

        color : {"red","blue","green","cyan","yellow","purple"}
            the color to use for the non-grayscale part of the color scale.
        """
        self.N = n_boxes
        self.percentile = pcntle
        self.dof = dof_per_box
        hmin = 0  #we'll normalize all values to [0,1] and then
        hmax = 1  # plot.ly will map this range linearly to (also) [0,1]
                  # range of our (and every) colorscale.

        #Notes on statistics below:
        # consider random variable Y = max(X_i) and CDF of X_i's is F(x)
        # then CDF of Y is given by: P( Y <= y ) = P( max(X_i) <= y )
        # which is the probability that *all* X_i's are <= y, which equals
        # product( P(X_i <= y) ) = prod( F(y) ), so if i=1...n then
        # CDF of Y is F(y)^n.
        # Below, we need the inverse of the CDF:
        # x such that CDF(x) = given_percentage, so 
        # x such that F(x)^n = percentage, so
        # x such that F(x) = percentage^{1/n}
        # Our percentage = "1-percentile" and b/c (1-x)^{1/n} ~= 1 - x/n
        # we take the ppf at 1-percentile/N
        
        N = max(self.N,1) #don't divide by N == 0 (if there are no boxes)
        self.trans = _np.ceil(_chi2.ppf(1 - self.percentile / N, self.dof))
          # the linear-log transition point

        self.vmin = vmin
        self.vmax = max(vmax,self.trans) #so linear portion color scale ends at trans


        # Colors ranging from white to gray on [0.0, 0.5) and pink to red on
        # [0.5, 1.0] such that the perceived brightness of the pink matches the
        # gray.
        gray = (0.4,0.4,0.4)
        if color == "red":
            c = (0.77, 0.143, 0.146); mx = (1.0, 0, 0)
        elif color == "blue":
            c = (0,0,0.7); mx = (0,0,1.0)
        elif color == "green":
            c = (0.0, 0.483, 0.0); mx = (0, 1.0, 0)
        elif color == "cyan":
            c = (0.0, 0.46, 0.46); mx = (0.0, 1.0, 1.0)
        elif color == "yellow":
            c = (0.415, 0.415, 0.0); mx = (1.0, 1.0, 0)
        elif color == "purple":
            c = (0.72, 0.0, 0.72); mx = (1.0, 0, 1.0)
        else:
            raise ValueError("Unknown color: %s" % color)

        super(LinlogColormap, self).__init__(
            [ [0.0, (1.,1.,1.)], [0.499999999, gray],
              [0.5, c], [1.0, mx] ], hmin,hmax)


    @smart_cached
    def normalize(self, value):
        """ 
        Scale value to a value between self.hmin and self.hmax (heatmap endpoints).

        Parameters
        ----------
        value : float or ndarray

        Returns
        -------
        float or ndarray
        """
        #Safety stuff -- needed anymore? TODO
        if isinstance(value, _np.ma.MaskedArray) and value.count() == 0:
            # no unmasked elements, in which case a matplotlib bug causes the
            # __call__ below to fail (numpy.bool_ has no attribute '_mask')
            return_value = _np.ma.array( _np.zeros(value.shape),
                                         mask=_np.ma.getmask(value))
            # so just create a dummy return value with the correct size
            # that has all it's entries masked (like value does)
            if return_value.shape==(): return return_value.item()
            else: return return_value.view(_np.ma.MaskedArray)

        #deal with numpy bug in handling masked nan values (nan still gives
        # "invalid value" warnings/errors even when masked)
        if _np.ma.is_masked(value):
            value = _np.ma.array(value.filled(1e100),
                                 mask=_np.ma.getmask(value))

        lin_norm_value = _vnorm(value, self.vmin, self.vmax)
        norm_trans = _vnorm(self.trans, self.vmin, self.vmax)
        log10_norm_trans = _np.ma.log10(norm_trans)
        with _np.errstate(divide='ignore'):
            # Ignore the division-by-zero error that occurs when 0 is passed to
            # log10 (the resulting NaN is filtered out by the where and is
            # harmless).

            #deal with numpy bug in handling masked nan values (nan still gives
            # "invalid value" warnings/errors even when masked)
            if _np.ma.is_masked(lin_norm_value):
                lin_norm_value = _np.ma.array(lin_norm_value.filled(1e100),
                                              mask=_np.ma.getmask(lin_norm_value))

            if norm_trans == 1.0:
                #then transition is at highest possible normalized value (1.0)
                # and the call to greater(...) below will always be True.
                # To avoid the False-branch getting div-by-zero errors, set:
                log10_norm_trans = 1.0 # because it's never used.

            return_value = _np.ma.where(_np.ma.greater(norm_trans, lin_norm_value),
                                        lin_norm_value/(2*norm_trans),
                                        (log10_norm_trans -
                                         _np.ma.log10(lin_norm_value)) /
                                        (2*log10_norm_trans) + 0.5)

        if return_value.shape==():
            return return_value.item()
        else:
            return return_value.view(_np.ma.MaskedArray)

    def get_matplotlib_norm_and_cmap(self):
        """
        Creates and returns normalization and colormap 
        classes for matplotlib heatmap plots.

        Returns
        -------
        norm, cmap
        """
        from .mpl_colormaps import mpl_LinLogNorm as _mpl_LinLogNorm
        _, cmap = super(LinlogColormap, self).get_matplotlib_norm_and_cmap()
        norm = _mpl_LinLogNorm(self)
        cmap.set_bad('w',1)
        return norm, cmap                


class DivergingColormap(Colormap):
    """ A diverging color map """
    
    def __init__(self, vmin, vmax, midpoint=0.0, color="RdBu"):
        """
        Create a new DivergingColormap
        
        Parameters
        ----------
        vmin, vmax : float
            Min and max values of the data being colormapped.

        midpoint : float, optional
            The midpoint of the color scale.
        
        color : {"RdBu"}
            What colors to use.
        """
        hmin = vmin
        hmax = vmax
        self.midpoint = midpoint
        assert(midpoint == 0.0), "midpoint doesn't work yet!"

        if color == "RdBu": # blue -> white -> red
            rgb_colors = [ [0.0, (0.0,0.0,1.0)],
                           [0.5, (1.0,1.0,1.0)],
                           [1.0, (1.0,0.0,0.0)] ]
        else:
            raise ValueError("Unknown color: %s" % color)

        super(DivergingColormap, self).__init__(rgb_colors, hmin, hmax)

        #*Normalize* scratch
        #vmin, vmax, midpoint = self.vmin, self.vmax, self.midpoint
        #
        #is_scalar = False
        #if isinstance(value, float) or _compat.isint(value, int):
        #    is_scalar = True
        #result = _np.ma.array(value)
        #
        #if not (vmin < midpoint < vmax):
        #    raise ValueError("midpoint must be between maxvalue and minvalue.")
        #elif vmin == vmax:
        #    result.fill(0) # Or should it be all masked? Or 0.5?
        #elif vmin > vmax:
        #    raise ValueError("maxvalue must be bigger than minvalue")
        #else:
        #    # ma division is very slow; we can take a shortcut
        #    resdat = result.filled(0) #masked entries to 0 to avoid nans
        #
        #    #First scale to -1 to 1 range, than to from 0 to 1.
        #    resdat -= midpoint
        #    resdat[resdat>0] /= abs(vmax - midpoint)
        #    resdat[resdat<0] /= abs(vmin - midpoint)
        #
        #    resdat /= 2.
        #    resdat += 0.5
        #    result = _np.ma.array(resdat, mask=result.mask, copy=False)
        #
        #if is_scalar:
        #    result = float(result)
        #return result

        

class SequentialColormap(Colormap):
    """ A sequential color map """
    def __init__(self, vmin, vmax, color="whiteToBlack"):
        """
        Create a new SequentialColormap
        
        Parameters
        ----------
        vmin, vmax : float
            Min and max values of the data being colormapped.

        color : {"whiteToBlack", "blackToWhite"}
            What colors to use.
        """
        hmin = vmin
        hmax = vmax

        if color == "whiteToBlack":
            rgb_colors = [ [0, (1.,1.,1.)], [1.0, (0.0,0.0,0.0)] ]
        elif color == "blackToWhite":
            rgb_colors = [ [0, (0.0,0.0,0.0)], [1.0, (1.,1.,1.)] ]
        elif color == "whiteToBlue":
            rgb_colors = [ [0, (1.,1.,1.)], [1.0, (0.,0.,1.)] ]
        elif color == "whiteToRed":
            rgb_colors = [ [0, (1.,1.,1.)], [1.0, (1.,0.,0.)] ]
        else:
            raise ValueError("Unknown color: %s" % color)

        super(SequentialColormap, self).__init__(rgb_colors, hmin,hmax)

        #*Normalize* scratch
        #is_scalar = False
        #if isinstance(value, float) or _compat.isint(value, int):
        #    is_scalar = True
        #
        #result = _np.ma.array(value)
        #
        #if self.vmin == self.vmax:
        #    result.fill(0) # Or should it be all masked? Or 0.5?
        #elif self.vmin > self.vmax:
        #    raise ValueError("maxvalue must be bigger than minvalue")
        #else:
        #    resdat = result.filled(0) #masked entries to 0 to avoid nans
        #    resdat = _vnorm(resdat, self.vmin, self.vmax)
        #    result = _np.ma.array(resdat, mask=result.mask, copy=False)
        #
        #if is_scalar:
        #    result = result[0]
        #return result
        


class PiecewiseLinearColormap(Colormap):
    """ A piecewise-linear color map """
    
    def __init__(self, rgb_colors):
        """
        Create a new PiecewiseLinearColormap
        
        Parameters
        ----------
        rgb_colors : list
            A list of `[val, (R,G,B)]` elements where `val` is a floating point
            number (pre-normalization) of the value corresponding to the color
            given by `R`,`G`,and `B`: red, green, and blue floating point values
            in [0,1].  The color will be interpolated between the different "point"
            elements in this list.
        """
        hmin = min([v for v,rgb in rgb_colors])
        hmax = max([v for v,rgb in rgb_colors])
        def norm(x): #normalize color "point" values to [0,1] interval
            return (x-hmin)/(hmax-hmin) if (hmax > hmin) else 0.0

        norm_rgb_colors = [ [norm(val),rgb] for val,rgb in rgb_colors ]
        super(PiecewiseLinearColormap, self).__init__(norm_rgb_colors,hmin,hmax)
