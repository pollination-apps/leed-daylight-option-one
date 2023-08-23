"""Functions to download results."""
import streamlit as st
from packaging import version


def check_run_recipe(study_tab):
    """Checks the run status and recipe version."""
    run = st.session_state.run
    if run.status.status.value != 'Succeeded':
        st.error(
            'The run status must be \'Succeeded\'. '
            f'The input run has status \'{run.status.status.value}\'.'
        )
        st.stop()
    if f'{run.recipe.owner}/{run.recipe.name}' != \
        'pollination/leed-daylight-option-one':
        st.error(
            'This app is designed to work with pollination/leed-daylight-option-one '
            f'recipe. The input run is using {run.recipe.owner}/{run.recipe.name}.'
        )
        st.stop()
    if version.parse(run.recipe.tag) < version.parse('0.0.19'):
        with study_tab:
            st.error(
                'Only versions pollination/leed-daylight-option-one:0.0.19 or higher '
                f'are valid. Current version of the recipe: {run.recipe.tag}.'
            )
        st.stop()
