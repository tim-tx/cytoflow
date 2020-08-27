#!/usr/bin/env python3.4
# coding: latin-1

# (c) Massachusetts Institute of Technology 2015-2018
# (c) Brian Teague 2018-2019
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
Channel statistic
-----------------

Apply a function to subsets of a data set, and add it as a statistic
to the experiment.

First, the module groups the data by the unique values of the variables
in **By**, then applies **Function** to the **Channel** in each group.
    

.. object:: Name

    The operation name.  Becomes the first part of the new statistic's name.
    
.. object:: Channel

    The channel to apply the function to.
    
.. object:: Function

    The function to compute on each group.
        
.. object:: Subset

    Only apply the function to a subset of the data.  Useful if the function 
    is very slow.

'''

import numpy as np
import scipy.stats

from traitsui.api import (View, Item, EnumEditor, Controller, VGroup,
                          CheckListEditor, TextEditor)
from envisage.api import Plugin, contributes_to
from traits.api import (provides, Callable, List, Str, Property, Any,
                        on_trait_change)
from pyface.api import ImageResource

from cytoflow.operations.channel_stat import ChannelStatisticOp
import cytoflow.utility as util

from cytoflowgui.op_plugins import IOperationPlugin, OpHandlerMixin, OP_PLUGIN_EXT, shared_op_traits
from cytoflowgui.subset import ISubset, SubsetListEditor
from cytoflowgui.op_plugins.i_op_plugin import PluginOpMixin, PluginHelpMixin
from cytoflowgui.workflow import Changed
from cytoflowgui.serialization import camel_registry, traits_repr

ChannelStatisticOp.__repr__ = traits_repr

mean_95ci = lambda x: util.ci(x, np.mean, boots = 100)
geomean_95ci = lambda x: util.ci(x, util.geom_mean, boots = 100)

summary_functions = {"Mean" : np.mean,
                     "Geom.Mean" : util.geom_mean,
                     "Median" : np.median,
                     "Count" : len,
                     "Std.Dev" : np.std,
                     "Geom.SD" : util.geom_sd_range,
                     "SEM" : scipy.stats.sem,
                     "Geom.SEM" : util.geom_sem_range,
                     "Mean 95% CI" : mean_95ci,
                     "Geom.Mean 95% CI" : geomean_95ci
                     }

fill = {"Mean" : 0,
        "Geom.Mean" : 0,
        "Median" : 0,
        "Count" : 0,
        "Std.Dev" : 0,
        "Geom.SD" : (0,0),
        "SEM" : 0,
        "Geom.SEM" : (0,0),
        "Mean 95% CI" : 0,
        "Geom.Mean 95% CI" : 0
        }


class ChannelStatisticHandler(OpHandlerMixin, Controller):
    def default_traits_view(self):
        return View(Item('name',
                         editor = TextEditor(auto_set = False)),
                    Item('channel',
                         editor=EnumEditor(name='context.previous_wi.channels'),
                         label = "Channel"),
                    Item('statistic_name',
                                editor = EnumEditor(values = sorted(summary_functions.keys())),
                                label = "Function"),
                    Item('by',
                         editor = CheckListEditor(cols = 2,
                                                  name = 'handler.previous_conditions_names'),
                         label = 'Group\nBy',
                         style = 'custom'),
                    VGroup(Item('subset_list',
                                show_label = False,
                                editor = SubsetListEditor(conditions = "context.previous_wi.conditions")),
                           label = "Subset",
                           show_border = False,
                           show_labels = False),
                    shared_op_traits)

class ChannelStatisticPluginOp(PluginOpMixin, ChannelStatisticOp):
    handler_factory = Callable(ChannelStatisticHandler)
    
    # functions aren't picklable, so make this one transient 
    # and send the name instead
    function = Callable(transient = True)
    
    # we need to automatically pick a good fill
    fill = Property(Any, depends_on = 'statistic_name', transient = True)
    
    # MAGIC - returns the value of the 'fill' property
    def _get_fill(self):
        if self.statistic_name:
            return fill[self.statistic_name]
        else:
            return 0
    
    # bits to support the subset editor
    
    subset_list = List(ISubset)    
    subset = Property(Str, depends_on = "subset_list.str")
        
    # MAGIC - returns the value of the "subset" Property, above
    def _get_subset(self):
        return " and ".join([subset.str for subset in self.subset_list if subset.str])
    
    @on_trait_change('subset_list.str')
    def _subset_changed(self, obj, name, old, new):
        self.changed = (Changed.OPERATION, ('subset_list', self.subset_list))

    def apply(self, experiment):
        if not self.statistic_name:
            raise util.CytoflowOpError("Summary function isn't set")
        
        self.function = summary_functions[self.statistic_name]
        
        return ChannelStatisticOp.apply(self, experiment) 
    
    def get_notebook_code(self, idx):
        op = ChannelStatisticOp()
        op.copy_traits(self, op.copyable_trait_names())
        
        fn_import = {"Mean" : "from numpy import mean",
                     "Median" : "from numpy import median",
                     "Geom.Mean" : None,
                     "Count" : None,
                     "Std.Dev" : "from numpy import std",
                     "Geom.SD" : None,
                     "SEM" : "from scipy.stats import sem",
                     "Geom.SEM" : None,
                     "Mean 95% CI" : "from numpy import mean",
                     "Geom.Mean 95% CI" : None
                  }
        
        fn_name = {"Mean" : "mean",
                   "Median" : "median",
                   "Geom.Mean" : "geom_mean",
                   "Count" : "len",
                   "Std.Dev" : "std",
                   "Geom.SD" : "geom_sd_range",
                   "SEM" : "sem",
                   "Geom.SEM" : "geom_sem_range",
                   "Mean 95% CI" : "lambda x: ci(x, mean, boots = 100)",
                   "Geom.Mean 95% CI" : "lambda x: ci(x, geom_mean, boots = 100)"
                   }
        
        op.function = summary_functions[self.statistic_name]
        
        try:
            # this doesn't work for builtins like "len"
            op.function.__name__ = fn_name[self.statistic_name]
        except AttributeError:
            pass
        
        return "\n{import_statement}\nop_{idx} = {repr}\n\nex_{idx} = op_{idx}.apply(ex_{prev_idx})"\
            .format(import_statement = (fn_import[self.statistic_name]
                                        if fn_import[self.statistic_name] is not None
                                        else ""),
                    repr = repr(op),
                    idx = idx,
                    prev_idx = idx - 1)

@provides(IOperationPlugin)
class ChannelStatisticPlugin(Plugin, PluginHelpMixin):
    
    id = 'edu.mit.synbio.cytoflowgui.op_plugins.channel_statistic'
    operation_id = 'edu.mit.synbio.cytoflow.operations.channel_statistic'

    short_name = "Channel Statistic"
    menu_group = "Gates"
    
    def get_operation(self):
        return ChannelStatisticPluginOp()
    
    def get_icon(self):
        return ImageResource('channel_stat')
    
    @contributes_to(OP_PLUGIN_EXT)
    def get_plugin(self):
        return self
    
    
### Serialization
@camel_registry.dumper(ChannelStatisticPluginOp, 'channel-statistic', version = 1)
def _dump(op):
    return dict(name = op.name,
                channel = op.channel,
                statistic_name = op.statistic_name,
                by = op.by,
                subset_list = op.subset_list)
    
@camel_registry.loader('channel-statistic', version = 1)
def _load(data, version):
    return ChannelStatisticPluginOp(**data)
