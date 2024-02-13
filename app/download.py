"""Functions to download results."""
import zipfile
import json

import streamlit as st
from honeybee.model import Model
from honeybee_display.model import model_to_vis_set
from ladybug_vtk.visualization_set import VisualizationSet as VTKVisualizationSet

from vis_metadata import _leed_daylight_option_one_vis_metadata


def download_files() -> None:
    """Download files from a run on Pollination. This function uses the run
    saved in the sessions state."""
    run = st.session_state.run
    run_folder = st.session_state.run_folder

    _, info = next(run.job.runs_dataframe.input_artifacts.iterrows())
    model_dict = json.load(run.job.download_artifact(info.model))
    hb_model = Model.from_dict(model_dict)
    hb_model.to_hbjson(name='model', folder=run_folder)

    leed_summary_folder = run_folder.joinpath('leed-summary')

    output = run.download_zipped_output('leed-summary')
    with zipfile.ZipFile(output) as zip_folder:
        zip_folder.extractall(leed_summary_folder)

    if not leed_summary_folder.joinpath('states_schedule_err.json').is_file():
        json.dump({}, leed_summary_folder.joinpath('states_schedule_err.json'))

    results_folder = leed_summary_folder.joinpath('results')
    metric_info_dict = _leed_daylight_option_one_vis_metadata()
    for metric, data in metric_info_dict.items():
        file_path = results_folder.joinpath(metric, 'vis_metadata.json')
        with open(file_path, 'w') as file:
            json.dump(data, file, indent=4)

    vis_set = model_to_vis_set(
        hb_model, color_by=None, include_wireframe=True,
        grid_data_path=str(results_folder), active_grid_data='da'
    )
    vtk_vs = VTKVisualizationSet.from_visualization_set(vis_set)
    vtk_vs.to_vtkjs(folder=run_folder, name='vis_set')
