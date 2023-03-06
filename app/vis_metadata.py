"""Visualization metadata for LEED Daylight Option I"""
from ladybug.datatype.fraction import Fraction
from ladybug.datatype.time import Time
from ladybug.legend import LegendParameters
from ladybug.color import Colorset


def _leed_daylight_option_one_vis_metadata():
    """Return visualization metadata for leed daylight option one."""
    da_lpar = LegendParameters(min=0, max=100, colors=Colorset.annual_comfort())
    ase_hrs_lpar = LegendParameters(min=0, max=250, colors=Colorset.original())

    metric_info_dict = {
        'da': {
            'type': 'VisualizationMetaData',
            'data_type': Fraction('Daylight Autonomy').to_dict(),
            'unit': '%',
            'legend_parameters': da_lpar.to_dict()
        },
        'ase_hours_above': {
            'type': 'VisualizationMetaData',
            'data_type': Time('Hours above direct threshold').to_dict(),
            'unit': 'hr',
            'legend_parameters': ase_hrs_lpar.to_dict()
        }
    }

    return metric_info_dict
