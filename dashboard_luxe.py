from pathlib import Path
import pandas as pd
import numpy as np
import os
from html import escape
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent
st.set_page_config(page_title='RetailIQ AI | Intelligence workspace', page_icon='📊', layout='wide', initial_sidebar_state='expanded')

# Account access and public portfolio preview.
import hashlib
import hmac
import secrets
import re
import time
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

AUTH_ITERATIONS = 600_000


def database_url():
    load_dotenv(ROOT / '.env')
    for key in ('AUTH_DATABASE_URL', 'DATABASE_URL'):
        value = os.environ.get(key)
        if value:
            return value
        try:
            value = st.secrets.get(key)
            if value:
                return value
        except Exception:
            pass
    return None


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), AUTH_ITERATIONS)
    return f'pbkdf2_sha256${AUTH_ITERATIONS}${salt}${digest.hex()}'


def verify_password(password, stored):
    try:
        method, rounds, salt, expected = stored.split('$')
        rounds = int(rounds)
        if method != 'pbkdf2_sha256' or not (100_000 <= rounds <= 1_000_000):
            return False
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), rounds)
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError, AttributeError):
        return False


def valid_email(email):
    return len(email) <= 254 and bool(re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email))


@st.cache_resource(show_spinner=False)
def account_engine(url):
    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.begin() as conn:
            conn.execute(text('''CREATE TABLE IF NOT EXISTS public.retailiq_accounts (
                email VARCHAR(254) PRIMARY KEY,
                display_name VARCHAR(100) NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )'''))
        return engine
    except Exception:
        engine.dispose()
        raise


def register_account(name, email, password):
    engine = account_engine(database_url())
    with engine.begin() as conn:
        conn.execute(text('''INSERT INTO public.retailiq_accounts
            (email, display_name, password_hash) VALUES (:email, :name, :password_hash)'''),
            {'email': email, 'name': name, 'password_hash': hash_password(password)})
    return {'name': name, 'email': email, 'guest': False}


def authenticate_account(email, password):
    engine = account_engine(database_url())
    with engine.connect() as conn:
        record = conn.execute(text('''SELECT email, display_name, password_hash
            FROM public.retailiq_accounts WHERE email = :email'''), {'email': email}).mappings().first()
    # Perform comparable hashing work even if the account is absent.
    if record is None:
        hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), b'\x00' * 16, AUTH_ITERATIONS)
        return None
    if not verify_password(password, record['password_hash']):
        return None
    return {'name': record['display_name'], 'email': record['email'], 'guest': False}


def enter_workspace(user):
    st.session_state['retailiq_user'] = user
    st.session_state['active_page'] = 'Overview'
    st.session_state.pop('auth_attempts', None)
    st.session_state.pop('auth_blocked_until', None)
    st.rerun()


def sign_out():
    # Clear navigation, uploads, filters and authentication for this session.
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    st.rerun()


def record_failed_login():
    attempts = st.session_state.get('auth_attempts', 0) + 1
    st.session_state['auth_attempts'] = attempts
    if attempts >= 5:
        st.session_state['auth_blocked_until'] = time.monotonic() + 30
        st.session_state['auth_attempts'] = 0


def access_screen():
    st.markdown('''<style>
    :root {--access-accent:#087b68;--access-ink:#182a39;}
    html,body,.stApp {font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
    .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background-color:#091c29;
        background-image:radial-gradient(ellipse at 5% 95%,#124a476e 0%,transparent 54%),radial-gradient(ellipse at 75% 0%,#1a4b5559 0%,transparent 47%),linear-gradient(120deg,#0a1b2a,#112b38 58%,#0c252e);
        color:#e6f2f5;
    }
    [data-testid="stMain"]:before {content:'';position:fixed;inset:0;pointer-events:none;opacity:.18;background-image:linear-gradient(#93d8ca17 1px,transparent 1px),linear-gradient(90deg,#93d8ca17 1px,transparent 1px);background-size:64px 64px;mask-image:linear-gradient(90deg,#000,transparent 85%);}
    [data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stSidebarCollapseButton"] {display:none!important;}
    [data-testid="stHeader"] {background:transparent;}
    [data-testid="stHeader"] button {color:#c2d7dc;}
    .block-container {position:relative;max-width:1320px;padding:clamp(2rem,5vh,4rem) clamp(1.25rem,5vw,4.5rem) 2rem;min-height:100vh;}
    .access-brand {display:flex;align-items:center;gap:12px;padding-bottom:clamp(14px,3vh,32px);color:#f0faf8;}
    .access-logo {width:44px;height:44px;display:grid;place-items:center;background:#b9f2dc;color:#0c4238;border-radius:12px;box-shadow:0 7px 22px #0003;flex-shrink:0;}
    .access-brand b {font-size:25px;letter-spacing:-1.5px;line-height:1;display:block;}
    .access-brand small {font-size:9px;color:#9eb9c3;letter-spacing:1.5px;display:block;margin-top:5px;}
    .access-brand-tag {margin-left:auto;color:#c4ddd9;font-size:11px;font-weight:550;border:1px solid #8bd6c52d;border-radius:999px;padding:8px 13px;display:flex;align-items:center;gap:7px;white-space:nowrap;}
    .access-brand-tag:before {content:'';width:7px;height:7px;border-radius:50%;background:#80e0bf;box-shadow:0 0 12px #80e0bf70;}
    .access-hero {position:relative;isolation:isolate;overflow:hidden;padding:clamp(18px,3.5vw,40px) clamp(6px,2vw,24px) 20px 2px;min-height:560px;}
    .access-hero:before {content:'';position:absolute;z-index:-1;right:-220px;top:22%;width:440px;height:440px;border:1px solid #8de4cb1c;border-radius:50%;box-shadow:0 0 0 44px #8de4cb09,0 0 0 88px #8de4cb07;pointer-events:none;}
    .access-kicker {display:inline-flex;gap:8px;align-items:center;font-size:10px;letter-spacing:1.35px;color:#91e5cd;text-transform:uppercase;font-weight:750;border:1px solid #83ddc53b;border-radius:6px;padding:7px 10px;background:#8ae5c60b;}
    .access-kicker:before {content:'';width:6px;height:6px;border-radius:50%;background:#a5ecd6;}
    .access-hero h1 {font-size:clamp(38px,4.3vw,64px)!important;letter-spacing:-.045em;line-height:1.07;font-weight:750;color:#f3f9fc!important;margin:23px 0 16px;padding:0;}
    .access-hero h1 em {font-style:normal;color:#9debcf;}
    .access-hero p {font-size:15px;line-height:1.7;color:#b6cbd4!important;margin:0 0 27px;max-width:455px;}
    .access-chart {padding:19px 19px 11px;border-radius:14px;border:1px solid #b7e0e129;background:linear-gradient(150deg,#ffffff0d,#ffffff04);box-shadow:0 14px 40px #0002;margin-top:12px;max-width:510px;}
    .access-chart-head {display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:4px;}
    .access-chart span {color:#a9c8d0;font-size:11px;display:block;}
    .access-chart strong {display:block;color:#f3fffc;font-size:32px;letter-spacing:-1.15px;line-height:1.2;}
    .access-chart small {color:#a4decf;font-size:10px;border:1px solid #81cdb93b;border-radius:5px;padding:5px 7px;white-space:nowrap;}
    .access-metrics {display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:12px;max-width:510px;}
    .access-metrics div {border:1px solid #b7e0e125;border-radius:11px;padding:15px 17px;background:#ffffff06;}
    .access-metrics b {display:block;color:#effff9;font-size:24px;letter-spacing:-.8px;line-height:1.2;margin-bottom:4px;}
    .access-metrics small {color:#a9c8d0;font-size:11px;}
    .access-foot {color:#a7bec9;font-size:11px;margin-top:22px;line-height:1.6;}
    .access-title {margin:3px 0 14px;}
    .access-title .overline {font-size:10px;font-weight:750;letter-spacing:1.3px;color:#087b68;display:block;margin:0 0 10px;}
    .access-title h2 {font-size:clamp(25px,2.5vw,35px)!important;letter-spacing:-1.25px;padding:0;margin:0 0 8px;color:#162b39!important;line-height:1.15;}
    .access-title p {font-size:13px;color:#5b6d7c!important;margin:0;line-height:1.6;}
    .st-key-access_card,[data-testid="stVerticalBlockBorderWrapper"]:has(.access-title) {background:#fcfefd!important;border:1px solid #ffffffb0!important;border-radius:22px!important;box-shadow:0 25px 75px #0004,0 0 0 1px #bddfd50d;}
    .st-key-access_card {padding:clamp(18px,2.5vw,34px)!important;color:var(--access-ink);}
    .st-key-access_card [data-testid="stVerticalBlock"] {gap:.82rem;}
    .st-key-access_card p,.st-key-access_card label,.st-key-access_card label p {color:var(--access-ink)!important;}
    .st-key-access_card [data-testid="stCaptionContainer"] p {color:#637582!important;font-size:11px;line-height:1.5;}
    .st-key-access_card [data-testid="stRadio"] [role="radiogroup"] {background:#edf3f1;border:1px solid #e0e9e5;padding:6px 11px;border-radius:10px;gap:14px;flex-wrap:wrap;}
    .st-key-access_card [data-testid="stForm"] {border:0;padding:0;}
    .st-key-access_card [data-testid="stTextInput"] label p {font-size:12px;font-weight:650;}
    .st-key-access_card [data-baseweb="input"],.st-key-access_card [data-baseweb="base-input"] {background:#fff!important;border-color:#d5e1de;color:#182a39!important;border-radius:9px;}
    .st-key-access_card [data-testid="stTextInput"] input {font-size:14px;color:#182a39!important;min-height:42px;}
    .st-key-access_card input::placeholder {color:#84949a!important;}
    .st-key-access_card [data-testid="stTextInput"] svg {color:#526971!important;}
    .st-key-access_card [data-testid="stFormSubmitButton"] button {background:#087b68;border-color:#087b68;min-height:47px;border-radius:9px;font-weight:650;box-shadow:0 5px 14px #087b6820;transition:background .15s;}
    .st-key-access_card [data-testid="stFormSubmitButton"] button p {color:white!important;font-weight:650;}
    .st-key-access_card [data-testid="stFormSubmitButton"] button:not(:disabled):hover {background:#096452;border-color:#096452;}
    .st-key-access_card [data-testid="stFormSubmitButton"] button:disabled {background:#d9e4e0;border-color:#d9e4e0;box-shadow:none;}
    .st-key-access_card [data-testid="stFormSubmitButton"] button:disabled p {color:#526971!important;}
    .st-key-access_card [data-testid="stButton"] button {min-height:45px;border-radius:9px;background:#f0f6f3;border:1px solid #d7e6df;color:#183e36;font-weight:650;}
    .st-key-access_card [data-testid="stButton"] button:hover {border-color:#087b68;background:#e5f3eb;}
    .st-key-access_card button:focus-visible {outline:2px solid #087b68;outline-offset:3px;}
    .st-key-access_card hr {border-color:#e1e9e5;}
    .access-demo-label {font-weight:700;font-size:12px;color:#18362f;margin-bottom:0;}
    .access-bottom {display:flex;gap:16px;justify-content:space-between;flex-wrap:wrap;color:#a5bdc7;font-size:11px;margin-top:26px;border-top:1px solid #a6cfd325;padding-top:15px;}
    @media(max-width:900px){.access-hero{min-height:0;padding-top:16px;}.access-hero h1{font-size:clamp(34px,5vw,48px)!important;}.access-chart{margin-top:8px;}.block-container{padding-top:2rem;}.st-key-access_card{padding:20px!important;}}
    @media(max-width:760px){.access-brand-tag{display:none;}.access-hero{padding-right:0;}.access-hero h1{font-size:36px!important;}.access-hero p{font-size:14px;margin-bottom:14px;}.access-chart,.access-metrics{max-width:none;}.access-bottom{margin-top:15px;}}
    @media(prefers-reduced-motion:reduce){.st-key-access_card button{transition:none!important;}}
    </style>''', unsafe_allow_html=True)
    st.markdown('<div class="access-brand"><div class="access-logo"><svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true"><path d="M6 23V9h9a6 6 0 0 1 0 12h-3m3-5 8 8M23 9h3v3" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></div><div><b>retailiq.</b><small>INTELLIGENCE PLATFORM</small></div><span class="access-brand-tag">Portfolio workspace</span></div>', unsafe_allow_html=True)
    left, right = st.columns([1.15, 1], gap='large')
    with left:
        st.markdown('''<div class="access-hero">
        <div class="access-kicker">Retail intelligence, reimagined</div>
        <h1>Better data.<br>Smarter <em>retail</em><br><em>decisions.</em></h1>
        <p>Turn sales, customer behavior and predictive analytics into actionable business insights. All in one intelligence workspace.</p>
        <div class="access-chart"><div class="access-chart-head"><div><span>Historical net revenue</span><strong>£19.01M</strong></div><small>2009–2011</small></div>
        <svg viewBox="0 0 380 74" width="100%" height="74" role="img" aria-label="Illustrative trend, not actual time series"><defs><linearGradient id="authFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#8de5c6" stop-opacity=".27"/><stop offset="100%" stop-color="#8de5c6" stop-opacity="0"/></linearGradient></defs><path d="M0 18H380M0 38H380M0 58H380" stroke="#c1e8e7" stroke-opacity=".13" stroke-dasharray="3 6"/><path d="M0 48L26 53L52 39L78 45L105 35L131 41L157 26L184 35L211 19L237 26L264 8L290 17L316 11L342 20L380 4V74H0Z" fill="url(#authFill)"/><path d="M0 48L26 53L52 39L78 45L105 35L131 41L157 26L184 35L211 19L237 26L264 8L290 17L316 11L342 20L380 4" fill="none" stroke="#99e9ce" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/></svg></div>
        <div class="access-metrics"><div><b>1.03M+</b><small>Historical transaction lines</small></div><div><b>15</b><small>Analytics modules</small></div></div>
        <div class="access-foot">Historical portfolio dataset. Trend graphic is illustrative.</div></div>''', unsafe_allow_html=True)
    with right:
        with st.container(border=True, key='access_card'):
            st.markdown('<div class="access-title"><span class="overline">YOUR INTELLIGENCE WORKSPACE</span><h2>Welcome to RetailIQ.</h2><p>Sign in or create an account to access the workspace.</p></div>', unsafe_allow_html=True)
            mode = st.radio('Account access', ['Sign in', 'Create account'], horizontal=True, label_visibility='collapsed', key='auth_mode')
            configured = bool(database_url())
            if not configured:
                st.info('Account database is not configured. You can still explore the demo.')
            if mode == 'Sign in':
                with st.form('login_form', clear_on_submit=True):
                    email = st.text_input('Email address', placeholder='you@example.com', max_chars=254).strip().lower()
                    password = st.text_input('Password', type='password', max_chars=256)
                    submitted = st.form_submit_button('Sign in to workspace', type='primary', use_container_width=True, disabled=not configured)
                if submitted:
                    if time.monotonic() < st.session_state.get('auth_blocked_until', 0):
                        st.warning('Too many attempts. Please wait 30 seconds and try again.')
                    elif not valid_email(email) or not password:
                        st.error('Enter a valid email address and password.')
                    else:
                        try:
                            user = authenticate_account(email, password)
                        except Exception:
                            st.error('Account service unavailable. Check your PostgreSQL configuration or use the demo.')
                        else:
                            if user:
                                enter_workspace(user)
                            else:
                                record_failed_login()
                                st.error('Email or password is incorrect.')
            else:
                with st.form('registration_form', clear_on_submit=True):
                    name = st.text_input('Full name', placeholder='Your name', max_chars=100).strip()
                    email = st.text_input('Email address', placeholder='you@example.com', max_chars=254).strip().lower()
                    password = st.text_input('Create password', type='password', help='Use at least 10 characters.', max_chars=256)
                    confirm = st.text_input('Confirm password', type='password', max_chars=256)
                    submitted = st.form_submit_button('Create my account', type='primary', use_container_width=True, disabled=not configured)
                if submitted:
                    if time.monotonic() < st.session_state.get('auth_blocked_until', 0):
                        st.warning('Too many attempts. Please wait 30 seconds and try again.')
                    elif not name or not valid_email(email):
                        st.error('Enter your name and a valid email address.')
                    elif len(password) < 10:
                        st.error('Choose a password with at least 10 characters.')
                    elif password != confirm:
                        st.error('Passwords do not match.')
                    else:
                        try:
                            user = register_account(name, email, password)
                        except IntegrityError:
                            record_failed_login()
                            st.error('Unable to create account. Try signing in or using another email.')
                        except Exception:
                            st.error('Account service unavailable. Check your PostgreSQL configuration or use the demo.')
                        else:
                            enter_workspace(user)
            st.divider()
            st.markdown('<div class="access-demo-label">Just exploring?</div>', unsafe_allow_html=True)
            if st.button('Explore recruiter demo  →', use_container_width=True, key='guest_access'):
                enter_workspace({'name': 'Demo visitor', 'email': '', 'guest': True})
            st.caption('No account required for the public historical-data demo. Accounts do not create private workspaces.')
    st.markdown('<div class="access-bottom"><span>RetailIQ AI · Retail Intelligence Platform</span><span>Portfolio project · Passwords stored as salted hashes</span></div>', unsafe_allow_html=True)


if 'retailiq_user' not in st.session_state:
    access_screen()
    st.stop()

current_user = st.session_state['retailiq_user']


PAGES = {
    'WORKSPACE': ['Overview', 'Sales analytics', 'Products', 'Customers'],
    'PREDICTIVE INTELLIGENCE': ['Segmentation', 'Churn risk', 'Forecast', 'Market basket', 'Customer value', 'Anomaly detection', 'Explainable AI'],
    'PLANNING & OPERATIONS': ['Business insights', 'What-if simulator', 'Data workspace'],
    'RESOURCES': ['About RetailIQ']
}
ICONS = {'Overview':'◈', 'Sales analytics':'↗', 'Products':'▦', 'Customers':'◎',
         'Segmentation':'◉', 'Churn risk':'⚑', 'Forecast':'⌁', 'Market basket':'⊞',
         'Customer value':'◇', 'Anomaly detection':'ϟ', 'Explainable AI':'✳',
         'Business insights':'✦', 'What-if simulator':'≋', 'Data workspace':'▤', 'About RetailIQ':'ⓘ'}
if 'active_page' not in st.session_state:
    st.session_state.active_page = 'Overview'

def navigate(name):
    st.session_state.active_page = name


def jump_to_module():
    target = st.session_state.get('module_jump')
    if target in [name for names in PAGES.values() for name in names]:
        navigate(target)
    st.session_state['module_jump'] = 'Find a module…'

with st.sidebar:
    st.markdown('<div class="brand"><span class="brand-mark"><svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true"><path d="M6 23V9h9a6 6 0 0 1 0 12h-3m3-5 8 8M23 9h3v3" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg></span><div><b>retail<span>iq.</span></b><small>INTELLIGENCE PLATFORM</small></div></div><div class="workspace-label"><span class="workspace-icon">R</span><div><strong>Retail workspace</strong><small>Analytics & planning</small></div></div>', unsafe_allow_html=True)
    for section, names in PAGES.items():
        st.markdown(f'<div class="nav-section">{section}</div>', unsafe_allow_html=True)
        for name in names:
            st.button(f'{ICONS[name]}   {name}', key='nav_'+name,
                      type='primary' if st.session_state.active_page == name else 'secondary',
                      use_container_width=True, on_click=navigate, args=(name,))
    with st.expander('Workspace settings'):
        dark = st.toggle('Dark appearance', value=False)
        if current_user['guest']:
            backend = 'Local Parquet'
            st.caption('Public historical snapshot')
        else:
            backend = st.radio('Data source', ['Local Parquet', 'PostgreSQL'])
        if st.button('Refresh data', use_container_width=True):
            st.cache_data.clear()
    name = escape(current_user['name'])
    account_label = 'Recruiter demo' if current_user['guest'] else 'Signed-in account'
    initial = escape(current_user['name'][:1].upper())
    st.markdown(f'<div class="workspace-label" style="margin-top:13px"><span class="workspace-icon">{initial}</span><div><strong style="overflow-wrap:anywhere">{name}</strong><small>{account_label}</small></div></div>', unsafe_allow_html=True)
    if st.button('↪  Sign out', key='sign_out', use_container_width=True):
        sign_out()
page = st.session_state.active_page

bg, panel, ink, muted, border = ('#101827','#182333','#f1f5f9','#a9bad0','#304055') if dark else ('#f4f6fa','#ffffff','#14243b','#5d6c82','#e1e7ef')
accent = '#54d8bf' if dark else '#087f73'
side = '#111e30'
st.markdown(f'<style>:root{{--bg:{bg};--panel:{panel};--ink:{ink};--muted:{muted};--border:{border};--accent:{accent};}}</style>', unsafe_allow_html=True)
st.markdown('''<style>
html, body, .stApp {font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;}
.stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {background:var(--bg);color:var(--ink);}
[data-testid="stHeader"] {background:transparent;}
[data-testid="stToolbar"] {right:1rem;}
.block-container {max-width:1680px;padding:3.3rem clamp(1rem,2.5vw,2.6rem) 2rem;}
[data-testid="stMain"] [data-testid="stVerticalBlock"] {gap:.86rem;}
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3, [data-testid="stMain"] p, [data-testid="stMain"] label {color:var(--ink);}
[data-testid="stMain"] [data-testid="stCaptionContainer"] p {color:var(--muted);font-size:.78rem;}
[data-testid="stSidebar"] {background:#111e30;border-right:1px solid #26374e;}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding-top:.55rem;}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap:2px;}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3 {color:#d5e3e0!important;}
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] p {color:#a1b8b5!important;font-size:11px;}
[data-testid="stSidebar"] [data-testid="stButton"] button {width:100%;min-height:32px;padding:4px 11px;border:1px solid transparent;border-radius:7px;background:transparent;justify-content:flex-start;text-align:left;box-shadow:none;}
[data-testid="stSidebar"] [data-testid="stButton"] button p {font-size:13px;line-height:1.3;font-weight:500;}
[data-testid="stSidebar"] [data-testid="stButton"] button:hover {background:#24374b;border-color:#34475c;}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {background:#1c4a4c;border:1px solid #2c6663;border-left:3px solid #65deb9;}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] p {color:#edfffa!important;font-weight:650;}
[data-testid="stSidebar"] [data-testid="stExpander"] {border:1px solid #355450;border-radius:8px;}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {color:#d5e3e0!important;}
[data-testid="stSidebar"] svg {color:#b7cfca;}
.brand {display:flex;gap:11px;align-items:center;padding:3px 1px 16px;}
.brand-mark {width:43px;height:43px;display:grid;place-items:center;border-radius:12px;background:#b9f2db;color:#124337;font-weight:800;font-size:25px;letter-spacing:-2px;}
.brand-mark span {display:none;}
.brand b {display:block;font-size:22px;letter-spacing:-1px;color:#f3fcf9;line-height:1.2;}
.brand b span {color:#9ce4ca;} .brand small {display:block;font-size:9px;letter-spacing:1.5px;color:#a5c0b9;margin-top:3px;}
.workspace-label {display:flex;gap:9px;align-items:center;border:1px solid #304158;background:#1a2b40;border-radius:9px;padding:9px;margin-bottom:9px;}
.workspace-icon {display:grid;place-items:center;width:31px;height:31px;border-radius:7px;background:#294b56;color:#c7f4e4;font-size:12px;font-weight:700;}
.workspace-label strong {display:block;font-size:12px;color:#e5f3ef;}.workspace-label small {display:block;font-size:10px;color:#a9c4bd;}
.nav-section {font-size:9px;letter-spacing:1.25px;font-weight:700;color:#8fa5be;margin:11px 0 3px 10px;}
.app-route {display:flex;align-items:center;gap:9px;min-height:39px;color:var(--muted);font-size:12px;flex-wrap:wrap;}
.app-route strong {color:var(--ink);font-weight:650;}.route-icon {display:grid;place-items:center;width:27px;height:27px;border:1px solid var(--border);border-radius:7px;background:var(--panel);color:var(--accent);}
.environment {display:flex;align-items:center;justify-content:flex-end;gap:7px;color:var(--muted);font-size:11px;min-height:39px;white-space:nowrap;}
.environment i {width:7px;height:7px;border-radius:50%;background:#28ac85;display:inline-block;}
.page-heading {padding:9px 0 3px;}.page-heading small {font-size:10px;font-weight:750;text-transform:uppercase;letter-spacing:1.5px;color:var(--accent);}
.page-heading h1 {font-size:clamp(26px,3vw,38px)!important;font-weight:730;letter-spacing:-1.4px;line-height:1.18;margin:6px 0;padding:0;}
.page-heading p {font-size:14px;color:var(--muted)!important;margin:0;}
.page-meta {display:flex;gap:7px;flex-wrap:wrap;}.page-meta span {font-size:11px;color:var(--muted);padding:5px 9px;border:1px solid var(--border);border-radius:6px;background:var(--panel);}
.product-hero {position:relative;isolation:isolate;overflow:hidden;display:flex;justify-content:space-between;align-items:center;gap:20px;background:linear-gradient(115deg,#102e32,#174a46);border:1px solid #39615c;padding:23px 26px;border-radius:15px;min-height:155px;}
.product-hero:after {content:'';position:absolute;z-index:-1;right:-45px;top:-165px;width:330px;height:330px;border:1px solid #a2e5cc30;border-radius:50%;box-shadow:0 0 0 35px #b8e7d30c,0 0 0 75px #b8e7d309;}
.product-hero small {font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#9de5ce;font-weight:700;}
.product-hero h1 {color:#f5fff9!important;font-size:clamp(25px,3vw,37px)!important;font-weight:700;letter-spacing:-1.4px;margin:8px 0;line-height:1.15;padding:0;}
.product-hero p {color:#c1ddd5!important;font-size:13px;margin:0;max-width:460px;line-height:1.5;}
.hero-asof {min-width:154px;border:1px solid #c7ecdd38;border-radius:11px;padding:13px 15px;background:#e2f7ed0d;}
.hero-asof span {display:block;color:#b3d7cb;font-size:10px;text-transform:uppercase;letter-spacing:1px;}.hero-asof strong {display:block;color:#f5fff9;font-size:22px;letter-spacing:-.6px;margin-top:4px;}.hero-asof em {display:block;font-size:11px;color:#b3d7cb;font-style:normal;margin-top:5px;}
.section-head {display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin:7px 0 1px;}.section-head strong {color:var(--ink);font-size:17px;font-weight:700;letter-spacing:-.35px;}.section-head small {color:var(--muted);font-size:11px;}
.kpi {background:var(--panel);border:1px solid var(--border);border-radius:12px;min-height:139px;padding:14px 16px;box-shadow:0 2px 5px #102b2e08;transition:transform .15s,border-color .15s;}
.kpi:hover {border-color:var(--accent);transform:translateY(-2px);}.kpi-top {display:flex;align-items:center;justify-content:space-between;gap:4px;color:var(--muted);font-size:12px;font-weight:600;}.kpi-icon {display:grid;place-items:center;width:28px;height:28px;flex-shrink:0;border-radius:8px;font-size:15px;}
.kpi-value {color:var(--ink);font-size:clamp(20px,2.35vw,32px);line-height:1.15;font-weight:750;letter-spacing:-1px;margin:8px 0 4px;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;}.kpi-foot {color:var(--muted);font-size:11px;line-height:1.35;}.sparkline {width:100%;height:27px;display:block;margin:7px 0 -4px;}
.brief {background:var(--panel);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:10px;padding:15px 16px;min-height:115px;}.brief small {font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.8px;color:var(--accent);}.brief b {display:block;color:var(--ink);font-size:16px;margin:5px 0;}.brief div {color:var(--muted);font-size:12px;line-height:1.55;}
[data-testid="stMetric"] {background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:15px 17px;min-height:103px;}
[data-testid="stMetricValue"] {color:var(--ink);font-size:clamp(19px,2vw,28px);letter-spacing:-.75px;}
[data-testid="stMetricLabel"] p {color:var(--muted)!important;font-size:12px;}
[data-testid="stPlotlyChart"] {background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:3px 5px;box-shadow:0 2px 5px #102b2e06;}
[data-testid="stDataFrame"] {border:1px solid var(--border);border-radius:10px;overflow:hidden;}
[data-testid="stMain"] [data-testid="stExpander"] {background:var(--panel);border:1px solid var(--border);border-radius:9px;}
[data-testid="stMain"] [data-testid="stExpander"] summary {color:var(--ink);}
[data-testid="stMain"] [data-baseweb="select"] > div,[data-testid="stMain"] [data-baseweb="input"], [data-testid="stMain"] [data-baseweb="base-input"] {background:var(--panel);color:var(--ink);border-color:var(--border);}
[data-testid="stMain"] input {color:var(--ink);}
[data-testid="stMain"] [data-testid="stButton"] button,[data-testid="stMain"] [data-testid="stDownloadButton"] button {min-height:38px;background:var(--panel);color:var(--ink);border:1px solid var(--border);border-radius:8px;}
[data-testid="stMain"] [data-testid="stButton"] button:hover,[data-testid="stMain"] [data-testid="stDownloadButton"] button:hover {border-color:var(--accent);color:var(--accent);}
[data-testid="stMain"] [data-testid="stButton"] button[kind="primary"] {background:#087c69;border-color:#087c69;color:white;}
[data-testid="stMain"] [data-testid="stButton"] button[kind="primary"] p {color:white!important;}
button:focus-visible {outline:2px solid var(--accent)!important;outline-offset:2px;}
.footer-brand {display:flex;gap:10px;justify-content:space-between;flex-wrap:wrap;color:var(--muted);font-size:11px;padding:5px 0;}
@media(max-width:950px) {.block-container {padding-left:1.2rem;padding-right:1.2rem;}.environment {justify-content:flex-start;}.hero-asof {display:none;}}
@media(max-width:650px) {.block-container{padding:3rem 1rem 1rem;}.section-head small {display:none;}.product-hero{padding:20px;}.kpi{min-height:110px;}}
@media(prefers-reduced-motion:reduce) {.kpi {transition:none;}.kpi:hover {transform:none;}}

/* Product design system: restrained color, clear hierarchy, compact dashboard. */
[data-testid="stMain"] [data-testid="stVerticalBlock"] {gap:.72rem;}
[data-testid="stSidebar"] [data-testid="stSidebarContent"] {padding-top:.25rem;}
.brand {padding-bottom:14px;}.brand-mark {background:#a9efd9;color:#133d3b;box-shadow:0 4px 14px #0002;}
.product-mast {display:flex;align-items:center;justify-content:space-between;gap:18px;padding:22px 26px;border-radius:15px;background:linear-gradient(112deg,#14263e 0%,#173b4a 100%);border:1px solid #36545e;color:#f5fbff;position:relative;overflow:hidden;isolation:isolate;}
.product-mast:before {position:absolute;content:'';width:300px;height:300px;right:-120px;top:-180px;border:1px solid #77e4c650;border-radius:50%;box-shadow:0 0 0 24px #77e4c610,0 0 0 50px #77e4c60a;z-index:-1;}
.mast-kicker {font-size:10px;letter-spacing:1.9px;color:#8ee7d4;font-weight:750;display:flex;align-items:center;gap:7px;}.mast-kicker:before {content:'';width:6px;height:6px;background:#8ee7d4;border-radius:50%;}
.product-mast h1 {color:#f5fbff!important;font-size:clamp(24px,2.8vw,36px)!important;letter-spacing:-1.3px;font-weight:720;line-height:1.2;margin:6px 0 4px;padding:0;}
.product-mast p {color:#bdcfdb!important;font-size:13px;margin:0;line-height:1.5;}
.mast-date {border:1px solid #8cc7cd36;border-radius:10px;padding:11px 15px;min-width:162px;background:#ffffff08;}.mast-date small {display:block;color:#a7c2d1;font-size:10px;letter-spacing:.6px;}.mast-date b {display:block;color:#f0f9ff;font-size:17px;font-weight:650;margin:3px 0;}.mast-date span {color:#9ee7cf;font-size:11px;}
.kpi {padding:13px 15px;min-height:126px;border-radius:11px;box-shadow:0 2px 6px #18273b05;}.kpi-top {font-size:11px;letter-spacing:.1px;}.kpi-value {font-size:clamp(21px,2.35vw,31px);margin:6px 0 3px;}.kpi-foot {font-size:10.5px;}.sparkline {height:25px;}
.section-head {margin:7px 0 1px;}.section-head strong {font-size:17px;}.section-head small {font-size:11px;}
.decision-panel {background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:19px 19px 14px;min-height:366px;box-shadow:0 2px 6px #18273b05;}
.decision-panel header {display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;}.decision-panel header b {font-size:15px;color:var(--ink);}.decision-panel header span {font-size:10px;color:var(--accent);background:#12998113;padding:4px 8px;border-radius:5px;font-weight:650;}
.decision-item {border-top:1px solid var(--border);padding:11px 0 8px;}.decision-item small {display:block;color:var(--muted);font-size:11px;}.decision-item strong {display:block;color:var(--ink);font-size:19px;font-weight:690;letter-spacing:-.5px;margin:3px 0;}.decision-item em {display:block;color:var(--muted);font-size:11px;line-height:1.4;font-style:normal;}.decision-track {height:4px;background:var(--border);border-radius:3px;margin:7px 0 3px;overflow:hidden;}.decision-track i {display:block;height:100%;background:var(--accent);border-radius:3px;}
.operating-strip {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--border);background:var(--panel);border-radius:12px;overflow:hidden;}.operating-strip div {padding:15px;border-right:1px solid var(--border);}.operating-strip div:last-child {border-right:0;}.operating-strip small {display:block;color:var(--muted);font-size:11px;}.operating-strip b {display:block;font-size:21px;letter-spacing:-.65px;color:var(--ink);margin-top:4px;}.operating-strip em {font-size:10px;color:var(--muted);font-style:normal;}
.module-card {padding:13px 15px;background:var(--panel);border:1px solid var(--border);border-radius:10px;min-height:91px;}.module-card small {display:block;font-size:10px;letter-spacing:1px;font-weight:700;color:var(--accent);}.module-card b {display:block;color:var(--ink);font-size:14px;margin:4px 0;}.module-card span {font-size:11px;color:var(--muted);line-height:1.4;}
[data-testid="stMain"] [data-testid="stTabs"] button {font-size:13px;font-weight:600;}
[data-testid="stMain"] [data-testid="stPlotlyChart"] {box-shadow:0 2px 6px #18273b05;}
[data-testid="stMain"] [data-testid="stButton"] button[kind="primary"] {background:#087f73;border-color:#087f73;}
@media(max-width:950px){.product-mast {padding:19px 20px;}.mast-date{display:none;}.decision-panel{min-height:0;}.operating-strip{grid-template-columns:repeat(2,minmax(0,1fr));}.operating-strip div:nth-child(2){border-right:none;}.operating-strip div:nth-child(-n+2){border-bottom:1px solid var(--border);}}
@media(max-width:650px){.product-mast h1{font-size:25px!important;}.operating-strip b{font-size:18px;}.section-head small{display:none;}}

/* Shared premium design language after sign-in. */
.stApp,[data-testid="stAppViewContainer"],[data-testid="stMain"] {background:radial-gradient(ellipse at 100% 0%,#0d8b7910,transparent 38%),var(--bg);}
[data-testid="stSidebar"] {background:radial-gradient(ellipse at 0% 100%,#174d4b80,transparent 52%),linear-gradient(165deg,#0b1b2a,#142c39);}
[data-testid="stSidebar"] [data-testid="stButton"] button[kind="primary"] {background:linear-gradient(90deg,#205553,#1b4248);border-color:#34726d;border-left:3px solid #9debcf;}
.product-mast,.product-hero {background:radial-gradient(ellipse at 100% 100%,#28735d75,transparent 62%),linear-gradient(120deg,#102538,#153e45);}
.product-mast {box-shadow:0 6px 20px #10253814;}
.kpi,[data-testid="stMetric"],[data-testid="stPlotlyChart"],.decision-panel,.module-card {box-shadow:0 4px 17px #0b273509;}
</style>''', unsafe_allow_html=True)

@st.cache_data
def load_data(path, modified):
    df = pd.read_parquet(path)
    df['invoice_date'] = pd.to_datetime(df['invoice_date'])
    return df

source = ROOT / 'data/processed/transactions.parquet'
@st.cache_data(ttl=300, show_spinner='Reading PostgreSQL warehouse...')
def load_warehouse():
    load_dotenv(ROOT / '.env')
    url = os.environ.get('DATABASE_URL')
    if not url:
        try:
            url = st.secrets['DATABASE_URL']
        except Exception:
            raise ValueError('Database URL not configured') from None
    engine = create_engine(url, pool_pre_ping=True)
    try:
        data = pd.read_sql("""SELECT f.invoice, f.invoice_date,
            f.product_key AS stock_code, p.description,
            f.customer_key AS customer_id, f.country_key AS country,
            f.quantity, f.unit_price, f.line_amount, f.is_return, f.is_outlier
            FROM retail.fact_sales f JOIN retail.dim_product p
            ON f.product_key = p.product_key""", engine)
        data['invoice_date'] = pd.to_datetime(data.invoice_date)
        return data
    finally:
        engine.dispose()

active = backend
if backend == 'Local Parquet' and not source.exists():
    if current_user['guest']:
        st.error('The public demo snapshot is missing. Add the historical Parquet dataset to enable demo access.')
        st.stop()
    active = 'PostgreSQL'
if active == 'PostgreSQL':
    try:
        df = load_warehouse()
    except Exception:
        st.warning('PostgreSQL unavailable. Using the local snapshot if present.')
        active = 'Local Parquet (fallback)'
if active != 'PostgreSQL':
    if not source.exists():
        st.error('No local dataset available. Check the database or run ETL.')
        st.stop()
    df = load_data(source, source.stat().st_mtime)
if df.empty:
    st.warning('The selected data source contains no transactions.')
    st.stop()
@st.cache_data(show_spinner=False)
def normalize_data(df):
    df = df.copy()
    for col in ['invoice', 'stock_code', 'description', 'country', 'customer_id']:
        df[col] = df[col].astype('string').str.strip().replace('', pd.NA)
    df['customer_id'] = df.customer_id.str.replace(r'\.0$', '', regex=True)
    for col in ['quantity', 'unit_price', 'line_amount']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    if not pd.api.types.is_bool_dtype(df['is_return']):
        df['is_return'] = df['is_return'].astype('string').str.strip().str.lower().isin(['true', '1', '1.0', 'yes', 't'])
    else:
        df['is_return'] = df['is_return'].fillna(False)
    df = df.dropna(subset=['invoice_date','line_amount'])
    return df

df = normalize_data(df)
if df.empty:
    st.error('No valid transaction dates or amounts found.')
    st.stop()
st.sidebar.caption('Active source: ' + active)

with st.sidebar:
    st.caption('PORTFOLIO WORKSPACE  /  HISTORICAL DATA')

category = next(group for group, names in PAGES.items() if page in names)
left, middle, right = st.columns([1.65, 1.25, 1.1])
with left:
    st.markdown(f'<div class="app-route"><span class="route-icon">{escape(ICONS[page])}</span>{escape(category.title())} / <strong>{escape(page)}</strong></div>', unsafe_allow_html=True)
with middle:
    st.selectbox('Find a module', ['Find a module…'] + [name for names in PAGES.values() for name in names], key='module_jump', label_visibility='collapsed', on_change=jump_to_module)
with right:
    st.markdown(f'<div class="environment"><i></i>{escape(active)} · historical</div>', unsafe_allow_html=True)
start, end = df.invoice_date.min().date(), df.invoice_date.max().date()
with st.expander('Filters  ·  market and reporting period', expanded=False):
    a,b = st.columns([1,1])
    with a:
        countries = st.multiselect('Markets', sorted(df.country.dropna().unique()), placeholder='All markets', key='market_filter')
    with b:
        dates = st.date_input('Date range', (start,end), min_value=start,max_value=end,key='date_filter')
    st.caption('Transaction filters apply to descriptive analytics and scenarios, not saved historical model outputs.')

if len(dates) != 2:
    st.info('Select both dates.')
    st.stop()
mask = (df.invoice_date >= pd.Timestamp(dates[0])) & (df.invoice_date < pd.Timestamp(dates[1])+pd.Timedelta(days=1))
if countries:
    mask &= df.country.isin(countries)
data = df.loc[mask]
MODEL_PAGES = {'Segmentation','Churn risk','Forecast','Market basket','Customer value','Explainable AI'}
if data.empty and page not in MODEL_PAGES and page not in {'Data workspace','About RetailIQ'}:
    st.warning('No transactions match these filters. Choose a wider period or different market.')
    st.stop()
sales = data[~data.is_return]
returns = data[data.is_return]
net = data.line_amount.sum()
orders = sales.invoice.nunique()
rate = len(returns)/len(data)*100 if len(data) else 0
money = lambda x: f'£{x:,.2f}'

def chart(fig, height=338):
    fig.update_layout(height=height, hoverlabel=dict(bgcolor=panel,font_color=ink), title_font_size=15, title_x=0.04, template='plotly_dark' if dark else 'plotly_white', paper_bgcolor=panel, plot_bgcolor=panel, font=dict(color=ink, family='Inter, Arial, sans-serif'), margin=dict(l=24,r=24,t=54,b=32), colorway=[accent,'#587aa6','#c58a4c','#9873a5','#748a90'], legend_title_text='')
    fig.update_geos(bgcolor=panel, landcolor=bg, lakecolor=panel, showframe=False, coastlinecolor=border)
    fig.update_xaxes(showgrid=False, zerolinecolor=border, automargin=True, tickfont=dict(size=11))
    fig.update_yaxes(gridcolor=border, zerolinecolor=border, automargin=True, tickfont=dict(size=11))
    st.plotly_chart(fig, use_container_width=True, theme=None, config={'displaylogo':False, 'responsive':True, 'modeBarButtonsToRemove':['lasso2d','select2d']})

def report(name):
    path = ROOT / 'reports' / name
    if not path.exists():
        st.warning(f'Report unavailable: {name}. Run its module first.')
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError):
        st.warning(f'Unable to read report: {name}. Regenerate it using its module.')
        return pd.DataFrame()
    frame.columns = frame.columns.str.strip().str.lower().str.replace(' ', '_')
    aliases = {
        'clustering/cluster_summary.csv': {'customer_count':'customers','count':'customers','total_monetary':'total_revenue','total_spending':'total_revenue','total_spend':'total_revenue'},
        'churn/model_results.csv': {'auc':'roc_auc','roc-auc':'roc_auc','f1':'f1_score','f1-score':'f1_score'},
        'churn/churn_predictions.csv': {'risk':'risk_level','churn_risk':'risk_level'}
    }
    for old,new in aliases.get(name,{}).items():
        if old in frame and new not in frame: frame = frame.rename(columns={old:new})
    required = {
        'clustering/cluster_summary.csv': {'cluster','customers','total_revenue'},
        'churn/model_results.csv': {'model','accuracy','precision','recall','f1_score','roc_auc'},
        'churn/churn_predictions.csv': {'risk_level'},
        'forecast/future_forecast.csv': {'date','predicted_revenue'},
        'basket/association_rules.csv': {'antecedents','consequents','support','confidence','lift'}
    }.get(name,set())
    missing=required-set(frame.columns)
    if missing:
        st.warning(f'Report {name} is missing expected columns: '+', '.join(sorted(missing)))
        st.dataframe(frame.head(20),use_container_width=True)
        return pd.DataFrame()
    if 'risk_level' in frame:
        frame['risk_level']=frame.risk_level.astype('string').str.strip().str.title().str.replace(r'^(Low|Medium|High)$',r'\1 Risk',regex=True)
    return frame

def table(data, name):
    st.caption(f'{len(data):,} rows • CSV export')
    st.dataframe(data, use_container_width=True, hide_index=True)
    st.download_button('↓  Export CSV', data.to_csv(index=False).encode('utf-8-sig'), name+'.csv', 'text/csv', key=name)

def hero(title, subtitle):
    label = 'Intelligence studio' if page == 'Overview' else category.title()
    st.markdown(f'<div class="page-heading"><small>{escape(label)}</small><h1>{escape(title)}</h1><p>{escape(subtitle)}</p></div>', unsafe_allow_html=True)
    scope = 'Historical model scope · transaction filters not applied' if page in MODEL_PAGES else f'{dates[0]:%d %b %Y} – {dates[1]:%d %b %Y} · {len(countries) if countries else "All"} markets'
    st.markdown(f'<div class="page-meta"><span>{escape(scope)}</span><span>GBP · Historical data</span></div>', unsafe_allow_html=True)

@st.cache_data(show_spinner='Training historical customer value model...')
def value_model(data):
    d=data.dropna(subset=['customer_id']).copy()
    d['customer_id']=d.customer_id.astype(str)
    end=d.invoice_date.max().normalize()+pd.Timedelta(days=1)
    names=['recency','frequency','monetary','units']
    def snapshot(cutoff, target=True):
        past=d[(d.invoice_date<cutoff)&(d.invoice_date>=cutoff-pd.Timedelta(days=180))&(~d.is_return)]
        x=past.groupby('customer_id').agg(last=('invoice_date','max'),frequency=('invoice','nunique'),monetary=('line_amount','sum'),units=('quantity','sum'))
        x['recency']=(cutoff-x['last']).dt.days
        x=x[names]
        if target:
            future=d[(d.invoice_date>=cutoff)&(d.invoice_date<cutoff+pd.Timedelta(days=90))].groupby('customer_id').line_amount.sum()
            x['target']=future.reindex(x.index).fillna(0)
        return x
    train=snapshot(end-pd.Timedelta(days=180)); test=snapshot(end-pd.Timedelta(days=90)); current=snapshot(end,False)
    if min(len(train),len(test),len(current))<10: raise ValueError('Not enough historical customers to train and validate.')
    model=RandomForestRegressor(n_estimators=70,max_depth=8,min_samples_leaf=8,random_state=42,n_jobs=-1)
    model.fit(train[names],train.target)
    pred=model.predict(test[names])
    scores=(mean_absolute_error(test.target,pred),np.sqrt(mean_squared_error(test.target,pred)))
    baseline=mean_absolute_error(test.target,np.full(len(test),train.target.median()))
    model.fit(pd.concat([train[names],test[names]]),pd.concat([train.target,test.target]))
    scores=(*scores,baseline)
    values=current.copy(); values['predicted_value']=model.predict(current[names]); values=values.reset_index().sort_values('predicted_value',ascending=False)
    return model,scores,values,names,test[names].sample(min(150,len(test)),random_state=42)

monthly = data.set_index('invoice_date').line_amount.resample('MS').sum().rename('revenue').reset_index()
regional = data.groupby('country').line_amount.sum().rename('revenue').reset_index().sort_values('revenue', ascending=False)
def compact_number(value, prefix=''):
    if abs(value) >= 1_000_000:
        return f'{prefix}{value/1_000_000:,.2f}M'
    if abs(value) >= 100_000:
        return f'{prefix}{value/1_000:,.1f}K'
    return f'{prefix}{value:,.0f}'


def sparkline(series, color):
    values = np.asarray(series, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) < 2:
        return ''
    lo, hi = values.min(), values.max()
    y = 23 - 19 * (values-lo)/(hi-lo) if hi>lo else np.full(len(values), 13)
    x = np.linspace(2, 148, len(values))
    points = ' '.join(f'{u:.2f},{v:.2f}' for u,v in zip(x,y))
    return f'<svg class="sparkline" viewBox="0 0 150 28" preserveAspectRatio="none" aria-hidden="true"><polygon points="2,27 {points} 148,27" fill="{color}" opacity=".09"/><polyline points="{points}" fill="none" stroke="{color}" stroke-width="1.8" vector-effect="non-scaling-stroke" stroke-linecap="round"/></svg>'


def kpi(label, value, foot, symbol, color, series=None):
    mini = sparkline(series, color) if series is not None else ''
    st.markdown(f'<div class="kpi"><div class="kpi-top">{escape(label)}<span class="kpi-icon" style="color:{color};background:{color}18">{escape(symbol)}</span></div><div class="kpi-value">{escape(value)}</div><div class="kpi-foot">{escape(foot)}</div>{mini}</div>', unsafe_allow_html=True)


def section(title, detail=''):
    st.markdown(f'<div class="section-head"><strong>{escape(title)}</strong><small>{escape(detail)}</small></div>', unsafe_allow_html=True)


def brief(label, value, description):
    st.markdown(f'<div class="brief"><small>{escape(label)}</small><b>{escape(value)}</b><div>{escape(description)}</div></div>', unsafe_allow_html=True)


if page == 'Overview':
    scope = f'{dates[0]:%d %b %Y} – {dates[1]:%d %b %Y} · {len(countries) if countries else "All"} markets'
    st.markdown(f'<div class="product-mast"><div><div class="mast-kicker">RETAIL INTELLIGENCE STUDIO</div><h1>Performance overview</h1><p>Monitor revenue, customer behavior and opportunities across your retail business.</p></div><div class="mast-date"><small>REPORTING THROUGH</small><b>{dates[1]:%d %b %Y}</b><span>Historical workspace · GBP</span></div></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-meta"><span>{escape(scope)}</span><span>Net revenue includes returns</span><span>{len(data):,} transaction lines</span></div>', unsafe_allow_html=True)
    days=(dates[1]-dates[0]).days+1
    previous_end=pd.Timestamp(dates[0])
    previous_start=previous_end-pd.Timedelta(days=days)
    previous=df[(df.invoice_date >= previous_start) & (df.invoice_date < previous_end)]
    if countries: previous=previous[previous.country.isin(countries)]
    prior_net=previous.line_amount.sum()
    comparable=previous_start>=df.invoice_date.min().normalize() and not previous.empty and prior_net>0
    comparison=f'{net/prior_net-1:+.1%} vs preceding period' if comparable else f'{len(data):,} transaction lines'
    period = data.assign(month=data.invoice_date.dt.to_period('M'))
    trends = period.groupby('month').agg(revenue=('line_amount','sum'), customers=('customer_id','nunique'), lines=('invoice','size'), returned=('is_return','sum'))
    trend_orders = period.loc[~period.is_return].groupby('month').invoice.nunique().reindex(trends.index,fill_value=0)
    section('Business performance', 'Sparklines show monthly trends within the selected period')
    a,b,c,d=st.columns(4)
    with a: kpi('Net revenue',compact_number(net,'£'),comparison,'£',accent,trends.revenue)
    with b: kpi('Purchase invoices',f'{orders:,}','Distinct non-return invoices','▤','#169a8a',trend_orders)
    with c: kpi('Known customers',f'{data.customer_id.nunique():,}','Unique identified customers','◎','#567bc2',trends.customers)
    with d: kpi('Return line rate',f'{rate:.2f}%',f'{len(returns):,} return lines','↩','#be783d',100*trends.returned/trends.lines)
    section('Performance & opportunities', 'Selected period · GBP')
    a,b=st.columns([1.85,1])
    with a:
        granularity = st.radio('Revenue interval', ['Monthly', 'Weekly', 'Daily'], horizontal=True, key='overview_granularity', label_visibility='collapsed')
        interval = {'Monthly':'MS','Weekly':'W-MON','Daily':'D'}[granularity]
        trend = data.set_index('invoice_date').line_amount.resample(interval).sum()
        fig=go.Figure(go.Scatter(x=trend.index,y=trend.values,mode='lines+markers' if len(trend)<=60 else 'lines',line=dict(color=accent,width=2.6),marker=dict(size=4),fill='tozeroy',fillcolor='rgba(15,145,128,0.10)',hovertemplate='%{x|%d %b %Y}<br>£%{y:,.2f}<extra></extra>'))
        fig.update_layout(title=f'{granularity} net revenue',yaxis_title='Revenue (GBP)',showlegend=False)
        fig.update_yaxes(tickprefix='£',tickformat='~s')
        chart(fig, height=322)
    with b:
        market_share=regional.iloc[0].revenue/net if net>0 and not regional.empty else None
        counts=sales.dropna(subset=['customer_id']).groupby('customer_id').invoice.nunique()
        repeat=float(counts.gt(1).mean()) if len(counts) else None
        coverage=float(data.customer_id.notna().mean())
        def item(label, value, note, proportion):
            bar = '' if proportion is None else f'<div class="decision-track"><i style="width:{min(100,max(0,proportion*100)):.1f}%"></i></div>'
            return f'<div class="decision-item"><small>{escape(label)}</small><strong>{escape(value)}</strong>{bar}<em>{escape(note)}</em></div>'
        leader=f'{regional.iloc[0].country} · {market_share:.1%}' if market_share is not None else 'Not available'
        loyalty=f'{repeat:.1%} repeat buyers' if repeat is not None else 'Not available'
        decision = '<div class="decision-panel"><header><b>Decision brief</b><span>DATA-DRIVEN</span></header>'
        decision += item('Leading market',leader,'Review revenue concentration and diversification.',market_share)
        decision += item('Customer retention',loyalty,'Share of known buyers with multiple invoices.',repeat)
        decision += item('Customer ID coverage',f'{coverage:.1%} identified','Unknown IDs remain in revenue, not customer models.',coverage)
        st.markdown(decision+'</div>',unsafe_allow_html=True)
    a,b=st.columns([1,1])
    with a:
        st.download_button('↓  Export revenue trend', trend.rename('net_revenue_gbp').to_csv().encode('utf-8-sig'), 'revenue_trend.csv', 'text/csv', key='trend_export',use_container_width=True)
    with b:
        st.button('Explore business insights →',key='launch_insights',use_container_width=True,on_click=navigate,args=('Business insights',))
    section('Operating metrics')
    metrics=[('Gross sales',compact_number(sales.line_amount.sum(),'£'),'Non-return revenue'),('Return value',compact_number(abs(returns.line_amount.sum()),'£'),'Absolute return value'),('Revenue / invoice',money(net/orders) if orders else '—','Net revenue per purchase invoice'),('Markets',f'{data.country.nunique():,}',f'{data.stock_code.nunique():,} product codes')]
    st.markdown('<div class="operating-strip">'+''.join(f'<div><small>{escape(label)}</small><b>{escape(value)}</b><em>{escape(note)}</em></div>' for label,value,note in metrics)+'</div>',unsafe_allow_html=True)
    section('Explore the business', 'Distribution and trading patterns')
    t1,t2,t3=st.tabs(['Leading markets','Transaction mix','Weekly trading'])
    with t1:
        top=regional.head(10).sort_values('revenue')
        fig=go.Figure(go.Bar(x=top.revenue,y=top.country,orientation='h',marker_color=accent,hovertemplate='%{y}<br>£%{x:,.2f}<extra></extra>'))
        fig.update_layout(title='Top markets by net revenue'); fig.update_xaxes(tickprefix='£',tickformat='~s'); chart(fig)
    with t2:
        fig=go.Figure(go.Pie(labels=['Sales','Returns'],values=[len(sales),len(returns)],hole=.75,marker=dict(colors=['#159c92','#e49b65']),textinfo='none',hovertemplate='%{label}: %{value:,} (%{percent})<extra></extra>'))
        fig.add_annotation(text=f'<b>{rate:.2f}%</b><br>returns',showarrow=False,font=dict(size=19,color=ink),x=.5,y=.5)
        fig.update_layout(title='Transaction mix',legend=dict(orientation='h',y=-.1,x=.5,xanchor='center')); chart(fig)
    with t3:
        daily=data.assign(weekday=data.invoice_date.dt.day_name()).groupby('weekday').line_amount.sum().reindex(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'],fill_value=0)
        fig=go.Figure(go.Bar(x=[x[:3] for x in daily.index],y=daily.values,marker_color=[accent if val==daily.max() else '#7696aa' for val in daily.values],hovertemplate='%{x}<br>£%{y:,.2f}<extra></extra>'))
        fig.update_layout(title='Revenue by weekday'); fig.update_yaxes(tickprefix='£',tickformat='~s'); chart(fig)
    section('Intelligence modules', 'From descriptive analytics to business decisions')
    modules=[('01 / RETENTION','Churn risk','Identify customers at risk of inactivity.','Churn risk','quick_churn'),('02 / PLANNING','Sales forecasting','Explore the 30-day historical projection.','Forecast','quick_forecast'),('03 / CROSS-SELL','Product affinities','Discover product bundles using Apriori.','Market basket','quick_basket')]
    for col,(tag,title,note,target,key) in zip(st.columns(3),modules):
        with col:
            st.markdown(f'<div class="module-card"><small>{tag}</small><b>{title}</b><span>{note}</span></div>',unsafe_allow_html=True)
            st.button('Open module →',key=key,use_container_width=True,on_click=navigate,args=(target,))
    with st.expander('Inspect and export monthly revenue'):
        table(monthly,'overview_monthly_revenue')
    st.caption('Historical data · first and last months may be partial · revenue includes returns · insights are descriptive, not measured outcomes.')
elif page == 'Sales analytics':
    hero('Sales analytics','Track revenue, growth and weekly trading patterns.')
    monthly['growth_pct']=monthly.revenue.pct_change(fill_method=None).replace([float('inf'),-float('inf')],float('nan'))*100
    chart(px.line(monthly,x='invoice_date',y='revenue',markers=True,title='Monthly net revenue'))
    chart(px.bar(monthly,x='invoice_date',y='growth_pct',title='Month-on-month growth (%)'))
    chart(px.choropleth(regional,locations='country',locationmode='country names',color='revenue',title='Geographic revenue (recognized country names)',color_continuous_scale='Viridis'))
    daily=data.assign(day=data.invoice_date.dt.day_name(),hour=data.invoice_date.dt.hour).pivot_table(index='day',columns='hour',values='line_amount',aggfunc='sum',fill_value=0).reindex(['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'])
    if not daily.empty: chart(px.imshow(daily,aspect='auto',title='Revenue by weekday and hour',color_continuous_scale='Viridis'))
    st.caption('Month-on-month changes can be distorted by partial months and low or negative prior revenue.')
    table(monthly,'monthly_sales')
elif page == 'Products':
    hero('Product performance','Discover revenue leaders and inventory opportunities.')
    search=st.text_input('Search product names or codes')
    n=st.slider('Products to display',5,50,15)
    products=data[data.stock_code.astype(str).str.match(r'^\d{5}[A-Za-z]*$')].groupby('stock_code').agg(description=('description','first'),revenue=('line_amount','sum'),net_units=('quantity','sum')).reset_index()
    if search:
        products=products[products.description.str.contains(search,case=False,regex=False,na=False) | products.stock_code.astype(str).str.contains(search,case=False,regex=False)]
    products=products.nlargest(n,'revenue')
    chart(px.bar(products.sort_values('revenue'),x='revenue',y='description',orientation='h',color='revenue',title='Leading merchandise codes'))
    table(products,'products')
elif page == 'Customers':
    hero('Customer intelligence','Understand purchasing patterns and customer value.')
    counts=sales.dropna(subset=['customer_id']).groupby('customer_id').invoice.nunique()
    st.metric('Repeat purchase rate',f'{(counts.gt(1).mean()*100 if len(counts) else 0):.2f}%')
    customers=data.dropna(subset=['customer_id']).groupby('customer_id').line_amount.sum().rename('spending').reset_index().sort_values('spending',ascending=False)
    customers.customer_id=customers.customer_id.astype(str)
    chart(px.bar(customers.head(20),x='customer_id',y='spending',title='Top customers'))
    table(customers,'customers')
elif page == 'Segmentation':
    hero('Customer segmentation','RFM • K-Means • historical model snapshot')
    s=report('clustering/cluster_summary.csv')
    if not s.empty:
        st.metric('Customers analyzed',f'{s.customers.sum():,}')
        a,b=st.columns(2)
        with a: chart(px.pie(s,names='cluster',values='customers',hole=.65,title='Cluster composition'))
        with b: chart(px.bar(s.assign(cluster=s.cluster.astype(str)),x='cluster',y='total_revenue',color='cluster',title='Revenue by cluster'))
        table(s,'cluster_summary')
        if (ROOT/'reports/clustering/customer_clusters.png').exists(): st.image(str(ROOT/'reports/clustering/customer_clusters.png'))
elif page == 'Churn risk':
    hero('Retention intelligence','Historical test results • 90-day inactivity definition')
    m=report('churn/model_results.csv'); p=report('churn/churn_predictions.csv')
    if not m.empty:
        best=m.sort_values('roc_auc',ascending=False).iloc[0]
        a,b,c=st.columns(3); a.metric('Selected model',best.model); b.metric('ROC-AUC',f'{best.roc_auc:.3f}'); c.metric('Recall',f'{best.recall:.1%}')
        chart(px.bar(m,x='model',y=['precision','recall','f1_score','roc_auc'],barmode='group',title='Model comparison'))
        st.caption('Models were compared on the historical holdout; independent final testing is still needed.')
        image_path=ROOT/'reports/churn/confusion_matrix.png'
        if image_path.exists():
            with st.expander('View confusion matrix'): st.image(str(image_path))
    if not p.empty:
        r=p.risk_level.value_counts().rename_axis('risk').reset_index(name='customers')
        chart(px.pie(r,names='risk',values='customers',hole=.65,title='Risk distribution',color='risk',color_discrete_map={'Low Risk':'#169a8a','Medium Risk':'#d59a47','High Risk':'#cb6264'}))
        level=st.selectbox('Risk segment',['All']+list(r.risk))
        table(p if level=='All' else p[p.risk_level==level],'churn_predictions')
elif page == 'Forecast':
    hero('Revenue forecasting','30-day model forecast after the historical dataset ends.')
    f=report('forecast/future_forecast.csv'); m=report('forecast/model_results.csv')
    if not f.empty:
        st.metric('Forecast net revenue',money(f.predicted_revenue.sum()))
        # Align to saved forecast start, not the end of a newly refreshed warehouse.
        first=pd.to_datetime(f.date).min()
        h=df[df.invoice_date<first].set_index('invoice_date').line_amount.resample('D').sum().tail(90)
        fig=go.Figure(); fig.add_scatter(x=h.index,y=h.values,name='Historical'); fig.add_scatter(x=pd.to_datetime(f.date),y=f.predicted_revenue,name='Forecast',line=dict(dash='dash'))
        fig.update_layout(title='Historical revenue and 30-day recursive projection', yaxis_title='Net revenue (GBP)'); chart(fig); table(f,'forecast')
        st.caption('Saved forecasts are historical projections, not current-year predictions. Comparison metrics are one-day-ahead errors, not a validated 30-day accuracy estimate.')
    if not m.empty: table(m,'forecast_metrics')
elif page == 'Market basket':
    hero('Product affinities','Apriori recommendations • historical UK top-product baskets')
    r=report('basket/association_rules.csv')
    if not r.empty:
        search=st.text_input('Find a product in recommendation rules')
        if search: r=r[r.antecedents.str.contains(search,case=False,regex=False,na=False)]
        threshold=st.slider('Minimum confidence',0.,1.,.3)
        r=r[r.confidence>=threshold]
        st.metric('Matching rules',len(r))
        chart(px.scatter(r,x='support',y='confidence',color='lift',hover_data=['antecedents','consequents'],title='Association strength'))
        table(r,'association_rules')
elif page == 'Business insights':
    hero('Decision center','Rule-based recommendations for retail teams.')
    if net>0 and not regional.empty:
        share=regional.iloc[0].revenue/net
        st.subheader('Market concentration'); st.write(f'{regional.iloc[0].country}: {share:.1%} of selected net revenue. '+('Review diversification opportunities.' if share>.7 else 'Continue monitoring the market mix.'))
    st.subheader('Returns'); st.write(f'{rate:.2f}% of selected transaction lines are flagged as returns. Investigate frequently returned merchandise.')
    p=report('churn/churn_predictions.csv')
    if not p.empty: st.write(f"Retention: review {(p.risk_level=='High Risk').sum():,} high-risk customers in the historical test cohort.")
    st.caption('Recommendations are hypotheses, not measured business outcomes.')
elif page == 'Customer value':
    hero('Customer value prediction','Estimate next-90-day net spending using historical customer behavior.')
    st.caption('Global historical model; transaction filters do not apply. A 90-day value proxy, not full lifetime value.')
    try:
        model, scores, values, features, sample = value_model(df)
        a,b,c,d=st.columns(4)
        a.metric('Holdout MAE',money(scores[0])); b.metric('Holdout RMSE',money(scores[1])); c.metric('Median baseline MAE',money(scores[2])); d.metric('Scored customers',len(values))
        st.caption('Temporal holdout comparison. Current scores use the model refit on both completed target windows. No full-lifetime value or realized outcome is claimed.')
        chart(px.bar(values.head(20),x='customer_id',y='predicted_value',title='Highest predicted 90-day customer value'))
        table(values,'customer_value')
    except ValueError as exc: st.warning(str(exc))
elif page == 'Anomaly detection':
    hero('Revenue anomaly monitor','Spot unusual daily revenue against the previous 28 days.')
    daily=data.set_index('invoice_date').line_amount.resample('D').sum().rename('revenue').to_frame()
    daily['baseline']=daily.revenue.shift().rolling(28,min_periods=14).mean()
    std=daily.revenue.shift().rolling(28,min_periods=14).std().replace(0,np.nan)
    daily['z_score']=(daily.revenue-daily.baseline)/std
    limit=st.slider('Anomaly threshold (standard deviations)',2.0,4.0,3.0,.25)
    unusual=daily[daily.z_score.abs()>=limit].reset_index()
    st.metric('Flagged days',len(unusual))
    fig=go.Figure(); fig.add_scatter(x=daily.index,y=daily.revenue,name='Revenue'); fig.add_scatter(x=daily.index,y=daily.baseline,name='Prior baseline'); fig.add_scatter(x=unusual.invoice_date,y=unusual.revenue,mode='markers',name='Flagged',marker=dict(color='#f97373',size=10))
    chart(fig); table(unusual,'anomalies')
    st.caption('Statistical flags, not confirmed fraud. Missing trading dates are treated as zero.')
elif page == 'What-if simulator':
    hero('Scenario lab','Explore the impact of changes in sales and return value.')
    a,b=st.columns(2)
    growth=a.slider('Gross sales change (%)',-50,100,10)
    improvement=b.slider('Return value reduction (%)',0,100,10)
    gross=sales.line_amount.sum(); refunds=returns.line_amount.sum()
    scenario=gross*(1+growth/100)+refunds*(1-improvement/100)
    a.metric('Scenario net revenue',money(scenario),money(scenario-net)); b.metric('Baseline net revenue',money(net))
    chart(go.Figure(go.Bar(x=['Baseline','Scenario'],y=[net,scenario],marker_color=[accent,'#19b9a8'])))
    st.caption('Arithmetic scenario, not a causal or ML prediction. Sales and returns changes are independent assumptions.')
elif page == 'Explainable AI':
    hero('Model explainability','SHAP explanations for the 90-day customer value model.')
    st.caption('Global historical model; filters do not apply. Explains model behavior, not causality.')
    try:
        model, scores, values, features, sample = value_model(df)
        import shap
        explanation=shap.TreeExplainer(model)(sample)
        importance=pd.DataFrame({'feature':features,'mean_abs_shap':np.abs(explanation.values).mean(axis=0)}).sort_values('mean_abs_shap')
        chart(px.bar(importance,x='mean_abs_shap',y='feature',orientation='h',title='Global SHAP feature importance'))
        table(importance,'shap_importance')
        st.caption('Mean absolute SHAP values for a sample of historical feature rows, using the refit model.')
        index=st.selectbox('Inspect sample customer',list(range(len(sample))),format_func=lambda i: str(sample.index[i]))
        local=pd.DataFrame({'feature':features,'contribution':np.asarray(explanation.values)[index]}).sort_values('contribution')
        chart(px.bar(local,x='contribution',y='feature',color=local.contribution.ge(0).map({True:'Increases value',False:'Decreases value'}),orientation='h',title='Individual prediction contributions'))
    except ImportError: st.warning('Install shap to enable this page.')
    except Exception as exc: st.warning(f'Explanation unavailable: {type(exc).__name__}')
elif page == 'About RetailIQ':
    hero('Built for better retail decisions.','A data science and analytics portfolio project by N. Lalu Prasad.')
    st.markdown('RetailIQ AI brings together historical transaction analytics, customer intelligence, machine learning and decision support in one workspace.')
    a,b,c = st.columns(3)
    a.metric('Transaction lines',f'{len(df):,}')
    b.metric('Known customers',f'{df.customer_id.nunique():,}')
    c.metric('Markets',f'{df.country.nunique():,}')
    section('System architecture','End-to-end pipeline')
    stages = [('01 / INGEST','Retail transactions','Python · Pandas · ETL'),('02 / STORE','Data warehouse','PostgreSQL · local Parquet snapshot'),('03 / MODEL','Predictive intelligence','Scikit-learn · Apriori · SHAP'),('04 / SERVE','Decision workspace','Streamlit · Plotly')]
    for col, item in zip(st.columns(4),stages):
        with col: brief(*item)
    section('Model methodology')
    methods = pd.DataFrame([
        ('Segmentation','RFM, K-Means','Silhouette score and cluster profiles'),
        ('Retention','Classification','Historical holdout metrics; 90-day inactivity'),
        ('Forecasting','Regression with temporal features','One-day-ahead holdout error; recursive 30-day projection'),
        ('Product affinities','Apriori','Support, confidence and lift; UK subset'),
        ('Customer value','Random Forest','Temporal holdout MAE/RMSE; 90-day value proxy'),
        ('Anomaly detection','Rolling z-score','Statistical flags, not fraud labels'),
        ('Explainability','SHAP','Value-model feature contributions')],columns=['Module','Technique','Evaluation / scope'])
    table(methods,'methodology')
    section('Start the product tour')
    a,b,c=st.columns(3)
    with a: st.button('Business overview →',key='tour_overview',use_container_width=True,on_click=navigate,args=('Overview',))
    with b: st.button('Model performance →',key='tour_churn',use_container_width=True,on_click=navigate,args=('Churn risk',))
    with c: st.button('Data quality →',key='tour_data',use_container_width=True,on_click=navigate,args=('Data workspace',))
    st.caption('Portfolio demonstration using a historical dataset. No live commercial outcomes or independently validated production readiness are claimed.')

else:
    hero('Data workspace','Inspect the active dataset or validate an incoming CSV.')
    a,b,c,d=st.columns(4)
    a.metric('Historical lines',f'{len(df):,}')
    b.metric('Missing customer IDs',f'{df.customer_id.isna().sum():,}')
    c.metric('Return lines',f'{df.is_return.sum():,}')
    d.metric('Outlier flags',f'{df.is_outlier.sum():,}' if 'is_outlier' in df else 'Unavailable')
    st.caption('Outlier flags are indicators for investigation; they are not automatically removed.')
    table(data.head(1000),'transaction_preview')
    upload=st.file_uploader('Upload cleaned CSV for validation only',type=['csv'])
    if upload is not None:
        try:
            incoming=pd.read_csv(upload,nrows=100001)
            required={'invoice','invoice_date','customer_id','stock_code','description','country','quantity','unit_price','line_amount','is_return'}
            missing=required-set(incoming.columns)
            if missing: st.error('Missing columns: '+', '.join(sorted(missing)))
            else:
                bad_dates=pd.to_datetime(incoming.invoice_date,errors='coerce').isna().sum()
                bad_numbers=sum(pd.to_numeric(incoming[c],errors='coerce').isna().sum() for c in ['quantity','unit_price','line_amount'])
                st.write({'sample_rows':len(incoming),'invalid_dates':int(bad_dates),'invalid_numeric_cells':int(bad_numbers),'duplicate_rows':int(incoming.duplicated().sum())})
                st.dataframe(incoming.head(20))
            st.caption('Preview only (up to 100,001 rows). Upload does not replace data or retrain models.')
        except Exception as exc: st.error(f'Unable to read CSV: {exc}')
st.divider()
st.markdown('<div class="footer-brand"><span>RetailIQ AI · Intelligence Studio</span><span>Built by N. Lalu Prasad · Historical analytics</span></div>', unsafe_allow_html=True)
