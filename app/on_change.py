"""On_change functions for Streamlit widgets."""
import streamlit as st


def radio_show_all_grids(grids_ids: list):
    if st.session_state['show_all_grids']:
        st.session_state['select_grids'] = []
    else:
        st.session_state['select_grids'] = grids_ids


def multiselect_grids(grids_ids: list):
    if len(st.session_state['select_grids']) != len(grids_ids):
        st.session_state['show_all_grids'] = True


def radio_show_all(aperture_groups: list):
    if st.session_state['show_all']:
        st.session_state['select_aperture_groups'] = []
    else:
        st.session_state['select_aperture_groups'] = aperture_groups


def multiselect_aperture_groups(aperture_groups: list):
    if len(st.session_state['select_aperture_groups']) != len(aperture_groups):
        st.session_state['show_all'] = True


def radio_show_all_ase(grids_info: list):
    if st.session_state['show_all_ase']:
        st.session_state['select_ase'] = []
    else:
        st.session_state['select_ase'] = grids_info


def multiselect_ase(grids_info: list):
    if len(st.session_state['select_ase']) != len(grids_info):
        st.session_state['show_all_ase'] = True


def legend_min_on_change():
    if st.session_state['legend_min'] >= st.session_state['legend_max']:
        st.session_state['legend_min'] = st.session_state['legend_max'] - 0.5

def legend_max_on_change():
    if st.session_state['legend_max'] <= st.session_state['legend_min']:
        st.session_state['legend_max'] = st.session_state['legend_min'] + 0.5
