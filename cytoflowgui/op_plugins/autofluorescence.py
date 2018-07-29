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

'''
Autofluorescence correction
---------------------------

Apply autofluorescence correction to a set of fluorescence channels.

This module estimates the arithmetic median fluorescence from cells that are
not fluorescent, then subtracts the median from the experimental data.

Check the diagnostic plot to make sure that the sample is actually 
non-fluorescent, and that the module found the population median.

.. object:: Channels

    The channels to correct

.. object:: Blank file

    The FCS file containing measurements of blank cells.
    
.. note::

    You cannot have any operations before this one which estimate model
    parameters based on experimental conditions.  (Eg, you can't use a
    **Density Gate** to choose morphological parameters and set *by* to an
    experimental condition.)  If you need this functionality, you can access it 
    using the Python module interface.
    
.. plot::

    import cytoflow as flow
    import_op = flow.ImportOp()
    import_op.tubes = [flow.Tube(file = "tasbe/rby.fcs")]
    ex = import_op.apply()

    af_op = flow.AutofluorescenceOp()
    af_op.channels = ["Pacific Blue-A", "FITC-A", "PE-Tx-Red-YG-A"]
    af_op.blank_file = "tasbe/blank.fcs"

    af_op.estimate(ex)
    af_op.default_view().plot(ex) 
'''
import warnings

from traitsui.api import (View, Item, Controller, ButtonEditor, CheckListEditor,
                          VGroup)
from envisage.api import Plugin, contributes_to
from traits.api import (provides, Callable, List, Str, File, on_trait_change,
                        Property, DelegatesTo)
from pyface.api import ImageResource

import cytoflow.utility as util

from cytoflow.operations.autofluorescence import AutofluorescenceOp, AutofluorescenceDiagnosticView
from cytoflow.views.i_selectionview import IView

from cytoflowgui.view_plugins.i_view_plugin import ViewHandlerMixin, PluginViewMixin
from cytoflowgui.op_plugins import IOperationPlugin, OpHandlerMixin, OP_PLUGIN_EXT, shared_op_traits
from cytoflowgui.color_text_editor import ColorTextEditor
from cytoflowgui.subset import ISubset, SubsetListEditor
from cytoflowgui.op_plugins.i_op_plugin import PluginOpMixin, PluginHelpMixin
from cytoflowgui.workflow import Changed
from cytoflowgui.serialization import camel_registry, traits_repr, traits_str, dedent

AutofluorescenceOp.__repr__ = traits_repr

class AutofluorescenceHandler(OpHandlerMixin, Controller):
    
    def default_traits_view(self):
        return View(Item('blank_file'),
                    Item('channels',
                         editor = CheckListEditor(cols = 2,
                                                  name = 'context.previous_wi.channels'),
                         style = 'custom'),
                    VGroup(Item('subset_list',
                                show_label = False,
                                editor = SubsetListEditor(conditions = "context.previous_wi.conditions",
                                                          metadata = "context.previous_wi.metadata",
                                                          when = "'experiment' not in vars() or not experiment")),
                           label = "Subset",
                           show_border = False,
                           show_labels = False),
                    Item('do_estimate',
                         editor = ButtonEditor(value = True,
                                               label = "Estimate!"),
                         show_label = False),
                    shared_op_traits)

class AutofluorescencePluginOp(PluginOpMixin, AutofluorescenceOp):
    handler_factory = Callable(AutofluorescenceHandler)
    
    channels = List(Str, estimate = True)
    blank_file = File(filter = ["*.fcs"], estimate = True)

    @on_trait_change('channels', post_init = True)
    def _channels_changed(self):
        self.changed = (Changed.ESTIMATE, ('channels', self.channels))
    
    # bits to support the subset editor
    
    subset_list = List(ISubset, estimate = True)    
    subset = Property(Str, depends_on = "subset_list.str")
        
    # MAGIC - returns the value of the "subset" Property, above
    def _get_subset(self):
        return " and ".join([subset.str for subset in self.subset_list if subset.str])
    
    @on_trait_change('subset_list.str')
    def _subset_changed(self, obj, name, old, new):
        self.changed = (Changed.ESTIMATE, ('subset_list', self.subset_list))

    def default_view(self, **kwargs):
        return AutofluorescencePluginView(op = self, **kwargs)
    
    def estimate(self, experiment):
        if not self.subset:
            warnings.warn("Are you sure you don't want to specify a subset "
                          "used to estimate the model?",
                          util.CytoflowOpWarning)
            
        # check for experiment metadata used to estimate operations in the
        # history, and bail if we find any
        for op in experiment.history:
            if hasattr(op, 'by'):
                for by in op.by:
                    if 'experiment' in experiment.metadata[by]:
                        raise util.CytoflowOpError('experiment',
                                                   "Prior to applying this operation, "
                                                   "you must not apply any operation with 'by' "
                                                   "set to an experimental condition.")
        
        try:
            super().estimate(experiment, subset = self.subset)
        except:
            raise
        finally:
            self.changed = (Changed.ESTIMATE_RESULT, self)
        
        
    def clear_estimate(self):
        self._af_median.clear()
        self._af_stdev.clear()
        self._af_histogram.clear()
        self.changed = (Changed.ESTIMATE_RESULT, self)
        
    
    def should_apply(self, changed, payload):
        if changed == Changed.PREV_RESULT or changed == Changed.ESTIMATE_RESULT:
            return True
        
        return False

    
    def should_clear_estimate(self, changed, payload):
        if changed == Changed.ESTIMATE:
            return True
        
        return False
    
    def get_notebook_code(self, idx):
        op = AutofluorescenceOp()
        op.copy_traits(self, op.copyable_trait_names())

        return dedent("""
        op_{idx} = {repr}
        
        op_{idx}.estimate(ex_{prev_idx}{subset})
        ex_{idx} = op_{idx}.apply(ex_{prev_idx})
        """
        .format(repr = repr(op),
                idx = idx,
                prev_idx = idx - 1,
                subset = ", subset = " + repr(self.subset) if self.subset else ""))
        

class AutofluorescenceViewHandler(ViewHandlerMixin, Controller):
    def default_traits_view(self):
        return View(Item('context.view_warning',
                         resizable = True,
                         visible_when = 'context.view_warning',
                         editor = ColorTextEditor(foreground_color = "#000000",
                                                 background_color = "#ffff99")),
                    Item('context.view_error',
                         resizable = True,
                         visible_when = 'context.view_error',
                         editor = ColorTextEditor(foreground_color = "#000000",
                                                  background_color = "#ff9191")))

@provides(IView)
class AutofluorescencePluginView(PluginViewMixin, AutofluorescenceDiagnosticView):
    handler_factory = Callable(AutofluorescenceViewHandler)
    subset = DelegatesTo('op', transient = True)
    
    def plot_wi(self, wi):
        self.plot(wi.previous_wi.result)
    
    def should_plot(self, changed, payload):
        if changed == Changed.ESTIMATE_RESULT:
            return True
        
        return False
    
    def get_notebook_code(self, idx):
        view = AutofluorescenceDiagnosticView()
        view.copy_traits(self, view.copyable_trait_names())
        
        return dedent("""
        op_{idx}.default_view({traits}).plot(ex_{prev_idx})
        """
        .format(traits = traits_str(view),
                idx = idx,
                prev_idx = idx - 1))
    

@provides(IOperationPlugin)
class AutofluorescencePlugin(Plugin, PluginHelpMixin):

    id = 'edu.mit.synbio.cytoflowgui.op_plugins.autofluorescence'
    operation_id = 'edu.mit.synbio.cytoflow.operations.autofluorescence'

    short_name = "Autofluorescence correction"
    menu_group = "Calibration"
    
    def get_operation(self):
        return AutofluorescencePluginOp()
    
    def get_icon(self):
        return ImageResource('autofluorescence')
    
    @contributes_to(OP_PLUGIN_EXT)
    def get_plugin(self):
        return self
    
### Serialization
@camel_registry.dumper(AutofluorescencePluginOp, 'autofluorescence', version = 1)
def _dump(op):
    return dict(blank_file = op.blank_file,
                channels = op.channels,
                subset_list = op.subset_list)
    
@camel_registry.loader('autofluorescence', version = 1)
def _load(data, version):
    return AutofluorescencePluginOp(**data)

@camel_registry.dumper(AutofluorescencePluginView, 'autofluorescence-view', version = 1)
def _dump_view(view):
    return dict(op = view.op)

@camel_registry.loader('autofluorescence-view', version = 1)
def _load_view(data, version):
    return AutofluorescencePluginView(**data)