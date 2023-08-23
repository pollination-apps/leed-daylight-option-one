"""Functions to download results."""
import streamlit as st

from pollination_streamlit.interactors import Run
from pollination_streamlit.api.client import ApiClient
from pollination_streamlit.selectors import get_api_client, run_selector
from pollination_streamlit_io import (auth_user, select_account, select_project,
    select_study, select_run)


def select_load_method():
    """Select how to load the results."""
    st.radio(
    'Load method', options=st.session_state.options,
    horizontal=True, label_visibility='collapsed', key='load_method',
    index=st.session_state.options.index(st.session_state.active_option)
    )


st.cache_data
def select_menu(api_client: ApiClient, user: dict):
    """Select menu to navigate to a run."""
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

                        st.session_state.run_folder = \
                            st.session_state.data_folder.joinpath(run.id)
                        st.session_state.run = run
                    else:
                        st.session_state.run = None


def get_run():
    """Get run."""
    if st.session_state['load_method'] != ' Try the sample run':
        api_client = get_api_client()
        user = auth_user('auth-user', api_client)
    if st.session_state['load_method'] == 'Load from a project':
        select_menu(api_client, user)
    elif st.session_state['load_method'] == 'Load from a URL':
        run = run_selector(
            api_client, default=st.session_state['run_url'],
            help='Paste run URL.'
        )
        st.session_state['run'] = run


def study_menu():
    """Select load method and get run."""
    select_load_method()
    get_run()
