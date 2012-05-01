import logging
import json
import decimal
import copy
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict

__all__ = [
    "AggregationBrowser",
    "Cell",
    "Cut",
    "PointCut",
    "RangeCut",
    "SetCut",
    "AggregationResult",
    "cuts_from_string",
    "string_from_cuts",
    "string_from_path",
    "path_from_string"
]

class AggregationBrowser(object):
    """Class for browsing data cube aggregations

    :Attributes:
      * `cube` - cube for browsing

    """

    def __init__(self, cube):
        super(AggregationBrowser, self).__init__()

        if not cube:
            raise AttributeError("No cube given for aggregation browser")

        self.cube = cube

    def full_cube(self):
        return Cell(self.cube)

    def dimension_object(self, dimension):
        """Helper function to return proper dimension object as a subclass of Dimension.

        .. Warning::

            Depreciated. Use :meth:`cubes.Cube.dimension`

        :Arguments:
            * `dimension` - a dimension object or a string, if it is a string, then dimension
              object is retrieved from cube
        """

        if type(dimension) == str:
            return self.cube.dimension(dimension)
        else:
            return dimension

    def aggregate(self, cell, measures = None, drilldown = None, **options):
        """Return aggregate of a cell.

        Subclasses of aggregation browser should implement this method.

        :Attributes:

            * `drilldown` - dimensions and levels through which to drill-down, default `None`
            * `measures` - list of measures to be aggregated. By default all measures are
              aggregated.
            
        Drill down can be specified in two ways: as a list of dimensions or as a dictionary. If it
        is specified as list of dimensions, then cell is going to be drilled down on the next
        level of specified dimension. Say you have a cell for year 2010 and you want to drill
        down by months, then you specify ``drilldown = ["date"]``.
        
        If `drilldown` is a dictionary, then key is dimension or dimension name and value is last
        level to be drilled-down by. If the cell is at `year` level and drill down is: ``{
        "date": "day" }`` then both `month` and `day` levels are added.
        
        If there are no more levels to be drilled down, an exception is raised. Say your model has
        three levels of the `date` dimension: `year`, `month`, `day` and you try to drill down by
        `date` then ``ValueError`` will be raised.
        
        Retruns a :class:AggregationResult object.
        """
        raise NotImplementedError
        
    # def crosstab(self, cell, measures, drilldown, rows = None, columns = None, **options):
    #     """Aggregate facts and return cross-table. Calls `aggregate()` to get results then
    #     transforms the `AggregationResult` into a cross-tab.
    # 
    #     :Parameters:
    #         * cell - cell to be aggregated
    #         * rows - list of dimensions to be put on rows
    #         * columns - list of dimensions to be put on columns
    #     """
    #     raise NotImplementedError("cross tab is under development, body of this function should be considered as development notes")
    #     
    #     drilldown = []
    # 
    #     if rows:
    #         for dim in rows:
    #             dim = self.cube.dimension(dim)

    def facts(self, cell, **options):
        """Return an iterable object with of all facts within cell"""
        
        raise NotImplementedError

    def fact(self, key):
        """Returns a single fact from cube specified by fact key `key`"""
        raise NotImplementedError

    def values(self, cell, dimension, depth=None, paths=None, hierarchy=None, **options):
        """Return values for `dimension` with level depth `depth`. If `depth` is ``None``, all
        levels are returned.
        
        .. note::
            
            Some backends might support only default hierarchy. 
        """
        raise NotImplementedError
        
    def report(self, cell, report):
        """Creates multiple outputs specified in the `report`.
        
        `report` is a dictionary with multiple aggregation browser queries. Keys are custom names
        of queries which requestor can later use to retrieve respective query result. Values are
        dictionaries specifying single query arguments. Each query should contain at least
        one required value ``query`` which contains name of the query function: ``aggregate``,
        ``facts``, ``fact`` or ``values``. Rest of values are function specific, please refer to
        the respective function documentation for more information.
        
        Result is a dictionary where keys wil lbe the query names specified in report
        specification and values will be result values from each query call.

        This method provides convenient way to perform multiple common queries at once, for example
        you might want to have always on a page: total transaction count, total transaction amount,
        drill-down by year and drill-down by transaction type.

        *Roll-up*
        
        Report queries might contain ``rollup`` specification which will result in "rolling-up"
        one or more dimensions to desired level. This functionality is provided for cases when you
        would like to report at higher level of aggregation than the cell you provided is in.
        It works in similar way as drill down in :meth:`AggregationBrowser.aggregate` but in
        the opposite direction (it is like ``cd ..`` in a UNIX shell).
        
        Example: You are reporting for year 2010, but you want to have a bar chart with all years.
        You specify rollup::

            ...
            "rollup": "date",
            ...
        
        Roll-up can be:
        
            * a string - single dimension to be rolled up one level
            * an array - list of dimension names to be rolled-up one level
            * a dictionary where keys are dimension names and values are levels to be rolled up-to
        
        *Future*
        
        In the future there might be optimisations added to this method, therefore it will become
        faster than subsequent separate requests. Also when used with Slicer OLAP service server
        number of HTTP call overhead is reduced.
        """
        
        report_result = {}
        
        for result_name, report_query in report.items():
            query = report_query.get("query")
            if not query:
                raise KeyError("No report query for '%s'" % result_name)
                
            args = dict(report_query)
            del args["query"]
            
            # Note: we do not just convert name into function from symbol for possible future
            # more fine-tuning of queries as strings

            # Handle rollup
            rollup = report_query.get("rollup")
            if rollup:
                query_cell = cell.rollup(rollup)
            else:
                query_cell = cell

            if query == "aggregate":
                result = self.aggregate(query_cell, **args)
            elif query == "facts":
                result = self.facts(query_cell, **args)
            elif query == "fact":
                # Be more tolerant: by default we want "key", but "id" might be common
                key = args.get("key")
                if not key:
                    key = args.get("id")
                result = self.fact(key)
            elif query == "values":
                result = self.values(query_cell, **args)
            elif query == "drilldown":
                raise NotImplementedError("Drill-down queries are not yet implemented")
            else:
                raise KeyError("Unknown report query '%s' for '%s'" % (query, result_name))

            report_result[result_name] = result
            
        return report_result
        
        
class Cell(object):
    """Part of a cube determined by slicing dimensions. Immutable object."""
    def __init__(self, cube=None, cuts=[]):
        self.cube = cube
        self.cuts = cuts

    def slice(self, dimension, path):
        """Create another cell by slicing receiving cell through `dimension` at `path`.
        Receiving object is not modified. If cut with dimension exists it is replaced with new one.
        If path is empty list or is none, then cut for given dimension is removed.

        Example::

            full_cube = Cell(cube)
            contracts_2010 = full_cube.slice("date", [2010])

        Returns: new derived cell object.
        """
        dimension = self.cube.dimension(dimension)
        cuts = self._filter_dimension_cuts(dimension, exclude=True)
        if path:
            cut = PointCut(dimension, path)
            cuts.append(cut)
        return Cell(cube=self.cube, cuts=cuts)

    def drilldown(self, dimension, value):
        """Create another cell by drilling down `dimension` next level on
        current level's key `value`.

        Example::

            cell = cubes.Cell(cube)
            cell = cell.drilldown("date", 2010)
            cell = cell.drilldown("date", 1)
            
        is equivalent to:
        
            cut = cubes.PointCut("date", [2010, 1])
            cell = cubes.Cell(cube, [cut])

        Reverse operation is ``cubes.rollup("date")``
        
        Works only if the cut for dimension is `PointCut`. Otherwise the
        behaviour is undefined.

        Returns: new derived cell object.
        """
        dimension = self.cube.dimension(dimension)
        dim_cut = self.cut_for_dimension(dimension)

        old_path = dim_cut.path if dim_cut else []
        new_cut = PointCut(dimension, old_path + [value])
        
        cuts = [cut for cut in self.cuts if cut is not dim_cut]
        cuts.append(new_cut)

        return Cell(cube=self.cube, cuts=cuts)

    # def cut(self, cuts):
    #     """Cretes another cell by cutting with multiple cuts. `cut` can be a :class:`cubes.Cut`
    #     subclass instance or list of such instances."""
    #     
    # raise NotImplementedError()
            

    def multi_slice(self, cuts):
        """Create another cell by slicing through multiple slices. `cuts` can be list or a dictionry.
        If it is a list, it should be a list of two item tuples where first item is a dimension, second
        item is a dimension cut path. If `cuts` is a dictionary, then keys are dimensions, values are
        cut paths.

        See :meth:`Cell.slice` for more information about slicing."""

        cell = self

        if type(cuts) == dict:
            for dim, path in cuts.items():
                cell = cell.slice(dim, path)
        elif type(cuts) == list or type(cuts) == tuple:
            for dim, path in cuts:
                cell = cell.slice(dim, path)
        else:
            raise TypeError("Cuts for multi_slice sohuld be a list or a dictionary, is '%s'" \
                                % cuts.__class__)

        return cell

    def cut_for_dimension(self, dimension):
        """Return first found cut for given `dimension`"""
        dimension = self.cube.dimension(dimension)

        cut_dimension = None
        for cut in self.cuts:
            cut_dimension = self.cube.dimension(cut.dimension)

            if cut_dimension == dimension:
                return cut

        return None

    def rollup_dim(self, dimension, level=None):
        """Rolls-up cell - goes one or more levels up through dimension
        hierarchy. If there is no level to go up (we are at the top level),
         then the cut is removed.
         
         Returns new cell object.

        .. note::

                Only default hierarchy is currently supported.
        """

        # FIXME: make this the default roll-up
        # Reason:
        #     * simpler to use
        #     * can be used more nicely in Jinja templates

        dimension = self.cube.dimension(dimension)
        dim_cut = self.cut_for_dimension(dimension)

        if not dim_cut:
            return copy.copy(self)
            # raise ValueError("No cut to roll-up for dimension '%s'" % dimension.name)
        if type(dim_cut) != PointCut:
            raise NotImplementedError("Only PointCuts are currently supported for "
                                      "roll-up (rollup dimension: %s)" % dimension.name)

        cuts = [cut for cut in self.cuts if cut is not dim_cut]

        hier = dimension.default_hierarchy
        rollup_path = hier.rollup(dim_cut.path, level)

        # If the rollup path is empty, we are at the top level therefore we
        # are removing the cut for the dimension.

        if rollup_path:
            new_cut = PointCut(dimension, rollup_path)
            cuts.append(new_cut)

        return Cell(cube=self.cube, cuts=cuts)

    def rollup(self, rollup):
        """Rolls-up cell - goes one or more levels up through dimension hierarchy. It works in
        similar way as drill down in :meth:`AggregationBrowser.aggregate` but in the opposite
        direction (it is like ``cd ..`` in a UNIX shell).
        
        Roll-up can be:
        
            * a string - single dimension to be rolled up one level
            * an array - list of dimension names to be rolled-up one level
            * a dictionary where keys are dimension names and values are levels to be rolled up-to

        .. note::
            
                Only default hierarchy is currently supported.
        """

        # FIXME: rename this to something like really_complex_rollup :-)
        # Reason:
        #     * see reasons above for rollup_dim()
        #     * used only by Slicer server

        cuts = OrderedDict()
        for cut in self.cuts:
            dim = self.cube.dimension(cut.dimension)
            cuts[dim.name] = cut

        new_cuts = []

        # If it is a string, handle it as list of single string
        if isinstance(rollup, basestring):
            rollup = [rollup]

        if type(rollup) == list or type(rollup) == tuple:
            for dim_name in rollup:
                cut = cuts.get(dim_name)
                if cut is None:
                    continue
                #     raise ValueError("No cut to roll-up for dimension '%s'" % dim_name)
                if type(cut) != PointCut:
                    raise NotImplementedError("Only PointCuts are currently supported for "
                                              "roll-up (rollup dimension: %s)" % dim_name)

                dim = self.cube.dimension(cut.dimension)
                hier = dim.default_hierarchy
                
                rollup_path = hier.rollup(cut.path)
                
                cut = PointCut(cut.dimension, rollup_path)
                new_cuts.append(cut)
                
        elif isinstance(self.drilldown, dict):
            for (dim_name, level_name) in rollup.items():
                cut = cuts[dim_name]
                if not cut:
                    raise ValueError("No cut to roll-up for dimension '%s'" % dim_name)
                if type(cut) != PointCut:
                    raise NotImplementedError("Only PointCuts are currently supported for "
                                              "roll-up (rollup dimension: %s)" % dim_name)

                dim = selfcube.dimension(cut.dimension)
                hier = dim.default_hierarchy
                
                rollup_path = hier.rollup(cut.path, level_name)
                
                cut = PointCut(cut.dimension, rollup_path)
                new_cuts.append(cut)
        else:
            raise TypeError("Rollup is of unknown type: %s" % self.drilldown.__class__)
        
        cell = Cell(cube=self.cube, cuts=new_cuts)
        return cell

    def level_depths(self):
        """Returns a dictionary of dimension names as keys and level depths
        (index of deepest level)."""
        
        # TODO: should accept hierarchies
        
        levels = {}
        
        for cut in self.cuts:
            level = cut.level_depth()
            dim = self.cube.dimension(cut.dimension)
            dim_name = str(dim)

            levels[dim_name] = max(level, levels.get(dim_name))

        return levels
    
    def _filter_dimension_cuts(self, dimension, exclude=False):
        dimension = self.cube.dimension(dimension)
        cuts = []
        for cut in self.cuts:
            if (exclude and cut.dimension != dimension) \
                    or (not exclude and cut.dimension == dimension):
                cuts.append(cut)
        return cuts

    def __eq__(self, other):
        """cells are considered equal if:
            * they refer to the same cube
            * they have same set of cuts (regardless of their order)
        """

        if self.cube != other.cube:
            return False
        elif len(self.cuts) != len(other.cuts):
            return False

        for cut in self.cuts:
            if cut not in other.cuts:
                return False

        return True

    def __ne__(self, other):
        return not self.__eq__(other)
        
    def to_str(self):
        """Return string representation of the cell by using standard cuts-to-string conversion."""
        return string_from_cuts(self.cuts)

    def __str__(self):
        """Return string representation of the cell by using standard cuts-to-string conversion."""
        return self.to_str()

CUT_STRING_SEPARATOR = '|'
DIMENSION_STRING_SEPARATOR = ':'
PATH_STRING_SEPARATOR = ','
RANGE_CUT_SEPARATOR = '-'
SET_CUT_SEPARATOR = '+'

"""
point: date:2004
range: date:2004-2010
set ?1 : date:2004+2010+2011,04+
set ?2 : date:[2004;2010;2033,04]

"""

def cuts_from_string(string):
    """Return list of cuts specified in `string`. You can use this function to parse cuts encoded
    in a URL.
    
    Examples::

        date:2004
        date:2004,1
        date:2004,1|class=5
        date:2004,1,1|category:5,10,12|class:5

    Grammar::
    
        <list> ::= <cut> | <cut> '|' <list>
        <cut> ::= <dimension> ':' <path>
        <dimension> ::= <identifier>
        <path> ::= <value> | <value> ',' <path>
        
    The characters '|', ':' and ',' are configured in `CUT_STRING_SEPARATOR`,
    `DIMENSION_STRING_SEPARATOR`, `PATH_STRING_SEPARATOR` respectively.
    """
    
    if not string:
        return []
    
    cut_strings = string.split(CUT_STRING_SEPARATOR)

    cuts = []
    
    for cut_string in cut_strings:
        (dimension_name, path_string) = cut_string.split(DIMENSION_STRING_SEPARATOR)
        
        path = path_string.split(PATH_STRING_SEPARATOR)
        if not path:
            path = []
        cut = PointCut(dimension_name, path)
        cuts.append(cut)
        
    return cuts

def string_from_cuts(cuts):
    """Returns a string represeting cuts. String can be used in URLs"""
    strings = [str(cut) for cut in cuts]
    string = CUT_STRING_SEPARATOR.join(strings)
    return string

def string_from_path(path):
    """Returns a string representing dimension path."""
    
    # FIXME: do some escaping or something like URL encoding
    path = [unicode(s) if s is not None else "" for s in path]
    string = PATH_STRING_SEPARATOR.join(path)
    return string
    
def path_from_string(string):
    """Returns a dimension path from string"""
    
    # FIXME: do some un-escaping when escaping in string_from_path is implemented
    path = string.split(PATH_STRING_SEPARATOR)
    path = [v if v != "" else None for v in path]
    return path

class Cut(object):
    def __init__(self, dimension):
        self.dimension = dimension

    def to_dict(self):
        """Returns dictionary representation fo the receiver. The keys are:
        `dimension`."""
        d = {"dimension": self.dimension.name}
        return d
        
class PointCut(Cut):
    """Object describing way of slicing a cube (cell) through point in a dimension"""

    def __init__(self, dimension, path):
        super(PointCut, self).__init__(dimension)
        self.path = path

    def to_dict(self):
        """Returns dictionary representation of the receiver. The keys are:
        `dimension`, `type`=``point`` and `path`."""
        d = super(PointCut, self).to_dict()
        d["type"] = "point"
        d["path"] = self.path
        return d
        
    def level_depth(self):
        """Returns index of deepest level."""
        return len(self.path)

    def __str__(self):
        """Return string representation of point cut, you can use it in URLs"""
        path_str = string_from_path(self.path)
        
        if type(self.dimension) == str or type(self.dimension) == unicode:
            dim_name = self.dimension
        else:
            dim_name = self.dimension.name
            
        string = dim_name + DIMENSION_STRING_SEPARATOR + path_str
        
        return string        

    def __repr__(self):
        if isinstance(self.dimension, basestring):
            dim_name = self.dimension
        else:
            dim_name = self.dimension.name

        return '{"cut": "%s", "dimension":"%s", "path": "%s"}' % ("PointCut", dim_name, self.path)

    def __eq__(self, other):
        if self.dimension != other.dimension:
            return False
        elif self.path != other.path:
            return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

class RangeCut(Cut):
    """Object describing way of slicing a cube (cell) between two points of a dimension that
    has ordered points. For dimensions with unordered points behaviour is unknown."""

    def __init__(self, dimension, from_path, to_path):
        super(RangeCut, self).__init__(dimension)
        self.from_path = from_path
        self.to_path = to_path

    def to_dict(self):
        """Returns dictionary representation of the receiver. The keys are:
        `dimension`, `type`=``range``, `from` and `to` paths."""
        d = super(RangeCut, self).to_dict()
        d["type"] = "range"
        d["from"] = self.from_path
        d["to"] = self.to_path
        return d

    def level_depth(self):
        """Returns index of deepest level which is equivalent to the longest
        path."""
        return max(len(self.from_path), len(self.to_path))
    
    def __str__(self):
        """Return string representation of point cut, you can use it in URLs"""
        if self.from_path:
            from_path_str = string_from_path(self.from_path)
        else:
            from_path_str = string_from_path([])
        if self.to_path:
            to_path_str = string_from_path(self.to_path)
        else:
            to_path_str = string_from_path([])

        if type(self.dimension) == str or type(self.dimension) == unicode:
            dim_name = self.dimension
        else:
            dim_name = self.dimension.name

        range_stsr = from_path_str + RANGE_CUT_SEPARATOR + to_path_str
        string = dim_name + DIMENSION_STRING_SEPARATOR + range_str

        return string        

    def __repr__(self):
        if type(self.dimension) == str:
            dim_name = self.dimension
        else:
            dim_name = self.dimension.name

        return '{"cut": "%s", "dimension":"%s", "from": "%s", "to": "%s"}' % \
                    ("RangeCut", dim_name, self.from_path, self.to_path)

    def __eq__(self, other):
        if self.dimension != other.dimension:
            return False
        elif self.from_path != other.from_path:
            return False
        elif self.to_path != other.to_path:
            return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)
        
class SetCut(Cut):
    """Object describing way of slicing a cube (cell) between two points of a dimension that
    has ordered points. For dimensions with unordered points behaviour is unknown."""

    def __init__(self, dimension, paths):
        super(SetCut, self).__init__(dimension)
        self.paths = paths

    def to_dict(self):
        """Returns dictionary representation of the receiver. The keys are:
        `dimension`, `type`=``range`` and `set` as a list of paths."""
        d = super(SetCut, self).to_dict()
        d["type"] = "set"
        d["paths"] = paths
        return d

    def level_depth(self):
        """Returns index of deepest level which is equivalent to the longest
        path."""
        return max([len(path) for path in self.paths])

    def __str__(self):
        """Return string representation of set cut, you can use it in URLs"""
        path_strings = []
        for path in self.paths:
            path_strings.append(string_from_path(path))

        if type(self.dimension) == str or type(self.dimension) == unicode:
            dim_name = self.dimension
        else:
            dim_name = self.dimension.name

        set_string = SET_CUT_SEPARATOR.join(path_strings)
        string = dim_name + DIMENSION_STRING_SEPARATOR + set_string

        return string        

    def __repr__(self):
        if type(self.dimension) == str:
            dim_name = self.dimension
        else:
            dim_name = self.dimension.name

        return '{"cut": "%s", "dimension":"%s", "paths": "%s"}' % \
                    ("SetCut", dim_name, self.paths)

    def __eq__(self, other):
        if self.dimension != other.dimension:
            return False
        elif self.paths != other.paths:
            return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

class AggregationResult(object):
    """Result of aggregation or drill down.
    
    :Attributes:
        * summary - dictionary of summary row fields
        * drilldown - list of drilled-down cells
        * remainder - summary of remaining cells (not yet implemented)
        * total_cell_count - number of total cells in drill-down (after limit, before pagination)
    
    """
    def __init__(self):
        super(AggregationResult, self).__init__()
        self.summary = {}
        self.drilldown = {}
        self.remainder = {}
        self.total_cell_count = None
    

    def as_dict(self):
        """Depreciated, use to_dict instead. """
        # FIXME: remove this
        raise DeprecationWarning
        return self.to_dict()
        
    def to_dict(self):
        """Return dictionary representation of the aggregation result. Can be
        used for JSON serialisation."""
        
        d = {}
        
        d["summary"] = self.summary
        d["drilldown"] = self.drilldown
        d["remainder"] = self.remainder
        d["total_cell_count"] = self.total_cell_count
        
        return d

    def as_json(self):
        # FIXME: Eiter depreciate this or move it into backend. Also provide option for iterable
        # result
        
        def default(o):
            if type(o) == decimal.Decimal:
                return float(o)
            else:
                return JSONEncoder.default(self, o)

        encoder = json.JSONEncoder(default = default, indent = 4)
        json_string = encoder.encode(self.as_dict())

        return json_string
