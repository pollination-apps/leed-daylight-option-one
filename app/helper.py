"""Functions to support the leed-daylight-option-one app."""
import zipfile
import json
import pandas as pd
from pathlib import Path

import streamlit as st
from honeybee.model import Model
from pollination_streamlit.selectors import Run
from pollination_streamlit.api.client import ApiClient
from pollination_streamlit_io import (select_account, select_project,
    select_study, select_run)
from honeybee_display.model import model_to_vis_set
from ladybug_vtk.visualization_set import VisualizationSet as VTKVisualizationSet

from on_change import (radio_show_all_grids, radio_show_all,
    multiselect_grids, multiselect_aperture_groups, radio_show_all_ase,
    multiselect_ase, legend_min_on_change, legend_max_on_change)
from plot import figure_grids, figure_aperture_group_schedule, figure_ase
from vis_metadata import _leed_daylight_option_one_vis_metadata


@st.cache(show_spinner=False)
def download_files(run: Run) -> None:
    """Download files from a run on Pollination.

    Args:
        run: Run.
    """
    _, info = next(run.job.runs_dataframe.input_artifacts.iterrows())
    model_dict = json.load(run.job.download_artifact(info.model))
    hb_model = Model.from_dict(model_dict)

    data_folder = Path(f'{st.session_state.target_folder}/data')
    leed_summary_folder = data_folder.joinpath('leed-summary')

    output = run.download_zipped_output('leed-summary')
    with zipfile.ZipFile(output) as zip_folder:
        zip_folder.extractall(leed_summary_folder)

    grids_info = leed_summary_folder.joinpath('grids_info.json')
    grids_info.unlink() # remove later
    with open(leed_summary_folder.joinpath('summary.json')) as json_file:
        summary = json.load(json_file)
    with open(leed_summary_folder.joinpath('summary_grid.json')) as json_file:
        summary_grid = json.load(json_file)
    with open(leed_summary_folder.joinpath('states_schedule.json')) as json_file:
        states_schedule = json.load(json_file)
    if leed_summary_folder.joinpath('states_schedule_err.json').is_file():
        with open(leed_summary_folder.joinpath('states_schedule_err.json')) as json_file:
            states_schedule_err = json.load(json_file)
    else:
        states_schedule_err = None

    results_folder = leed_summary_folder.joinpath('results')
    metric_info_dict = _leed_daylight_option_one_vis_metadata()
    for metric, data in metric_info_dict.items():
        file_path = results_folder.joinpath(metric, 'vis_metadata.json')
        with open(file_path, 'w') as fp:
            json.dump(data, fp, indent=4)

    vs = model_to_vis_set(
        hb_model, color_by=None, include_wireframe=True,
        grid_data_path=str(results_folder), active_grid_data='da'
    )
    vtk_vs = VTKVisualizationSet.from_visualization_set(vs)
    vtjks_file = Path(vtk_vs.to_vtkjs(folder=data_folder, name='vis_set'))

    return (leed_summary_folder, vtjks_file, summary, summary_grid,
            states_schedule, states_schedule_err)


def process_summary(summary: dict):
    points = summary['credits']
    if points > 1:
        color = 'Green'
    else:
        color = 'Gray'
    credit_text = f'<h2 style="color:{color}">LEED Credits: {points} points</h2>'
    st.markdown(credit_text, unsafe_allow_html=True)

    # sda
    sda = summary['sda']
    sda_text = f'Spatial Daylight Autonomy: {round(sda, 2)}%'
    st.markdown(sda_text)

    # ase
    ase = summary['ase']
    ase_text = f'Annual Sunlight Exposure: {round(ase, 2)}%'
    st.markdown(ase_text)

    # total floor area / total sensor count
    if 'total_floor_area' in summary:
        floor_area_passing_sda = summary['floor_area_passing_sda']
        floor_area_passing_sda_text = \
            f'Floor area passing sDA: {round(floor_area_passing_sda, 2)}'
        st.markdown(floor_area_passing_sda_text)

        floor_area_passing_ase = summary['floor_area_passing_ase']
        floor_area_passing_ase_text = \
            f'Floor area passing ASE: {round(floor_area_passing_ase, 2)}'
        st.markdown(floor_area_passing_ase_text)

        total_floor_area = summary['total_floor_area']
        total_floor_area_text = f'Total floor area: {round(total_floor_area, 2)}'
        st.markdown(total_floor_area_text)
    else:
        sensor_count_passing_sda = summary['sensor_count_passing_sda']
        sensor_count_passing_sda_text = \
            f'Sensor count passing sDA: {round(sensor_count_passing_sda, 2)}'
        st.markdown(sensor_count_passing_sda_text)

        sensor_count_passing_ase = summary['sensor_count_passing_ase']
        sensor_count_passing_ase_text = \
            f'Sensor count passing ASE: {round(sensor_count_passing_ase, 2)}'
        st.markdown(sensor_count_passing_ase_text)

        total_sensor_count = summary['total_sensor_count']
        total_sensor_count_text = \
            f'Total sensor count: {round(total_sensor_count, 2)}'
        st.markdown(total_sensor_count_text)


def show_warnings_and_errors(
        summary: dict, summary_grid: dict, states_schedule_err: dict):
    # display warnings and errors
    if 'note' in summary:
        st.error(summary['note'])
    if states_schedule_err is not None:
        states_schedule_err_label = (
            'Hours where 2% of the floor area receives direct illuminance of '
            '1000 lux or more.'
        )
        with st.expander(states_schedule_err_label, expanded=True):
            st.write(
                'These are hours where no combination of blinds was able to '
                'reduce the direct illuminance below the target of 2% of the '
                'floor area receiving direct illuminance of 1000 lux or more. '
                'For LEED compliance it is a requirement that this target is '
                'met for all hours.')

            grids_ids = list(states_schedule_err.keys())

            if not 'show_all_grids' in st.session_state:
                # This is only run the first time
                if len(grids_ids) > 3:
                    st.session_state['show_all_grids'] = True
                else:
                    st.session_state['show_all_grids'] = False
                    st.session_state['select_grids'] = grids_ids

            show_all_grids_labels = {
                True: 'Select sensor grids',
                False: 'Show all sensor grids'
            }
            st.radio(
                'Select or show all sensor grids',
                options=[True, False], format_func=lambda x: show_all_grids_labels[x],
                horizontal=True, label_visibility='collapsed',
                on_change=radio_show_all_grids, args=(grids_ids,), key='show_all_grids'
            )

            st.multiselect(
                'Select sensor grids', grids_ids,
                label_visibility='collapsed',
                on_change=multiselect_grids, args=(grids_ids,),
                key='select_grids'
            )

            for grid_id in st.session_state['select_grids']:
                figure_grids(grid_id, states_schedule_err)

    for value in summary_grid.values():
        if 'ase_note' in value:
            st.warning(f'{value["ase_note"]}')
        elif 'ase_warning' in value:
            st.error(f'{value["ase_warning"]}')


def process_space(summary_grid: dict):
    st.header('Space by space breakdown')
    df = pd.DataFrame.from_dict(summary_grid).transpose()

    try:
        df = df[
            ['ase', 'sda', 'floor_area_passing_ase', 'floor_area_passing_sda',
             'total_floor_area']
            ]
        # rename columns
        df.rename(
            columns={
                'ase': 'ASE [%]',
                'sda': 'sDA [%]',
                'floor_area_passing_ase': 'Floor area passing ASE',
                'floor_area_passing_sda': 'Floor area passing sDA',
                'total_floor_area': 'Total floor area'
                }, inplace=True)
    except Exception:
        df = df[
            ['ase', 'sda', 'sensor_count_passing_ase',
             'sensor_count_passing_sda', 'total_sensor_count']
            ]
        # rename columns
        df.rename(
            columns={
                'ase': 'ASE [%]',
                'sda': 'sDA [%]',
                'sensor_count_passing_ase': 'Sensor count passing ASE',
                'sensor_count_passing_sda': 'Sensor count passing sDA',
                'total_sensor_count': 'Total sensor count'
            }
        )

    st.dataframe(df)


def process_states_schedule(states_schedule: dict):
    st.info(
        'Visualize shading schedules of each aperture group.'
    )

    aperture_groups = list(states_schedule.keys())

    if not 'show_all' in st.session_state:
        # This is only run the first time
        if len(aperture_groups) > 3:
            st.session_state['show_all'] = True
        else:
            st.session_state['show_all'] = False
            st.session_state['select_aperture_groups'] = aperture_groups

    aperture_group_schedule_labels = {
        True: 'Select aperture groups',
        False: 'Show all aperture groups'
    }
    st.radio(
        'Select or show all aperture groups',
        options=[True, False], format_func=lambda x: aperture_group_schedule_labels[x],
        horizontal=True, label_visibility='collapsed',
        on_change=radio_show_all, args=(aperture_groups,), key='show_all'
    )

    st.multiselect(
        'Select aperture groups', aperture_groups,
        label_visibility='collapsed',
        on_change=multiselect_aperture_groups, args=(aperture_groups,),
        key='select_aperture_groups'
    )

    for aperture_group in st.session_state['select_aperture_groups']:
        figure_aperture_group_schedule(aperture_group, states_schedule)


def process_ase(folder: Path):
    st.info(
        'Visualize the percentage of floor area where the direct illuminance '
        'is larger than 1000.'
    )

    results_folder = folder.joinpath('datacollections', 'ase_percentage_above')
    with open(results_folder.joinpath('grids_info.json')) as json_file:
        grids_info = json.load(json_file)

    grid_ids = [grid_info['full_id'] for grid_info in grids_info]
    if not 'show_all_ase' in st.session_state:
        # This is only run the first time
        if len(grids_info) > 3:
            st.session_state['show_all_ase'] = True
        else:
            st.session_state['show_all_ase'] = False
            st.session_state['select_ase'] = grid_ids

    aperture_group_schedule_labels = {
        True: 'Select sensor grids',
        False: 'Show all sensor grids'
    }
    st.radio(
        'Select or show all sensor grids',
        options=[True, False], format_func=lambda x: aperture_group_schedule_labels[x],
        horizontal=True, label_visibility='collapsed',
        on_change=radio_show_all_ase, args=(grid_ids,), key='show_all_ase'
    )

    st.multiselect(
        'Select sensor grids', grid_ids,
        label_visibility='collapsed',
        on_change=multiselect_ase, args=(grid_ids,),
        key='select_ase'
    )

    legend_min, legend_max = st.columns(2)
    if not 'legend_min' in st.session_state:
        st.session_state['legend_min'] = float(0)
    if not 'legend_max' in st.session_state:
        st.session_state['legend_max'] = float(100)
    with legend_min:
        st.number_input(
            'Legend minimum', min_value=float(0), max_value=float(100),
            format='%.2f', key='legend_min', on_change=legend_min_on_change)
    with legend_max:
        st.number_input(
            'Legend maximum', min_value=float(0), max_value=float(100),
            format='%.2f', key='legend_max', on_change=legend_max_on_change)

    for grid_id in st.session_state['select_ase']:
        figure_ase(grid_id, results_folder)


def select_menu(api_client: ApiClient, user: dict):
    if user and 'username' in user:
        username = user['username']
        account = select_account(
            'select-account',
            api_client,
            default_account_username=username
        )

        if account:
            st.subheader('Hi ' + username + ', select a project:')
            if 'owner' in account:
                username = account['account_name']

            project = select_project(
                'select-project',
                api_client,
                project_owner=username,
                default_project_id=st.session_state['project_id']
            )

            if project and 'name' in project:
                st.session_state['project_id'] = project['id']

                st.subheader('Select a study:')
                study = select_study(
                    'select-study',
                    api_client,
                    project_name=project['name'],
                    project_owner=username
                )

                if study and 'id' in study:
                    st.session_state['study_id'] = study['id']

                    st.subheader('Select a run:')
                    run = select_run(
                        'select-run',
                        api_client,
                        project_name=project['name'],
                        project_owner=username,
                        job_id=study['id']
                    )

                    if run is not None:
                        st.session_state['run_id'] = run['id']

                        project_owner = username
                        project_name = project['name']
                        job_id = study['id']
                        run_id = run['id']
                        run = Run(project_owner, project_name,
                                  job_id, run_id, api_client)
                        run_url = (f'{run._client.host}/{run.owner}/projects/'
                                   f'{run.project}/studies/{run.job_id}/runs/'
                                   f'{run.id}')
                        st.experimental_set_query_params(url=run_url)
                        st.session_state.run_url = run_url
                        st.session_state.active_option = 'Load from a URL'
                        st.session_state['run'] = run
                    else:
                        st.session_state['run'] = None


def load_sample():
    sample_folder = Path(f'{st.session_state.target_folder}/sample')
    leed_summary_folder = sample_folder.joinpath('leed-summary')

    with open(leed_summary_folder.joinpath('summary.json')) as json_file:
        summary = json.load(json_file)
    with open(leed_summary_folder.joinpath('summary_grid.json')) as json_file:
        summary_grid = json.load(json_file)
    with open(leed_summary_folder.joinpath('states_schedule.json')) as json_file:
        states_schedule = json.load(json_file)
    if leed_summary_folder.joinpath('states_schedule_err.json').is_file():
        with open(leed_summary_folder.joinpath('states_schedule_err.json')) as json_file:
            states_schedule_err = json.load(json_file)
    else:
        states_schedule_err = None

    vtjks_file = Path(sample_folder, 'vis_set.vtkjs')

    return (leed_summary_folder, vtjks_file, summary, summary_grid,
            states_schedule, states_schedule_err)
