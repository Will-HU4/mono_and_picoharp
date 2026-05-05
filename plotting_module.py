import pyqtgraph as pg


class PlotData:
    def __init__(self, plot_widget: pg.PlotWidget):
        self.plot_widget = plot_widget

    def update_plot_properties(self, unit: str, mono_unit: str):
        self.plot_widget.setLabel('left', f'Power ({unit})')
        self.plot_widget.setLabel('bottom', mono_unit)
        self.plot_widget.setTitle('Monochromator scan Data')
        self.plot_widget.addLegend()
        self.plot_widget.showGrid(x=True, y=True)

    def update_plot(self, x_values: list, y_values: list, unit: str = "nw", mono_unit: str = "step"):
        self.plot_widget.clear()
        self.plot_widget.plot(x_values, y_values, pen='r', name='Data')
        self.update_plot_properties(unit=unit, mono_unit=mono_unit)
