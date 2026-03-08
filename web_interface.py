# === User config save/load helpers ===
def get_user_config_path():
    eid = st.session_state.get('employee_id')
    if eid:
        config_dir = BASE_DIR / "user_data" / eid / "configs"
        os.makedirs(config_dir, exist_ok=True)
        return config_dir / "user_config.json"
    return None

def load_user_config():
    path = get_user_config_path()
    if path and path.exists():
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            for k, v in data.items():
                # dimensions가 비어있는 값으로 덮어쓰지 않도록 보호
                if k == 'dimensions' and not v and st.session_state.get('dimensions'):
                    continue
                st.session_state[k] = v
            
            # Sync critical values to user .env file only (NOT os.environ to avoid cross-user contamination)
            if 'openai_api_key' in data and data['openai_api_key']:
                update_user_env('OPENAI_API_KEY', data['openai_api_key'])
            
            if 'selected_model' in data and data['selected_model']:
                update_user_env('OPENAI_MODEL', data['selected_model'])
                
        except Exception as e:
            st.warning(f"사용자 설정 로드 실패: {e}")

def save_user_config():
    path = get_user_config_path()
    if path:
        data = {}
        # Save only relevant keys
        for k in ["openai_api_key", "selected_model", "dimensions", "user_topic", "config_loaded", "config_file_name"]:
            if k in st.session_state:
                data[k] = st.session_state[k]
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            st.warning(f"사용자 설정 저장 실패: {e}")
"""
Web Interface for TaxoAdapt using Streamlit
Run with: streamlit run web_interface.py
"""
import streamlit as st
import os
import json
import csv
import tempfile
import yaml
import threading
from pathlib import Path
from config_manager import DimensionConfig
import subprocess
import sys
from dotenv import load_dotenv, set_key, find_dotenv
from user_auth import UserManager

# Get base directory
BASE_DIR = Path(__file__).parent.resolve()

# Load .env file from project directory (fallback)
ENV_PATH = os.path.join(BASE_DIR, '.env')
load_dotenv(ENV_PATH, override=True)

# Multi-user support
_user_manager = UserManager(BASE_DIR / "user_data")


def _sanitize_field_name(name: str) -> str:
    """
    Convert a dimension name into a valid Python identifier by
    replacing invalid characters with underscores and ensuring it
    doesn't start with a digit. Returns a non-empty identifier.
    """
    import re
    if not isinstance(name, str):
        name = str(name)
    # Replace any character that's not alphanumeric or underscore with '_'
    sanitized = re.sub(r'[^0-9a-zA-Z_]', '_', name)
    # Collapse multiple underscores first
    sanitized = re.sub(r'_+', '_', sanitized)
    # Strip trailing underscores only (not leading ones)
    sanitized = sanitized.rstrip('_')
    # If starts with digit, prefix with 'field_' instead of underscore (Pydantic doesn't allow leading underscores)
    if sanitized and sanitized[0].isdigit():
        sanitized = 'field_' + sanitized
    # Handle empty string case
    return sanitized or 'field'


def get_user_datasets_dir():
    """Get user-specific datasets directory"""
    eid = st.session_state.get('employee_id')
    if eid:
        d = BASE_DIR / "user_data" / eid / "datasets"
        os.makedirs(d, exist_ok=True)
        return d
    return BASE_DIR / "datasets"


def get_user_configs_dir():
    """Get user-specific configs directory"""
    eid = st.session_state.get('employee_id')
    if eid:
        d = BASE_DIR / "user_data" / eid / "configs"
        os.makedirs(d, exist_ok=True)
        return d
    return BASE_DIR / "configs"


def get_user_output_dir():
    """Get user-specific output directory"""
    eid = st.session_state.get('employee_id')
    if eid:
        d = BASE_DIR / "user_data" / eid / "save_output"
        os.makedirs(d, exist_ok=True)
        return d
    return BASE_DIR / "save_output"


def get_user_dataset_path(dataset_name):
    """Get full path to a user's dataset folder"""
    return get_user_datasets_dir() / dataset_name.lower().replace(' ', '_')


def get_user_code_dir():
    """Get user-specific code directory"""
    eid = st.session_state.get('employee_id')
    if eid:
        d = BASE_DIR / "user_data" / eid / "code"
        os.makedirs(d, exist_ok=True)
        return d
    return BASE_DIR


def get_user_env_path():
    """Get path to user-specific .env file"""
    eid = st.session_state.get('employee_id')
    if eid:
        user_code_dir = get_user_code_dir()
        return user_code_dir / '.env'
    return BASE_DIR / '.env'


def read_user_env_value(key, default=''):
    """Read a value from user-specific .env file WITHOUT modifying os.environ.
    This is safe for concurrent multi-user access."""
    user_env_path = get_user_env_path()
    if user_env_path.exists():
        try:
            with open(user_env_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, _, v = line.partition('=')
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k == key:
                            return v
        except Exception:
            pass
    return default


def get_effective_api_key(openai_api_key=None):
    """Get the effective OpenAI API key from session state or user env file.
    Priority: explicit param > session_state > user .env file"""
    if openai_api_key:
        return openai_api_key
    session_key = st.session_state.get('openai_api_key', '')
    if session_key:
        return session_key
    return read_user_env_value('OPENAI_API_KEY', '')


def ensure_user_env_exists():
    """Ensure user has their own .env file, create from template if needed"""
    user_env_path = get_user_env_path()
    if not user_env_path.exists():
        # Copy from global .env as template
        base_env_path = BASE_DIR / '.env'
        if base_env_path.exists():
            import shutil
            shutil.copy(base_env_path, user_env_path)
        else:
            # Create empty .env file
            user_env_path.touch()
    return user_env_path


def update_user_env(key, value):
    """Update user-specific .env file with key-value pair"""
    user_env_path = ensure_user_env_exists()
    set_key(str(user_env_path), key, value)


def get_user_prompts_path():
    """Get path to user-specific prompts.py file"""
    return get_user_code_dir() / "prompts.py"


def ensure_user_prompts_exists():
    """Ensure user has their own prompts.py file, create from template if needed"""
    user_prompts = get_user_prompts_path()
    if not user_prompts.exists():
        # Copy from global prompts.py as template
        original_prompts = BASE_DIR / 'prompts.py'
        if original_prompts.exists():
            import shutil
            shutil.copy(original_prompts, user_prompts)
            st.info(f"✨ Created user-specific prompts.py at {user_prompts}")
        else:
            st.error("Template prompts.py not found!")
    return user_prompts


def load_user_prompts_content():
    """Load current content of user's prompts.py file"""
    user_prompts = ensure_user_prompts_exists()
    try:
        with open(user_prompts, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        st.error(f"Error reading prompts.py: {e}")
        return ""


def show_login_page():
    """Display login page with employee ID input"""
    st.markdown("""
    <style>
    .login-container {
        max-width: 450px;
        margin: 80px auto;
        padding: 40px;
        border-radius: 12px;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
    }
    </style>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("### 🔬 TaxoAdapt")
        st.markdown("##### Taxonomy Generation Framework")
        st.markdown("---")
        st.markdown("**사번으로 로그인하세요**")

        with st.form("login_form"):
            employee_id = st.text_input(
                "사번 (Employee ID):",
                placeholder="예: P12345",
                max_chars=20
            )
            display_name = st.text_input(
                "이름 (선택사항):",
                placeholder="예: 홍길동",
                max_chars=30
            )
            submitted = st.form_submit_button("🔐 로그인", use_container_width=True)

            if submitted:
                if not employee_id.strip():
                    st.error("사번을 입력해주세요.")
                else:
                    try:
                        user_info = _user_manager.register_or_login(employee_id.strip(), display_name.strip())
                        st.session_state.employee_id = employee_id.strip()
                        st.session_state.user_info = user_info
                        st.session_state.logged_in = True
                        load_user_config()  # 로그인 시 사용자 설정 로드
                        st.rerun()
                    except Exception as e:
                        st.error(f"로그인 오류: {e}")

        st.markdown("---")
        st.caption("처음 로그인하면 자동으로 계정이 생성됩니다.")


# Page config
st.set_page_config(
    page_title="TaxoAdapt Interface",
    page_icon="🔬",
    layout="wide"
)

# Initialize session state
if 'config' not in st.session_state:
    st.session_state.config = None
if 'dimensions' not in st.session_state:
    st.session_state.dimensions = {}
if 'running' not in st.session_state:
    st.session_state.running = False
if 'user_topic' not in st.session_state:
    st.session_state.user_topic = 'battery'
if 'config_loaded' not in st.session_state:
    st.session_state.config_loaded = False
if 'config_file_name' not in st.session_state:
    st.session_state.config_file_name = None

# Load user config if logged in (this will sync to env variables)
if st.session_state.get('logged_in', False):
    load_user_config()
    print(f"[DEBUG] After load_user_config: dims={len(st.session_state.get('dimensions', {}))}, config_loaded={st.session_state.get('config_loaded')}, config_file_name={st.session_state.get('config_file_name')}")
# 중요: dimensions가 JSON에서 복원되었지만 config 객체가 없으면 복구
if st.session_state.get('dimensions') and not st.session_state.get('config'):
    st.session_state.config = DimensionConfig(config_path=None)
    st.session_state.config.dimensions = st.session_state.dimensions.copy()
    if not st.session_state.get('config_loaded'):
        st.session_state.config_loaded = True



def load_yaml_config(uploaded_file):
    """Load a YAML config file and return DimensionConfig"""
    content = uploaded_file.getvalue().decode('utf-8')
    raw = yaml.safe_load(content)
    
    print(f"[DEBUG] YAML content loaded: {raw}")
    
    config = DimensionConfig(config_path=None)
    config.dimensions = raw.get('dimensions', {})
    
    print(f"[DEBUG] Config dimensions set: {list(config.dimensions.keys())}")
    
    return config


def main():
    # ============ Login Gate ============
    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        show_login_page()
        return

    # ============ Logged-in user info ============
    employee_id = st.session_state.employee_id
    user_info = st.session_state.get('user_info', {})
    display_name = user_info.get('display_name', employee_id)

    st.title("🔬 TaxoAdapt - Taxonomy Generation Framework")
    st.markdown("---")
    
    # ============ Mode Selection ============
    # Show mode selector if no mode chosen yet, or always in sidebar
    with st.sidebar:
        # User info & logout
        st.markdown(f"👤 **{display_name}** (`{employee_id}`)")
        if st.button("🚪 로그아웃", key="logout_btn", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        st.markdown("---")

        st.header("🏠 메뉴 선택")
        mode = st.radio(
            "기능 선택:",
            ["🛠️ Taxonomy 입력 만들기", "▶️ TaxoAdapt 실행", "💾 결과값 저장", "📜 실행 이력"],
            key="mode_selector",
            help="원하는 기능을 선택하세요"
        )
        
        st.markdown("---")
        
        # ============ Common: API Key ============
        st.subheader("🔑 API Key")
        
        # Read user-specific .env file (without modifying os.environ)
        user_env_path = ensure_user_env_exists()
        default_openai_key = read_user_env_value('OPENAI_API_KEY', '')
        
        if user_env_path.exists():
            if default_openai_key:
                st.success(f"✅ .env (Key: ...{default_openai_key[-6:] if len(default_openai_key) > 6 else '***'})")
            else:
                st.warning("⚠️ user .env: OPENAI_API_KEY 비어있음")
        else:
            st.warning("⚠️ user .env 파일 없음")
        
        # Load user-specific API key if present
        user_api_key = st.session_state.get("openai_api_key", default_openai_key)
        openai_api_key = st.text_input(
            "OpenAI API Key:",
            value=user_api_key if user_api_key else "",
            type="password",
            help="Auto-loaded from .env or user config",
            key="openai_api_key_input"
        )
        # Initialize session state for API key tracking
        if "_api_key_initialized" not in st.session_state:
            st.session_state["openai_api_key"] = user_api_key if user_api_key else ""
            st.session_state["_api_key_initialized"] = True
        
        # Only update on explicit user change (comparing with widget key value)
        widget_key_val = st.session_state.get("openai_api_key_input", "")
        if widget_key_val and widget_key_val != st.session_state.get("openai_api_key", ""):
            st.session_state["openai_api_key"] = widget_key_val
            save_user_config()
            if widget_key_val:
                update_user_env('OPENAI_API_KEY', widget_key_val)
        
        # ============ 병렬 실행용 추가 API Keys ============
        with st.expander("🔑 병렬 실행용 추가 API Keys (선택사항)", expanded=False):
            st.caption("dimension별 병렬 실행 시 각각 다른 API key를 사용합니다. 비워두면 기본 key만 사용합니다.")
            extra_keys_changed = False
            for i in range(1, 6):  # OPENAI_API_KEY_1 ~ _5
                env_key_name = f'OPENAI_API_KEY_{i}'
                existing_val = read_user_env_value(env_key_name, '')
                new_val = st.text_input(
                    f"API Key #{i}:",
                    value=existing_val,
                    type="password",
                    key=f"extra_api_key_{i}",
                    placeholder="sk-..."
                )
                if new_val != existing_val:
                    if new_val:
                        update_user_env(env_key_name, new_val)
                    extra_keys_changed = True
            if extra_keys_changed:
                st.info("💾 추가 API key가 .env에 저장되었습니다.")
            
            # Show count of total available keys
            total_keys = 1 if openai_api_key else 0
            for i in range(1, 6):
                if read_user_env_value(f'OPENAI_API_KEY_{i}', ''):
                    total_keys += 1
            if total_keys > 1:
                st.success(f"✅ {total_keys}개 API key → dimension별 병렬 실행 가능")
            else:
                st.info("ℹ️ 1개 API key → 순차 실행 (추가 key 입력 시 병렬 실행)")
        
        col_save1, col_save2 = st.columns([1, 1])
        with col_save1:
            if st.button("💾 Save", key="save_env_btn"):
                try:
                    if openai_api_key:
                        # Update user-specific .env file
                        update_user_env('OPENAI_API_KEY', openai_api_key)
                        st.success("✅ Saved to user .env!")
                        save_user_config()
                    else:
                        st.warning("⚠️ Please enter an API key first")
                except Exception as e:
                    st.error(f"❌ {str(e)}")
        with col_save2:
            if st.button("🔄 Reload", key="reload_env_btn"):
                # Re-read user env values into session state (without touching os.environ)
                reloaded_key = read_user_env_value('OPENAI_API_KEY', '')
                if reloaded_key:
                    st.session_state['openai_api_key'] = reloaded_key
                reloaded_model = read_user_env_value('OPENAI_MODEL', '')
                if reloaded_model:
                    st.session_state['selected_model'] = reloaded_model
                st.success("✅ 설정이 다시 로드되었습니다.")
        
        st.markdown("---")
    
    # Get effective API key from session state
    effective_api_key = st.session_state.get("openai_api_key", "") or openai_api_key
    
    # ============ Render selected page ============
    if mode == "🛠️ Taxonomy 입력 만들기":
        page_taxonomy_builder(effective_api_key)
    elif mode == "▶️ TaxoAdapt 실행":
        page_taxoadapt(effective_api_key)
    elif mode == "💾 결과값 저장":
        page_save_results(effective_api_key)
    elif mode == "📜 실행 이력":
        page_execution_history()


def page_taxonomy_builder(openai_api_key):
    """Taxonomy 입력 만들기 페이지: YAML 생성 + Initial Taxonomy TXT 생성"""
    
    st.header("🛠️ Taxonomy 입력 만들기")
    st.markdown("Excel 파일에서 **Dimension YAML** 및 **Initial Taxonomy** 파일을 자동 생성합니다.")
    
    # Output folder in sidebar
    with st.sidebar:
        st.subheader("📁 출력 설정")
        if 'taxo_builder_output_folder' not in st.session_state:
            st.session_state['taxo_builder_output_folder'] = "web_custom_data"
        taxo_output_folder = st.text_input(
            "출력 폴더 (datasets 하위):",
            value=st.session_state['taxo_builder_output_folder'],
            key="taxo_builder_output_folder",
            help="생성된 파일이 저장될 폴더"
        )
        # Create folder immediately when the value is set/changed
        _taxo_out_dir = get_user_datasets_dir() / taxo_output_folder.strip().lower().replace(' ', '_')
        os.makedirs(_taxo_out_dir, exist_ok=True)
        st.caption(f"📂 `datasets/{taxo_output_folder.strip().lower().replace(' ', '_')}/`")
    
    tab_yaml, tab_taxo = st.tabs(["1️⃣ Dimension YAML 생성", "2️⃣ Initial Taxonomy TXT 생성"])
    
    # ============ Tab 1: Dimension YAML 생성 ============
    with tab_yaml:
        st.subheader("1️⃣ Dimension YAML 생성")
        st.markdown("""
        **입력 Excel 형식:** `Topic`, `Level1`, `Level1_Dimension_Name`, `Level1_Dimension_Definitions`, `Level1_Node_Dimension_Definitions`
        
        각 행이 하나의 Dimension이 됩니다.
        """)
        
        yaml_excel_file = st.file_uploader(
            "📂 Dimension Excel 파일 업로드",
            type=['xlsx', 'xls'],
            key="yaml_excel_uploader",
            help="Topic, Level1, Level1_Dimension_Name, Level1_Dimension_Definitions, Level1_Node_Dimension_Definitions 컬럼 필요"
        )
        
        if yaml_excel_file is not None:
            try:
                import pandas as pd
                df_yaml = pd.read_excel(yaml_excel_file)
                df_yaml.columns = [col.strip() for col in df_yaml.columns]
                
                st.info(f"📋 컬럼: {list(df_yaml.columns)} | 행 수: {len(df_yaml)}")
                
                with st.expander("📄 데이터 미리보기", expanded=False):
                    st.dataframe(df_yaml)
                
                required_cols = ['Level1_Dimension_Name', 'Level1_Dimension_Definitions', 'Level1_Node_Dimension_Definitions']
                missing_cols = [c for c in required_cols if c not in df_yaml.columns]
                
                if missing_cols:
                    st.error(f"❌ 필수 컬럼 누락: {missing_cols}")
                else:
                    yaml_filename = st.text_input("출력 YAML 파일명:", value="generated_config.yaml", key="yaml_output_name")
                    
                    if st.button("🔧 YAML 생성", key="gen_yaml_btn"):
                        yaml_content = generate_yaml_from_excel(df_yaml)
                        
                        if yaml_content:
                            st.success("✅ YAML 생성 완료!")
                            st.code(yaml_content, language="yaml")
                            
                            save_path = get_user_configs_dir() / yaml_filename
                            os.makedirs(save_path.parent, exist_ok=True)
                            with open(save_path, 'w', encoding='utf-8') as f:
                                f.write(yaml_content)
                            st.info(f"💾 저장 완료: {save_path}")
                            
                            st.download_button(
                                label="📥 YAML 다운로드",
                                data=yaml_content,
                                file_name=yaml_filename,
                                mime="text/yaml",
                                key="download_yaml_gen"
                            )
                        else:
                            st.error("❌ YAML 생성 실패")
                            
            except Exception as e:
                st.error(f"❌ Excel 읽기 오류: {e}")
                import traceback
                st.code(traceback.format_exc())
    
    # ============ Tab 2: Initial Taxonomy TXT 생성 ============
    with tab_taxo:
        st.subheader("2️⃣ Initial Taxonomy TXT 생성")
        st.markdown("""
        **입력 Excel 형식:** `Level1` ~ `Level4`, `Level1_Description` ~ `Level4_Description`, 
        `Level1_Dimension_Name` ~ `Level4_Dimension_Name`, `topic` (선택사항) etc.
        
        - **Dimension_Name/Definitions가 있으면:** 바로 initial_taxo 파일 생성
        - **없으면:** GPT로 Description에서 자동 생성
        - **topic 컬럼이 있으면:** 해당 값을 Level 0 dimension으로 사용 (없으면 출력 폴더명 사용)
        """)
        
        taxo_excel_file = st.file_uploader(
            "📂 Taxonomy Excel 파일 업로드",
            type=['xlsx', 'xls'],
            key="taxo_excel_uploader",
            help="Level1~4 계층 + Description + Dimension_Name/Definitions 컬럼 포함"
        )
        
        if taxo_excel_file is not None:
            try:
                import pandas as pd
                df_taxo = pd.read_excel(taxo_excel_file)
                df_taxo.columns = [col.strip() for col in df_taxo.columns]
                
                st.info(f"📋 컬럼: {list(df_taxo.columns)} | 행 수: {len(df_taxo)}")
                
                # Topic 컬럼 확인 (대소문자 구분 안함)
                topic_col = None
                for col in df_taxo.columns:
                    if col.lower() == 'topic':
                        topic_col = col
                        break
                
                if topic_col:
                    unique_topics = df_taxo[topic_col].dropna().unique()
                    st.success(f"✅ Topic 컬럼 발견 ({topic_col}): {list(unique_topics)}")
                else:
                    st.info("💡 Topic 컬럼이 없습니다. 출력 폴더명을 topic으로 사용합니다.")
                
                with st.expander("📄 데이터 미리보기", expanded=False):
                    st.dataframe(df_taxo)
                
                level_cols = [c for c in ['Level1', 'Level2', 'Level3', 'Level4'] if c in df_taxo.columns]
                st.info(f"📊 감지된 레벨: {level_cols}")
                
                if 'Level1' in df_taxo.columns:
                    level1_values = df_taxo['Level1'].dropna().unique().tolist()
                    st.info(f"📌 Level1 Dimensions: {level1_values}")
                    
                    missing_data = check_taxonomy_data_completeness(df_taxo, level_cols)
                    
                    if missing_data:
                        st.warning(f"⚠️ Dimension 데이터 누락 레벨: {missing_data}")
                        use_gpt = st.checkbox("🤖 GPT로 누락 데이터 자동 생성", value=True, key="use_gpt_taxo")
                    else:
                        st.success("✅ 모든 레벨에 Dimension 데이터가 있습니다.")
                        use_gpt = False
                    
                    if st.button("🔧 Initial Taxonomy 생성", key="gen_taxo_btn"):
                        output_dir = get_user_datasets_dir() / taxo_output_folder.lower().replace(' ', '_')
                        os.makedirs(output_dir, exist_ok=True)
                        
                        api_key = get_effective_api_key(openai_api_key)
                        
                        if use_gpt and missing_data and not api_key:
                            st.error("❌ GPT 사용을 위해 OpenAI API Key가 필요합니다.")
                        else:
                            # Topic 컬럼이 있으면 첫 번째 값 사용, 없으면 폴더명 사용
                            topic_value = taxo_output_folder
                            topic_col = None
                            for col in df_taxo.columns:
                                if col.lower() == 'topic':
                                    topic_col = col
                                    break
                            
                            if topic_col:
                                first_topic = df_taxo[topic_col].dropna().iloc[0] if len(df_taxo[topic_col].dropna()) > 0 else taxo_output_folder
                                topic_value = str(first_topic).strip()
                                st.info(f"📋 감지된 Topic ({topic_col}): {topic_value}")
                            
                            with st.spinner("🔄 Initial Taxonomy 생성 중..."):
                                generated_files = generate_initial_taxo_files(
                                    df_taxo, level_cols, output_dir,
                                    topic=topic_value,
                                    use_gpt=use_gpt if missing_data else False,
                                    api_key=api_key
                                )
                            
                            if generated_files:
                                st.success(f"✅ {len(generated_files)}개 파일 생성 완료!")
                                
                                for fname, content in generated_files.items():
                                    with st.expander(f"📄 {fname}", expanded=False):
                                        st.text_area(f"내용:", content, height=300, key=f"taxo_preview_{fname}")
                                    
                                    st.download_button(
                                        label=f"📥 {fname} 다운로드",
                                        data=content,
                                        file_name=fname,
                                        mime="text/plain",
                                        key=f"download_taxo_{fname}"
                                    )
                                
                                st.info(f"💾 파일 저장 위치: datasets/{taxo_output_folder}/")
                            else:
                                st.error("❌ 파일 생성 실패")
                
            except Exception as e:
                st.error(f"❌ Excel 읽기 오류: {e}")
                import traceback
                st.code(traceback.format_exc())


def page_taxoadapt(openai_api_key):
    """TaxoAdapt 실행 페이지: 기존 Dimensions, prompts.py Editor, Run, Save Config"""
    
    # Sidebar for TaxoAdapt configuration
    with st.sidebar:
        # ============ 2. YAML Config Upload ============
        st.subheader("2. Dimension Config (YAML)")

        # ============ LLM Model Selection ============
        st.subheader("LLM Model 선택")
        model_options = {
            'GPT-5 (2025-08-07)': 'gpt-5-2025-08-07',
            'GPT-4o-mini (2024-07-18)': 'gpt-4o-mini-2024-07-18'
        }
        # Load user-specific model if present (read from user .env, not os.environ)
        user_model = st.session_state.get("selected_model", read_user_env_value('OPENAI_MODEL', 'gpt-5-2025-08-07'))
        model_display = {v: k for k, v in model_options.items()}
        selected_model = st.radio(
            "사용할 LLM 모델을 선택하세요:",
            list(model_options.keys()),
            index=list(model_options.values()).index(user_model) if user_model in model_options.values() else 0
        )
        # Only update if user explicitly changed the model (not on every render)
        current_model = model_options[selected_model]
        if st.session_state.get("_last_selected_model") != current_model:
            st.session_state["_last_selected_model"] = current_model
            if user_model != current_model:
                st.session_state["selected_model"] = current_model
                save_user_config()
                update_user_env('OPENAI_MODEL', current_model)
                st.success(f"✅ OPENAI_MODEL이 {current_model}(으)로 변경되었습니다.")

        config_file = st.file_uploader("Upload YAML config", type=['yaml', 'yml'], key="yaml_uploader")

        if config_file is not None:
            # config_file_name이 같고 config_loaded=True여도, dimensions가 비어있으면 강제 리로드
            force_reload = (len(st.session_state.get('dimensions', {})) == 0)
            if st.session_state.config_file_name != config_file.name or not st.session_state.config_loaded or force_reload:
                try:
                    config = load_yaml_config(config_file)
                    st.session_state.config = config
                    st.session_state.dimensions = config.dimensions.copy()
                    st.session_state.config_loaded = True
                    st.session_state.config_file_name = config_file.name
                    
                    # 디버깅 정보 출력
                    print(f"[DEBUG] YAML loaded: {len(config.dimensions)} dimensions")
                    
                    st.success(f"✅ Loaded: {config_file.name} ({len(config.dimensions)} dimensions)")
                    save_user_config()  # dimensions를 JSON에 즉시 저장
                except Exception as e:
                    st.error(f"❌ Error: {str(e)}")
                    import traceback
                    st.write(f"[DEBUG] Exception details: {traceback.format_exc()}")
            else:
                st.success(f"✅ Config loaded: {config_file.name} ({len(st.session_state.dimensions)} dimensions)")

        if st.button("📄 Create Empty Config"):
            st.session_state.config = DimensionConfig(config_path=None)
            st.session_state.config.dimensions = {}
            st.session_state.dimensions = {}
            st.session_state.config_loaded = True
            st.session_state.config_file_name = None
            st.success("✅ Empty config created!")
            st.rerun()

        if st.session_state.config_loaded and st.session_state.dimensions:
            with st.expander("📋 Loaded Dimensions", expanded=False):
                for dim_name in st.session_state.dimensions.keys():
                    st.write(f"  • {dim_name}")

        st.markdown("---")
        
        # ============ 3. Dataset Upload ============
        st.subheader("3. Custom Data Upload")
        
        dataset = st.text_input(
            "Dataset folder name:",
            value="web_custom_data",
            help="This will create a folder under datasets/ to store all results"
        )
        
        st.write("**Upload your paper data:**")
        
        upload_format = st.radio(
            "Data format:",
            ["Excel (xlsx)", "JSON Lines (Title & Abstract)", "CSV", "TXT (one paper per line)"],
            key="upload_format"
        )
        
        uploaded_data = st.file_uploader(
            "Upload file",
            type=['xlsx', 'xls', 'jsonl', 'json', 'csv', 'txt'],
            help="Upload papers with title and abstract"
        )
        
        if upload_format == "Excel (xlsx)":
            st.info('Expected columns: "Title" and "Abstract"')
        elif upload_format == "JSON Lines (Title & Abstract)":
            st.info('Each line: {"title": "...", "abstract": "..."}')
        elif upload_format == "CSV":
            st.info('Expected columns: "title" and "abstract"')
        else:
            st.info('Each line: {"Title": "...", "Abstract": "..."}')
        
        dataset_folder = get_user_dataset_path(dataset)
        if uploaded_data is not None:
            st.success(f"📁 Data will be saved to: {dataset_folder}")
            import pandas as pd
            from io import BytesIO, StringIO
            df = None
            filetype = None
            # Try to read as DataFrame
            try:
                if upload_format == "Excel (xlsx)":
                    df = pd.read_excel(uploaded_data)
                    filetype = 'excel'
                elif upload_format == "CSV":
                    df = pd.read_csv(uploaded_data)
                    filetype = 'csv'
                elif upload_format == "JSON Lines (Title & Abstract)":
                    df = pd.read_json(uploaded_data, lines=True)
                    filetype = 'jsonl'
                elif upload_format == "TXT (one paper per line)":
                    # Try to parse as JSON lines or tab-separated
                    content = uploaded_data.read().decode('utf-8')
                    try:
                        df = pd.read_json(StringIO(content), lines=True)
                        filetype = 'jsonl'
                    except Exception:
                        # Try tab-separated
                        lines = [l for l in content.splitlines() if l.strip()]
                        if lines and ('\t' in lines[0]):
                            df = pd.DataFrame([l.split('\t') for l in lines])
                            filetype = 'txt-tsv'
            except Exception as e:
                st.error(f"❌ 파일을 읽을 수 없습니다: {e}")
                df = None

            if df is not None:
                df.columns = [str(c).strip() for c in df.columns]
                cols = set(df.columns)
                # 1) patent_ids, title, abstract 모두 있으면 그대로 진행
                if {'patent_ids', 'title', 'abstract'}.issubset(cols):
                    st.success('✅ patent_ids, title, abstract 필드 감지: 그대로 사용합니다.')
                    
                    # DataFrame을 papers 형태로 변환하고 internal.txt 생성
                    papers = []
                    for _, row in df.iterrows():
                        if pd.notna(row['patent_ids']) and pd.notna(row['title']) and pd.notna(row['abstract']):
                            paper_data = {
                                "Patent_ID": str(row['patent_ids']).strip(),
                                "Title": str(row['title']).strip(),
                                "Abstract": str(row['abstract']).strip()
                            }
                            papers.append(paper_data)
                    
                    # internal.txt 파일로 저장 (모든 데이터)
                    if papers:
                        internal_file = dataset_folder / 'internal.txt'
                        os.makedirs(dataset_folder, exist_ok=True)
                        
                        with open(internal_file, 'w', encoding='utf-8') as f:
                            for paper in papers:
                                formatted_dict = json.dumps(paper, ensure_ascii=False)
                                f.write(f'{formatted_dict}\n')
                        
                        st.success(f"📊 처리 완료: {len(papers)}개 데이터 (전체 저장) → {internal_file}")
                        st.info("🎯 Run 단계에서 test_samples 수만큼 사용됩니다.")
                    else:
                        st.warning("⚠️ 유효한 데이터가 없습니다.")
                        
                # 2) 출원번호, 발명의 명칭, 요약, 대표청구항 있으면 변환
                elif {'출원번호', '발명의 명칭', '요약', '대표청구항'}.issubset(cols):
                    st.info('ℹ️ WIPS 특허 rawdata 감지: 변환하여 사용합니다.')
                    df['patent_ids'] = df['출원번호']
                    df['title'] = df['발명의 명칭']
                    df['abstract'] = "(요약) " + df['요약'].astype(str) + "\n (청구항) " + df['대표청구항'].astype(str)
                    df = df[['patent_ids', 'title', 'abstract']]
                    
                    # WIPS 변환 데이터를 user datasets에 저장
                    wips_output_path = dataset_folder / 'wips_converted_data.xlsx'
                    df.to_excel(wips_output_path, index=False)
                    st.success(f"✅ WIPS 변환 데이터 저장: {wips_output_path}")
                    
                    # DataFrame을 papers 형태로 변환하고 internal.txt 생성
                    papers = []  # papers 리스트 선언
                    for _, row in df.iterrows():
                        if pd.notna(row['patent_ids']) and pd.notna(row['title']) and pd.notna(row['abstract']):
                            paper_data = {
                                "Patent_ID": str(row['patent_ids']).strip(),
                                "Title": str(row['title']).strip(),
                                "Abstract": str(row['abstract']).strip()
                            }
                            papers.append(paper_data)
                    
                    # internal.txt 파일로 저장 (모든 데이터)
                    if papers:
                        internal_file = dataset_folder / 'internal.txt'
                        os.makedirs(dataset_folder, exist_ok=True)
                        
                        with open(internal_file, 'w', encoding='utf-8') as f:
                            for paper in papers:
                                formatted_dict = json.dumps(paper, ensure_ascii=False)
                                f.write(f'{formatted_dict}\n')
                        
                        st.success(f"📊 변환 완료: {len(papers)}개 특허 데이터 (전체 저장) → {internal_file}")
                        st.info("🎯 Run 단계에서 test_samples 수만큼 사용됩니다.")
                    else:
                        st.warning("⚠️ 변환 가능한 유효한 데이터가 없습니다.")
                else:
                    st.error('❌ [필수] patent_ids, title, abstract 필드 또는 출원번호, 발명의 명칭, 요약, 대표청구항 필드가 필요합니다.')
                    st.warning('출원번호, 발명의 명칭, 요약, 대표청구항 필드가 포함된 Wips on rawdata가 필요합니다. 데이터를 다시 업로드 해주세요.')
                    st.stop()
                # Optionally preview
                with st.expander('📄 데이터 미리보기', expanded=False):
                    st.dataframe(df.head(20))
        
        internal_txt_path = dataset_folder / 'internal.txt'
        if internal_txt_path.exists():
            line_count = sum(1 for line in open(internal_txt_path, 'r', encoding='utf-8') if line.strip())
            if line_count > 0:
                st.info(f"ℹ️ Existing data: {line_count} papers")
        
        st.markdown("---")
        
        # ============ 4. Initial Taxonomy Upload (Optional) ============
        st.subheader("4. Initial Taxonomy (Optional)")
        
        initial_taxonomy_files = st.file_uploader(
            "Upload initial_taxo_*.txt files",
            type=['txt'],
            accept_multiple_files=True,
            help="Upload pre-defined initial taxonomy files"
        )
        
        if initial_taxonomy_files:
            st.success(f"✅ {len(initial_taxonomy_files)} file(s) uploaded")
        
        st.markdown("---")
        
        # ============ 5. Execution parameters ============
        st.subheader("5. Execution Parameters")
        topic = st.text_input("Topic (User_Topic):", value=st.session_state.user_topic)
        st.session_state.user_topic = topic
        
        max_depth = st.number_input("Max Depth:", min_value=1, max_value=10, value=2)
        init_levels = st.number_input("Init Levels:", min_value=1, max_value=5, value=1)
        max_density = st.number_input("Max Density:", min_value=1, max_value=200, value=40)
        test_samples = st.number_input("Test Samples (0=All):", min_value=0, value=0)

        # Store in session state for access in other parts
        st.session_state.test_samples = test_samples
        # Get the actual selected model
        selected_model_name = st.session_state.get("selected_model", 'gpt-5-2025-08-07')
        llm_type = "gpt"
        huggingface_token = None
    
    # ============ Main area ============
    if not st.session_state.config_loaded or st.session_state.config is None:
        st.info("👈 Please upload a YAML config file or create an empty config from the sidebar.")
        
        with st.expander("📖 Example YAML config format"):
            st.code("""dimensions:
  energy_efficiency_improvement:
    definition: 'Energy Efficiency Improvement: technologies that enhance energy efficiency...'
    node_definition: 'Types of technologies for improving energy efficiency...'
  fuel_substitution:
    definition: 'Fuel Substitution: technologies that replace conventional fuels...'
    node_definition: 'Types of fuel substitution approaches...'""", language="yaml")
        return
    
    # Tabs for different sections
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Dimensions", "📝 prompts.py Editor", "▶️ Run", "💾 Save Config"])
    
    # ============ TAB 1: Dimensions ============
    with tab1:
        st.header("Dimension Configuration")
        
        if st.session_state.dimensions:
            st.subheader(f"Current Dimensions ({len(st.session_state.dimensions)})")
            
            for dim_name, dim_config in list(st.session_state.dimensions.items()):
                with st.expander(f"📌 {dim_name}", expanded=False):
                    col1, col2 = st.columns([4, 1])
                    
                    with col1:
                        st.text_area(
                            "Definition:",
                            dim_config.get('definition', ''),
                            key=f"def_{dim_name}",
                            height=100
                        )
                        st.text_area(
                            "Node Definition:",
                            dim_config.get('node_definition', ''),
                            key=f"node_def_{dim_name}",
                            height=100
                        )
                    
                    with col2:
                        st.write("")
                        st.write("")
                        if st.button("🗑️ Remove", key=f"remove_{dim_name}"):
                            del st.session_state.dimensions[dim_name]
                            st.session_state.config.dimensions = st.session_state.dimensions
                            save_user_config()
                            st.rerun()
                        
                        if st.button("💾 Update", key=f"update_{dim_name}"):
                            st.session_state.dimensions[dim_name]['definition'] = st.session_state[f"def_{dim_name}"]
                            st.session_state.dimensions[dim_name]['node_definition'] = st.session_state[f"node_def_{dim_name}"]
                            st.session_state.config.dimensions = st.session_state.dimensions
                            save_user_config()
                            st.success(f"✅ Updated {dim_name}")
        else:
            st.warning("No dimensions loaded. Add dimensions below or upload a YAML config.")
        
        # Add new dimension
        st.markdown("---")
        st.subheader("Add New Dimension")
        
        with st.form("add_dimension_form"):
            new_dim_name = st.text_input("Dimension Name (e.g., 'challenges'):")
            new_dim_def = st.text_area("Definition:", height=100)
            new_node_def = st.text_area("Node Definition:", height=100)
            
            if st.form_submit_button("➕ Add Dimension"):
                if new_dim_name and new_dim_def and new_node_def:
                    st.session_state.dimensions[new_dim_name] = {
                        'definition': new_dim_def,
                        'node_definition': new_node_def
                    }
                    st.session_state.config.dimensions = st.session_state.dimensions
                    st.success(f"✅ Added dimension: {new_dim_name}")
                    save_user_config()
                    st.rerun()
                else:
                    st.error("Please fill in all fields")
    
    # ============ TAB 2: prompts.py Editor ============
    with tab2:
        st.header("📝 prompts.py Editor")
        st.markdown("Edit and apply definitions to `prompts.py` for taxonomy generation.")
        
        st.info(f"**Current Topic:** `{topic}` | **Dimensions:** {len(st.session_state.dimensions)}")
        
        if not st.session_state.dimensions:
            st.warning("No dimensions to edit. Please load a config first.")
        else:
            # Dimension Definitions
            st.subheader("Dimension Definitions")
            
            # Load current user prompts file content to show existing values
            current_content = load_user_prompts_content()
            
            updated_dim_defs = {}
            for dim_name, dim_config in st.session_state.dimensions.items():
                # Try to extract current definition from user's prompts.py
                current_def = dim_config.get('definition', '')
                if current_content:
                    import re
                    pattern = rf"'{dim_name}':\s*\"\"\"(.*?)\"\"\""
                    match = re.search(pattern, current_content, re.DOTALL)
                    if match:
                        current_def = match.group(1).strip()
                
                updated_dim_defs[dim_name] = st.text_area(
                    f"Definition: '{dim_name}'",
                    value=current_def,
                    key=f"prompt_def_{dim_name}",
                    height=120
                )
            
            st.markdown("---")
            st.subheader("Node Dimension Definitions")
            updated_node_defs = {}
            for dim_name, dim_config in st.session_state.dimensions.items():
                # Try to extract current node definition from user's prompts.py
                current_node_def = dim_config.get('node_definition', '')
                if current_content:
                    import re
                    # Look in node_dimension_definitions
                    pattern = rf"'{dim_name}':\s*\"\"\"(.*?)\"\"\""
                    # Search in node_dimension_definitions section
                    node_section_match = re.search(r'node_dimension_definitions = \{(.*?)\}', current_content, re.DOTALL)
                    if node_section_match:
                        node_section = node_section_match.group(1)
                        match = re.search(pattern, node_section, re.DOTALL)
                        if match:
                            current_node_def = match.group(1).strip()
                
                updated_node_defs[dim_name] = st.text_area(
                    f"Node Definition: '{dim_name}'",
                    value=current_node_def,
                    key=f"prompt_node_def_{dim_name}",
                    height=120
                )
            
            st.markdown("---")
            
            # Apply button
            if st.button("🚀 Apply to prompts.py", type="primary"):
                # Update session state
                for dim_name in st.session_state.dimensions.keys():
                    st.session_state.dimensions[dim_name]['definition'] = updated_dim_defs[dim_name]
                    st.session_state.dimensions[dim_name]['node_definition'] = updated_node_defs[dim_name]
                st.session_state.config.dimensions = st.session_state.dimensions
                save_user_config()
                
                # Update user-specific prompts.py
                try:
                    user_prompts_path = ensure_user_prompts_exists()
                    update_prompts_file_dynamic_with_path(user_prompts_path, st.session_state.config, topic)
                    st.success(f"✅ User prompts.py updated successfully at {user_prompts_path}!")
                    
                    # Show what was updated
                    with st.expander("📄 Updated contents", expanded=True):
                        dim_list = list(st.session_state.dimensions.keys())
                        st.markdown("**User_Topic:**")
                        st.code(f'User_Topic="{topic}"', language="python")
                        
                        st.markdown("**TypeClsSchema (with sanitized field names):**")
                        schema_code = "class TypeClsSchema(BaseModel):\n"
                        for d in dim_list:
                            sanitized = _sanitize_field_name(d)
                            if sanitized != d:
                                schema_code += f"  {sanitized}: bool = Field(alias='{d}')\n"
                            else:
                                schema_code += f"  {sanitized}: bool\n"
                        st.code(schema_code, language="python")
                        
                        st.markdown("**dimension_definitions:**")
                        st.code(f"{len(dim_list)} dimensions: {', '.join(dim_list)}", language="text")
                        
                        st.markdown(f"**📁 File location:** `{user_prompts_path}`")
                        
                except Exception as e:
                    st.error(f"❌ Error updating prompts.py: {e}")
                    import traceback
                    st.code(traceback.format_exc())
                save_user_config()
            
            # Preview section
            with st.expander("🔍 Preview prompts.py Changes", expanded=False):
                st.markdown("**dimension_definitions:**")
                preview = "dimension_definitions = {\n"
                for dim, definition in updated_dim_defs.items():
                    preview += f"    '{dim}': \"\"\"{definition}\"\"\",\n"
                preview += "}"
                st.code(preview, language="python")
                
                st.markdown("**node_dimension_definitions:**")
                preview2 = "node_dimension_definitions = {\n"
                for dim, definition in updated_node_defs.items():
                    preview2 += f"    '{dim}': \"\"\"{definition}\"\"\",\n"
                preview2 += "}"
                st.code(preview2, language="python")
    
    # ============ TAB 3: Run ============
    with tab3:
        st.header("Run TaxoAdapt")
        
        # ============ 차원 선택 섹션 ============
        st.subheader("🎯 실행할 차원 선택")
        
        if st.session_state.dimensions:
            # 전체 선택/해제 버튼
            col_select1, col_select2, col_select3 = st.columns([2, 2, 4])
            with col_select1:
                if st.button("✅ 전체 선택", key="select_all_dims"):
                    st.session_state.selected_dimensions = list(st.session_state.dimensions.keys())
            with col_select2:
                if st.button("❌ 전체 해제", key="deselect_all_dims"):
                    st.session_state.selected_dimensions = []
            
            # 멀티셀렉트를 위한 세션 상태 초기화
            if 'selected_dimensions' not in st.session_state:
                st.session_state.selected_dimensions = list(st.session_state.dimensions.keys())
            
            # 차원 선택 멀티셀렉트
            selected_dims = st.multiselect(
                "실행할 차원을 선택하세요: (Raw Material 차원만 선택하려면 다른 차원들은 해제하세요)", 
                options=list(st.session_state.dimensions.keys()),
                default=st.session_state.selected_dimensions,
                help="선택된 차원들만 실행됩니다. Raw_Material_Cost_Reduction_Technologies만 선택하면 단일 차원 실행 가능"
            )
            
            # 선택된 차원들 업데이트
            st.session_state.selected_dimensions = selected_dims
            
            if selected_dims:
                st.success(f"✅ 선택된 차원: {len(selected_dims)}개 - {', '.join(selected_dims)}")
            else:
                st.warning("⚠️ 실행할 차원을 최소 1개 이상 선택하세요.")
        else:
            st.warning("⚠️ 설정된 차원이 없습니다.")
        
        st.markdown("---")
        
        # Resume 옵션
        resume_mode = st.checkbox(
            "🔄 Resume Mode (이어하기)",
            value=False,
            key="resume_mode",
            help="이전에 실패하거나 중단된 작업을 이어서 실행합니다. 기존 final_taxo_*.json 파일이 있으면 해당 dimension은 건너뜁니다."
        )
        if resume_mode:
            st.info("ℹ️ Resume Mode: 완료된 dimension은 건너뛰고, 미완료 dimension만 이어서 실행합니다.")
        
        st.markdown("---")
        
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Topic", topic)
            st.metric("Dataset Folder", f"datasets/{dataset}/")
            st.metric("Max Depth", max_depth)
            st.metric("Test Samples", test_samples if test_samples > 0 else "All")
        
        with col2:
            st.metric("Total Dimensions", len(st.session_state.dimensions))
            st.metric("Selected Dimensions", len(st.session_state.get('selected_dimensions', [])))
            st.metric("Max Density", max_density)
            st.metric("LLM Type", "GPT (OpenAI)")
            st.metric("Initial Taxonomy Files", len(initial_taxonomy_files) if initial_taxonomy_files else 0)
            # Show data status
            ds_folder = get_user_dataset_path(dataset)
            if (ds_folder / 'internal.txt').exists():
                paper_count = sum(1 for l in open(ds_folder / 'internal.txt', 'r', encoding='utf-8') if l.strip())
                if test_samples > 0 and test_samples < paper_count:
                    st.metric("Papers Total", f"{paper_count:,}")
                    st.metric("Papers to Use", f"{test_samples:,} (샘플링)")
                else:
                    st.metric("Papers to Use", f"{paper_count:,} (전체)")
        
        if st.session_state.dimensions:
            st.markdown("**Dimensions:** " + ", ".join(st.session_state.dimensions.keys()))
        
        st.markdown("---")
        
        # API Key Status
        if openai_api_key:
            st.success("✅ OpenAI API Key provided")
        elif st.session_state.get('openai_api_key') or read_user_env_value('OPENAI_API_KEY'):
            st.info("ℹ️ Using OPENAI_API_KEY from user config")
        else:
            st.warning("⚠️ No OpenAI API Key")
        
        st.markdown("---")
        
        # Validation
        errors = []
        selected_dims = st.session_state.get('selected_dimensions', [])
        
        if not st.session_state.dimensions:
            errors.append("⚠️ Please configure at least one dimension.")
        elif not selected_dims:
            errors.append("⚠️ Please select at least one dimension to run.")
        # Check if data exists (either uploaded or pre-existing internal.txt)
        dataset_folder_check = get_user_dataset_path(dataset)
        internal_exists = (dataset_folder_check / 'internal.txt').exists() and \
                          (dataset_folder_check / 'internal.txt').stat().st_size > 0
        if uploaded_data is None and not internal_exists:
            errors.append("⚠️ Please upload your dataset file (or ensure internal.txt exists).")
        if not get_effective_api_key(openai_api_key):
            errors.append("⚠️ OpenAI API Key is required.")
        
        for err in errors:
            st.warning(err)
        
        if not errors:
            if st.button("🚀 Run TaxoAdapt", type="primary", disabled=st.session_state.running):
                # 선택된 차원들만 포함하는 임시 config 생성
                filtered_config = DimensionConfig(config_path=None)
                filtered_config.dimensions = {
                    dim: st.session_state.config.dimensions[dim] 
                    for dim in selected_dims 
                    if dim in st.session_state.config.dimensions
                }
                
                run_taxoadapt(
                    config=filtered_config,  # 필터링된 config 사용
                    dataset=dataset,
                    topic=topic,
                    max_depth=max_depth,
                    init_levels=init_levels,
                    max_density=max_density,
                    llm="gpt",  # LLM type, not model name
                    openai_api_key=openai_api_key,
                    huggingface_token=huggingface_token,
                    uploaded_data=uploaded_data,
                    upload_format=st.session_state.get('upload_format', None),
                    initial_taxonomy_files=initial_taxonomy_files,
                    test_samples=test_samples if test_samples > 0 else None,
                    resume=resume_mode
                )
    
    # ============ TAB 4: Save Config ============
    with tab4:
        st.header("Save Configuration")
        
        save_path = st.text_input(
            "Save path:",
            value="my_config.yaml",
            help="파일명 (사용자 전용 configs 폴더에 저장)"
        )
        
        if st.button("💾 Save Configuration"):
            try:
                full_path = get_user_configs_dir() / save_path
                os.makedirs(full_path.parent, exist_ok=True)
                st.session_state.config.save_config(full_path)
                st.success(f"✅ Saved to {save_path}")
                
                with open(full_path, 'r') as f:
                    st.download_button(
                        label="📥 Download Config File",
                        data=f.read(),
                        file_name=os.path.basename(save_path),
                        mime="text/yaml"
                    )
            except Exception as e:
                st.error(f"❌ Error: {e}")


def page_save_results(openai_api_key):
    """결과값 저장 페이지: TaxoAdapt 실행 결과를 다양한 형태로 저장"""
    import pandas as pd
    from collections import defaultdict
    import re
    import io
    
    st.header("💾 결과값 저장")
    st.markdown("TaxoAdapt 실행 결과(`final_taxo_*.json`)를 다양한 형태의 Excel/CSV로 변환합니다.")
    
    # ============ Sidebar: 설정 ============
    with st.sidebar:
        st.subheader("📁 데이터 설정")
        
        # Dataset folder
        sr_dataset = st.text_input(
            "Dataset 폴더명:",
            value="web_custom_data",
            key="sr_dataset_folder",
            help="datasets/ 하위 폴더 (final_taxo_*.json 파일 위치)"
        )
        
        sr_dataset = sr_dataset.lower().replace(' ', '_')

        sr_data_dir = get_user_dataset_path(sr_dataset) 
        
        if sr_data_dir.exists():
            json_files = list(sr_data_dir.glob("final_taxo_*.json"))
            st.success(f"✅ {len(json_files)}개 final_taxo 파일 발견")
            for jf in json_files:
                st.write(f"  • {jf.name}")
        else:
            st.warning(f"⚠️ 폴더 없음: {sr_data_dir}")
            json_files = []
        
        st.markdown("---")
        
        # YAML config upload for dimensions
        st.subheader("📋 Dimension Config")
        sr_config_file = st.file_uploader(
            "YAML config 업로드:",
            type=['yaml', 'yml'],
            key="sr_yaml_uploader",
            help="dimension 목록을 읽기 위한 YAML config"
        )
        
        sr_dimensions = {}
        if sr_config_file is not None:
            try:
                config_content = sr_config_file.getvalue().decode('utf-8')
                config_data = yaml.safe_load(config_content)
                sr_dimensions = config_data.get('dimensions', {})
                st.success(f"✅ {len(sr_dimensions)}개 dimension 로드")
                for d in sr_dimensions.keys():
                    st.write(f"  • {d}")
            except Exception as e:
                st.error(f"❌ Config 로드 실패: {e}")
        else:
            # Try to auto-detect from json files
            if json_files:
                for jf in json_files:
                    dim_name = jf.stem.replace('final_taxo_', '')
                    sr_dimensions[dim_name] = {'definition': '', 'node_definition': ''}
                if sr_dimensions:
                    st.info(f"ℹ️ JSON 파일명에서 {len(sr_dimensions)}개 dimension 자동 감지")
        
        st.markdown("---")
        
        # Korean names mapping
        st.subheader("🇰🇷 한글 차원명")
        st.markdown("각 Dimension의 한글 이름을 입력하세요.")
        
        sr_korean_names = {}
        for dim_name in sr_dimensions.keys():
            kr_name = st.text_input(
                f"{dim_name}:",
                value=dim_name.replace('_', ' ').title(),
                key=f"sr_kr_{dim_name}"
            )
            sr_korean_names[dim_name] = kr_name
        
        st.markdown("---")
        
        # Original Excel for merge
        st.subheader("📊 원본 데이터 (Excel)")
        sr_excel_file = st.file_uploader(
            "원본 Excel 업로드 (merge용):",
            type=['xlsx', 'xls'],
            key="sr_excel_uploader",
            help="merge_taxonomy_with_data 및 merge_taxonomy_detailed에 사용"
        )
        
        # Output folder
        st.subheader("📂 출력 설정")
        sr_output_folder = st.text_input(
            "출력 폴더:",
            value=str(get_user_output_dir()),
            key="sr_output_folder",
            help="결과 파일이 저장될 폴더"
        )
    
    # ============ Main content ============
    if not sr_dimensions:
        st.warning("👈 사이드바에서 YAML config를 업로드하거나, Dataset 폴더에 final_taxo_*.json 파일이 있어야 합니다.")
        return
    
    # 출력 폴더 생성
    output_dir = Path(sr_output_folder)
    os.makedirs(output_dir, exist_ok=True)
    
    st.markdown("---")
    
    # Step selection
    st.subheader("📋 실행할 단계 선택")
    
    col_all, _ = st.columns([1, 3])
    with col_all:
        run_all = st.checkbox("✅ 전체 실행", value=True, key="sr_run_all")
    
    step1 = st.checkbox("1️⃣ Merge Taxonomy with Data (기본 병합)", value=run_all, key="sr_step1", disabled=run_all)
    step2 = st.checkbox("2️⃣ Merge Taxonomy Detailed (상세 병합 - Long/Wide)", value=run_all, key="sr_step2", disabled=run_all)
    step3 = st.checkbox("3️⃣ Export Taxonomy Structure (분류체계 Excel)", value=run_all, key="sr_step3", disabled=run_all)
    step4 = st.checkbox("4️⃣ Export Taxonomy Structure Korean (한글 분류체계)", value=run_all, key="sr_step4", disabled=run_all)
    step5 = st.checkbox("5️⃣ Export Taxonomy Translated (GPT 번역 포함)", value=run_all, key="sr_step5", disabled=run_all)
    step6 = st.checkbox("6️⃣ Merged 결과 한글 라벨 변환", value=run_all, key="sr_step6", disabled=run_all)
    
    if (step1 or step2) and sr_excel_file is None:
        st.warning("⚠️ 1️⃣, 2️⃣ 단계를 실행하려면 사이드바에서 **원본 Excel 파일**을 업로드하세요.")
    
    if step5:
        api_key = get_effective_api_key(openai_api_key)
        if not api_key:
            st.warning("⚠️ 5️⃣ 단계(GPT 번역)를 실행하려면 **OpenAI API Key**가 필요합니다.")
    
    if step6 and not step5:
        st.warning("⚠️ 6️⃣ 단계는 5️⃣ 단계(GPT 번역)의 결과가 필요합니다. 이미 생성된 translated 파일이 있으면 사용합니다.")
    
    st.markdown("---")
    
    # ============ Execute button ============
    if st.button("🚀 결과값 저장 실행", type="primary", key="sr_run_btn"):
        # Inject dimensions into config_utils
        sys.path.insert(0, str(BASE_DIR / "save_result"))
        from save_result.config_utils import set_override_config, clear_override_config
        set_override_config(dimensions=sr_dimensions, korean_names=sr_korean_names)
        
        generated_files = {}  # {filename: filepath}
        
        try:
            progress = st.progress(0, text="준비 중...")
            total_steps = sum([step1, step2, step3, step4, step5, step6])
            current_step = 0
            
            # ============ Step 1: merge_taxonomy_with_data ============
            if step1:
                progress.progress(current_step / max(total_steps, 1), text="1️⃣ Merge Taxonomy with Data...")
                with st.expander("1️⃣ Merge Taxonomy with Data", expanded=True):
                    if sr_excel_file is None:
                        st.error("❌ 원본 Excel 파일이 필요합니다.")
                    else:
                        try:
                            from save_result.merge_taxonomy_with_data import (
                                load_taxonomy_files as mtwd_load,
                                merge_with_original_data as mtwd_merge
                            )
                            
                            # Save uploaded excel temporarily
                            tmp_excel = output_dir / "temp_original.xlsx"
                            with open(tmp_excel, 'wb') as f:
                                f.write(sr_excel_file.getvalue())
                            
                            st.write("📂 Taxonomy 분류 결과 로딩...")
                            classifications = mtwd_load(sr_data_dir)
                            st.write(f"  → {len(classifications)}개 논문 분류 발견")
                            
                            st.write("🔄 원본 데이터와 병합 중...")
                            df_merged = mtwd_merge(tmp_excel, classifications)
                            
                            # Save
                            out_xlsx = output_dir / f"{sr_dataset}_taxonomy_merged.xlsx"
                            out_csv = output_dir / f"{sr_dataset}_taxonomy_merged.csv"
                            df_merged.to_excel(out_xlsx, index=False, engine='openpyxl')
                            df_merged.to_csv(out_csv, index=False, encoding='utf-8')
                            
                            classified = df_merged['classified'].sum()
                            st.success(f"✅ 완료! 분류된 논문: {classified}/{len(df_merged)}")
                            generated_files[out_xlsx.name] = out_xlsx
                            generated_files[out_csv.name] = out_csv
                            
                        except Exception as e:
                            st.error(f"❌ 오류: {e}")
                            import traceback
                            st.code(traceback.format_exc())
                
                current_step += 1
            
            # ============ Step 2: merge_taxonomy_detailed ============
            if step2:
                progress.progress(current_step / max(total_steps, 1), text="2️⃣ Merge Taxonomy Detailed...")
                with st.expander("2️⃣ Merge Taxonomy Detailed", expanded=True):
                    if sr_excel_file is None:
                        st.error("❌ 원본 Excel 파일이 필요합니다.")
                    else:
                        try:
                            from save_result.merge_taxonomy_detailed import (
                                load_all_initial_descriptions as mtd_load_desc,
                                load_taxonomy_files as mtd_load,
                                create_long_format as mtd_long,
                                create_wide_format as mtd_wide
                            )
                            
                            # Ensure temp excel exists
                            tmp_excel = output_dir / "temp_original.xlsx"
                            if not tmp_excel.exists():
                                with open(tmp_excel, 'wb') as f:
                                    f.write(sr_excel_file.getvalue())
                            
                            st.write("📂 Initial taxonomy descriptions 로딩...")
                            initial_descriptions = mtd_load_desc(sr_data_dir)
                            
                            st.write("📂 Final taxonomy 분류 결과 로딩...")
                            classifications = mtd_load(sr_data_dir, initial_descriptions)
                            st.write(f"  → {len(classifications)}개 논문 분류 발견")
                            
                            st.write("📊 원본 데이터 로딩...")
                            df_original = pd.read_excel(tmp_excel)
                            st.write(f"  → {len(df_original)}개 논문")
                            
                            # Long format
                            st.write("🔄 Long format 생성 중...")
                            df_long = mtd_long(df_original, classifications)
                            out_long_xlsx = output_dir / f"{sr_dataset}_taxonomy_long.xlsx"
                            out_long_csv = output_dir / f"{sr_dataset}_taxonomy_long.csv"
                            df_long.to_excel(out_long_xlsx, index=False, engine='openpyxl')
                            df_long.to_csv(out_long_csv, index=False, encoding='utf-8')
                            st.write(f"  ✅ Long format: {len(df_long)} rows")
                            generated_files[out_long_xlsx.name] = out_long_xlsx
                            generated_files[out_long_csv.name] = out_long_csv
                            
                            # Wide format
                            st.write("🔄 Wide format 생성 중...")
                            df_wide = mtd_wide(df_original, classifications)
                            out_wide_xlsx = output_dir / f"{sr_dataset}_taxonomy_wide.xlsx"
                            out_wide_csv = output_dir / f"{sr_dataset}_taxonomy_wide.csv"
                            df_wide.to_excel(out_wide_xlsx, index=False, engine='openpyxl')
                            df_wide.to_csv(out_wide_csv, index=False, encoding='utf-8')
                            st.write(f"  ✅ Wide format: {len(df_wide)} rows")
                            generated_files[out_wide_xlsx.name] = out_wide_xlsx
                            generated_files[out_wide_csv.name] = out_wide_csv
                            
                            st.success("✅ 상세 병합 완료!")
                            
                        except Exception as e:
                            st.error(f"❌ 오류: {e}")
                            import traceback
                            st.code(traceback.format_exc())
                
                current_step += 1
            
            # ============ Step 3: export_taxonomy_structure ============
            if step3:
                progress.progress(current_step / max(total_steps, 1), text="3️⃣ Export Taxonomy Structure...")
                with st.expander("3️⃣ Export Taxonomy Structure (영문)", expanded=True):
                    try:
                        from save_result.export_taxonomy_structure import (
                            load_all_taxonomies as ets_load,
                            create_excel_report as ets_excel
                        )
                        
                        st.write("📂 Taxonomy 구조 로딩...")
                        all_rows, dim_summaries = ets_load(sr_data_dir)
                        st.write(f"  → {len(all_rows)} 노드, {len(dim_summaries)} 차원")
                        
                        out_structure = output_dir / f"{sr_dataset}_taxonomy_structure.xlsx"
                        st.write("📊 Excel 리포트 생성 중...")
                        ets_excel(out_structure, all_rows, dim_summaries)
                        
                        st.success(f"✅ 완료! {len(all_rows)}개 노드 저장")
                        generated_files[out_structure.name] = out_structure
                        
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")
                        import traceback
                        st.code(traceback.format_exc())
                
                current_step += 1
            
            # ============ Step 4: export_taxonomy_structure_korean ============
            if step4:
                progress.progress(current_step / max(total_steps, 1), text="4️⃣ Export Taxonomy Structure (한글)...")
                with st.expander("4️⃣ Export Taxonomy Structure 한글", expanded=True):
                    try:
                        from save_result.export_taxonomy_structure_korean import (
                            load_all_taxonomies as etsk_load,
                            create_excel_report as etsk_excel
                        )
                        
                        st.write("📂 Taxonomy 구조 로딩 (한글)...")
                        all_rows_kr, dim_summaries_kr = etsk_load(sr_data_dir)
                        st.write(f"  → {len(all_rows_kr)} 노드, {len(dim_summaries_kr)} 차원")
                        
                        out_structure_kr = output_dir / f"{sr_dataset}_taxonomy_structure_korean.xlsx"
                        st.write("📊 한글 Excel 리포트 생성 중...")
                        etsk_excel(out_structure_kr, all_rows_kr, dim_summaries_kr)
                        
                        st.success(f"✅ 완료! {len(all_rows_kr)}개 노드 저장")
                        generated_files[out_structure_kr.name] = out_structure_kr
                        
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")
                        import traceback
                        st.code(traceback.format_exc())
                
                current_step += 1
            
            # ============ Step 5: export_taxonomy_translated ============
            if step5:
                progress.progress(current_step / max(total_steps, 1), text="5️⃣ Export Taxonomy Translated (GPT 번역)...")
                with st.expander("5️⃣ Export Taxonomy Translated (GPT 번역)", expanded=True):
                    api_key = get_effective_api_key(openai_api_key)
                    if not api_key:
                        st.error("❌ OpenAI API Key가 필요합니다.")
                    else:
                        try:
                            from save_result.export_taxonomy_translated import (
                                load_all_taxonomies as ett_load,
                                create_excel_report as ett_excel
                            )
                            import httpx
                            from openai import OpenAI
                            
                            http_client = httpx.Client(verify=False)
                            client = OpenAI(api_key=api_key, http_client=http_client)
                            
                            st.write("📂 Taxonomy 구조 로딩 및 GPT 번역 중...")
                            st.write("⏳ GPT API 호출로 시간이 걸릴 수 있습니다...")
                            
                            all_rows_tr, dim_summaries_tr = ett_load(sr_data_dir, client)
                            st.write(f"  → {len(all_rows_tr)} 노드, {len(dim_summaries_tr)} 차원 번역 완료")
                            
                            out_translated = output_dir / f"{sr_dataset}_taxonomy_translated.xlsx"
                            st.write("📊 번역 Excel 리포트 생성 중...")
                            ett_excel(out_translated, all_rows_tr, dim_summaries_tr)
                            
                            st.success(f"✅ 완료! {len(all_rows_tr)}개 노드 번역 및 저장")
                            generated_files[out_translated.name] = out_translated
                            
                        except Exception as e:
                            st.error(f"❌ 오류: {e}")
                            import traceback
                            st.code(traceback.format_exc())
                
                current_step += 1
            
            # ============ Step 6: Merged 결과 한글 라벨 변환 ============
            if step6:
                progress.progress(current_step / max(total_steps, 1), text="6️⃣ Merged 결과 한글 라벨 변환...")
                with st.expander("6️⃣ Merged 결과 한글 라벨 변환", expanded=True):
                    try:
                        # 1) translated xlsx 찾기 (이번 실행에서 생성되었거나 기존 파일)
                        translated_file = output_dir / f"{sr_dataset}_taxonomy_translated.xlsx"
                        if not translated_file.exists():
                            st.error(f"❌ 번역 파일을 찾을 수 없습니다: {translated_file.name}")
                            st.info("5️⃣ 단계를 먼저 실행해 주세요.")
                        else:
                            st.write(f"📂 번역 매핑 로딩: {translated_file.name}")
                            df_tr = pd.read_excel(translated_file, sheet_name="전체 차원")
                            
                            # 영문→한글 매핑 생성 (기술명 → 기술명_한글)
                            en_to_kr = {}
                            for _, tr_row in df_tr.iterrows():
                                en_name = str(tr_row.get('기술명', '')).strip()
                                kr_name = str(tr_row.get('기술명_한글', '')).strip()
                                if en_name and kr_name and en_name != 'nan' and kr_name != 'nan':
                                    en_to_kr[en_name] = kr_name
                            
                            st.write(f"  → {len(en_to_kr)}개 영문→한글 매핑 로드 완료")
                            
                            if not en_to_kr:
                                st.warning("⚠️ 매핑 데이터가 비어있습니다.")
                            else:
                                # 2) merged xlsx/csv 찾기
                                merged_xlsx = output_dir / f"{sr_dataset}_taxonomy_merged.xlsx"
                                merged_csv = output_dir / f"{sr_dataset}_taxonomy_merged.csv"
                                
                                files_updated = 0
                                
                                for merged_file in [merged_xlsx, merged_csv]:
                                    if merged_file.exists():
                                        st.write(f"🔄 한글 변환 중: {merged_file.name}")
                                        
                                        if merged_file.suffix == '.xlsx':
                                            df_merged = pd.read_excel(merged_file)
                                        else:
                                            df_merged = pd.read_csv(merged_file)
                                        
                                        if 'all_labels' not in df_merged.columns:
                                            st.warning(f"  ⚠️ {merged_file.name}에 'all_labels' 컬럼이 없습니다.")
                                            continue
                                        
                                        # all_labels 한글 변환 ("차원:영문Label | 차원:영문Label" → "차원:한글Label | 차원:한글Label")
                                        def convert_labels_to_korean(all_labels_str):
                                            if not all_labels_str or pd.isna(all_labels_str) or str(all_labels_str).strip() == '':
                                                return ''
                                            parts = str(all_labels_str).split(' | ')
                                            kr_parts = []
                                            for part in parts:
                                                if ':' in part:
                                                    dim_part, label_part = part.split(':', 1)
                                                    kr_label = en_to_kr.get(label_part.strip(), label_part.strip())
                                                    kr_parts.append(f"{dim_part}:{kr_label}")
                                                else:
                                                    kr_label = en_to_kr.get(part.strip(), part.strip())
                                                    kr_parts.append(kr_label)
                                            return ' | '.join(kr_parts)
                                        
                                        # 원본 all_labels 보존 후 한글 컬럼 추가
                                        df_merged['all_labels_korean'] = df_merged['all_labels'].apply(convert_labels_to_korean)
                                        
                                        # 개별 dimension 컬럼도 한글 변환 (path 내 영문 label → 한글)
                                        dim_cols = [c for c in df_merged.columns if c.endswith(')') and '_(' in c]
                                        for dim_col in dim_cols:
                                            def convert_path_to_korean(path_str):
                                                if not path_str or pd.isna(path_str) or str(path_str).strip() == '':
                                                    return ''
                                                paths = str(path_str).split(' | ')
                                                kr_paths = []
                                                for path in paths:
                                                    segments = path.split('/')
                                                    kr_segments = [en_to_kr.get(seg.strip(), seg.strip()) for seg in segments]
                                                    kr_paths.append('/'.join(kr_segments))
                                                return ' | '.join(kr_paths)
                                            
                                            kr_col_name = f"{dim_col}_korean"
                                            df_merged[kr_col_name] = df_merged[dim_col].apply(convert_path_to_korean)
                                        
                                        # 저장
                                        if merged_file.suffix == '.xlsx':
                                            df_merged.to_excel(merged_file, index=False, engine='openpyxl')
                                        else:
                                            df_merged.to_csv(merged_file, index=False, encoding='utf-8')
                                        
                                        converted_count = (df_merged['all_labels_korean'] != '').sum()
                                        st.write(f"  ✅ {merged_file.name} 업데이트 완료 ({converted_count}건 변환)")
                                        files_updated += 1
                                    else:
                                        st.info(f"  ℹ️ {merged_file.name} 파일 없음 (1️⃣ 단계를 먼저 실행)")
                                
                                if files_updated > 0:
                                    st.success(f"✅ {files_updated}개 파일 한글 라벨 변환 완료!")
                                    
                                    # 매핑 미리보기
                                    with st.expander("🔍 영문→한글 매핑 미리보기", expanded=False):
                                        mapping_df = pd.DataFrame([
                                            {'영문': k, '한글': v} for k, v in list(en_to_kr.items())[:50]
                                        ])
                                        st.dataframe(mapping_df)
                                        if len(en_to_kr) > 50:
                                            st.info(f"... 외 {len(en_to_kr) - 50}개")
                                else:
                                    st.warning("⚠️ 업데이트할 merged 파일이 없습니다. 1️⃣ 단계를 먼저 실행하세요.")
                    
                    except Exception as e:
                        st.error(f"❌ 오류: {e}")
                        import traceback
                        st.code(traceback.format_exc())
                
                current_step += 1
            
            progress.progress(1.0, text="✅ 모든 단계 완료!")
            
            # ============ Results summary ============
            if generated_files:
                st.markdown("---")
                st.subheader("📦 생성된 파일")
                st.info(f"📂 출력 폴더: {output_dir}")
                
                for fname, fpath in generated_files.items():
                    col_name, col_dl = st.columns([3, 1])
                    with col_name:
                        file_size = fpath.stat().st_size
                        size_str = f"{file_size / 1024:.1f} KB" if file_size < 1024 * 1024 else f"{file_size / (1024*1024):.1f} MB"
                        st.write(f"📄 **{fname}** ({size_str})")
                    with col_dl:
                        with open(fpath, 'rb') as f:
                            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if fname.endswith('.xlsx') else "text/csv"
                            st.download_button(
                                label="📥",
                                data=f.read(),
                                file_name=fname,
                                mime=mime,
                                key=f"dl_{fname}"
                            )
            
            # Clean up temp file
            tmp_excel = output_dir / "temp_original.xlsx"
            if tmp_excel.exists():
                try:
                    os.remove(tmp_excel)
                except:
                    pass
        
        finally:
            # Always clear override config
            try:
                from save_result.config_utils import clear_override_config
                clear_override_config()
            except:
                pass


def generate_yaml_from_excel(df):
    """Excel 데이터에서 Dimension YAML 파일 생성"""
    import pandas as pd
    
    yaml_lines = ["dimensions:"]
    
    for _, row in df.iterrows():
        dim_name = row.get('Level1_Dimension_Name', '')
        dim_def = row.get('Level1_Dimension_Definitions', '')
        node_def = row.get('Level1_Node_Dimension_Definitions', '')
        
        if pd.isna(dim_name) or not str(dim_name).strip():
            continue
        
        dim_name = str(dim_name).strip()
        dim_def = str(dim_def).strip() if pd.notna(dim_def) else ''
        node_def = str(node_def).strip() if pd.notna(node_def) else ''
        
        # Escape single quotes in YAML
        dim_def_escaped = dim_def.replace("'", "''")
        node_def_escaped = node_def.replace("'", "''")
        
        yaml_lines.append(f"  {dim_name}:")
        yaml_lines.append(f"    definition: '{dim_def_escaped}'")
        yaml_lines.append(f"    node_definition: '{node_def_escaped}'")
    
    return "\n".join(yaml_lines) + "\n"


def check_taxonomy_data_completeness(df, level_cols):
    """각 레벨에서 Dimension_Name 데이터가 누락된 레벨 목록 반환"""
    import pandas as pd
    missing_levels = []
    
    for lv in level_cols:
        dim_name_col = f'{lv}_Dimension_Name'
        desc_col = f'{lv}_Description'
        
        if dim_name_col not in df.columns:
            # Dimension_Name 컬럼 자체가 없으면 누락
            if desc_col in df.columns and df[desc_col].notna().any():
                missing_levels.append(lv)
            continue
        
        # Description은 있는데 Dimension_Name이 없는 행이 있는지 확인
        if desc_col in df.columns:
            has_desc = df[desc_col].notna()
            has_dim_name = df[dim_name_col].notna()
            if (has_desc & ~has_dim_name).any():
                missing_levels.append(lv)
    
    return missing_levels


def gpt_generate_dimension_from_description(description, level_name, api_key):
    """GPT를 사용하여 Description에서 Dimension_Name, Definitions, Node_Definitions 생성"""
    import httpx
    from openai import OpenAI
    
    client = OpenAI(
        api_key=api_key,
        http_client=httpx.Client(verify=False)
    )
    
    output_format = '''{
  "Dimension_Name": "lithium",
  "Dimension_Definitions": "Lithium: Lithium resource extraction and manufacturing...",
  "Node_Dimension_Definitions": "Related patents focus on methods for efficiently extracting lithium..."
}'''
    
    prompt = f"""<입력 정보>를 참고해서, [기술]에 대한 [Description]을 읽고, 이를 [Two Definitions] 성격에 따라 재구성해줘. <출력 예시>를 참고해서 결과를 json 형태로 생성해.

---
<입력 정보>
[기술]
{level_name}

[Description]
{description}

[Two Definitions]
1) dimension_definitions: Dimension에 대해서 LLM이 알 수 있도록 Dimension의 정의 작성 
2) node_dimension_definitions: 해당 Dimension에 포함될 특허는 어떤 내용(기술) 또는 방식들이 포함되는지 예시 내포 작성     
</입력 정보>
---

Output your result ONLY in the following JSON format.
Do not include explanations outside the JSON.

---
<출력 예시>
{output_format}
</출력 예시>
---

CRITICAL JSON RULES:
- Output MUST be valid JSON.
- Do NOT include comments (// or /* */).
- DO NOT wrap the output in ``` or ```json. Output raw JSON only.
- Do NOT include explanations, apologies, or notes.
- If a suitable rationale sentence cannot be found, use an empty string "" instead.
- Every value in JSON must be a valid JSON type (string or array).
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Your role is to draft detailed and precise technology classification definitions."},
                {"role": "user", "content": prompt}
            ],
            timeout=60
        )
        result_text = response.choices[0].message.content.strip()
        
        # Clean JSON markers if present
        if result_text.startswith('```'):
            result_text = result_text.split('\n', 1)[1]
            if result_text.endswith('```'):
                result_text = result_text[:-3]
            result_text = result_text.strip()
        
        result = json.loads(result_text)
        return result
    except Exception as e:
        print(f"GPT API 오류: {e}")
        return None


def build_taxonomy_tree(df, level_columns=None, topic=""):
    """
    df에서 Level1~Level4 계층 정보와 Definition을 읽어
    중첩 JSON 트리(DAG) 구조로 변환하는 함수.
    
    Level 번호는 1씩 줄여서 Level1→Level0, Level2→Level1, ... 으로 변환.
    
    Returns:
        dict: 중첩 트리 구조의 Taxonomy
    """
    import pandas as pd
    
    if level_columns is None:
        level_columns = ['Level1', 'Level2', 'Level3', 'Level4']
    
    # Topic 컬럼 확인 (대소문자 구분 안함)
    topic_col = None
    for col in df.columns:
        if col.lower() == 'topic':
            topic_col = col
            break
    
    # 루트 노드 생성
    taxonomy = {
        "dimension_name": "root",
        "level": -1,
        "dimension_definitions": "",
        "node_dimension_definitions": "",
        "children": []
    }
    
    def get_definition_info(df_subset, level_col):
        """해당 레벨의 Definition 정보를 가져오는 함수"""
        dim_name_col = f'{level_col}_Dimension_Name'
        dim_def_col = f'{level_col}_Dimension_Definitions'
        node_def_col = f'{level_col}_Node_Dimension_Definitions'
        desc_en_col = f'{level_col}_Description'
        
        info = {
            "dimension_name": "",
            "dimension_definitions": "",
            "node_dimension_definitions": "",
            "description": ""
        }
        
        # 첫 번째 유효한 값 가져오기
        if dim_name_col in df_subset.columns:
            vals = df_subset[dim_name_col].dropna()
            if len(vals) > 0:
                info["dimension_name"] = str(vals.iloc[0])
        
        if dim_def_col in df_subset.columns:
            vals = df_subset[dim_def_col].dropna()
            if len(vals) > 0:
                info["dimension_definitions"] = str(vals.iloc[0])
        
        if node_def_col in df_subset.columns:
            vals = df_subset[node_def_col].dropna()
            if len(vals) > 0:
                info["node_dimension_definitions"] = str(vals.iloc[0])
        
        if desc_en_col in df_subset.columns:
            vals = df_subset[desc_en_col].dropna()
            if len(vals) > 0:
                info["description"] = str(vals.iloc[0])
        
        return info
    
    def build_subtree(df_subset, level_idx):
        """재귀적으로 서브트리를 구성하는 함수"""
        if level_idx >= len(level_columns):
            return []
        
        current_level_col = level_columns[level_idx]
        new_level_num = level_idx  # Level1→Level0, Level2→Level1, ...
        
        # 현재 레벨에서 NaN이 아닌 고유 값들
        if current_level_col not in df_subset.columns:
            return []
            
        unique_values = df_subset[current_level_col].dropna().unique()
        
        children = []
        for value in unique_values:
            # 해당 값에 해당하는 행들 필터링
            mask = df_subset[current_level_col] == value
            subset = df_subset[mask]
            
            if len(subset) == 0:
                continue
            
            # Definition 정보 가져오기
            def_info = get_definition_info(subset, current_level_col)
            
            # Topic 정보 가져오기 (Level 0에서만)
            actual_topic = topic
            if level_idx == 0 and topic_col:
                topic_values = subset[topic_col].dropna()
                if len(topic_values) > 0:
                    actual_topic = str(topic_values.iloc[0]).strip()
            
            # 노드 생성
            node = {
                "dimension_name": def_info["dimension_name"] if def_info["dimension_name"] else str(value),
                "original_value": str(value),
                "level": new_level_num,
                "description": def_info["description"],
                "dimension_definitions": def_info["dimension_definitions"],
                "node_dimension_definitions": def_info["node_dimension_definitions"],
                "topic": actual_topic,  # Topic 정보 저장
                "children": build_subtree(subset, level_idx + 1)
            }
            
            children.append(node)
        
        return children
    
    # 트리 구축
    taxonomy["children"] = build_subtree(df, 0)
    
    return taxonomy


def node_to_dag_text(node, indent=0, level0_label=None):
    """노드를 DAG 텍스트 형식으로 변환하는 함수"""
    prefix = "     " * indent
    sep = prefix + "-" * 40
    lines = []
    
    label = node.get("dimension_name", node.get("original_value", "root"))
    # dimension_name이 비어있으면 original_value 사용
    if not label or label == "":
        label = node.get("original_value", "root")
    
    level = node.get("level", -1)
    dim_def = node.get("description", "") or "None"
    children = node.get("children", [])
    topic = node.get("topic", "")
    
    # Dimension 결정: 모든 레벨에서 Level0의 Dimension_Name으로 통일
    # 단, Level0의 Label만 Topic 값 사용
    if level == 0:
        level0_label = label  # Level0의 Dimension_Name 저장 
        label = topic if topic else label  # Level0 Label은 Topic 사용
        dimension = level0_label  # Dimension은 Level0의 Dimension_Name
    else:
        dimension = level0_label if level0_label else "technology_classification"
    
    lines.append(f"{prefix}Label: {label}")
    lines.append(f"{prefix}Dimension: {dimension}")
    lines.append(f"{prefix}Description: {dim_def}")
    lines.append(f"{prefix}Level: {level}")
    lines.append(f"{prefix}Source: Initial")
    lines.append(sep)
    
    if children:
        lines.append(f"{prefix}Children:")
        for child in children:
            lines.extend(node_to_dag_text(child, indent + 1, level0_label))
        lines.append(sep)
    
    return lines


def taxonomy_to_dag_text(taxonomy_tree):
    """전체 Taxonomy 트리를 DAG 텍스트 형식으로 변환"""
    all_lines = []
    
    # 루트의 children을 최상위 노드로 출력
    for root_child in taxonomy_tree.get("children", []):
        all_lines.extend(node_to_dag_text(root_child, indent=0))
        all_lines.append("")  # 최상위 노드 간 빈 줄
    
    return "\n".join(all_lines)


def save_dag_by_level0(taxonomy_tree):
    """Level 0별로 DAG 텍스트를 분리해서 저장하는 함수"""
    generated_files = {}
    
    for root_child in taxonomy_tree.get("children", []):
        # Level 0 노드의 label 이름 가져오기
        label0_name = root_child.get("dimension_name", root_child.get("original_value", "unknown"))
        
        # 파일명에 사용할 수 없는 문자들을 안전하게 변환
        safe_filename = label0_name.replace("/", "_").replace("\\", "_").replace(":", "_").replace("*", "_").replace("?", "_").replace('"', "_").replace("<", "_").replace(">", "_").replace("|", "_")
        
        # 개별 노드의 DAG 텍스트 생성
        individual_dag_text = "\n".join(node_to_dag_text(root_child, indent=0))
        
        # 파일명 생성
        filename = f"initial_taxo_{safe_filename}.txt"
        
        generated_files[filename] = individual_dag_text
    
    return generated_files


def build_node_text(label, description, level, dimension, indent=""):
    """단일 노드의 텍스트 생성 (기존 함수 유지)"""
    lines = []
    lines.append(f"{indent}Label: {label}")
    lines.append(f"{indent}Dimension: {dimension}")
    lines.append(f"{indent}Description: {description}")
    lines.append(f"{indent}Level: {level}")
    lines.append(f"{indent}Source: Initial")
    lines.append(f"{indent}{'='*40 if level == 0 else '-'*40}")
    return lines


def generate_initial_taxo_files(df, level_cols, output_dir, topic="", use_gpt=False, api_key=None):
    """Excel 데이터에서 initial_taxo_*.txt 파일들 생성 (DAG 구조 사용)"""
    import pandas as pd
    import time
    
    generated_files = {}
    
    # Step 1: Fill missing Dimension data with GPT if needed
    df_work = df.copy()
    
    if use_gpt and api_key:
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        total_to_process = 0
        processed = 0
        
        # Count total items to process
        for s, lv in enumerate(level_cols):
            dim_name_col = f'{lv}_Dimension_Name'
            desc_col = f'{lv}_Description'
            if desc_col not in df_work.columns:
                continue
            
            selected_levels = level_cols[:s+1]
            unique_combos = df_work[selected_levels].drop_duplicates()
            
            for _, row in unique_combos.iterrows():
                if row[selected_levels].isna().any():
                    continue
                # Check if Dimension_Name is missing
                mask = pd.Series(True, index=df_work.index)
                for col in selected_levels:
                    mask = mask & (df_work[col] == row[col])
                idxs = df_work[mask].index
                if len(idxs) == 0:
                    continue
                
                if dim_name_col not in df_work.columns or pd.isna(df_work.loc[idxs[0], dim_name_col]) or str(df_work.loc[idxs[0], dim_name_col]).strip() == '':
                    if pd.notna(df_work.loc[idxs[0], desc_col]) and str(df_work.loc[idxs[0], desc_col]).strip():
                        total_to_process += 1
        
        if total_to_process > 0:
            st.info(f"🤖 GPT로 {total_to_process}개 항목 처리 중...")
        
        # Process each level
        for s, lv in enumerate(level_cols):
            dim_name_col = f'{lv}_Dimension_Name'
            dim_def_col = f'{lv}_Dimension_Definitions'
            node_def_col = f'{lv}_Node_Dimension_Definitions'
            desc_col = f'{lv}_Description'
            
            if desc_col not in df_work.columns:
                continue
            
            # Ensure columns exist
            for col in [dim_name_col, dim_def_col, node_def_col]:
                if col not in df_work.columns:
                    df_work[col] = None
            
            selected_levels = level_cols[:s+1]
            unique_combos = df_work[selected_levels].drop_duplicates()
            
            for _, row in unique_combos.iterrows():
                if row[selected_levels].isna().any():
                    continue
                
                mask = pd.Series(True, index=df_work.index)
                for col in selected_levels:
                    mask = mask & (df_work[col] == row[col])
                idxs = df_work[mask].index
                if len(idxs) == 0:
                    continue
                
                # Check if already has Dimension_Name
                current_name = df_work.loc[idxs[0], dim_name_col]
                if pd.notna(current_name) and str(current_name).strip():
                    continue
                
                description = df_work.loc[idxs[0], desc_col]
                if pd.isna(description) or not str(description).strip():
                    continue
                
                level_name = "-".join([str(row[col]) for col in selected_levels])
                status_text.text(f"🔄 처리 중: {level_name}")
                
                result = gpt_generate_dimension_from_description(str(description), level_name, api_key)
                
                if result:
                    df_work.loc[idxs, dim_name_col] = result.get("Dimension_Name", "")
                    df_work.loc[idxs, dim_def_col] = result.get("Dimension_Definitions", "")
                    df_work.loc[idxs, node_def_col] = result.get("Node_Dimension_Definitions", "")
                
                processed += 1
                progress_bar.progress(processed / max(total_to_process, 1))
                time.sleep(1)  # API rate limiting
        
        progress_bar.progress(1.0)
        status_text.text("✅ GPT 처리 완료!")
    
    # Step 2: DAG 구조를 사용하여 Taxonomy 트리 구축
    if 'Level1' not in df_work.columns:
        st.error("❌ Level1 컬럼이 필요합니다.")
        return {}
    
    try:
        # DAG 트리 구조 생성
        taxonomy_tree = build_taxonomy_tree(df_work, level_cols, topic)
        
        # Level 0별로 DAG 텍스트 분리 저장
        dag_files = save_dag_by_level0(taxonomy_tree)
        
        # 파일 저장 및 결과 수집
        for filename, content in dag_files.items():
            filepath = output_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            generated_files[filename] = content
        
        st.success(f"✅ {len(generated_files)}개의 DAG 구조 taxonomy 파일 생성 완료!")
        
        # 트리 구조 요약 출력
        with st.expander("📊 생성된 Taxonomy 구조", expanded=False):
            def print_tree_summary(node, indent=0):
                prefix = "  " * indent
                connector = "|-- " if indent > 0 else ""
                
                name = node.get("original_value", node.get("dimension_name", "root"))
                level = node.get("level", -1)
                n_children = len(node.get("children", []))
                has_def = "O" if node.get("dimension_definitions", "") else "X"
                topic = node.get("topic", "")
                
                if level >= 0:
                    level_info = f"[Level{level}] {name}"
                    if level == 0 and topic:
                        level_info += f" (Topic: {topic})"
                    level_info += f" (definitions: {has_def}, children: {n_children})"
                    st.text(f"{prefix}{connector}{level_info}")
                else:
                    st.text(f"{prefix}[ROOT] (children: {n_children})")
                
                for child in node.get("children", []):
                    print_tree_summary(child, indent + 1)
            
            st.text("=== Taxonomy 트리 구조 ===")
            print_tree_summary(taxonomy_tree)
    
    except Exception as e:
        st.error(f"❌ DAG 구조 생성 오류: {e}")
        import traceback
        st.code(traceback.format_exc())
        return {}
    
    return generated_files


def _combine_descriptions(dim_def, node_def):
    """Dimension_Definitions와 Node_Dimension_Definitions를 결합"""
    import pandas as pd
    parts = []
    if pd.notna(dim_def) and str(dim_def).strip():
        parts.append(str(dim_def).strip())
    if pd.notna(node_def) and str(node_def).strip():
        parts.append(str(node_def).strip())
    return " ".join(parts) if parts else "No description available."


def _build_children(sub_df, level_cols, current_depth, indent_unit, root_label, topic=""):
    """재귀적으로 자식 노드 트리 텍스트 생성"""
    import pandas as pd
    
    if current_depth >= len(level_cols):
        return []
    
    current_level = level_cols[current_depth]
    indent = indent_unit * current_depth
    
    lines = []
    
    # Get unique values at current level
    unique_values = sub_df[current_level].dropna().unique()
    
    for val in unique_values:
        mask = sub_df[current_level] == val
        child_df = sub_df[mask].copy()
        
        # Get dimension info for this node
        dim_name_col = f'{current_level}_Dimension_Name'
        dim_def_col = f'{current_level}_Dimension_Definitions'
        node_def_col = f'{current_level}_Node_Dimension_Definitions'
        desc_col = f'{current_level}_Description'
        
        # Get label (Dimension_Name or fallback to snake_case of value)
        dim_name = child_df.iloc[0].get(dim_name_col, None) if dim_name_col in child_df.columns else None
        if pd.isna(dim_name) or not str(dim_name).strip():
            dim_name = str(val).lower().replace(' ', '_').replace('/', '_')
        dim_name = str(dim_name).strip()
        
        # Get description
        dim_def = child_df.iloc[0].get(dim_def_col, None) if dim_def_col in child_df.columns else None
        node_def = child_df.iloc[0].get(node_def_col, None) if node_def_col in child_df.columns else None
        desc = child_df.iloc[0].get(desc_col, None) if desc_col in child_df.columns else None
        
        # Use Definitions if available, otherwise use Description
        description = _combine_descriptions(dim_def, node_def)
        if description == "No description available." and pd.notna(desc):
            description = str(desc).strip()
        
        # Get dimension for this level
        if current_depth == 0:
            # Level 0: use topic as dimension
            dimension = topic if topic else dim_name
        else:
            # Level 1+: use root label as dimension  
            dimension = root_label
        
        # Build node text
        lines.extend(build_node_text(dim_name, description, current_depth, dimension, indent))
        
        # Recurse into children
        child_lines = _build_children(child_df, level_cols, current_depth + 1, indent_unit, root_label, topic)
        if child_lines:
            lines.append(f"{indent}Children:")
            lines.extend(child_lines)
        
        # Close separator
        lines.append(f"{indent}{'-'*40}")
    
    return lines


def run_taxoadapt(config, dataset, topic, max_depth, init_levels, max_density, llm, 
                   openai_api_key=None, huggingface_token=None, uploaded_data=None, 
                   upload_format=None, initial_taxonomy_files=None, test_samples=None,
                   resume=False):
    """Run TaxoAdapt (main2.py) with the given configuration"""
    st.session_state.running = True
    employee_id = st.session_state.get('employee_id', 'unknown')
    
    try:
        # Prepare data directory (user-scoped)
        data_dir = get_user_dataset_path(dataset)
        os.makedirs(data_dir, exist_ok=True)
        
        # === Create user-specific code files to avoid conflicts ===
        user_code_dir = BASE_DIR / "user_data" / employee_id / "code"
        os.makedirs(user_code_dir, exist_ok=True)
        
        # Copy original model_definitions.py if not present
        user_model_defs = user_code_dir / "model_definitions.py"
        if not user_model_defs.exists():
            import shutil
            shutil.copy(BASE_DIR / "model_definitions.py", user_model_defs)
        
        # Always copy latest main2.py to ensure parallel features are available
        user_main2 = user_code_dir / "main2.py"
        import shutil
        shutil.copy(BASE_DIR / "main2.py", user_main2)
        print(f"[DEBUG] Updated user main2.py: {user_main2}")
        
        # Ensure user-specific .env file exists and is updated
        user_env_path = ensure_user_env_exists()
        if openai_api_key:
            update_user_env('OPENAI_API_KEY', openai_api_key)
        # Use the actual selected model name instead of just 'gpt'
        selected_model_name = st.session_state.get("selected_model", 'gpt-5-2025-08-07')
        update_user_env('OPENAI_MODEL', selected_model_name)
        
        # Create user-specific prompts.py with current config
        user_prompts = user_code_dir / "prompts.py"
        create_user_prompts_file(user_prompts, config, topic)
        
        # 디버깅: user-specific prompts.py 생성 확인
        st.info(f"[DEBUG] User prompts.py created at: {user_prompts}")
        if user_prompts.exists():
            # prompts.py에서 dimension_definitions 확인
            try:
                with open(user_prompts, 'r', encoding='utf-8') as f:
                    prompts_content = f.read()
                if 'dimension_definitions = {' in prompts_content:
                    st.info("[DEBUG] ✅ dimension_definitions found in user prompts.py")
                else:
                    st.warning("[DEBUG] ❌ dimension_definitions NOT found in user prompts.py")
            except Exception as e:
                st.warning(f"[DEBUG] Error reading user prompts.py: {e}")

        # Process uploaded data if provided
        if uploaded_data is not None:
            with st.spinner("📤 Processing uploaded data..."):
                num_papers = process_uploaded_data(uploaded_data, dataset, upload_format)
            st.success(f"✅ Custom data processed ({num_papers} papers)")

        # Process initial taxonomy files if provided
        if initial_taxonomy_files:
            with st.spinner("📤 Processing initial taxonomy files..."):
                for taxonomy_file in initial_taxonomy_files:
                    file_path = data_dir / taxonomy_file.name
                    with open(file_path, 'wb') as f:
                        f.write(taxonomy_file.getvalue())
                    st.info(f"  Saved: {taxonomy_file.name}")
            st.success(f"✅ {len(initial_taxonomy_files)} initial taxonomy file(s) saved")

        # Build isolated environment for subprocess (never modify os.environ)
        env = os.environ.copy()
        # Set API key from session-specific sources (not global os.environ)
        effective_api_key = openai_api_key or st.session_state.get('openai_api_key', '') or read_user_env_value('OPENAI_API_KEY', '')
        if effective_api_key:
            env['OPENAI_API_KEY'] = effective_api_key
        # Pass extra API keys for parallel dimension processing
        for i in range(1, 20):
            extra_key = read_user_env_value(f'OPENAI_API_KEY_{i}', '')
            if extra_key:
                env[f'OPENAI_API_KEY_{i}'] = extra_key
        # Set model from session state
        env['OPENAI_MODEL'] = st.session_state.get('selected_model', read_user_env_value('OPENAI_MODEL', 'gpt-5-2025-08-07'))
        if huggingface_token:
            env['HUGGINGFACE_TOKEN'] = huggingface_token
            env['HF_TOKEN'] = huggingface_token

        # Prepare command - Use user-specific main2.py
        cmd = [
            sys.executable,
            str(user_main2),
            "--topic", topic,
            "--dataset", dataset,
            "--llm", llm,
            "--max_depth", str(max_depth),
            "--init_levels", str(init_levels),
            "--max_density", str(max_density),
            "--data_dir", str(data_dir)
        ]
        # Add test_samples if specified
        if test_samples:
            cmd.extend(["--test_samples", str(test_samples)])
        # Add resume flag if specified
        if resume:
            cmd.append("--resume")

        st.info(f"🚀 Running TaxoAdapt with {len(config.dimensions)} dimensions...")
        st.info(f"[DEBUG] Dimensions: {list(config.dimensions.keys())}")
        st.code(" ".join(cmd), language="bash")

        # Set PYTHONPATH to prioritize user-specific files
        env['PYTHONPATH'] = str(user_code_dir) + os.pathsep + env.get('PYTHONPATH', '')
        
        st.success(f"✅ User-specific code files created in {user_code_dir}")

        # Real-time execution log streaming with fixed height and scrollbar
        st.subheader("📄 Execution Log")
        
        # CSS for fixed height log container with scrollbar
        st.markdown("""
        <style>
        .log-container {
            height: 400px;
            overflow-y: auto;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px;
            background-color: #f8f9fa;
            font-family: 'Courier New', monospace;
            font-size: 14px;
            white-space: pre-wrap;
            margin-bottom: 20px;
        }
        </style>
        """, unsafe_allow_html=True)
        
        # Create scrollable log area
        log_area = st.empty()
        status_text = st.empty()
        
        stdout_lines = []
        stderr_lines = []
        
        import time
        
        status_text.info("⏳ Running... This may take a while.")
        # Force unbuffered Python output for real-time log streaming
        env['PYTHONUNBUFFERED'] = '1'
        
        process = subprocess.Popen(
            cmd,
            cwd=str(BASE_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1  # line-buffered
        )
        
        # Windows-compatible threading approach for real-time log streaming
        import threading
        import queue
        
        # Thread-safe queues for communication
        stdout_queue = queue.Queue()
        stderr_queue = queue.Queue()
        
        def read_stream(stream, output_queue, lines_list):
            """Read from stream and put lines into queue and list"""
            try:
                while True:
                    line = stream.readline()
                    if not line:
                        break
                    lines_list.append(line)
                    output_queue.put(('data', line))
            except:
                pass
            finally:
                output_queue.put(('end', None))
        
        # Start reader threads
        stdout_thread = threading.Thread(target=read_stream, args=(process.stdout, stdout_queue, stdout_lines))
        stderr_thread = threading.Thread(target=read_stream, args=(process.stderr, stderr_queue, stderr_lines))
        
        stdout_thread.daemon = True
        stderr_thread.daemon = True
        stdout_thread.start()
        stderr_thread.start()
        
        last_update_time = time.time()
        streams_alive = 2
        
        while streams_alive > 0:
            # Check both queues for new data
            updated = False
            
            # Check stdout queue
            try:
                while True:
                    msg_type, data = stdout_queue.get_nowait()
                    if msg_type == 'end':
                        streams_alive -= 1
                        break
                    updated = True
            except queue.Empty:
                pass
            
            # Check stderr queue  
            try:
                while True:
                    msg_type, data = stderr_queue.get_nowait()
                    if msg_type == 'end':
                        streams_alive -= 1
                        break
                    updated = True
            except queue.Empty:
                pass
            
            # Update display at most every 0.3 seconds or when process ends
            now = time.time()
            if (updated and now - last_update_time >= 0.3) or streams_alive == 0:
                display_text = ""
                if stdout_lines:
                    display_text += "".join(stdout_lines[-200:])  # show last 200 lines
                if stderr_lines:
                    display_text += "\n--- STDERR ---\n"
                    display_text += "".join(stderr_lines[-50:])
                if display_text:
                    try:
                        # Escape HTML entities and preserve formatting
                        escaped_text = display_text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                        log_area.markdown(f'<div class="log-container">{escaped_text}</div>', unsafe_allow_html=True)
                    except Exception:
                        pass  # WebSocket disconnected, skip UI update
                last_update_time = now
            
            # Small sleep to prevent busy waiting
            if streams_alive > 0:
                time.sleep(0.1)
        process.wait()
        
        # Final display update with all output
        final_display = ""
        if stdout_lines:
            final_display += "".join(stdout_lines)
        if stderr_lines:
            final_display += "\n--- STDERR ---\n"
            final_display += "".join(stderr_lines)
        if final_display:
            try:
                # Escape HTML entities and preserve formatting
                escaped_text = final_display.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                log_area.markdown(f'<div class="log-container">{escaped_text}</div>', unsafe_allow_html=True)
            except Exception:
                pass  # WebSocket disconnected, skip UI update
        
        try:
            status_text.empty()
        except Exception:
            pass
        returncode = process.returncode

        if returncode == 0:
            st.success("✅ TaxoAdapt completed successfully!")
            st.info(f"📁 Results saved to: {data_dir}")
            if data_dir.exists():
                files = [f for f in os.listdir(data_dir) if f.startswith('final_taxo_')]
                if files:
                    st.write("**Generated taxonomies:**")
                    for f in files:
                        st.write(f"- {f}")
                        file_path = data_dir / f
                        try:
                            with open(file_path, 'r', encoding='utf-8', errors='replace') as fp:
                                file_content = fp.read()
                        except UnicodeDecodeError:
                            try:
                                with open(file_path, 'r', encoding='cp949', errors='replace') as fp:
                                    file_content = fp.read()
                            except:
                                with open(file_path, 'rb') as fp:
                                    file_content = fp.read().decode('utf-8', errors='replace')
                        st.download_button(
                            label=f"📥 Download {f}",
                            data=file_content,
                            file_name=f,
                            mime="text/plain" if f.endswith('.txt') else "application/json",
                            key=f"download_{f}"
                        )
        else:
            st.error(f"❌ TaxoAdapt failed with exit code {returncode}")

        # Save execution history
        _user_manager.save_execution_history(employee_id, {
            'action': 'TaxoAdapt 실행',
            'topic': topic,
            'dataset': dataset,
            'dimensions': list(config.dimensions.keys()),
            'max_depth': max_depth,
            'success': returncode == 0,
        })

    except Exception as e:
        st.error(f"❌ Error: {e}")
        import traceback
        st.code(traceback.format_exc())
    finally:
        st.session_state.running = False


def update_prompts_file_dynamic(config: DimensionConfig, user_topic: str = "battery"):
    """
    Dynamically update prompts.py with user-defined dimension definitions.
    This replaces dimension_definitions, node_dimension_definitions, 
    TypeClsSchema, type_cls_system_instruction, User_Topic, and type_cls_main_prompt.
    """
    import re
    
    # Allow custom prompts_path for user-specific file
    if hasattr(update_prompts_file_dynamic, 'prompts_path_override'):
        prompts_path = update_prompts_file_dynamic.prompts_path_override
    else:
        prompts_path = BASE_DIR / 'prompts.py'
    if prompts_path is not None:
        with open(prompts_path, 'r', encoding='utf-8') as f:
            content = f.read()
    else:
        return
    
    # Get dimensions from config
    dims = config.dimensions
    dim_list = list(dims.keys())
    
    # ============ 1. Update User_Topic ============
    pattern = r'User_Topic\s*=\s*"[^"]*"'
    content = re.sub(pattern, f'User_Topic="{user_topic}"', content, count=1)
    
    # ============ 2. Update dimension_definitions ============
    dim_def_str = "dimension_definitions = {\n"
    for dim_name, dim_config in dims.items():
        definition = dim_config.get('definition', '').replace('"""', '\\"\\"\\"')
        dim_def_str += f"    '{dim_name}': \"\"\"{definition}\"\"\",\n"
    dim_def_str += "    }"
    
    pattern = r'dimension_definitions = \{.*?\n    \}'
    content = re.sub(pattern, dim_def_str, content, count=1, flags=re.DOTALL)
    
    # ============ 3. Update node_dimension_definitions ============
    node_dim_def_str = "node_dimension_definitions = {\n"
    for dim_name, dim_config in dims.items():
        node_def = dim_config.get('node_definition', dim_config.get('definition', '')).replace('"""', '\\"\\"\\"')
        node_dim_def_str += f"    '{dim_name}': \"\"\"{node_def}\"\"\",\n"
    node_dim_def_str += "}"
    
    pattern = r'node_dimension_definitions = \{.*?\n\}'
    content = re.sub(pattern, node_dim_def_str, content, count=1, flags=re.DOTALL)
    
    # ============ 4. Update TypeClsSchema with sanitized field names ============
    # Import Field from pydantic at the top if not present
    if 'from pydantic import Field' not in content:
        # Add import after BaseModel import
        content = content.replace('from pydantic import BaseModel', 'from pydantic import BaseModel, Field')
    
    schema_fields = []
    for dim_name in dim_list:
        sanitized = _sanitize_field_name(dim_name)
        if sanitized != dim_name:
            # Use Field with alias for invalid identifiers
            schema_fields.append(f"  {sanitized}: bool = Field(alias='{dim_name}')")
        else:
            # Normal field
            schema_fields.append(f"  {sanitized}: bool")
    
    schema_body = "\n".join(schema_fields)
    new_schema = f"class TypeClsSchema(BaseModel):\n{schema_body}"
    
    pattern = r'class TypeClsSchema\(BaseModel\):[\s\S]*?(?=\n\ndef )'
    content = re.sub(pattern, new_schema + "\n", content, count=1)
    
    # ============ 5. No need to update type_cls_system_instruction ============
    # It's now a function generate_type_cls_system_instruction(dimension_definitions, User_Topic) 
    # that dynamically generates the instruction from the updated dimension_definitions and User_Topic args.
    # So we only need to make sure dimension_definitions and User_Topic are updated (steps 1-2 above).
    
    # ============ 6. No need to update type_cls_main_prompt function ============
    # It already takes (paper, dimension_definitions, User_Topic) as arguments
    # and dynamically generates the prompt. No regex replacement needed.
    
    # Write back
    with open(prompts_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"✅ Updated {prompts_path} with topic '{user_topic}' and {len(dim_list)} dimensions: {dim_list}")


def create_user_prompts_file(user_prompts_path, config: DimensionConfig, user_topic: str = "battery"):
    """
    Create a user-specific prompts.py file with the given configuration.
    This creates a complete standalone prompts.py file for the user.
    """
    import shutil
    
    # Copy original prompts.py as base
    original_prompts = BASE_DIR / 'prompts.py'
    shutil.copy(original_prompts, user_prompts_path)
    
    # Now update it with user-specific configuration
    update_prompts_file_dynamic_with_path(user_prompts_path, config, user_topic)


def update_prompts_file_dynamic_with_path(prompts_path, config: DimensionConfig, user_topic: str = "battery"):
    """
    Update prompts.py at the specified path with user-defined dimension definitions.
    """
    import re
    
    with open(prompts_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Get dimensions from config
    dims = config.dimensions
    dim_list = list(dims.keys())
    
    # ============ 1. Update User_Topic ============
    pattern = r'User_Topic\s*=\s*"[^"]*"'
    content = re.sub(pattern, f'User_Topic="{user_topic}"', content, count=1)
    
    # ============ 2. Update dimension_definitions ============
    dim_def_str = "dimension_definitions = {\n"
    for dim_name, dim_config in dims.items():
        definition = dim_config.get('definition', '').replace('"""', '\\"\\"\\"')
        dim_def_str += f"    '{dim_name}': \"\"\"{definition}\"\"\",\n"
    dim_def_str += "    }"
    
    pattern = r'dimension_definitions = \{.*?\n    \}'
    content = re.sub(pattern, dim_def_str, content, count=1, flags=re.DOTALL)
    
    # ============ 3. Update node_dimension_definitions ============
    node_dim_def_str = "node_dimension_definitions = {\n"
    for dim_name, dim_config in dims.items():
        node_def = dim_config.get('node_definition', dim_config.get('definition', '')).replace('"""', '\\"\\"\\"')
        node_dim_def_str += f"    '{dim_name}': \"\"\"{node_def}\"\"\",\n"
    node_dim_def_str += "}"
    
    pattern = r'node_dimension_definitions = \{.*?\n\}'
    content = re.sub(pattern, node_dim_def_str, content, count=1, flags=re.DOTALL)
    
    # ============ 4. Update TypeClsSchema with sanitized field names ============
    # Import Field from pydantic at the top if not present
    if 'from pydantic import Field' not in content:
        # Add import after BaseModel import
        content = content.replace('from pydantic import BaseModel', 'from pydantic import BaseModel, Field')
    
    schema_fields = []
    for dim_name in dim_list:
        sanitized = _sanitize_field_name(dim_name)
        if sanitized != dim_name:
            # Use Field with alias for invalid identifiers
            schema_fields.append(f"  {sanitized}: bool = Field(alias='{dim_name}')")
        else:
            # Normal field
            schema_fields.append(f"  {sanitized}: bool")
    
    schema_body = "\n".join(schema_fields)
    new_schema = f"class TypeClsSchema(BaseModel):\n{schema_body}"
    
    pattern = r'class TypeClsSchema\(BaseModel\):[\s\S]*?(?=\n\ndef )'
    content = re.sub(pattern, new_schema + "\n", content, count=1)
    
    # Write back
    with open(prompts_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"✅ Updated {prompts_path} with topic '{user_topic}' and {len(dim_list)} dimensions: {dim_list}")


def process_uploaded_data(uploaded_file, dataset_name, upload_format):
    """Process uploaded custom data and save as internal.txt in user's datasets/<dataset_name>/"""
    data_dir = get_user_dataset_path(dataset_name)
    os.makedirs(data_dir, exist_ok=True)
    
    internal_file = data_dir / 'internal.txt'
    papers = []
    
    # Handle Excel files separately (binary format)
    if upload_format == "Excel (xlsx)":
        import pandas as pd
        df = pd.read_excel(uploaded_file)
        df.columns = [col.strip() for col in df.columns]
        
        st.info(f"📋 Excel columns found: {list(df.columns)}")
        
        # Flexible column name matching (including WIPS patent data)
        title_col = None
        abstract_col = None
        patent_id_col = None
        claim_col = None
        
        for col in df.columns:
            col_lower = col.lower()
            # Title columns
            if col_lower in ('title', 'subject', '제목', '발명의 명칭', 'paper_title'):
                title_col = col
            # Abstract columns  
            elif col_lower in ('abstract', 'summary', '초록', '요약', 'paper_abstract'):
                abstract_col = col
            # Patent ID columns (WIPS data)
            elif col_lower in ('patent_id', '출원번호', 'application_number', '특허번호'):
                patent_id_col = col
            # Claim columns (optional for WIPS)
            elif col_lower in ('대표청구항', 'claim', 'claims', '청구항'):
                claim_col = col
        
        if title_col and abstract_col:
            for _, row in df.iterrows():
                title = row.get(title_col, '')
                abstract = row.get(abstract_col, '')
                
                if pd.notna(title) and pd.notna(abstract) and str(title).strip() and str(abstract).strip():
                    paper_data = {
                        "Title": str(title).strip(),
                        "Abstract": str(abstract).strip()
                    }
                    
                    # Add patent_id if available (WIPS data)
                    if patent_id_col and pd.notna(row.get(patent_id_col, '')):
                        paper_data["Patent_ID"] = str(row.get(patent_id_col, '')).strip()
                    
                    # Optionally append claim to abstract (WIPS data)
                    if claim_col and pd.notna(row.get(claim_col, '')):
                        claim_text = str(row.get(claim_col, '')).strip()
                        if claim_text:
                            paper_data["Abstract"] += f"\\n\\n[대표청구항] {claim_text}"
                    
                    papers.append(paper_data)
                    
            col_mapping = f"'{title_col}' → Title, '{abstract_col}' → Abstract"
            if patent_id_col:
                col_mapping += f", '{patent_id_col}' → Patent_ID"
            if claim_col:
                col_mapping += f", '{claim_col}' → Claim (appended to Abstract)"
            st.info(f"Using columns: {col_mapping}")
        else:
            st.error(f"Could not find title/abstract columns. Found: {list(df.columns)}")
            st.info("Expected column names: 'Title'/'title'/'제목'/'발명의 명칭' and 'Abstract'/'abstract'/'초록'/'요약'")
            return 0
    else:
        # Read uploaded file as text
        content = uploaded_file.getvalue().decode('utf-8')
    
        if upload_format == "JSON Lines (Title & Abstract)":
            # Parse JSON Lines
            for line in content.strip().split('\n'):
                if line.strip():
                    try:
                        paper = json.loads(line)
                        if 'title' in paper and 'abstract' in paper:
                            papers.append({
                                "Title": paper['title'],
                                "Abstract": paper['abstract']
                            })
                    except json.JSONDecodeError:
                        st.warning(f"Skipping invalid JSON line: {line[:50]}...")
    
        elif upload_format == "CSV":
            # Parse CSV
            import io
            csv_reader = csv.DictReader(io.StringIO(content))
            for row in csv_reader:
                if 'title' in row and 'abstract' in row:
                    papers.append({
                        "Title": row['title'],
                        "Abstract": row['abstract']
                    })
                elif 'Title' in row and 'Abstract' in row:
                    papers.append({
                        "Title": row['Title'],
                        "Abstract": row['Abstract']
                    })
    
        else:  # TXT format
            # Each line is expected to be a JSON string
            for line in content.strip().split('\n'):
                if line.strip():
                    try:
                        paper = json.loads(line)
                        if 'Title' in paper and 'Abstract' in paper:
                            papers.append(paper)
                        elif 'title' in paper and 'abstract' in paper:
                            papers.append({
                                "Title": paper['title'],
                                "Abstract": paper['abstract']
                            })
                    except json.JSONDecodeError:
                        st.warning(f"Skipping invalid line: {line[:50]}...")
    
    # Write to internal.txt in the required format
    with open(internal_file, 'w', encoding='utf-8') as f:
        for paper in papers:
            formatted_dict = json.dumps(paper, ensure_ascii=False)
            f.write(f'{formatted_dict}\n')
    
    st.info(f"📊 Processed {len(papers)} papers and saved to {internal_file}")
    return len(papers)


def page_execution_history():
    """실행 이력 페이지: 사용자의 작업 이력을 표시"""
    st.header("📜 실행 이력")

    employee_id = st.session_state.get('employee_id')
    if not employee_id:
        st.warning("로그인이 필요합니다.")
        return

    history = _user_manager.get_execution_history(employee_id)

    if not history:
        st.info("아직 실행 이력이 없습니다.")
        return

    st.info(f"총 {len(history)}건의 실행 이력")

    # Show in reverse chronological order
    for i, record in enumerate(reversed(history)):
        timestamp = record.get('timestamp', 'N/A')
        action = record.get('action', 'Unknown')
        topic = record.get('topic', '-')
        dataset = record.get('dataset', '-')
        success = record.get('success', None)
        dims = record.get('dimensions', [])

        status_icon = "✅" if success else ("❌" if success is False else "ℹ️")

        with st.expander(f"{status_icon} [{timestamp[:19]}] {action}", expanded=(i == 0)):
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**Topic:** {topic}")
                st.write(f"**Dataset:** {dataset}")
            with col2:
                st.write(f"**Dimensions:** {', '.join(dims) if dims else '-'}")
                st.write(f"**Max Depth:** {record.get('max_depth', '-')}")

    # Show user's data directories
    st.markdown("---")
    st.subheader("📁 내 데이터 폴더")
    user_dir = _user_manager.get_user_dir(employee_id)

    for folder_name in ['datasets', 'configs', 'save_output']:
        folder_path = user_dir / folder_name
        if folder_path.exists():
            files = list(folder_path.rglob('*'))
            file_count = len([f for f in files if f.is_file()])
            st.write(f"📂 **{folder_name}/**: {file_count}개 파일")
        else:
            st.write(f"📂 **{folder_name}/**: (비어있음)")


if __name__ == "__main__":
    main()
