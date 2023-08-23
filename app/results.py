"""Functions to download and load results."""
import json
from pathlib import Path
from typing import Tuple
import streamlit as st

from download import download_files


st.cache_data
def load_from_folder(folder: Path) \
    -> Tuple[Path, Path, dict, dict, dict, dict]:
    """Load results from folder."""
    leed_summary = folder.joinpath('leed-summary')
    with open(leed_summary.joinpath('summary.json')) as json_file:
        summary = json.load(json_file)
    with open(leed_summary.joinpath('summary_grid.json')) as json_file:
        summary_grid = json.load(json_file)
    with open(leed_summary.joinpath('states_schedule.json')) as json_file:
        states_schedule = json.load(json_file)
    with open(leed_summary.joinpath('states_schedule_err.json')) as json_file:
        states_schedule_err = json.load(json_file)

    vtjks_file = folder.joinpath('vis_set.vtkjs')

    return (leed_summary, vtjks_file, summary, summary_grid, states_schedule,
            states_schedule_err)


def load_results() -> tuple:
    """Load results from a run folder. If the the run folder does not exist
    the files will be downloaded to the run folder."""
    if not st.session_state.run_folder.exists():
        # download results to run folder
        with st.spinner('Downloading files...'):
            download_files()

    # load results from run folder
    leed_summary, vtjks_file, summary, summary_grid, states_schedule, \
        states_schedule_err = load_from_folder(st.session_state.run_folder)

    return (leed_summary, vtjks_file, summary, summary_grid, states_schedule,
            states_schedule_err)
