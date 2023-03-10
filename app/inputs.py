import streamlit as st
from pathlib import Path


def initialize():
    """Initialize any of the session state variables if they don't already exist."""
    # initialize session state variables
    if 'target_folder' not in st.session_state:
        st.session_state.target_folder = Path(__file__).parent
    if not 'select_aperture_groups' in st.session_state:
        st.session_state['select_aperture_groups'] = []
    if not 'select_grids' in st.session_state:
        st.session_state['select_grids'] = []
