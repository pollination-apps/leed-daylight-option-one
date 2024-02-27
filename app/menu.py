"""Functions to download results."""
import streamlit as st

from pollination_streamlit.interactors import Run
from pollination_streamlit.api.client import ApiClient
from pollination_streamlit.selectors import get_api_client, run_selector
from pollination_streamlit_io import (auth_user, select_account, select_project,
    select_study, select_run)
from pollination_io.api.user import UserApi


def select_load_method():
    """Select how to load the results."""
    st.radio(
    'Load method', options=st.session_state.options,
    horizontal=True, label_visibility='collapsed', key='load_method',
    index=st.session_state.options.index(st.session_state.active_option)
    )


def select_menu(api_client: ApiClient, user_api: UserApi):
    """Select menu to navigate to a run."""
    col_1, col_2 = st.columns(2)
    col_3, col_4 = st.columns(2)
    if user_api.client.is_authenticated:
        user = user_api.get_user()
        username = user['username']
        with col_1:
            account = select_account(
                'select-account',
                api_client,
                default_account_username=username
            )

        if account:
            if 'owner' in account:
                username = account['account_name']
            with col_2:
                project = select_project(
                    'select-project',
                    api_client,
                    project_owner=username
                )

            if project and 'name' in project:
                st.session_state['project_id'] = project['id']
                with col_3:
                    study = select_study(
                        'select-study',
                        api_client,
                        project_name=project['name'],
                        project_owner=username
                    )

                if study and 'id' in study:
                    st.session_state['study_id'] = study['id']
                    with col_4:
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
                        run = Run(project_owner,
                                  project_name,
                                  job_id,
                                  run_id,
                                  api_client)

                        st.session_state.run_folder = \
                            st.session_state.data_folder.joinpath(run.id)
                        st.session_state.run = run
                    else:
                        st.session_state.run = None


def get_run(api_client: ApiClient, user_api: UserApi):
    """Get run."""
    if st.session_state['load_method'] == 'Load from a project':
        select_menu(api_client, user_api)
    elif st.session_state['load_method'] == 'Load from a URL':
        run = run_selector(
            api_client, default=st.session_state['run_url'],
            help='Paste run URL.'
        )
        st.session_state['run'] = run


def study_menu():
    """Select load method and get run."""
    select_load_method()
    api_client = get_api_client()
    user_api = UserApi(api_client)
    get_run(api_client, user_api)
    return api_client, user_api
