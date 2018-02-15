#!/usr/bin/env python3.4
# coding: latin-1

# (c) Massachusetts Institute of Technology 2015-2017
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Table
-----

Make a table out of a statistic.  The table can then be exported.

.. object:: Statistic

    Which statistic to view.
    
.. object:: Rows

    Which variable to use for the rows

.. object:: Subrows

    Which variable to use for subrows.
    
.. object:: Columns

    Which variable to use for the columns.
    
.. object:: Subcolumns

    Which variable to use for the subcolumns.
    
.. object:: Export

    Export the table to a CSV file.

    
.. plot::
        
    import cytoflow as flow
    import_op = flow.ImportOp()
    import_op.tubes = [flow.Tube(file = "Plate01/RFP_Well_A3.fcs",
                                 conditions = {'Dox' : 10.0}),
                       flow.Tube(file = "Plate01/CFP_Well_A4.fcs",
                                 conditions = {'Dox' : 1.0})]
    import_op.conditions = {'Dox' : 'float'}
    ex = import_op.apply()
    
    ex2 = flow.ThresholdOp(name = 'Threshold',
                           channel = 'Y2-A',
                           threshold = 2000).apply(ex)
    

    ex3 = flow.ChannelStatisticOp(name = "ByDox",
                                  channel = "Y2-A",
                                  by = ['Dox', 'Threshold'],
                                  function = len).apply(ex2) 

    flow.TableView(statistic = ("ByDox", "len"),
                   row_facet = "Dox",
                   column_facet = "Threshold").plot(ex3)    

"""

import numpy as np
import pandas as pd

from traits.api import provides, Callable, Event, on_trait_change, Instance, Property
from traitsui.api import View, Item, Controller, VGroup, ButtonEditor, EnumEditor
from envisage.api import Plugin, contributes_to
from pyface.api import ImageResource, FileDialog, OK

from cytoflow import TableView
import cytoflow.utility as util

from cytoflowgui.subset import SubsetListEditor
from cytoflowgui.color_text_editor import ColorTextEditor
from cytoflowgui.ext_enum_editor import ExtendableEnumEditor
from cytoflowgui.view_plugins.i_view_plugin \
    import IViewPlugin, VIEW_PLUGIN_EXT, ViewHandlerMixin, PluginViewMixin, PluginHelpMixin
from cytoflowgui.util import DefaultFileDialog
from cytoflowgui.serialization import camel_registry, traits_repr, dedent

TableView.__repr__ = traits_repr

class TableHandler(ViewHandlerMixin, Controller):

    indices = Property(depends_on = "context.statistics, model.statistic, model.subset")
    levels = Property(depends_on = "context.statistics, model.statistic")

    def default_traits_view(self):
        return View(VGroup(
                    VGroup(Item('statistic',
                                editor = EnumEditor(name='handler.statistics_names'),
                                label = "Statistic"),
                           Item('row_facet',
                                editor = ExtendableEnumEditor(name='handler.indices',
                                                            extra_items = {"None" : ""}),
                                label = "Rows"),
                           Item('subrow_facet',
                                editor = ExtendableEnumEditor(name='handler.indices',
                                                            extra_items = {"None" : ""}),
                                label = "Subrows"),
                           Item('column_facet',
                                editor = ExtendableEnumEditor(name='handler.indices',
                                                            extra_items = {"None" : ""}),
                                label = "Columns"),
                           Item('subcolumn_facet',
                                editor = ExtendableEnumEditor(name='handler.indices',
                                                            extra_items = {"None" : ""}),
                                label = "Subcolumn"),
                           Item('export',
                                editor = ButtonEditor(label = "Export..."),
                                enabled_when = 'result is not None',
                                show_label = False),
                           label = "Table View",
                           show_border = False),
                    VGroup(Item('subset_list',
                                show_label = False,
                                editor = SubsetListEditor(conditions = "handler.levels")),
                           label = "Subset",
                           show_border = False,
                           show_labels = False),
                    Item('context.view_warning',
                         resizable = True,
                         visible_when = 'context.view_warning',
                         editor = ColorTextEditor(foreground_color = "#000000",
                                                 background_color = "#ffff99")),
                    Item('context.view_error',
                         resizable = True,
                         visible_when = 'context.view_error',
                         editor = ColorTextEditor(foreground_color = "#000000",
                                                  background_color = "#ff9191"))))
        
    # MAGIC: gets the value for the property indices
    def _get_indices(self):
        if not (self.context and self.context.statistics 
                and self.model.statistic in self.context.statistics):
            return []
        
        stat = self.context.statistics[self.model.statistic]
        data = pd.DataFrame(index = stat.index)
        
        if self.model.subset:
            data = data.query(self.model.subset)
            
        if len(data) == 0:
            return []       
        
        names = list(data.index.names)
        for name in names:
            unique_values = data.index.get_level_values(name).unique()
            if len(unique_values) == 1:
                data.index = data.index.droplevel(name)
        
        return list(data.index.names)
    
    # MAGIC: gets the value for the property 'levels'
    # returns a Dict(Str, pd.Series)
    
    def _get_levels(self):        
        if not (self.context and self.context.statistics 
                and self.model.statistic in self.context.statistics):
            return []
        
        stat = self.context.statistics[self.model.statistic]
        index = stat.index
        
        names = list(index.names)
        for name in names:
            unique_values = index.get_level_values(name).unique()
            if len(unique_values) == 1:
                index = index.droplevel(name)

        names = list(index.names)
        ret = {}
        for name in names:
            ret[name] = pd.Series(index.get_level_values(name)).sort_values()
            ret[name] = pd.Series(ret[name].unique())
            
        return ret
                    
    
class TablePluginView(PluginViewMixin, TableView):
    handler_factory = Callable(TableHandler)
    
    export = Event()
    
    # return the result for export
    result = Instance(pd.Series, status = True)
    
    def plot(self, experiment, plot_name = None, **kwargs):
        TableView.plot(self, experiment, **kwargs)
        self.result = experiment.statistics[self.statistic]
        
    def get_notebook_code(self, idx):
        view = TableView()
        view.copy_traits(self, view.copyable_trait_names())

        return dedent("""
        {repr}.plot(ex_{idx}{plot})
        """
        .format(repr = repr(view),
                idx = idx,
                plot = ", plot_name = " + repr(self.current_plot) if self.plot_names else ""))

    @on_trait_change('export')
    def _on_export(self):
        
        dialog = DefaultFileDialog(parent = None,
                                   action = 'save as', 
                                   default_suffix = "csv",
                                   wildcard = (FileDialog.create_wildcard("CSV", "*.csv") + ';' + #@UndefinedVariable  
                                               FileDialog.create_wildcard("All files", "*")))     #@UndefinedVariable  

        if dialog.open() != OK:
            return
 
        data = pd.DataFrame(index = self.result.index)
        data[self.result.name] = self.result   
        
        if self.subset:
            data = data.query(self.subset)
        
        names = list(data.index.names)
        for name in names:
            unique_values = data.index.get_level_values(name).unique()
            if len(unique_values) == 1:
                data.index = data.index.droplevel(name) 
                
        facets = [x for x in [self.row_facet, self.subrow_facet, 
                                      self.column_facet, self.subcolumn_facet] if x]
        
        if set(facets) != set(data.index.names):
            raise util.CytoflowViewError("Must use all the statistic indices as variables or facets: {}"
                                         .format(data.index.names))
            
        row_groups = data.index.get_level_values(self.row_facet).unique() \
                     if self.row_facet else [None]
                     
        subrow_groups = data.index.get_level_values(self.subrow_facet).unique() \
                        if self.subrow_facet else [None] 
        
        col_groups = data.index.get_level_values(self.column_facet).unique() \
                     if self.column_facet else [None]
                     
        subcol_groups = data.index.get_level_values(self.subcolumn_facet).unique() \
                        if self.subcolumn_facet else [None]

        row_offset = (self.column_facet != "") + (self.subcolumn_facet != "")        
        col_offset = (self.row_facet != "") + (self.subrow_facet != "")
        
        num_rows = len(row_groups) * len(subrow_groups) + row_offset
        num_cols = len(col_groups) * len(subcol_groups) + col_offset

        t = np.empty((num_rows, num_cols), dtype = np.object_)
 
        # make the main table       
        for (ri, r) in enumerate(row_groups):
            for (rri, rr) in enumerate(subrow_groups):
                for (ci, c) in enumerate(col_groups):
                    for (cci, cc) in enumerate(subcol_groups):
                        row_idx = ri * len(subrow_groups) + rri + row_offset
                        col_idx = ci * len(subcol_groups) + cci + col_offset
#                         agg_idx = [x for x in (r, rr, c, cc) if x is not None]
#                         agg_idx = tuple(agg_idx)
#                         if len(agg_idx) == 1:
#                             agg_idx = agg_idx[0]
#                         t[row_idx, col_idx] = self.result.get(agg_idx) 


                        # this is not pythonic, but i'm tired
                        agg_idx = []
                        for data_idx in data.index.names:
                            if data_idx == self.row_facet:
                                agg_idx.append(r)
                            elif data_idx == self.subrow_facet:
                                agg_idx.append(rr)
                            elif data_idx == self.column_facet:
                                agg_idx.append(c)
                            elif data_idx == self.subcolumn_facet:
                                agg_idx.append(cc)
                        
                        agg_idx = tuple(agg_idx)
                        if len(agg_idx) == 1:
                            agg_idx = agg_idx[0]
                            
                        try:
                            text = "{:g}".format(data.loc[agg_idx][self.result.name])
                        except ValueError:
                            text = data.loc[agg_idx][self.result.name]

                        t[row_idx, col_idx] = self.result.get(agg_idx) 
                        
        # row headers
        if self.row_facet:
            for (ri, r) in enumerate(row_groups):
                row_idx = ri * len(subrow_groups) + row_offset
                text = "{0} = {1}".format(self.row_facet, r)
                t[row_idx, 0] = text
                
        # subrow headers
        if self.subrow_facet:
            for (ri, r) in enumerate(row_groups):
                for (rri, rr) in enumerate(subrow_groups):
                    row_idx = ri * len(subrow_groups) + rri + row_offset
                    text = "{0} = {1}".format(self.subrow_facet, rr)
                    t[row_idx, 1] = text
                    
        # column headers
        if self.column_facet:
            for (ci, c) in enumerate(col_groups):
                col_idx = ci * len(subcol_groups) + col_offset
                text = "{0} = {1}".format(self.column_facet, c)
                t[0, col_idx] = text

        # column headers
        if self.subcolumn_facet:
            for (ci, c) in enumerate(col_groups):
                for (cci, cc) in enumerate(subcol_groups):
                    col_idx = ci * len(subcol_groups) + cci + col_offset
                    text = "{0} = {1}".format(self.subcolumn_facet, c)
                    t[1, col_idx] = text        
                    
        np.savetxt(dialog.path, t, delimiter = ",", fmt = "%s")
                    
           

@provides(IViewPlugin)
class TablePlugin(Plugin, PluginHelpMixin):

    id = 'edu.mit.synbio.cytoflowgui.view.table'
    view_id = 'edu.mit.synbio.cytoflow.view.table'
    short_name = "1D Statistics View"
    
    def get_view(self):
        return TablePluginView()

    def get_icon(self):
        return ImageResource('table')

    @contributes_to(VIEW_PLUGIN_EXT)
    def get_plugin(self):
        return self
    
### Serialization

@camel_registry.dumper(TablePluginView, 'table-view', version = 1)
def _dump(view):
    return dict(statistic = view.statistic,
                row_facet = view.row_facet,
                subrow_facet = view.subrow_facet,
                column_facet = view.column_facet,
                subcolumn_facet = view.subcolumn_facet,
                subset_list = view.subset_list)
    
@camel_registry.loader('table-view', version = 1)
def _load(data, version):
    data['statistic'] = tuple(data['statistic'])
    return TablePluginView(**data)