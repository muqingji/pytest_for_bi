pipeline {
    agent any

    options {
        skipDefaultCheckout(true)
        timestamps()
        disableConcurrentBuilds()
    }

    parameters {
        choice(name: 'TEST_ENV', choices: ['112', 'test', 'hk', 'prod'], description: 'Environment suffix; 112 runs the translation workbench suite')
        string(name: 'CASE_FILTER', defaultValue: '', description: 'Optional pytest -k expression, for example: get_user')
        booleanParam(name: 'USE_CONFIG_CREDENTIAL', defaultValue: true, description: 'Inject environment local JSON from Jenkins credentials')
    }

    environment {
        PYTHON_BIN = 'python3.11'
        VENV_DIR = '.venv'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Install dependencies') {
            steps {
                sh '''
                    set -eu
                    "$PYTHON_BIN" --version
                    "$PYTHON_BIN" -m venv "$VENV_DIR"
                    "$VENV_DIR/bin/python" -m pip install --upgrade pip
                    "$VENV_DIR/bin/python" -m pip install -r requirements.txt
                '''
            }
        }

        stage('Offline quality gate') {
            steps {
                sh '''
                    set -eu
                    mkdir -p artifacts
                    "$VENV_DIR/bin/python" -m pytest tests \
                        --junitxml=artifacts/framework-junit.xml
                    PYTHONPATH=qa-agents/src "$VENV_DIR/bin/python" -m pytest -q qa-agents/tests \
                        --junitxml=artifacts/qa-agents-junit.xml
                '''
            }
        }

        stage('Run interface cases') {
            steps {
                script {
                    def runTests = {
                        sh '''
                            set -eu
                            mkdir -p artifacts allure-results
                            local_config="config/environment.${TEST_ENV}.local.json"
                            cleanup() { rm -f "$local_config"; }
                            trap cleanup EXIT

                            if [ -n "${LOCAL_ENV_CONFIG:-}" ]; then
                                install -m 600 "$LOCAL_ENV_CONFIG" "$local_config"
                            fi

                            if [ "$TEST_ENV" = "112" ]; then
                                PYTHONPATH=src "$VENV_DIR/bin/python" scripts/preflight_112_auth.py
                                set -- -n 0 tests/translation_workbench/test_translation_language.py
                            else
                                set --
                            fi

                            if [ -n "$CASE_FILTER" ]; then
                                TEST_ENV="$TEST_ENV" "$VENV_DIR/bin/python" -m pytest --env "$TEST_ENV" \
                                    "$@" -k "$CASE_FILTER" --alluredir=allure-results \
                                    --clean-alluredir --junitxml=artifacts/interface-junit.xml
                            else
                                TEST_ENV="$TEST_ENV" "$VENV_DIR/bin/python" -m pytest --env "$TEST_ENV" \
                                    "$@" --alluredir=allure-results \
                                    --clean-alluredir --junitxml=artifacts/interface-junit.xml
                            fi
                        '''
                    }

                    if (params.USE_CONFIG_CREDENTIAL) {
                        def credentialId = "interface-test-${params.TEST_ENV}-config"
                        withCredentials([file(credentialsId: credentialId, variable: 'LOCAL_ENV_CONFIG')]) {
                            runTests()
                        }
                    } else {
                        runTests()
                    }
                }
            }
        }
    }

    post {
        always {
            sh '''
                if [ -d allure-results ]; then
                    "$VENV_DIR/bin/python" scripts/print_allure_report.py allure-results \
                        --output artifacts/interface-report.txt \
                        --summary-only --quiet || true
                fi
            '''
            junit allowEmptyResults: true, testResults: 'artifacts/*-junit.xml'
            archiveArtifacts allowEmptyArchive: true, artifacts: 'allure-results/**,artifacts/**'
            allure includeProperties: false, jdk: '', results: [[path: 'allure-results']]
        }
    }
}
