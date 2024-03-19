"""Functions to support the leed-daylight-option-one app."""
import json
from pathlib import Path
import pandas as pd

import streamlit as st
from ladybug.datacollection import HourlyContinuousCollection

from on_change import (radio_show_all_grids, radio_show_all,
    multiselect_grids, multiselect_aperture_groups, radio_show_all_ase,
    multiselect_ase, legend_min_on_change, legend_max_on_change)
from plot import figure_grids, figure_aperture_group_schedule, figure_ase, get_figure_config

UNITS_AREA = {
    'Meters': 'm',
    'Millimeters': 'mm',
    'Feet': 'ft',
    'Inches': 'in',
    'Centimeters': 'cm'
}

def process_summary(summary: dict, hb_model):
    """Process summary."""
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

    df = pd.DataFrame.from_dict(summary, orient='index').transpose()
    df.rename(columns={'sda': 'sDA [%]', 'ase': 'ASE [%]'}, inplace=True)
    # total floor area / total sensor count
    if 'total_floor_area' in summary:
        floor_area_passing_sda = summary['floor_area_passing_sda']
        floor_area_passing_sda_text = \
            f'Floor area passing sDA: {round(floor_area_passing_sda, 2)} {UNITS_AREA[hb_model.units]}<sup style>2</sup>'
        st.markdown(floor_area_passing_sda_text, unsafe_allow_html=True)

        floor_area_passing_ase = summary['floor_area_passing_ase']
        floor_area_passing_ase_text = \
            f'Floor area passing ASE: {round(floor_area_passing_ase, 2)} {UNITS_AREA[hb_model.units]}<sup style>2</sup>'
        st.markdown(floor_area_passing_ase_text, unsafe_allow_html=True)

        total_floor_area = summary['total_floor_area']
        total_floor_area_text = f'Total floor area: {round(total_floor_area, 2)} {UNITS_AREA[hb_model.units]}<sup style>2</sup>'
        st.markdown(total_floor_area_text, unsafe_allow_html=True)

        df.rename(columns={
            'floor_area_passing_sda': 'Floor area passing sDA',
            'floor_area_passing_ase': 'Floor area passing ASE',
            'total_floor_area': 'Total floor area',
            'credits': 'LEED Credits'
            }, inplace=True
        )
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

        df.rename(columns={
            'sensor_count_passing_sda': 'Sensor count passing sDA',
            'sensor_count_passing_ase': 'Sensor count passing ASE',
            'total_sensor_count': 'Total sensor count',
            'credits': 'LEED Credits'
            }, inplace=True
        )

    csv = df.to_csv(index=False, float_format='%.2f')
    st.download_button(
        'Download model breakdown', csv, 'summary.csv', 'text/csv',
        key='download_model_breakdown'
    )


def show_errors(summary: dict, states_schedule_err: dict):
    """Show errors from simulation."""
    if 'note' in summary:
        st.error(summary['note'])
    if bool(states_schedule_err):
        states_schedule_err_label = (
            'Hours where more than 2% of the floor area receives direct '
            'illuminance of 1000 lux or more.'
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
                fig = figure_grids(grid_id, states_schedule_err)
                st.plotly_chart(fig, use_container_width=True, config=get_figure_config(grid_id))


def process_space(summary_grid: dict, states_schedule_err: dict):
    """Process space."""
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
    df = df.rename_axis('Space Name').reset_index()
    round_columns = [
        'ASE [%]', 'sDA [%]', 'Floor area passing ASE', 'Floor area passing sDA',
        'Total floor area', 'Sensor count passing ASE', 'Sensor count passing sDA',
        'Total sensor count'
    ]
    style_round = {column: '{:.2f}' for column in round_columns}

    ase_notes = []
    for room_id, data in summary_grid.items():
        if 'ase_note' in data:
            ase_notes.append(data['ase_note'])
        else:
            ase_notes.append('')
    if not all(n=='' for n in ase_notes):
        df['ASE Note'] = ase_notes

    warning_rooms = []
    for room_id in df['Space Name']:
        if room_id in states_schedule_err.keys():
            warning_rooms.append('There are hours where more than 2% of the '
                                 'floor area receives direct illuminance of '
                                 '1000 lux or more.')
        else:
            warning_rooms.append('')
    if not all(w=='' for w in warning_rooms):
        df['Warning'] = warning_rooms

    def color_ase(val):
        alpha = 0.3
        color = f'rgba(255, 170, 0, {alpha})' if val > 10 else f'rgba(0, 255, 0, {alpha})'
        return f'background-color: {color}'
    def color_sda(val):
        alpha = 0.3
        if val >= 75:
            color = f'rgba(0, 255, 0, {alpha})'
        elif val >= 55:
            color = f'rgba(85, 255, 0, {alpha})'
        elif val >= 40:
            color = f'rgba(170, 255, 0, {alpha})'
        else:
            color = f'rgba(255, 170, 0, {alpha})'
        return f'background-color: {color}'
    def color_fail(val, failed_rooms):
        alpha = 0.3
        if val['Space Name'] in failed_rooms:
            color = [f'background-color: rgba(255, 0, 0, {alpha})']
        else:
            color = ['']
        return color * len(val)

    if states_schedule_err.keys():
        failed_rooms = list(states_schedule_err.keys())
        df_s = df.style.map(color_ase, subset=['ASE [%]']).map(
            color_sda, subset=['sDA [%]']).apply(
            color_fail, failed_rooms=failed_rooms, axis=1).format(style_round)
    else:
        df_s = df.style.map(color_ase, subset=['ASE [%]']).map(
            color_sda, subset=['sDA [%]']).format(style_round)

    st.table(df_s)

    csv = df.to_csv(index=False, float_format='%.2f')
    st.download_button(
        'Download space by space breakdown', csv, 'summary_space.csv',
        'text/csv', key='download_summary_space'
    )


def process_states_schedule(states_schedule: dict):
    """Process states schedule."""
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
        datacollection = \
            HourlyContinuousCollection.from_dict(states_schedule[aperture_group])
        fig = figure_aperture_group_schedule(aperture_group, datacollection)
        st.plotly_chart(fig, use_container_width=True, config=get_figure_config(aperture_group))


def process_ase(folder: Path):
    """Process ASE."""
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

    _labels = {
        True: 'Select sensor grids',
        False: 'Show all sensor grids'
    }
    st.radio(
        'Select or show all sensor grids',
        options=[True, False], format_func=lambda x: _labels[x],
        horizontal=True, label_visibility='collapsed',
        on_change=radio_show_all_ase, args=(grids_info,), key='show_all_ase'
    )

    st.multiselect(
        'Select sensor grids', grids_info, format_func=lambda gi: gi['name'],
        label_visibility='collapsed', on_change=multiselect_ase, args=(grids_info,),
        key='select_ase'
    )

    legend_min, legend_max = st.columns(2)
    with legend_min:
        st.number_input(
            'Legend minimum', min_value=float(0), max_value=float(100),
            value=float(0), format='%.2f',
            key='legend_min', on_change=legend_min_on_change)
    with legend_max:
        st.number_input(
            'Legend maximum', min_value=float(0), max_value=float(100),
            value=float(10), format='%.2f',
            key='legend_max', on_change=legend_max_on_change)

    for grid_info in st.session_state['select_ase']:
        figure_ase(grid_info, results_folder)
