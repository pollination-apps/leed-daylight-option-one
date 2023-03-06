"""Pollination LEED Daylight Option I App."""
import streamlit as st
from packaging import version

from pollination_streamlit.selectors import get_api_client
from pollination_streamlit_io import auth_user
from pollination_streamlit_viewer import viewer

from helper import (download_files, process_summary,
    show_warnings_and_errors, process_space, process_states_schedule,
    process_ase, select_menu)
from inputs import initialize


st.set_page_config(
    page_title='LEED Daylight Option I', layout='wide',
    page_icon='https://app.pollination.cloud/favicon.ico'
)

def main():
    # title
    st.header('LEED Daylight Option I')
    
    # initialize session state variables
    initialize()

    # set up tabs
    run_tab, summary_tab, space_tab, states_schedule_tab, dir_ill_tab, visualization_tab = \
        st.tabs(['Get run', 'Summary report', 'Space by space breakdown',
             'States schedule', 'Direct Illuminance', 'Visualization']
        )

    with run_tab:
        api_client = get_api_client()
        user = auth_user('auth-user', api_client)
        run = select_menu(api_client, user)

    if run is not None:
        if run.status.status.value != 'Succeeded':
            st.error(
                'The run status must be \'Succeeded\'. '
                f'The input run has status \'{run.status.status.value}\'.'
            )
            st.stop()
        if f'{run.recipe.owner}/{run.recipe.name}' != 'pollination/leed-daylight-option-one':
            st.error(
                'This app is designed to work with pollination/leed-daylight-option-one '
                f'recipe. The input run is using {run.recipe.owner}/{run.recipe.name}.'
            )
            st.stop()
        if version.parse(run.recipe.tag) < version.parse('0.0.14'):
            with run_tab:
                st.error(
                    'Only versions pollination/leed-daylight-option-one:0.0.14 or higher '
                    f'are valid. Current version of the recipe: {run.recipe.tag}.'
                )
            st.stop()

        with st.spinner('Downloading files...'):
            folder, vtjks_file, summary, summary_grid, states_schedule, states_schedule_err = download_files(run)
        
        with summary_tab:
            process_summary(summary)   
            show_warnings_and_errors(summary, summary_grid, states_schedule_err)

        with space_tab:
            process_space(summary_grid)

        with states_schedule_tab:
            process_states_schedule(states_schedule)

        with dir_ill_tab:
            process_ase(folder)
            
        with visualization_tab:
            viewer(content=vtjks_file.read_bytes(), key='viz')

if __name__ == '__main__':
    main()
