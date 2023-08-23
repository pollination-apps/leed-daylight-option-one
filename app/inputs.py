"""Initialize sessions state variables."""
from pathlib import Path
import streamlit as st


def initialize():
    """Initialize the session state variables."""
    if 'target_folder' not in st.session_state:
        st.session_state.target_folder = Path(__file__).parent
    if 'data_folder' not in st.session_state:
        st.session_state.data_folder = \
            st.session_state.target_folder.joinpath('data')
    if 'sample_folder' not in st.session_state:
        st.session_state.sample_folder = \
            st.session_state.target_folder.joinpath('sample')

    if 'select_aperture_groups' not in st.session_state:
        st.session_state.select_aperture_groups = []
    if 'select_grids' not in st.session_state:
        st.session_state.select_grids = []

    if 'active_option' not in st.session_state:
        st.session_state.active_option = 'Load from a project'
    if 'options' not in st.session_state:
        st.session_state.options = [
            'Load from a project', 'Try the sample run'
        ]
    query_params = st.experimental_get_query_params()
    if 'load_method' not in st.session_state:
        if 'url' in query_params:
            st.session_state.active_option = 'Load from a URL'
            st.session_state.run_url = query_params['url'][0]
    if 'run_url' not in st.session_state:
        st.session_state.run_url = None
    if 'run' not in st.session_state:
        st.session_state.run = None
    if 'project_id' not in st.session_state:
        st.session_state.project_id = None
    if 'study_id' not in st.session_state:
        st.session_state.study_id = None
    if 'run_id' not in st.session_state:
        st.session_state.run_id = None
    if 'run_folder' not in st.session_state:
        st.session_state.run_folder = None
