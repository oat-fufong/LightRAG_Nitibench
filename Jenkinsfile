pipeline {
    agent { label 'gpu-agent-5' }

    parameters {
        string(
            name: 'FILESTORE_PATH',
            defaultValue: '/mnt/filestore/lightrag/rag_storage',
            description: 'Filestore path where pre-processed LightRAG knowledge graph is stored'
        )
        string(
            name: 'RESULT_PATH',
            defaultValue: '/mnt/filestore/lightrag/results',
            description: 'Path to write tax_response.json and evaluation results'
        )
        choice(
            name: 'LIGHTRAG_MODE',
            choices: ['hybrid', 'local', 'global', 'naive', 'mix'],
            description: 'LightRAG query mode'
        )
        string(
            name: 'LIGHTRAG_CONCURRENCY',
            defaultValue: '3',
            description: 'Number of parallel queries to LightRAG'
        )
    }

    environment {
        HTTP_PROXY  = 'http://10.0.0.3:3128'
        HTTPS_PROXY = 'http://10.0.0.3:3128'
        NO_PROXY    = 'localhost,127.0.0.1,metadata.google.internal,lightrag'
        FILESTORE_PATH      = "${params.FILESTORE_PATH}"
        RESULT_PATH         = "${params.RESULT_PATH}"
        LIGHTRAG_MODE       = "${params.LIGHTRAG_MODE}"
        LIGHTRAG_CONCURRENCY = "${params.LIGHTRAG_CONCURRENCY}"
    }

    stages {
        stage('Cleanup') {
            steps {
                sh 'docker compose down --remove-orphans || true'
            }
        }

        stage('Build Images') {
            steps {
                sh 'docker compose build'
            }
        }

        stage('Start LightRAG') {
            steps {
                withCredentials([
                    string(credentialsId: 'OPENROUTER_API_KEY', variable: 'OPENROUTER_API_KEY')
                ]) {
                    sh '''
                        # Inject API key into LightRAG env file
                        sed -i "s|LLM_BINDING_API_KEY=.*|LLM_BINDING_API_KEY=${OPENROUTER_API_KEY}|" LightRAG_Prototype/.env
                        sed -i "s|EMBEDDING_BINDING_API_KEY=.*|EMBEDDING_BINDING_API_KEY=${OPENROUTER_API_KEY}|" LightRAG_Prototype/.env

                        docker compose up -d lightrag
                        echo "Waiting for LightRAG to be healthy..."
                        docker compose ps lightrag
                    '''
                }
            }
        }

        stage('Generate Responses') {
            steps {
                withCredentials([
                    string(credentialsId: 'OPENROUTER_API_KEY', variable: 'OPENROUTER_API_KEY')
                ]) {
                    sh '''
                        docker compose run --rm \
                            -e OPENROUTER_API_KEY="${OPENROUTER_API_KEY}" \
                            evaluator \
                            python /app/lightrag_response.py \
                                --dataset /app/test_data/hf_tax.csv \
                                --output /app/results/tax_response.json \
                                --url http://lightrag:9621 \
                                --mode ${LIGHTRAG_MODE} \
                                --concurrency ${LIGHTRAG_CONCURRENCY}
                    '''
                }
            }
        }

        stage('Evaluate') {
            steps {
                withCredentials([
                    string(credentialsId: 'OPENROUTER_API_KEY', variable: 'OPENROUTER_API_KEY')
                ]) {
                    sh '''
                        docker compose run --rm \
                            -e OPENROUTER_API_KEY="${OPENROUTER_API_KEY}" \
                            evaluator \
                            python /app/LRG/script/metric_e2e.py \
                                --config_path /app/LRG/config/all_e2e_metric_config/lightrag_tax_metric.yaml
                    '''
                }
            }
        }
    }

    post {
        always {
            sh 'docker compose down --remove-orphans || true'
        }
        success {
            echo 'Pipeline complete — results written to ${RESULT_PATH}'
        }
        unsuccessful {
            echo 'Pipeline failed — check logs above'
        }
    }
}
