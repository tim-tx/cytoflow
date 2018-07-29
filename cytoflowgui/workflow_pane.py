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

from traits.api import provides, Instance, List, Tuple

from pyface.qt import QtGui, QtCore
from pyface.tasks.api import TraitsDockPane, IDockPane, Task
from pyface.action.api import ToolBarManager
from pyface.tasks.action.api import TaskAction

from cytoflowgui.op_plugins import IOperationPlugin
from cytoflowgui.view_pane import HintedMainWindow

@provides(IDockPane)
class WorkflowDockPane(TraitsDockPane):
    
    id = 'edu.mit.synbio.cytoflowgui.workflow_pane'
    name = "Workflow"
    
    # the application instance from which to get plugin instances
    plugins = List(IOperationPlugin)
    
    # the task serving as the dock pane's controller
    task = Instance(Task)
    
    # IN INCHES
    image_size = Tuple((0.33, 0.33))

    def create_contents(self, parent):
        """ 
        Create and return the toolkit-specific contents of the dock pane.
        """
 
        dpi = self.control.physicalDpiX()
        image_size = (int(self.image_size[0] * dpi),
                      int(self.image_size[1] * dpi))
 
        self.toolbar = ToolBarManager(orientation='vertical',
                                      show_tool_names = False,
                                      image_size = image_size)
                 
        for plugin in self.plugins:
            
            # don't include the import plugin
            if plugin.id == 'edu.mit.synbio.cytoflowgui.op_plugins.import':
                continue
            
            task_action = TaskAction(name=plugin.short_name,
                                     on_perform = lambda pid=plugin.id: 
                                                    self.task.add_operation(pid),
                                     image = plugin.get_icon())
            self.toolbar.append(task_action)
             
        # see the comment in cytoflowgui.view_pane for an explanation of this
        # HintedMainWindow business.
        window = HintedMainWindow()                    
        window.addToolBar(QtCore.Qt.LeftToolBarArea,    # @UndefinedVariable
                          self.toolbar.create_tool_bar(window))
         
        self.ui = self.model.edit_traits(view = 'operations_traits',
                                         kind = 'subpanel', 
                                         parent = window)
        window.setCentralWidget(self.ui.control)
         
        window.setParent(parent)
        parent.setWidget(window)
         
        return window
