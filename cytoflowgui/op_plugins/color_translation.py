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
Color Translation
-----------------

Translate measurements from one color's scale to another, using a two-color
or three-color control.
    
To use, set up the **Controls** list with the channels to convert and the FCS 
files to compute the mapping.  Click **Estimate** and make sure to check that 
the diagnostic plots look good.
    
.. object:: Add Control, Remove Control

    Add and remove controls to compute the channel mappings.
    
.. object:: Use mixture model?

    If ``True``, try to model the **from** channel as a mixture of expressing
    cells and non-expressing cells (as you would get with a transient
    transfection), then weight the regression by the probability that the
    the cell is from the top (transfected) distribution.  Make sure you 
    check the diagnostic plots to see that this worked!
    
.. plot::
    
    import cytoflow as flow
    import_op = flow.ImportOp()
    import_op.tubes = [flow.Tube(file = "tasbe/mkate.fcs")]
    ex = import_op.apply()

    color_op = flow.ColorTranslationOp()
    color_op.controls = {("Pacific Blue-A", "FITC-A") : "tasbe/rby.fcs",
                         ("PE-Tx-Red-YG-A", "FITC-A") : "tasbe/rby.fcs"}
    color_op.mixture_model = True

    color_op.estimate(ex)
    color_op.default_view().plot(ex)  
    ex = color_op.apply(ex)  
'''

import warnings

from traitsui.api import View, Item, EnumEditor, Controller, VGroup, \
                         ButtonEditor, HGroup, InstanceEditor
from envisage.api import Plugin, contributes_to
from traits.api import (provides, Callable, Tuple, List, Str, HasTraits,
                        File, Event, Dict, on_trait_change, Bool, Constant,
                        Property)
from pyface.api import ImageResource

import cytoflow.utility as util

from cytoflow.operations.color_translation import ColorTranslationOp, ColorTranslationDiagnostic
from cytoflow.views.i_selectionview import IView

from cytoflowgui.view_plugins.i_view_plugin import ViewHandlerMixin, PluginViewMixin
from cytoflowgui.op_plugins import IOperationPlugin, OpHandlerMixin, OP_PLUGIN_EXT, shared_op_traits
from cytoflowgui.subset import ISubset, SubsetListEditor
from cytoflowgui.color_text_editor import ColorTextEditor
from cytoflowgui.op_plugins.i_op_plugin import PluginOpMixin, PluginHelpMixin
from cytoflowgui.vertical_list_editor import VerticalListEditor
from cytoflowgui.workflow import Changed
from cytoflowgui.serialization import camel_registry, traits_repr, traits_str, dedent

ColorTranslationOp.__repr__ = traits_repr

class _Control(HasTraits):
    from_channel = Str
    to_channel = Str
    file = File
    
    
    def __repr__(self):
        return traits_repr(self)


class ColorTranslationHandler(OpHandlerMixin, Controller):
    
    add_control = Event
    remove_control = Event
    
    # MAGIC: called when add_control is set
    def _add_control_fired(self):
        self.model.controls_list.append(_Control())
        
    def _remove_control_fired(self):
        if self.model.controls_list:
            self.model.controls_list.pop()
    
    def control_traits_view(self):
        return View(HGroup(Item('from_channel',
                                editor = EnumEditor(name = 'handler.context.previous_wi.channels')),
                           Item('to_channel',
                                editor = EnumEditor(name = 'handler.context.previous_wi.channels')),
                           Item('file',
                                show_label = False)),
                    handler = self)
    
    def default_traits_view(self):
        return View(VGroup(Item('controls_list',
                                editor = VerticalListEditor(editor = InstanceEditor(view = self.control_traits_view()),
                                                            style = 'custom',
                                                            mutable = False),
                                style = 'custom'),
                    Item('handler.add_control',
                         editor = ButtonEditor(value = True,
                                               label = "Add a control")),
                    Item('handler.remove_control',
                         editor = ButtonEditor(value = True,
                                               label = "Remove a control")),
                    label = "Controls",
                    show_labels = False),
                    Item('mixture_model',
                         label = "Use mixture\nmodel?"),
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

class ColorTranslationPluginOp(PluginOpMixin, ColorTranslationOp):
    handler_factory = Callable(ColorTranslationHandler)

    add_control = Event
    remove_control = Event

    controls = Dict(Tuple(Str, Str), File, transient = True)
    controls_list = List(_Control, estimate = True)
    mixture_model = Bool(False, estimate = True)
    translation = Constant(None)
        
    @on_trait_change('controls_list_items, controls_list:+', post_init = True)
    def _controls_changed(self):
        self.changed = (Changed.ESTIMATE, ('controls_list', self.controls_list))

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
        return ColorTranslationPluginView(op = self, **kwargs)
    
    def estimate(self, experiment):
        for i, control_i in enumerate(self.controls_list):
            for j, control_j in enumerate(self.controls_list):
                if control_i.from_channel == control_j.from_channel and i != j:
                    raise util.CytoflowOpError("Channel {0} is included more than once"
                                               .format(control_i.from_channel))
                                               
        self.controls = {}
        for control in self.controls_list:
            self.controls[(control.from_channel, control.to_channel)] = control.file
            
        if not self.subset:
            warnings.warn("Are you sure you don't want to specify a subset "
                          "used to estimate the model?",
                          util.CytoflowOpWarning)
                    
        ColorTranslationOp.estimate(self, experiment, subset = self.subset)
        
        self.changed = (Changed.ESTIMATE_RESULT, self)
        
    
    def should_clear_estimate(self, changed, payload):
        if changed == Changed.ESTIMATE:
            return True
        
        return False
        
    def clear_estimate(self):
        self._coefficients.clear()        
        self.changed = (Changed.ESTIMATE_RESULT, self)
        
        
    def get_notebook_code(self, idx):
        op = ColorTranslationOp()
        op.copy_traits(self, op.copyable_trait_names())

        for control in self.controls_list:
            op.controls[(control.from_channel, control.to_channel)] = control.file        

        return dedent("""
        op_{idx} = {repr}
        
        op_{idx}.estimate(ex_{prev_idx}{subset})
        ex_{idx} = op_{idx}.apply(ex_{prev_idx})
        """
        .format(repr = repr(op),
                idx = idx,
                prev_idx = idx - 1,
                subset = ", subset = " + repr(self.subset) if self.subset else ""))

class ColorTranslationViewHandler(ViewHandlerMixin, Controller):
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
class ColorTranslationPluginView(PluginViewMixin, ColorTranslationDiagnostic):
    handler_factory = Callable(ColorTranslationViewHandler)
    
    def plot_wi(self, wi):
        self.plot(wi.previous_wi.result)
        
    def should_plot(self, changed, payload):
        if changed == Changed.ESTIMATE_RESULT:
            return True
        
        return False
    
    def get_notebook_code(self, idx):
        view = ColorTranslationDiagnostic()
        view.copy_traits(self, view.copyable_trait_names())
        view.subset = self.subset
        
        return dedent("""
        op_{idx}.default_view({traits}).plot(ex_{prev_idx})
        """
        .format(traits = traits_str(view),
                idx = idx,
                prev_idx = idx - 1))


@provides(IOperationPlugin)
class ColorTranslationPlugin(Plugin, PluginHelpMixin):
 
    id = 'edu.mit.synbio.cytoflowgui.op_plugins.color_translation'
    operation_id = 'edu.mit.synbio.cytoflow.operations.color_translation'

    short_name = "Color Translation"
    menu_group = "Gates"
    
    def get_operation(self):
        return ColorTranslationPluginOp()
    
    def get_icon(self):
        return ImageResource('color_translation')
    
    @contributes_to(OP_PLUGIN_EXT)
    def get_plugin(self):
        return self
    
### Serialization
@camel_registry.dumper(ColorTranslationPluginOp, 'color-translation', version = 1)
def _dump(op):
    return dict(controls_list = op.controls_list,
                mixture_model = op.mixture_model,
                subset_list = op.subset_list)
    
@camel_registry.loader('color-translation', version = 1)
def _load(data, version):
    return ColorTranslationPluginOp(**data)

@camel_registry.dumper(_Control, 'color-translation-control', version = 1)
def _dump_control(c):
    return dict(from_channel = c.from_channel,
                to_channel = c.to_channel,
                file = c.file)
    
@camel_registry.loader('color-translation-control', version = 1)
def _load_control(data, version):
    return _Control(**data)

@camel_registry.dumper(ColorTranslationPluginView, 'color-translation-view', version = 1)
def _dump_view(view):
    return dict(op = view.op)

@camel_registry.loader('color-translation-view', version = 1)
def _load_view(data, ver):
    return ColorTranslationPluginView(**data)