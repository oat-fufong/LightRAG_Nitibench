pipeline {
    agent { label 'gpu-agent-5' }

    parameters {
        // --- Infrastructure ---
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

        // --- LightRAG server ---
        string(
            name: 'LLM_MODEL',
            defaultValue: 'deepseek/deepseek-v4-flash',
            description: 'LLM model for LightRAG (OpenRouter format: provider/model)'
        )
        string(
            name: 'EMBEDDING_MODEL',
            defaultValue: 'openai/text-embedding-3-small',
            description: 'Embedding model for LightRAG (OpenRouter format: provider/model)'
        )
        string(
            name: 'EMBEDDING_DIM',
            defaultValue: '1536',
            description: 'Embedding dimension matching the embedding model'
        )
        string(
            name: 'LLM_MAX_TOKENS',
            defaultValue: '8000',
            description: 'Max output tokens for LightRAG LLM responses'
        )
        string(
            name: 'TOP_K',
            defaultValue: '40',
            description: 'Number of entities/relations retrieved from knowledge graph per query'
        )
        string(
            name: 'MAX_ASYNC',
            defaultValue: '4',
            description: 'Max concurrent LLM requests inside LightRAG server'
        )

        // --- Query ---
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
        string(
            name: 'QUESTION_LIMIT',
            defaultValue: '0',
            description: 'Cap number of questions to run (0 = all; use 5-10 for quick smoke tests)'
        )

        // --- Evaluation judge ---
        string(
            name: 'JUDGE_MODEL',
            defaultValue: 'openai/gpt-4o-mini',
            description: 'LLM judge model for coverage/contradiction scoring (OpenRouter format)'
        )
        string(
            name: 'JUDGE_MAX_TOKENS',
            defaultValue: '2048',
            description: 'Max tokens for judge model response'
        )
        string(
            name: 'BATCH_SIZE',
            defaultValue: '50',
            description: 'Number of questions evaluated concurrently by the judge'
        )
    }

    environment {
        OPENROUTER_API_KEY = credentials('OPENROUTER_API_KEY')
        OPENAI_API_KEY     = credentials('OPENROUTER_API_KEY')

        HTTP_PROXY  = 'http://10.0.0.3:3128'
        HTTPS_PROXY = 'http://10.0.0.3:3128'
        NO_PROXY    = 'localhost,127.0.0.1,metadata.google.internal,lightrag'

        // Infrastructure
        FILESTORE_PATH = "${params.FILESTORE_PATH}"
        RESULT_PATH    = "${params.RESULT_PATH}"

        // LightRAG server
        LLM_MODEL       = "${params.LLM_MODEL}"
        EMBEDDING_MODEL = "${params.EMBEDDING_MODEL}"
        EMBEDDING_DIM   = "${params.EMBEDDING_DIM}"

        // Query
        LLM_MAX_TOKENS  = "${params.LLM_MAX_TOKENS}"
        TOP_K           = "${params.TOP_K}"
        MAX_ASYNC       = "${params.MAX_ASYNC}"
        LIGHTRAG_MODE        = "${params.LIGHTRAG_MODE}"
        LIGHTRAG_CONCURRENCY = "${params.LIGHTRAG_CONCURRENCY}"
        QUESTION_LIMIT       = "${params.QUESTION_LIMIT}"

        // Evaluation
        JUDGE_MODEL      = "${params.JUDGE_MODEL}"
        JUDGE_MAX_TOKENS = "${params.JUDGE_MAX_TOKENS}"
        BATCH_SIZE       = "${params.BATCH_SIZE}"
    }

    stages {
        stage('Init Submodules') {
            steps {
                sh 'git submodule update --init --recursive'
            }
        }

        stage('Prepare Config') {
            steps {
                sh 'cp LightRAG_Prototype/.env.poc LightRAG_Prototype/.env'
            }
        }

        stage('Cleanup') {
            steps {
                sh 'docker compose down --remove-orphans || true'
            }
        }

        stage('Generate Metric Config') {
            steps {
                script {
                    sh 'mkdir -p nitibench/config/all_e2e_metric_config'
                    writeFile(
                        file: 'nitibench/config/all_e2e_metric_config/lightrag_tax_metric.yaml',
                        text: """\
chunk_node_path: /app/LRG/chunking/reduced_golden/nodes.json
golden_node_path: /app/LRG/chunking/reduced_golden/nodes.json

result_dir: /app/results

llm_config:
  model: ${params.JUDGE_MODEL}
  base_url: https://openrouter.ai/api/v1
  max_tokens: ${params.JUDGE_MAX_TOKENS}
  temperature: 0.3
  n: 1

eval_retrieval: False
batch_size: ${params.BATCH_SIZE}
datasets: ["tax"]
"""
                    )
                }
            }
        }

        stage('Build Images') {
            steps {
                sh 'docker compose build'
            }
        }

        stage('Start LightRAG') {
            steps {
                sh '''
                    docker compose up -d --wait --wait-timeout 180 lightrag
                    echo "LightRAG is healthy"
                    docker compose ps lightrag
                '''
            }
        }

        stage('Generate Responses') {
            steps {
                sh '''
                    docker compose run --rm \
                        -e OPENROUTER_API_KEY="${OPENROUTER_API_KEY}" \
                        evaluator \
                        python /app/lightrag_response.py \
                            --dataset /app/test_data/hf_tax.csv \
                            --output /app/results/tax_response.json \
                            --url http://lightrag:9621 \
                            --mode ${LIGHTRAG_MODE} \
                            --concurrency ${LIGHTRAG_CONCURRENCY} \
                            --limit ${QUESTION_LIMIT}
                '''
            }
        }

        stage('Evaluate') {
            steps {
                sh '''
                    docker compose run --rm \
                        -e OPENROUTER_API_KEY="${OPENROUTER_API_KEY}" \
                        -e OPENAI_API_KEY="${OPENAI_API_KEY}" \
                        evaluator \
                        python /app/LRG/script/metric_e2e.py \
                            --config_path /app/LRG/config/all_e2e_metric_config/lightrag_tax_metric.yaml
                '''
            }
        }
    }

    post {
        always {
            sh 'docker compose down --rmi local --remove-orphans || true'
        }
        success {
            echo 'Pipeline complete — results written to ${RESULT_PATH}'
        }
        unsuccessful {
            echo 'Pipeline failed — check logs above'
        }
    }
}
