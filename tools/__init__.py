from .llm_client import OllamaClient
from .scanner import scan_project, ProjectSummary
from .file_writer import (
    extract_files_from_response, write_files,
    save_project_context, load_project_context,
    _try_parse_json, _try_extract_embedded_json,
)
from .scaffold import scaffold_project
from .gitignore import write_gitignore, write_env_example
from .manifests import get_manifest, FileSpec
from .generator import generate_files
from .domain_extractor import extract_domain
from .api_contract import extract_api_contract
from .fullstack import resolve_combo, COMBOS, write_shared_files
from .web_research import (
    web_search, search_and_summarize,
    fetch_stack_versions, fetch_scaffold_command,
    versions_to_context, clear_cache, cache_info,
)
from .task_classifier import classify, TaskResult
from .knowledge_base import (
    extract_infra_context, get_global_kb,
    InfraContext, GlobalKnowledge,
)
from .infra_generator import generate_infra
from .validator import validate, print_result as print_validation, ValidationResult
from .dependency_fixer import fix_dependencies, print_dep_report
from .self_healer import heal as auto_heal
from .setup_runner import (
    run_post_generation_pipeline, delivery_report,
    setup_env, install_deps, health_check,
)
from .research_agent import (
    research_topic, research_for_task,
    research_and_answer, list_knowledge, clear_knowledge,
)
from .intent_analyzer import analyze as analyze_intent, Intent
from .planner import Planner, Plan, Step
from .orchestrator_helpers import *
from .code_fixer import (
    fix_all, is_valid_content, fix_ts_content,
    fix_dto_imports, fix_guard_import_path,
    generate_barrel_files, integrate_module_into_app,
    preinstall_nestjs_deps, apply_fixes_to_project,
    ensure_db_in_app_module,
)
from .project_fixer import (
    fix_project, run_build, parse_errors,
    install_missing_packages, fix_wrong_import_paths,
    fix_code_errors_with_llm, ensure_node_modules,
)
from .run_verifier import try_run, extract_runtime_errors, check_db_and_warn
from .project_fixer import run_verify_fix_loop
from .db_strategy import (
    DbStrategy, detect_database, get_strategy,
    strategy_for_description, docker_service_for_db,
    nestjs_db_module_config, python_db_config,
    STRATEGIES, DB_ALIASES,
)
from .knowledge_templates import (
    DOCKER_COMPOSE_FULL, DOCKER_COMPOSE_DEV,
    REDIS_SLAVE_CONF, REDIS_SENTINEL_CONF,
    DOCKERFILE_NESTJS, ENTRYPOINT_SH, ENTRYPOINT_SH_DEV,
    CONFIG_SERVICE_TS, REDIS_SENTINELS_CONFIG_TS, WINSTON_CONFIG_TS,
    APP_MODULE_FULL_TS, MAIN_TS_FULL, TSCONFIG_JSON, ENV_EXAMPLE_FULL,
    REFERENCE_PACKAGES, REFERENCE_DEV_PACKAGES,
    MONGOOSE_SCHEMA_EXAMPLE,
    KAFKA_PRODUCER_EXAMPLE, WEBSOCKET_GATEWAY_EXAMPLE, BULL_PROCESSOR_EXAMPLE,
)
from .file_trainer import (
    train_file, train_directory, train_project,
    get_relevant_templates,
)
from .vector_store import (backfill_embeddings,
    save as ts_save, get as ts_get,
    search_relevant as ts_search,
    list_all as ts_list_all,
    export_markdown as ts_export,
    clear_all as ts_clear,
)

from .embeddings import embed, model_available, cosine_similarity
