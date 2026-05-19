import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go
import cr_utils as cr_CG_utils

# ==============================================================================
# --- 🔒 SECURITY: Initial LOGIN ---
# ==============================================================================
# This stops the app from loading ANY data until the password is correct.

def check_password():
    """Returns `True` if the user had the correct password."""
    if st.session_state.get("password_correct", False):
        return True

    st.header("🔒 Protected Internal Tool")
    password_input = st.text_input("Enter Company Password", type="password")
    
    if password_input:
        if password_input == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            st.rerun()  
        else:
            st.error("😕 Password incorrect")
            
    return False

if not check_password():
    st.stop()  

# ==============================================================================
# --- PAGE CONFIG ---
# ==============================================================================

# ==============================================================================
# --- HELPER FUNCTIONS ---
# ==============================================================================

def display_filter_context(ctx, tool_name=None):
    """Displays a clear banner indicating exactly what data is currently filtered and active."""
    if not ctx:
        tool_str = f" | **Tool:** {tool_name}" if tool_name and tool_name != 'Multiple Tools (Rolled-Up)' else ""
        st.info(f"🗂️ **Current Filter Scope:** All Data{tool_str}")
        return
        
    active_filters = [f"**{k}:** {v}" for k, v in ctx.items() if v != "All"]
    if tool_name and tool_name != "Multiple Tools (Rolled-Up)":
        active_filters.append(f"**Tool:** {tool_name}")
        
    if active_filters:
        st.info("🗂️ **Current Filter Scope:** " + " | ".join(active_filters))
    else:
        st.info(f"🗂️ **Current Filter Scope:** All Global Data")

def create_capsule(value, color_logic="neutral", suffix="", inverse=False):
    """
    Generates an HTML string for a styled pill/capsule.
    """
    bg_color = "#262730" 
    text_color = "#ffffff"
    
    if color_logic == "grey":
        bg_color = "#41424C" 
        text_color = "#ffffff"
    elif color_logic == "good_bad":
        if value >= 90: bg_color = cr_CG_utils.PASTEL_COLORS['green']; text_color = "#0E1117"
        elif value >= 75: bg_color = cr_CG_utils.PASTEL_COLORS['orange']; text_color = "#0E1117"
        else: bg_color = cr_CG_utils.PASTEL_COLORS['red']; text_color = "#0E1117"
    elif color_logic == "bad_good":
        if value <= 10: bg_color = cr_CG_utils.PASTEL_COLORS['green']; text_color = "#0E1117"
        elif value <= 20: bg_color = cr_CG_utils.PASTEL_COLORS['orange']; text_color = "#0E1117"
        else: bg_color = cr_CG_utils.PASTEL_COLORS['red']; text_color = "#0E1117"
    elif color_logic == "net":
        if value >= 0: bg_color = cr_CG_utils.PASTEL_COLORS['green']; text_color = "#0E1117"
        else: bg_color = cr_CG_utils.PASTEL_COLORS['red']; text_color = "#0E1117"

    return f'<span style="background-color:{bg_color}; color:{text_color}; padding:2px 8px; border-radius:10px; font-weight:bold; font-size:0.8em;">{value:,.1f}{suffix}</span>'

# ==============================================================================
# --- 1. RENDER FUNCTIONS ---
# ==============================================================================

def render_risk_tower(df_tool, config):
    """Renders the Risk Tower (Tab 1)."""
    st.header("Capacity Risk Tower")
    st.info("This tower identifies tools at risk by analyzing weekly production gaps over the last 4 weeks based on your active filters.")

    with st.expander("ℹ️ How the Risk Tower Works"):
        st.markdown("""
        The Risk Tower evaluates each tool based on its performance over its own most recent 4-week period.
        
        ### 1. Risk Score (0-100)
        Represents the **Average Capacity Achievement %** over the analysis period.
        - **Formula:** `Average(Actual Output / Target Output)` across the active weeks.
        - **Goal:** A score of 95+ indicates the tool is consistently meeting capacity demand.
        
        ### 2. Primary Risk Factor
        Identifies the dominant root cause preventing the tool from hitting 100% capacity.
        - **Downtime:** The majority of lost parts are due to machine stops (Run Rate Downtime).
        - **Cycle Time:** The majority of lost parts are due to slow cycles (Running above Ideal CT).
        - **Stable:** The tool is operating above 95% achievement; no significant risk detected.
        
        ### 3. Achievement Trend
        Displays the weekly progression of Capacity Achievement to highlight stability.
        - Shows: `Week 1 % → Week 2 % → Week 3 % → Week 4 %`
        - Helps identify if performance is improving, degrading, or fluctuating wildly.
        
        ### 4. Details
        Provides specific context on the magnitude of the risk.
        - Displays the total **Net Parts Lost** attributed to the Primary Risk Factor.
        """, unsafe_allow_html=True)

    results = []
    tools = sorted(df_tool['tool_id'].unique())
    
    for tool_id in tools:
        tool_specific_df = df_tool[df_tool['tool_id'] == tool_id]
        
        weekly_df = cr_CG_utils.get_aggregated_data(tool_specific_df, 'Weekly', config)
        
        if weekly_df.empty:
            continue
            
        recent = weekly_df.tail(4).copy()
        
        cols_needed = ['Actual Output', 'Target Output', 'Downtime Loss', 'Slow Loss']
        for c in cols_needed:
            if c not in recent.columns: recent[c] = 0
            
        recent['Target Output'] = recent['Target Output'].replace(0, 1)
        recent['Achieve %'] = (recent['Actual Output'] / recent['Target Output'] * 100).fillna(0)
        
        trend_str = " → ".join([f"{x:.0f}%" for x in recent['Achieve %']])
        
        avg_achieve = recent['Achieve %'].mean()
        risk_score = min(avg_achieve, 100)
        
        total_dt_loss = recent['Downtime Loss'].sum()
        total_slow_loss = recent['Slow Loss'].sum()
        net_gap = recent['Target Output'].sum() - recent['Actual Output'].sum()
        
        risk_factor = "Stable"
        details = f"Running well. Overall achievement is {avg_achieve:.1f}%."
        
        if avg_achieve < 95:
            if total_dt_loss > total_slow_loss:
                risk_factor = "Downtime"
                details = f"Primary loss driver is Downtime ({total_dt_loss:,.0f} parts lost)."
            elif total_slow_loss > 0:
                risk_factor = "Cycle Time"
                details = f"Primary loss driver is Slow Cycles ({total_slow_loss:,.0f} parts lost)."
            else:
                risk_factor = "Unspecified"
                details = f"Output is below target by {net_gap:,.0f} parts."
        
        p_min = recent['Period'].min()
        p_max = recent['Period'].max()
        if isinstance(p_min, pd.Period): p_min = p_min.start_time.date()
        if isinstance(p_max, pd.Period): p_max = p_max.start_time.date() 

        results.append({
            "Tool ID": tool_id,
            "Analysis Period": f"{p_min} to {p_max}",
            "Risk Score": risk_score,
            "Primary Risk Factor": risk_factor,
            "Achievement Trend": trend_str,
            "Details": details
        })

    if not results:
        st.warning("Not enough data to generate the Risk Tower for the current selection.")
        return

    risk_df = pd.DataFrame(results)

    def style_risk_tower(row):
        score = row['Risk Score']
        styles = [''] * len(row)
        
        if score >= 90: base_color = cr_CG_utils.PASTEL_COLORS['green']
        elif score >= 75: base_color = cr_CG_utils.PASTEL_COLORS['orange']
        else: base_color = cr_CG_utils.PASTEL_COLORS['red']
        
        return [f'background-color: {base_color}; color: black' for _ in row]

    st.dataframe(
        risk_df.style.apply(style_risk_tower, axis=1)
        .format({'Risk Score': '{:.0f}'}),
        use_container_width=True, 
        hide_index=True
    )

def render_trends_tab(df_tool, config, key_suffix=''):
    """Renders the Trends Tab."""
    from plotly.subplots import make_subplots
    st.header("Historical Performance Trends")
    st.info("Trends are calculated using the core engine matching the Optimal Capacity logic.")

    col_freq, col_mode, _ = st.columns([1, 1, 2])
    with col_freq:
        trend_freq = st.selectbox("Select Trend Frequency", ["Daily", "Weekly", "Monthly"],
                                  key=f"cr_trend_freq{key_suffix}")
    with col_mode:
        trend_mode = st.selectbox("Dashboard Mode", ["Optimal", "Target"],
                                  key=f"cr_trend_mode{key_suffix}")

    agg_df = cr_CG_utils.get_aggregated_data(df_tool, trend_freq, config)

    if agg_df.empty:
        st.warning("No trend data available.")
        return

    # Rename to match RR conventions
    agg_df = agg_df.rename(columns={
        'Run Time':        'Total Run Duration (h)',
        'Downtime':        'RR Downtime',
        'Production Time': 'Production Time',
        'Run Time Sec':    'Run Time Sec',
    })
    # Convert seconds to hours where applicable
    if 'Run Time Sec' in agg_df.columns:
        agg_df['Total Run Duration (h)'] = (agg_df['Run Time Sec'] / 3600).round(2)
    if 'Production Time Sec' in agg_df.columns:
        agg_df['Production Time (h)'] = (agg_df['Production Time Sec'] / 3600).round(2)
    if 'Downtime Sec' in agg_df.columns:
        agg_df['RR Downtime (h)'] = (agg_df['Downtime Sec'] / 3600).round(2)

    # Rename output columns with (parts)
    agg_df = agg_df.rename(columns={
        'Actual Output':  'Actual Output (parts)',
        'Optimal Output': 'Optimal Output (parts)',
        'Target Output':  'Target Output (parts)',
        'Downtime Loss':  'Loss: RR Downtime (parts)',
        'Slow Loss':      'Loss: Slow Cycles (parts)',
        'Fast Gain':      'Gain: Fast Cycles (parts)',
        'Total Loss':     'Total Net Loss (parts)',
    })

    display_cols = ['Period', 'Total Run Duration (h)', 'Production Time (h)', 'RR Downtime (h)']
    if trend_mode == "Optimal":
        for c in ['Actual Output (parts)', 'Optimal Output (parts)',
                  'Loss: RR Downtime (parts)', 'Loss: Slow Cycles (parts)',
                  'Gain: Fast Cycles (parts)', 'Total Net Loss (parts)']:
            if c in agg_df.columns:
                display_cols.append(c)
    else:
        if 'Target Output (parts)' in agg_df.columns:
            agg_df['Net Diff vs Target (parts)'] = (
                agg_df['Actual Output (parts)'] - agg_df['Target Output (parts)']
            )
            for c in ['Actual Output (parts)', 'Target Output (parts)', 'Net Diff vs Target (parts)']:
                if c in agg_df.columns:
                    display_cols.append(c)

    view_df = agg_df[[c for c in display_cols if c in agg_df.columns]].copy()

    def style_trends(row):
        styles = [''] * len(row)
        for i, col in enumerate(view_df.columns):
            val = row[col]
            if isinstance(val, (int, float)):
                if 'Loss' in col and 'Net' not in col:
                    styles[i] = 'color: #ff6961'
                elif 'Gain' in col:
                    styles[i] = 'color: #77dd77'
                elif 'Net Diff' in col:
                    styles[i] = 'color: #ff6961' if val < 0 else 'color: #77dd77'
        return styles

    st.dataframe(
        view_df.style.apply(style_trends, axis=1).format(precision=2),
        use_container_width=True, hide_index=True
    )

    # ── Dual-axis visual trend (aligned to RR) ────────────────────────────────
    st.subheader("Visual Trend")

    _all_metrics = [c for c in [
        'Actual Output (parts)', 'Optimal Output (parts)', 'Target Output (parts)',
        'Total Net Loss (parts)', 'Loss: RR Downtime (parts)', 'Loss: Slow Cycles (parts)',
        'Gain: Fast Cycles (parts)', 'Total Run Duration (h)', 'Production Time (h)',
        'RR Downtime (h)', 'Total Shots', 'Normal Shots', 'Downtime Shots',
    ] if c in agg_df.columns]

    _chart_types = ['Line', 'Bar']
    ca, cb = st.columns([2, 2])
    with ca:
        m1 = st.selectbox("Primary metric (left Y)", _all_metrics, index=0,
                          key=f"cr_trend_m1{key_suffix}")
        t1 = st.radio("Chart type", _chart_types, horizontal=True,
                      key=f"cr_trend_t1{key_suffix}")
    with cb:
        m2_opts = ['None'] + _all_metrics
        m2 = st.selectbox("Secondary metric (right Y)", m2_opts, index=0,
                          key=f"cr_trend_m2{key_suffix}")
        if m2 != 'None':
            t2 = st.radio("Chart type ", _chart_types, horizontal=True,
                          key=f"cr_trend_t2{key_suffix}")
        else:
            t2 = 'Line'

    df_plot = agg_df.sort_values('Period', ascending=True)
    fig = make_subplots(specs=[[{"secondary_y": m2 != 'None'}]])

    def _add_trace(fig, df, x, y, chart_type, secondary, name, colour):
        if y not in df.columns:
            return
        if chart_type == 'Bar':
            fig.add_trace(go.Bar(x=df[x], y=df[y], name=name,
                                 marker_color=colour, opacity=0.75), secondary_y=secondary)
        else:
            fig.add_trace(go.Scatter(x=df[x], y=df[y], name=name, mode='lines+markers',
                                     line=dict(color=colour, width=2),
                                     marker=dict(size=6)), secondary_y=secondary)

    _c1 = cr_CG_utils.PASTEL_COLORS['blue']
    _c2 = cr_CG_utils.PASTEL_COLORS['orange']

    _add_trace(fig, df_plot, 'Period', m1, t1, False, m1, _c1)
    if m2 != 'None':
        _add_trace(fig, df_plot, 'Period', m2, t2, True, m2, _c2)

    title = f"{m1} Trend ({trend_freq})" + (f"  vs  {m2}" if m2 != 'None' else '')
    fig.update_layout(
        title=title, barmode='group',
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
        xaxis_title='Period',
    )
    fig.update_yaxes(title_text=m1, secondary_y=False)
    if m2 != 'None':
        fig.update_yaxes(title_text=m2, secondary_y=True)

    st.plotly_chart(fig, use_container_width=True, key=f"cr_trend_fig{key_suffix}")

def render_dashboard(df_tool, config, dashboard_mode="Optimal", min_shots_filter=1, key_suffix=''):
    """
    Renders the Main Capacity Dashboard.
    """
    st.header(f"Capacity Dashboard ({dashboard_mode})")
    
    benchmark_mode = "Optimal Output" if dashboard_mode == "Optimal" else "Target Output"
    key_suffix = f"_{dashboard_mode.lower()}"

    # --- Controls ---
    c1, c2 = st.columns([2, 1])
    with c1:
        analysis_level = st.radio(f"Select Analysis Level ({dashboard_mode})",
            options=["Daily (by Run)", "Weekly (by Run)", "Monthly (by Run)", "Custom Period"],
            horizontal=True, key=f"cr_analysis_level{key_suffix}")
    with c2:
        enable_filter = min_shots_filter > 1
        min_shots_filter_local = min_shots_filter

    st.markdown("---")

    # df_tool is pre-processed (stop_flag, run_id, mode_ct etc. already computed
    # by the global CapacityRiskCalculator pass in main()). Use directly.
    df_processed = df_tool.copy()

    if df_processed.empty: st.error("No data."); return
    if enable_filter:
        run_counts = df_processed.groupby('run_id')['run_id'].transform('count')
        df_processed = df_processed[run_counts >= min_shots_filter_local]

    # --- Selection ---
    df_view = pd.DataFrame(); sub_header = ""; info_placeholder = None
    if "Daily" in analysis_level:
        col_d_sel, col_d_info = st.columns([1, 2])
        with col_d_sel:
            dates = sorted(df_processed['shot_time'].dt.date.unique())
            sel_date = st.selectbox("Select Date", dates, index=len(dates)-1, format_func=lambda x: x.strftime('%d %b %Y'), key=f"cr_date_select{key_suffix}")
        with col_d_info:
            info_placeholder = st.empty()
            info_base_text = f"**Viewing Date:** {sel_date.strftime('%A, %d %b %Y')}"
        df_view = df_processed[df_processed['shot_time'].dt.date == sel_date]
        sub_header = f"Summary for {sel_date.strftime('%d %b %Y')}"
    elif "Weekly" in analysis_level:
        col_w_sel, col_w_info = st.columns([1, 2])
        with col_w_sel:
            df_processed['week_lbl'] = df_processed['shot_time'].dt.to_period('W')
            weeks = sorted(df_processed['week_lbl'].unique())
            sel_week = st.selectbox("Select Week", weeks, index=len(weeks)-1, key=f"cr_week_select{key_suffix}")
        with col_w_info:
            info_placeholder = st.empty()
            info_base_text = f"**Viewing Period:** {sel_week}"
        df_view = df_processed[df_processed['week_lbl'] == sel_week]
        sub_header = f"Summary for {sel_week}"
    elif "Monthly" in analysis_level:
        col_m_sel, col_m_info = st.columns([1, 2])
        with col_m_sel:
            df_processed['month_lbl'] = df_processed['shot_time'].dt.to_period('M')
            months = sorted(df_processed['month_lbl'].unique())
            sel_month = st.selectbox("Select Month", months, index=len(months)-1, format_func=lambda x: x.strftime('%B %Y'), key=f"cr_month_select{key_suffix}")
        with col_m_info:
            info_placeholder = st.empty()
            info_base_text = f"**Viewing Period:** {sel_month.strftime('%B %Y')}"
        df_view = df_processed[df_processed['month_lbl'] == sel_month]
        sub_header = f"Summary for {sel_month.strftime('%B %Y')}"
    else:
        d_min = df_processed['shot_time'].min().date(); d_max = df_processed['shot_time'].max().date()
        col_c_sel, col_c_info = st.columns([1, 2])
        with col_c_sel:
            c1, c2 = st.columns(2)
            s_date = c1.date_input("Start Date", d_min, key=f"d1{key_suffix}")
            e_date = c2.date_input("End Date", d_max, key=f"d2{key_suffix}")
        with col_c_info:
            info_placeholder = st.empty()
            info_base_text = (
                f"**Viewing Period:** {s_date.strftime('%d %b %Y')} to {e_date.strftime('%d %b %Y')}"
                if s_date and e_date else "**Viewing Period:** Select dates"
            )
        if s_date and e_date:
            df_view = df_processed[(df_processed['shot_time'].dt.date >= s_date) & (df_processed['shot_time'].dt.date <= e_date)]
            sub_header = f"Summary for {s_date.strftime('%d %b %Y')} to {e_date.strftime('%d %b %Y')}"

    if df_view.empty: st.warning("No data found."); return

    # Populate viewing period info (run count needs df_view)
    run_count = df_view['run_id'].nunique() if 'run_id' in df_view.columns else 0
    if info_placeholder and info_base_text:
        info_placeholder.info(f"{info_base_text}\n\n**Number of Production Runs:** {run_count}")

    # --- Calculations ---
    # Shot metrics from df_view (correct — these are period-scoped).
    # Run duration/output from df_processed grouped by run_id, filtered to runs
    # whose start falls within the period — avoids boundary-cut truncation.

    total_shots  = len(df_view)
    normal_shots = int((df_view['stop_flag'] == 0).sum())
    stop_events  = int(df_view['stop_event'].sum()) if 'stop_event' in df_view.columns else 0

    prod_df   = df_view[df_view['stop_flag'] == 0]
    prod_time = float(prod_df['actual_ct'].sum())

    # Run duration — loop over df_view (period slice) exactly as RR does in
    # _run_metrics_from_processed. Uses the last shot within the period,
    # not the full run's last shot.
    total_runtime = 0.0
    opt_output    = 0.0
    for _, run_df in df_view.groupby('run_id'):
        if run_df.empty: continue
        start   = run_df['shot_time'].min()
        end     = run_df['shot_time'].max()
        last_ct = float(run_df.iloc[-1]['actual_ct'])
        dur     = (end - start).total_seconds() + last_ct
        total_runtime += dur
        r_ct  = float(run_df['approved_ct_for_run'].iloc[0]) if 'approved_ct_for_run' in run_df.columns else float(run_df['approved_ct'].iloc[0])
        r_cav = float(run_df['working_cavities'].max()) if 'working_cavities' in run_df.columns else 1.0
        if r_ct > 0:
            opt_output += (dur / r_ct) * r_cav

    downtime = max(0, total_runtime - prod_time)

    act_output = float(prod_df['working_cavities'].sum()) if 'working_cavities' in prod_df.columns else float(normal_shots)
    tgt_output = opt_output * (config.get('target_output_perc', 100.0) / 100.0)

    cap_gain_fast = cap_loss_slow = 0.0
    if not prod_df.empty and 'approved_ct_for_run' in prod_df.columns:
        parts_delta = (
            (prod_df['approved_ct_for_run'] - prod_df['actual_ct'])
            / prod_df['approved_ct_for_run'].replace(0, np.nan)
        ) * (prod_df['working_cavities'] if 'working_cavities' in prod_df.columns else 1)
        cap_gain_fast = float(parts_delta[parts_delta > 0].sum())
        cap_loss_slow = float(abs(parts_delta[parts_delta < 0].sum()))

    true_loss          = opt_output - act_output
    loss_downtime      = true_loss - (cap_loss_slow - cap_gain_fast)
    total_loss_parts   = true_loss
    total_cap_loss_sec = downtime + cap_loss_slow

    eff_rate   = (normal_shots / total_shots * 100) if total_shots > 0 else 0
    stab_index = (prod_time / total_runtime * 100)  if total_runtime > 0 else 0
    mttr_min   = (downtime / 60 / stop_events)      if stop_events > 0 else 0
    mtbf_min   = (prod_time / 60 / stop_events)     if stop_events > 0 else (prod_time / 60)

    run_breakdown_df = cr_CG_utils.calculate_run_summaries(df_view, config)
    if run_breakdown_df.empty: st.warning("No runs found."); return

    if dashboard_mode == "Target":
        benchmark_output = tgt_output
        net_diff = act_output - tgt_output
    else:
        benchmark_output = opt_output
        net_diff = act_output - opt_output

    res = {
        'total_runtime_sec': total_runtime, 'production_time_sec': prod_time, 'downtime_sec': downtime,
        'total_capacity_loss_sec': total_cap_loss_sec, 'efficiency_rate': eff_rate, 'stability_index': stab_index,
        'mttr_min': mttr_min, 'mtbf_min': mtbf_min, 'optimal_output_parts': opt_output,
        'target_output_parts': tgt_output, 'actual_output_parts': act_output, 'total_shots': total_shots,
        'normal_shots': normal_shots, 'stop_events': stop_events, 'capacity_loss_downtime_parts': loss_downtime,
        'capacity_loss_slow_parts': cap_loss_slow, 'capacity_gain_fast_parts': cap_gain_fast,
        'total_capacity_loss_parts': total_loss_parts, 'processed_df': df_view
    }

    # --- Header & Export ---
    c_head, c_btn = st.columns([3, 1])
    with c_head: st.subheader(sub_header)
    with c_btn:
        st.download_button(
            label="📥 Export Capacity Report",
            data=cr_CG_utils.prepare_and_generate_capacity_excel(df_view, config),
            file_name=f"Capacity_Report_{datetime.now():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key=f"dl_btn_{key_suffix}"
        )

    # ==========================================================================
    # --- KPI SECTION ---
    # ==========================================================================

    _PC = cr_CG_utils.PASTEL_COLORS
    _fmt_dhm = cr_CG_utils.format_seconds_to_dhm

    # --- Row 1: Capacity output — the primary objective, shown first ---
    with st.container(border=True):
        c1, c2, c3, c4, c5 = st.columns(5)
        pct_normal  = (normal_shots / total_shots * 100) if total_shots > 0 else 0
        pct_achieve = (act_output / benchmark_output * 100) if benchmark_output > 0 else 0
        pct_diff    = (net_diff / benchmark_output * 100) if benchmark_output > 0 else 0
        chip_col    = _PC['green'] if net_diff >= 0 else _PC['red']
        net_lbl     = "Net Gain (parts)" if net_diff >= 0 else "Net Loss (parts)"

        def _big(label, value, chip_html=""):
            st.markdown(
                f'<div style="padding:4px 0;">'
                f'<div style="font-size:0.85rem;color:var(--color-text-secondary);">{label}</div>'
                f'<div style="font-size:2rem;font-weight:500;color:var(--color-text-primary);line-height:1.2;">{value}</div>'
                f'{chip_html}</div>', unsafe_allow_html=True)

        with c1: _big("Total Shots", f"{total_shots:,.0f}")
        with c2: _big("Normal Shots", f"{normal_shots:,.0f}",
            f'<span style="background:{_PC["green"]};color:#0E1117;padding:2px 8px;border-radius:10px;font-size:0.8rem;font-weight:bold;">{pct_normal:.1f}% of Total</span>')
        with c3: _big(f"{dashboard_mode} Output (parts)", f"{benchmark_output:,.0f}")
        with c4: _big("Actual Output (parts)", f"{act_output:,.0f}",
            f'<span style="background:{_PC["blue"]};color:#0E1117;padding:2px 8px;border-radius:10px;font-size:0.8rem;font-weight:bold;">{pct_achieve:.1f}% of {dashboard_mode}</span>')
        with c5: _big(net_lbl, f"{abs(net_diff):,.0f}",
            f'<span style="background:{chip_col};color:#0E1117;padding:2px 8px;border-radius:10px;font-size:0.8rem;font-weight:bold;">{pct_diff:+.1f}% of {dashboard_mode}</span>')

    # --- Row 2: Time KPI cards ---
    with st.container(border=True):
        col1, col2, col3, col4, col5 = st.columns(5)
        prod_p = (prod_time / total_runtime * 100) if total_runtime > 0 else 0
        down_p = (downtime / total_runtime * 100)  if total_runtime > 0 else 0
        with col1:
            st.metric("Run Rate MTTR", f"{mttr_min:.1f} min",
                      help="Total Downtime / Stop Events")
        with col2:
            st.metric("Run Rate MTBF", f"{mtbf_min:.1f} min",
                      help="Production Time / Stop Events")
        with col3:
            st.metric("Total Run Duration", _fmt_dhm(total_runtime))
        with col4:
            st.metric("Production Time", _fmt_dhm(prod_time))
            st.markdown(
                f'<span style="background-color:{_PC["green"]};color:#0E1117;'
                f'padding:3px 8px;border-radius:10px;font-size:0.8rem;font-weight:bold;">'
                f'{prod_p:.1f}%</span>', unsafe_allow_html=True)
        with col5:
            st.metric("Run Rate Downtime", _fmt_dhm(downtime))
            st.markdown(
                f'<span style="background-color:{_PC["red"]};color:#0E1117;'
                f'padding:3px 8px;border-radius:10px;font-size:0.8rem;font-weight:bold;">'
                f'{down_p:.1f}%</span>', unsafe_allow_html=True)

    # Gauges — use RR's needle-style create_gauge (same as RR dashboard)
    c_g1, c_g2 = st.columns(2)
    with c_g1:
        with st.container(border=True):
            st.plotly_chart(
                cr_CG_utils.create_gauge(eff_rate, "Run Rate Shot Efficiency (%)"),
                use_container_width=True, key=f"eff_gauge_{key_suffix}"
            )
            st.markdown(
                f'<div style="text-align:center;font-size:1rem;color:var(--text-color,#555);margin-top:4px;">'
                f'{normal_shots:,.0f} Normal &nbsp;/&nbsp; {total_shots:,.0f} Total Shots</div>',
                unsafe_allow_html=True
            )
    with c_g2:
        with st.container(border=True):
            steps = [
                {'range': [0, 50],  'color': _PC['red']},
                {'range': [50, 70], 'color': _PC['orange']},
                {'range': [70, 100],'color': _PC['green']},
            ]
            st.plotly_chart(
                cr_CG_utils.create_gauge(stab_index, "Run Rate Time Stability (%)", steps=steps),
                use_container_width=True, key=f"stab_gauge_{key_suffix}"
            )
            st.markdown(
                f'<div style="text-align:center;font-size:1rem;color:var(--text-color,#555);margin-top:4px;">'
                f'{_fmt_dhm(prod_time)} Production &nbsp;/&nbsp; {_fmt_dhm(total_runtime)} Total</div>',
                unsafe_allow_html=True
            )

    with st.container(border=True):
        st.plotly_chart(
            cr_CG_utils.create_stability_driver_bar(mtbf_min, mttr_min, stab_index),
            use_container_width=True, key=f"stab_driver_{key_suffix}"
        )
        with st.expander("🔍 View Correlation Analysis"):
            st.markdown(cr_CG_utils.generate_mttr_mtbf_analysis(run_breakdown_df),
                        unsafe_allow_html=True)

    with st.expander("ℹ️ Metric Definitions"):
        st.markdown(f"""
        ### 1. Run Rate Shot Efficiency (%)
        **Definition:** Normal Shots / Total Shots

        ### 2. Run Rate Time Stability (%)
        **Definition:** Production Time / Total Run Duration

        ### 3. Run Rate MTTR
        **Definition:** Total Downtime / Stop Events

        ### 4. Run Rate MTBF
        **Definition:** Production Time / Stop Events

        ### 5. Capacity Outputs
        - **{dashboard_mode} Output:** {"Run Duration / Approved CT × Cavities" if dashboard_mode == "Optimal" else "Optimal Output × Target %"}
        - **Actual Output:** Sum of working cavities for all normal shots
        - **Net Loss/Gain:** Actual Output vs {dashboard_mode} Output
        """)

    with st.container(border=True):
        _lo_min = run_breakdown_df['mode_lower'].min()
        _lo_max = run_breakdown_df['mode_lower'].max()
        _mc_min = run_breakdown_df['mode_ct'].min()
        _mc_max = run_breakdown_df['mode_ct'].max()
        _up_min = run_breakdown_df['mode_upper'].min()
        _up_max = run_breakdown_df['mode_upper'].max()
        _approved = df_view['approved_ct'].dropna().mean() if 'approved_ct' in df_view.columns else 0
        def _r(a, b): return f"{a:.2f}" if abs(a-b) < 0.005 else f"{a:.2f}–{b:.2f}"
        ct_main, ct_app = st.columns([3, 1])
        with ct_main:
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Lower Limit (sec)", _r(_lo_min, _lo_max))
            with rc2:
                with st.container(border=True):
                    st.metric("Mode CT (sec)", _r(_mc_min, _mc_max))
            rc3.metric("Upper Limit (sec)", _r(_up_min, _up_max))
        with ct_app:
            with st.container(border=True):
                st.metric("Approved CT (sec)", f"{_approved:.2f}")

    st.markdown("---")

    with st.expander("🤖 View Automated Analysis Summary", expanded=True):
        insights = cr_CG_utils.generate_capacity_insights(res, dashboard_mode)
        st.markdown(f"""
        **Overall:** {insights['overall']}

        **Drivers:** {insights['drivers']}

        **Recommendation:** {insights['recommendation']}
        """, unsafe_allow_html=True)
    
    with st.expander("View Detailed Run Breakdown Table", expanded=False):
        d_df = run_breakdown_df.copy()
        d_df = d_df.sort_values('start_time').reset_index(drop=True)
        d_df['RUN ID'] = d_df.index.map(lambda x: f"Run {x+1:03d}")
        d_df["Period"] = d_df.apply(
            lambda r: f"{r['start_time'].strftime('%Y-%m-%d %H:%M')} to {r['end_time'].strftime('%Y-%m-%d %H:%M')}", axis=1
        )
        _raw_total = d_df['total_shots']
        d_df["Total Shots"] = _raw_total.apply(lambda x: f"{x:,}")
        d_df["Normal Shots"] = d_df.apply(
            lambda r: f"{r['normal_shots']:,} ({r['normal_shots'] / _raw_total.loc[r.name] * 100:.1f}%)"
            if _raw_total.loc[r.name] > 0 else "0 (0.0%)", axis=1
        )
        d_df["Stop Events"] = d_df.apply(
            lambda r: f"{r['stop_events']} ({r['stop_events'] / _raw_total.loc[r.name] * 100:.1f}%)"
            if _raw_total.loc[r.name] > 0 else "0 (0.0%)", axis=1
        )
        d_df['Run Rate MTTR (min)'] = (d_df['downtime_sec'] / 60 / d_df['stop_events'].replace(0, 1)).where(d_df['stop_events'] > 0, 0)
        d_df['Run Rate MTBF (min)'] = (d_df['production_time_sec'] / 60 / d_df['stop_events'].replace(0, 1)).where(d_df['stop_events'] > 0, d_df['production_time_sec'] / 60)
        d_df['RR Time Stability (%)'] = (d_df['production_time_sec'] / d_df['total_runtime_sec'] * 100).where(d_df['total_runtime_sec'] > 0, 0)
        d_df["Total Run Duration"] = d_df['total_runtime_sec'].apply(cr_CG_utils.format_seconds_to_dhm)
        d_df["Production Time"] = d_df['production_time_sec'].apply(cr_CG_utils.format_seconds_to_dhm)
        d_df["Run Rate Downtime"] = d_df['downtime_sec'].apply(cr_CG_utils.format_seconds_to_dhm)

        d_df = d_df.rename(columns={
            'tool_ids':                    'Tool(s)',
            'mode_ct':                     'Mode CT (sec)',
            'optimal_output_parts':        'Optimal Output (parts)',
            'actual_output_parts':         'Actual Output (parts)',
            'capacity_loss_downtime_parts':'Loss: RR Downtime (parts)',
            'capacity_loss_slow_parts':    'Loss: Slow Cycles (parts)',
            'capacity_gain_fast_parts':    'Gain: Fast Cycles (parts)',
            'total_capacity_loss_parts':   'Total Net Loss (parts)',
        })

        cols_to_show = [
            'RUN ID', 'Tool(s)', 'Period', 'Total Shots', 'Normal Shots', 'Stop Events',
            'Mode CT (sec)', 'Optimal Output (parts)', 'Actual Output (parts)',
            'Loss: RR Downtime (parts)', 'Loss: Slow Cycles (parts)',
            'Gain: Fast Cycles (parts)', 'Total Net Loss (parts)',
            'Total Run Duration', 'Production Time', 'Run Rate Downtime',
            'Run Rate MTTR (min)', 'Run Rate MTBF (min)', 'RR Time Stability (%)'
        ]
        cols_to_show = [c for c in cols_to_show if c in d_df.columns]

        fmt = {c: '{:.2f}' for c in [
            'Mode CT (sec)', 'Run Rate MTTR (min)', 'Run Rate MTBF (min)', 'RR Time Stability (%)'
        ] if c in d_df.columns}
        fmt.update({c: '{:,.0f}' for c in [
            'Optimal Output (parts)', 'Actual Output (parts)',
            'Loss: RR Downtime (parts)', 'Loss: Slow Cycles (parts)',
            'Gain: Fast Cycles (parts)', 'Total Net Loss (parts)'
        ] if c in d_df.columns})

        st.dataframe(d_df[cols_to_show].style.format(fmt, na_rep='—'),
                     use_container_width=True, hide_index=True)


    waterfall_mode = "Standard (Net)"
    is_allocated = False
    if dashboard_mode == "Target":
        waterfall_mode = st.selectbox("Waterfall View Mode", ["Standard (Net)", "Allocated Impact"], key=f"wf_mode_{key_suffix}")
        if waterfall_mode == "Allocated Impact":
            is_allocated = True

    c_chart, c_details = st.columns([1.5, 1]) 
    gap_tgt = max(0, tgt_output - act_output)
    
    with c_chart:
        if is_allocated and dashboard_mode == "Target":
             net_loss_optimal = loss_downtime + (loss_slow - gain_fast)
             alloc_dt = 0; alloc_slow = 0; alloc_fast = 0
             if gap_tgt > 0 and net_loss_optimal > 0:
                 scale_factor = gap_tgt / net_loss_optimal
                 alloc_dt = loss_downtime * scale_factor
                 alloc_slow = loss_slow * scale_factor
                 alloc_fast = gain_fast * scale_factor
             
             y_dt = -alloc_dt
             y_slow = -alloc_slow
             y_fast = alloc_fast
             
             fig_wf = go.Figure(go.Waterfall(
                name="Allocated Impact", orientation="v",
                measure=["absolute", "relative", "relative", "relative", "total"],
                x=["Target Output", "Allocated: Downtime", "Allocated: Slow Cycles", "Allocated: Fast Cycles", "Actual Output"],
                y=[tgt_output, y_dt, y_slow, y_fast, act_output],
                text=[f"{tgt_output:,.0f}", f"{abs(y_dt):,.0f}", f"{abs(y_slow):,.0f}", f"+{abs(y_fast):,.0f}", f"{act_output:,.0f}"],
                textposition="outside",
                connector={"line": {"color": "rgb(63, 63, 63)"}},
                decreasing={"marker": {"color": cr_CG_utils.PASTEL_COLORS['red']}},
                increasing={"marker": {"color": cr_CG_utils.PASTEL_COLORS['green']}},
                totals={"marker": {"color": cr_CG_utils.PASTEL_COLORS['blue']}}
             ))
             fig_wf.update_layout(title="Allocated Capacity Loss (Target -> Actual)", showlegend=False, height=450)
             st.plotly_chart(fig_wf, use_container_width=True, key=f"waterfall_chart_{key_suffix}")
        else:
             st.plotly_chart(cr_CG_utils.plot_waterfall(res, benchmark_mode), use_container_width=True, key=f"waterfall_chart_{key_suffix}")
    
    with c_details:
        with st.container(border=True):
            if is_allocated:
                st.markdown(f"**Total Gap to Target**")
                color_hex = "#ff6961" if gap_tgt > 0 else "#77dd77" 
                st.markdown(f"<h2 style='color:{color_hex}; margin:0;'>-{gap_tgt:,.0f} parts</h2>", unsafe_allow_html=True)
                st.caption("Gap allocated by root cause ratios")
            else:
                st.markdown(f"**Total Net Impact (vs {dashboard_mode})**")
                color_hex = "#77dd77" if net_diff >= 0 else "#ff6961"
                st.markdown(f"<h2 style='color:{color_hex}; margin:0;'>{net_diff:+,.0f} parts</h2>", unsafe_allow_html=True)
                if dashboard_mode == "Optimal":
                    st.caption(f"Net Time Lost: {cr_CG_utils.format_seconds_to_dhm(res['total_capacity_loss_sec'])}")
        
        if is_allocated:
            net_loss_optimal = loss_downtime + (loss_slow - gain_fast)
            scale_factor = gap_tgt / net_loss_optimal if (gap_tgt > 0 and net_loss_optimal > 0) else 0
            
            a_dt = loss_downtime * scale_factor
            a_sl = loss_slow * scale_factor
            a_fg = gain_fast * scale_factor
            
            breakdown_data = [
                {"Metric": "Target Output", "Parts": tgt_output},
                {"Metric": "Actual Output", "Parts": act_output},
                {"Metric": "Total Gap", "Parts": gap_tgt},
                {"Metric": "--- Allocation ---", "Parts": 0},
                {"Metric": "Allocated Impact: Downtime", "Parts": a_dt},
                {"Metric": "Allocated Impact: Slow Cycles", "Parts": a_sl},
                {"Metric": "Allocated Impact: Fast Cycles (Gain)", "Parts": a_fg},
            ]
        else:
            net_cycle_loss = res['capacity_loss_slow_parts'] - res['capacity_gain_fast_parts']
            breakdown_data = [
                {"Metric": "Loss (RR Downtime)", "Parts": res['capacity_loss_downtime_parts']},
                {"Metric": "Net Loss (Cycle Time)", "Parts": net_cycle_loss},
                {"Metric": "└ Loss (Slow Cycles)", "Parts": res['capacity_loss_slow_parts']},
                {"Metric": "└ Gain (Fast Cycles)", "Parts": res['capacity_gain_fast_parts']},
            ]

        df_breakdown = pd.DataFrame(breakdown_data)
        
        def style_breakdown(row):
            styles = [''] * len(row)
            if "Allocated" in row['Metric']:
                 styles[0] = 'font-style: italic;'
                 if "Gain" in row['Metric'] or "Fast" in row['Metric']:
                     if row['Parts'] > 0: styles[1] = 'color: #77dd77;' 
                 elif row['Parts'] > 0: 
                     styles[1] = 'color: #ff6961;' 
            
            if row['Metric'] == "Total Gap":
                 styles[1] = 'color: #ff6961; font-weight: bold;'
            
            if row['Metric'] == "Loss (RR Downtime)":
                styles[1] = 'color: #ff6961; font-weight: bold;'
            elif row['Metric'] == "Net Loss (Cycle Time)":
                color = '#ff6961' if row['Parts'] > 0 else '#77dd77'
                styles[1] = f'color: {color}; font-weight: bold;'
            elif "Gain" in row['Metric']:
                styles[1] = 'color: #77dd77;'
            elif "Loss" in row['Metric'] and "Net" not in row['Metric']:
                styles[1] = 'color: #ff6961;'
            return styles

        st.dataframe(
            df_breakdown.style.apply(style_breakdown, axis=1).format({"Parts": "{:,.0f}"}), 
            use_container_width=True, 
            hide_index=True
        )

    st.markdown("---")

    st.subheader("Performance Breakdown (Stacked Trend)")
    st.info("View how capacity and losses were distributed over the selected period.")
    
    chart_freq = st.selectbox("Chart Aggregation", ["Daily", "Weekly", "Run"], key=f"chart_agg_{key_suffix}")
    freq_map = {"Daily": "Daily", "Weekly": "Weekly", "Run": "by Run"}
    
    agg_chart_df = cr_CG_utils.get_aggregated_data(df_view, freq_map[chart_freq], config)
    if not agg_chart_df.empty:
        st.plotly_chart(
            cr_CG_utils.plot_performance_breakdown(agg_chart_df, 'Period', benchmark_mode), 
            use_container_width=True,
            key=f"perf_breakdown_{key_suffix}"
        )
    else:
        st.warning("Not enough data to generate breakdown chart.")

    if not agg_chart_df.empty:
        st.subheader(f"Production Totals Report ({chart_freq})")
        
        totals_df = agg_chart_df.copy()
        if 'Production Time Sec' in totals_df and 'Run Time Sec' in totals_df:
            totals_df['Actual Production Time'] = totals_df.apply(
                lambda r: f"{cr_CG_utils.format_seconds_to_dhm(r['Production Time Sec'])} ({r['Production Time Sec']/r['Run Time Sec']:.1%})" if r['Run Time Sec'] > 0 else "0m (0.0%)", 
                axis=1
            )
        else:
            totals_df['Actual Production Time'] = "N/A"

        if 'Normal Shots' in totals_df and 'Total Shots' in totals_df:
            totals_df['Production Shots (Pct)'] = totals_df.apply(
                lambda r: f"{r['Normal Shots']:,.0f} ({r['Normal Shots']/r['Total Shots']:.1%})" if r['Total Shots'] > 0 else "0 (0.0%)", 
                axis=1
            )
        else:
            totals_df['Production Shots (Pct)'] = "N/A"
        
        totals_table = pd.DataFrame()
        totals_table['Period'] = totals_df['Period']
        totals_table['Total Run Duration'] = totals_df['Run Time'] + " (" + totals_df['Run Time Sec'].apply(lambda x: f"{x:.0f}s") + ")"
        totals_table['Actual Production Time'] = totals_df['Actual Production Time']
        totals_table['Total Shots'] = totals_df['Total Shots'].map('{:,.0f}'.format)
        totals_table['Production Shots'] = totals_df['Production Shots (Pct)']
        totals_table['Downtime Shots'] = totals_df['Downtime Shots'].map('{:,.0f}'.format)
        
        st.dataframe(totals_table, use_container_width=True, hide_index=True)

        st.subheader(f"Capacity Loss & Gain Report — vs Optimal Output (parts) ({chart_freq})")
        
        lg_table_opt = pd.DataFrame()
        lg_table_opt['Period'] = totals_df['Period']
        lg_table_opt['Optimal Output (parts)'] = totals_df['Optimal Output'].map('{:,.2f}'.format)
        lg_table_opt['Actual Output (parts)'] = totals_df['Actual Output'].map('{:,.2f}'.format)
        lg_table_opt['Loss: RR Downtime (parts)'] = totals_df['Downtime Loss'].map('{:,.2f}'.format)
        lg_table_opt['Loss: Slow Cycles (parts)'] = totals_df['Slow Loss'].map('{:,.2f}'.format)
        lg_table_opt['Gain: Fast Cycles (parts)'] = totals_df['Fast Gain'].map('{:,.2f}'.format)
        lg_table_opt['Total Net Loss (parts)'] = totals_df['Total Loss'].map('{:,.2f}'.format)

        def style_loss_gain(col):
            col_name = col.name
            if 'Loss' in col_name and 'Net' not in col_name:
                return ['color: #ff6961'] * len(col)
            if 'Gain' in col_name:
                return ['color: #77dd77'] * len(col)
            if 'Total Net Loss' in col_name:
                return ['font-weight: bold; color: #ff6961'] * len(col)
            return [''] * len(col)

        st.dataframe(lg_table_opt.style.apply(style_loss_gain, axis=0), use_container_width=True, hide_index=True)

        if dashboard_mode == "Target" and 'Target Output' in totals_df.columns:
            st.subheader(f"Capacity Loss & Gain Report — vs Target Output (parts) [Allocated] ({chart_freq})")
            
            tgt_table = pd.DataFrame()
            tgt_table['Period'] = totals_df['Period']
            tgt_table['Target Output (parts)'] = totals_df['Target Output'].map('{:,.2f}'.format)
            tgt_table['Actual Output (parts)'] = totals_df['Actual Output'].map('{:,.2f}'.format)
            
            def calc_alloc(row):
                gap = max(0, row['Target Output'] - row['Actual Output'])
                net_loss_opt = row['Downtime Loss'] + (row['Slow Loss'] - row['Fast Gain'])
                scale = gap / net_loss_opt if (gap > 0 and net_loss_opt > 0) else 0
                return pd.Series([gap, row['Downtime Loss'] * scale,
                                  row['Slow Loss'] * scale, row['Fast Gain'] * scale])

            alloc_res = totals_df.apply(calc_alloc, axis=1)
            alloc_res.columns = ['Gap', 'Alloc_DT', 'Alloc_Slow', 'Alloc_Fast']

            tgt_table['Gap to Target (parts)'] = alloc_res['Gap'].map('{:,.2f}'.format)
            tgt_table['Allocated: RR Downtime (parts)'] = alloc_res['Alloc_DT'].map('{:,.2f}'.format)
            tgt_table['Allocated: Slow Cycles (parts)'] = alloc_res['Alloc_Slow'].map('{:,.2f}'.format)
            tgt_table['Allocated: Fast Cycles Gain (parts)'] = alloc_res['Alloc_Fast'].map('{:,.2f}'.format)
            
            def style_target_alloc(col):
                if 'Gap' in col.name or 'Allocated' in col.name:
                    if 'Gain' in col.name or 'Fast' in col.name:
                        return ['color: #77dd77'] * len(col) 
                    return ['color: #ff6961'] * len(col) 
                return [''] * len(col)

            st.dataframe(tgt_table.style.apply(style_target_alloc, axis=0), use_container_width=True, hide_index=True)

    st.markdown("---")

    st.subheader("Shot Analysis")
    _mode_ct_val = run_breakdown_df['mode_ct'].mean() if not run_breakdown_df.empty else None
    _mode_lo_val = run_breakdown_df['mode_lower'].min() if not run_breakdown_df.empty else None
    _mode_hi_val = run_breakdown_df['mode_upper'].max() if not run_breakdown_df.empty else None
    _shot_fig = cr_CG_utils.plot_shot_bar_chart(
        res['processed_df'],
        mode_lower=_mode_lo_val, mode_upper=_mode_hi_val, mode_ct=_mode_ct_val
    )
    if _shot_fig is not None:
        st.plotly_chart(_shot_fig, use_container_width=True, key=f"shot_bar_{key_suffix}")
    
    with st.expander("View Shot Data Table", expanded=False):
        _df_src = res['processed_df']
        _shot_cols, _shot_names = [], {}

        for _col, _lbl in [('tool_id', 'Tooling ID'), ('supplier_id', 'Supplier'),
                            ('tooling_type', 'Tooling Type'), ('part_id', 'Part(s)')]:
            if _col in _df_src.columns:
                _shot_cols.append(_col)
                _shot_names[_col] = _lbl

        if 'run_id' in _df_src.columns:
            _shot_cols.append('run_id')
            _shot_names['run_id'] = 'Run ID'

        _shot_cols  += ['shot_time', 'mode_ct', 'actual_ct', 'adj_ct_sec', 'approved_ct',
                        'time_diff_sec', 'stop_flag', 'stop_event']
        _shot_names.update({
            'shot_time':     'Date / Time',
            'mode_ct':       'Mode CT (sec)',
            'actual_ct':     'Actual CT (sec)',
            'adj_ct_sec':    'Adjusted CT (sec)',
            'approved_ct':   'Approved CT (sec)',
            'time_diff_sec': 'Time Difference (sec)',
            'stop_flag':     'Stop Flag',
            'stop_event':    'Stop Event',
        })

        _existing = [c for c in _shot_cols if c in _df_src.columns]
        df_shot_data = _df_src[_existing].copy()
        df_shot_data.rename(columns=_shot_names, inplace=True)

        if 'Date / Time' in df_shot_data.columns:
            df_shot_data['Date / Time'] = pd.to_datetime(
                df_shot_data['Date / Time']
            ).dt.strftime('%Y-%m-%d %H:%M:%S.%f').str[:-3]

        _fmt_shot = {c: '{:.2f}' for c in [
            'Actual CT (sec)', 'Adjusted CT (sec)', 'Approved CT (sec)',
            'Mode CT (sec)', 'Time Difference (sec)'
        ] if c in df_shot_data.columns}

        st.dataframe(df_shot_data.style.format(_fmt_shot, na_rep='—'), use_container_width=True)
        st.download_button(
            "📥 Download Shot Data (CSV)",
            data=df_shot_data.to_csv(index=False),
            file_name=f"shot_data_{datetime.now():%Y%m%d}.csv",
            mime="text/csv",
            key=f"cr_shot_csv_{key_suffix}"
        )

# ==============================================================================
# --- MAIN ENTRY POINT ---
# ==============================================================================

APP_VERSION = "v5.0"

def main():
    st.set_page_config(layout="wide", page_title=f"Capacity Risk Dashboard ({APP_VERSION})")

    # ── Sidebar version badge ────────────────────────────────────────────────
    st.sidebar.markdown(
        f"<div style='text-align:left;padding:4px 0 10px 0;margin:0;"
        f"font-size:0.78rem;color:var(--text-color);opacity:0.55;"
        f"display:block;width:100%;'>"
        f"Capacity Risk &nbsp;|&nbsp; <strong>{APP_VERSION}</strong></div>",
        unsafe_allow_html=True
    )

    # ── File Upload ──────────────────────────────────────────────────────────
    st.sidebar.title("File Upload")
    files = st.sidebar.file_uploader(
        "Upload Production Data (Excel / CSV)",
        accept_multiple_files=True, type=['xlsx', 'xls', 'csv'],
        key="cr_file_uploader"
    )
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Machine Fit (Optional)")
    tmd_log_file = st.sidebar.file_uploader(
        "TMD Log (Excel)", type=['xlsx', 'xls'], key="cr_tmd_log",
        help="Upload tmd_log.xlsx to derive machine-tool sessions and enable the Machine Fit tab."
    )
    machine_master_file = st.sidebar.file_uploader(
        "Machine Master (Excel)", type=['xlsx', 'xls'], key="cr_machine_master",
        help="Upload machines.xlsx to enrich the Machine Fit tab with maker, tonnage etc."
    )
    tools_ref_file = st.sidebar.file_uploader(
        "Tools Reference (Excel)", type=['xlsx', 'xls'], key="cr_tools_ref",
        help="Upload tools_reference.xlsx to enable copy group detection."
    )

    st.sidebar.markdown("---")
    st.sidebar.markdown("### Shift Configuration")
    n_shifts = st.sidebar.selectbox("Number of Shifts", [1, 2, 3], index=2, key="shift_count")
    shift_start_hr = st.sidebar.number_input("First Shift Start (24h)", 0, 23, 6, key="shift_start")
    max_hours = st.sidebar.number_input("Max Working Hours / Shift", 4, 12, 8, key="shift_max_hrs")

    # Build shift config list: [(name, start_hr, end_hr), ...]
    shift_hrs = max_hours
    shift_config = []
    for i in range(n_shifts):
        s = (shift_start_hr + i * shift_hrs) % 24
        e = (s + shift_hrs) % 24
        names = ["Shift 1", "Shift 2", "Shift 3"]
        shift_config.append((names[i], s, e))
    # Pass to session state so render function can access
    st.session_state['shift_config'] = shift_config

    if not files:
        st.info("👈 Upload one or more production data files to begin.")
        st.stop()

    df_all = cr_CG_utils.load_all_data_cr(files)
    if df_all.empty:
        st.error("No valid production data found. Check file format.")
        st.stop()

    machine_master = pd.DataFrame()
    if machine_master_file:
        try:
            machine_master = pd.read_excel(machine_master_file)
            machine_master.columns = [c.strip() for c in machine_master.columns]
        except Exception:
            st.sidebar.warning("Could not load machine master file.")

    tools_ref = pd.DataFrame()
    if tools_ref_file:
        try:
            tools_ref = pd.read_excel(tools_ref_file)
        except Exception:
            st.sidebar.warning("Could not load tools reference file.")

    if tmd_log_file:
        df_tmd = cr_CG_utils.load_tmd_log(tmd_log_file)
        if not df_tmd.empty:
            df_all = cr_CG_utils.assign_machine_from_tmd(
                df_all, df_tmd,
                shift_config=st.session_state.get('shift_config')
            )
            matched_pct = df_all['machine_id'].notna().mean() * 100
            st.sidebar.success(f"TMD log loaded — {matched_pct:.0f}% of shots matched to a machine session.")
        else:
            st.sidebar.warning("TMD log could not be parsed. Check column names.")

    # ── Sidebar: Global Filters (aligned to RR) ──────────────────────────────
    # Date Range → Project → Material → Part → Supplier → Plant → Tooling Type
    # Empty selection = show all. Only render filters where data exists.

    def get_options_multi(df, col):
        if col not in df.columns:
            return []
        raw = sorted(set(
            str(x).strip() for x in df[col].unique()
            if str(x).strip().lower() not in ["nan", "none", "", "nat", "unknown"]
        ))
        return raw

    def apply_filter(df, col, sel):
        if not sel or col not in df.columns:
            return df
        return df[df[col].astype(str).isin(sel)]

    st.sidebar.markdown("### Global Filters")

    _data_min = df_all['shot_time'].min().date() if not df_all.empty else datetime.now().date()
    _data_max = df_all['shot_time'].max().date() if not df_all.empty else datetime.now().date()
    _range = st.sidebar.date_input(
        "Date Range", value=[_data_min, _data_max],
        min_value=_data_min, max_value=_data_max,
        key="cr_global_date_range"
    )
    if isinstance(_range, (list, tuple)) and len(_range) == 2:
        start_d, end_d = _range
        df_all = df_all[
            (df_all['shot_time'].dt.date >= start_d) &
            (df_all['shot_time'].dt.date <= end_d)
        ]
    else:
        st.sidebar.warning("Please select both a start and end date.")
        st.stop()

    if df_all.empty:
        st.sidebar.warning("No data for the selected date range.")
        st.stop()

    opts_proj = get_options_multi(df_all, 'project_id')
    if opts_proj:
        sel_proj = st.sidebar.multiselect("Project", opts_proj, default=[], key="cr_f_project")
        df_f1 = apply_filter(df_all, 'project_id', sel_proj)
    else:
        df_f1 = df_all

    opts_mat = get_options_multi(df_f1, 'material')
    if opts_mat:
        sel_mat = st.sidebar.multiselect("Material", opts_mat, default=[], key="cr_f_material")
        df_f2 = apply_filter(df_f1, 'material', sel_mat)
    else:
        df_f2 = df_f1

    opts_part = get_options_multi(df_f2, 'part_id')
    if opts_part:
        sel_part = st.sidebar.multiselect("Part", opts_part, default=[], key="cr_f_part")
        df_f3 = apply_filter(df_f2, 'part_id', sel_part)
    else:
        df_f3 = df_f2

    opts_sup = get_options_multi(df_f3, 'supplier_id')
    if opts_sup:
        sel_sup = st.sidebar.multiselect("Supplier", opts_sup, default=[], key="cr_f_supplier")
        df_f4 = apply_filter(df_f3, 'supplier_id', sel_sup)
    else:
        df_f4 = df_f3

    opts_plt = get_options_multi(df_f4, 'plant_id')
    if opts_plt:
        sel_plt = st.sidebar.multiselect("Plant", opts_plt, default=[], key="cr_f_plant")
        df_f5 = apply_filter(df_f4, 'plant_id', sel_plt)
    else:
        df_f5 = df_f4

    opts_tt = get_options_multi(df_f5, 'tooling_type')
    if opts_tt:
        sel_tt = st.sidebar.multiselect("Tooling Type", opts_tt, default=[], key="cr_f_tooling_type")
        df_filtered = apply_filter(df_f5, 'tooling_type', sel_tt)
    else:
        df_filtered = df_f5

    if df_filtered.empty:
        st.sidebar.warning("No data matches the current filters.")
        st.stop()

    # ── Configure Metrics ────────────────────────────────────────────────────
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Analysis Parameters ⚙️")
    with st.sidebar.expander("Configure Metrics", expanded=True):
        tolerance = st.slider("Tolerance Band", 0.01, 0.50, 0.05, 0.01, key="cr_tolerance")
        downtime_gap_tolerance = st.slider("Downtime Gap (sec)", 0.0, 5.0, 2.0, 0.5, key="cr_downtime_gap")
        run_interval_hours = st.slider("Run Interval (hours)", 1, 24, 8, 1, key="cr_run_interval")
        enable_min_shots = st.checkbox("Filter Small Production Runs", value=False, key="cr_filter_enable")
        min_shots_filter = (
            st.slider("Min Shots per Run", 1, 500, 10, 1, key="cr_min_shots_global")
            if enable_min_shots else 1
        )

    with st.sidebar.expander("Capacity Settings"):
        target_output_perc = st.slider("Target Output %", 50, 100, 90, key="cr_target_pct")
        default_cavities = st.number_input("Default Cavities", 1, key="cr_default_cav")
        remove_maint = st.checkbox("Remove Maintenance", False, key="cr_remove_maint")

    config = {
        'target_output_perc': target_output_perc,
        'tolerance': tolerance,
        'downtime_gap_tolerance': downtime_gap_tolerance,
        'run_interval_hours': run_interval_hours,
        'default_cavities': default_cavities,
        'remove_maintenance': remove_maint
    }

    # ── Page header ──────────────────────────────────────────────────────────
    st.title("Capacity Risk Dashboard")
    st.markdown("---")

    # ── In-page Tool Selection (aligned to RR) ───────────────────────────────
    tool_ids = sorted([
        str(x) for x in df_filtered['tool_id'].unique()
        if str(x).lower() not in ["nan", "unknown", "none"]
    ])

    if not tool_ids:
        st.warning("No tools found for the current filter scope.")
        st.stop()

    st.markdown("### Tool Selection")
    st.caption(
        f"{len(tool_ids)} tool{'s' if len(tool_ids) != 1 else ''} in current filter scope. "
        "Risk Tower uses all tools. Capacity & Trends tabs use the selection below."
    )

    _prev = st.session_state.get("cr_tool_select_inline", [])
    _valid_prev = [t for t in _prev if t in tool_ids]

    col_sel, col_mode = st.columns([3, 1])
    with col_sel:
        selected_tools = st.multiselect(
            "Select tool(s) for Capacity Dashboard & Trends",
            options=tool_ids,
            default=_valid_prev,
            placeholder="Choose a tool to begin analysis...",
            key="cr_tool_select_inline"
        )
    with col_mode:
        if len(selected_tools) >= 2:
            view_mode = st.radio(
                "View mode", ["Rolled-Up", "Side-by-Side"],
                horizontal=True, key="cr_view_mode_inline"
            )
            if view_mode == "Side-by-Side" and len(selected_tools) > 5:
                st.caption("⚠️ Side-by-Side limited to 5 tools.")
                selected_tools = selected_tools[:5]
        else:
            view_mode = "Rolled-Up"

    st.markdown("---")

    # Process per tool — matches RR which runs RunRateCalculator per tool.
    # Processing all tools together causes run_id numbering to be global,
    # producing different run boundaries vs single-tool processing.
    _processed_parts = []
    for _tid in tool_ids:
        _tdf = df_filtered[df_filtered['tool_id'].astype(str) == _tid]
        if _tdf.empty: continue
        _calc = cr_CG_utils.CapacityRiskCalculator(_tdf, **config)
        _pdf = _calc.results.get('processed_df', pd.DataFrame())
        if not _pdf.empty:
            _processed_parts.append(_pdf)

    if not _processed_parts:
        st.error("No valid data after processing.")
        st.stop()

    df_processed_global = pd.concat(_processed_parts, ignore_index=True)

    df_tool_scope = (df_processed_global[df_processed_global['tool_id'].isin(selected_tools)]
                     if selected_tools else pd.DataFrame())
    tool_name_display = (selected_tools[0] if len(selected_tools) == 1
                         else f"{len(selected_tools)} tools: {', '.join(selected_tools)}"
                         if selected_tools else "")

    def _render_side_by_side(render_fn, *args, **kwargs):
        cols = st.columns(len(selected_tools))
        for i, t_id in enumerate(selected_tools):
            with cols[i]:
                st.markdown(
                    f"<h3 style='text-align:center;color:#3498DB;'>Tool: {t_id}</h3>",
                    unsafe_allow_html=True
                )
                t_df = df_tool_scope[df_tool_scope['tool_id'].astype(str) == t_id]
                if not t_df.empty:
                    render_fn(t_df, *args, key_suffix=f"_{t_id}", **kwargs)
                else:
                    st.warning(f"No data for {t_id}")

    # ── Tabs ─────────────────────────────────────────────────────────────────
    t_risk, t_opt, t_tgt, t_trend, t_mfit = st.tabs([
        "Risk Tower", "Capacity (Optimal)", "Capacity (Target)", "Trends", "🔧 Machine Fit"
    ])
    with t_risk:
        render_risk_tower(df_processed_global, config)

    with t_opt:
        if not selected_tools:
            st.info("👆 Select one or more tools in the Tool Selection above to view capacity analysis.")
        elif view_mode == "Side-by-Side":
            _render_side_by_side(render_dashboard, config, "Optimal", min_shots_filter)
        else:
            if not df_tool_scope.empty:
                render_dashboard(df_tool_scope, config, "Optimal", min_shots_filter)
            else:
                st.warning("No data for selected tools.")

    with t_tgt:
        if not selected_tools:
            st.info("👆 Select one or more tools in the Tool Selection above to view capacity analysis.")
        elif view_mode == "Side-by-Side":
            _render_side_by_side(render_dashboard, config, "Target", min_shots_filter)
        else:
            if not df_tool_scope.empty:
                render_dashboard(df_tool_scope, config, "Target", min_shots_filter)
            else:
                st.warning("No data for selected tools.")

    with t_trend:
        if not selected_tools:
            st.info("👆 Select one or more tools in the Tool Selection above to view trends.")
        elif view_mode == "Side-by-Side":
            _render_side_by_side(render_trends_tab, config)
        else:
            if not df_tool_scope.empty:
                render_trends_tab(df_tool_scope, config)
            else:
                st.warning("No data for selected tools.")

    with t_mfit:
        render_machine_fit_tab(
            df_processed_global, config,
            machine_master=machine_master if not machine_master.empty else None,
            tools_ref=tools_ref if not tools_ref.empty else None,
        )

def _cr_pairing_dialog_body():
    """Shared body for CR analysis popup."""
    tool_id      = st.session_state.get('cr_dialog_tool')
    machine_id   = st.session_state.get('cr_dialog_machine')
    df_proc      = st.session_state.get('cr_dialog_df_proc', pd.DataFrame())
    config       = st.session_state.get('cr_dialog_config', {})
    date_from    = st.session_state.get('cr_dialog_date_from')
    date_to      = st.session_state.get('cr_dialog_date_to')
    shift_filter = st.session_state.get('cr_dialog_shift_filter')

    if not tool_id or df_proc.empty:
        st.warning("No data available for this pairing.")
        return

    # ── Base filter: tool + machine ───────────────────────────────────────────
    mask = df_proc['tool_id'].astype(str) == str(tool_id)
    if machine_id and 'machine_id' in df_proc.columns:
        mask &= df_proc['machine_id'].astype(str) == str(machine_id)
    base_df = df_proc[mask].copy()

    if base_df.empty:
        st.warning("No shot data found for this tool-machine pair.")
        return

    # ── Period filter for comparison ──────────────────────────────────────────
    period_df = base_df.copy()
    period_label = "Full History"

    if date_from and date_to:
        period_df = base_df[
            (base_df['shot_time'] >= pd.Timestamp(date_from)) &
            (base_df['shot_time'] <= pd.Timestamp(date_to))
        ]
        period_label = f"{pd.Timestamp(date_from).strftime('%d %b %Y')} → {pd.Timestamp(date_to).strftime('%d %b %Y')}"

    if shift_filter and 'session_period' in period_df.columns:
        period_df = period_df[period_df['session_period'] == shift_filter]
        period_label += f" · {shift_filter} only"

    if period_df.empty or len(period_df) < 5:
        st.warning(f"Not enough shots in the selected period ({period_label}) to run analysis.")
        return

    st.markdown(f"**Tool:** {tool_id} &nbsp;|&nbsp; **Machine:** {machine_id or 'All'}")
    st.caption(f"Analysis period: **{period_label}**")

    def _run_calc(df):
        if len(df) < 5:
            return None
        try:
            calc = cr_CG_utils.CapacityRiskCalculator(df, **config)
            return calc.results
        except Exception:
            return None

    with st.spinner("Running analysis…"):
        res_period = _run_calc(period_df)
        res_base   = _run_calc(base_df) if (date_from or shift_filter) else None

    if not res_period:
        st.error("Analysis could not be completed for this period.")
        return

    cap_eff = res_period.get('capacity_efficiency', 0) * 100

    # ── KPI strip ─────────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cap Efficiency", f"{cap_eff:.0f}%",
              delta=f"{cap_eff - 100:.0f} pp vs optimal")
    k2.metric("Stability",      f"{res_period.get('stability_index', 0):.0f}%")
    k3.metric("MTBF",           f"{res_period.get('mtbf_min', 0):.0f} min")
    k4.metric("MTTR",           f"{res_period.get('mttr_min', 0):.1f} min")

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Optimal Output",  f"{res_period.get('optimal_output_parts', 0):,.0f} parts")
    s2.metric("Actual Output",   f"{res_period.get('actual_output_parts',  0):,.0f} parts")
    s3.metric("Downtime Loss",   f"{res_period.get('capacity_loss_downtime_parts', 0):,.0f} parts")
    s4.metric("Slow Cycle Loss", f"{res_period.get('capacity_loss_slow_parts', 0):,.0f} parts")

    # ── Comparison table vs full history ──────────────────────────────────────
    if res_base:
        st.markdown("---")
        st.markdown("**Period vs Full History**")
        KPI_MAP = [
            ('capacity_efficiency',          'Cap Efficiency %',  True,  lambda v: f"{v*100:.0f}%"),
            ('stability_index',              'Stability %',       True,  lambda v: f"{v:.0f}%"),
            ('mtbf_min',                     'MTBF (min)',        True,  lambda v: f"{v:.0f}"),
            ('mttr_min',                     'MTTR (min)',        False, lambda v: f"{v:.1f}"),
            ('capacity_loss_downtime_parts', 'Downtime Loss',     False, lambda v: f"{v:,.0f}"),
            ('capacity_loss_slow_parts',     'Slow Cycle Loss',   False, lambda v: f"{v:,.0f}"),
        ]
        cmp_rows = []
        for key, label, higher_better, fmt in KPI_MAP:
            p_val = res_period.get(key, 0)
            b_val = res_base.get(key, 0)
            if key == 'capacity_efficiency':
                delta = (p_val - b_val) * 100
                p_str = fmt(p_val); b_str = fmt(b_val)
            else:
                delta = p_val - b_val
                p_str = fmt(p_val); b_str = fmt(b_val)
            good = (delta > 0 and higher_better) or (delta < 0 and not higher_better)
            cmp_rows.append({
                'KPI': label,
                period_label: p_str,
                'Full History': b_str,
                'Δ': f"{delta:+.1f}",
                '_good': good,
                '_delta': delta,
            })
        cmp_df = pd.DataFrame(cmp_rows)

        def _style_cmp(row):
            styles = ['', '', '', '']
            d = row['_delta']; g = row['_good']
            if abs(d) > 0.5:
                styles[3] = 'color:#4CAF50;font-weight:bold' if g else 'color:#FF5252'
            return styles

        display_cmp = cmp_df[['KPI', period_label, 'Full History', 'Δ']]
        st.dataframe(
            display_cmp.style.apply(
                lambda row: _style_cmp(cmp_df.loc[row.name]),
                axis=1
            ).format(na_rep='—'),
            use_container_width=True, hide_index=True
        )

    st.markdown("---")
    try:
        fig_wf = cr_CG_utils.plot_waterfall(res_period, benchmark_mode="Optimal")
        st.plotly_chart(fig_wf, use_container_width=True, key="dialog_waterfall")
    except Exception:
        st.info("Waterfall chart unavailable for this dataset.")


try:
    @st.dialog("📊 Capacity Risk Analysis — Optimal Pairing", width="large")
    def _cr_pairing_dialog():
        _cr_pairing_dialog_body()
except AttributeError:
    def _cr_pairing_dialog():
        with st.expander("📊 CR Analysis Result", expanded=True):
            _cr_pairing_dialog_body()


def render_machine_fit_tab(df_processed_global, config, machine_master=None, tools_ref=None, key_suffix=''):
    """Renders the Machine Fit Analysis tab — 3 sub-tabs: Overview, Rankings, Deep Dive."""
    st.header("🔧 Machine Fit Analysis")

    if 'machine_id' not in df_processed_global.columns or df_processed_global['machine_id'].isna().all():
        st.warning(
            "⚠️ No machine session data found. Upload a TMD Log in the sidebar to enable this tab."
        )
        return

    with st.spinner("Computing machine-tool metrics…"):
        fit_df = cr_CG_utils.compute_machine_fit_metrics(df_processed_global, config)

    if fit_df.empty:
        st.warning("No machine-tool pair data could be computed.")
        return

    # Build copy group map
    copy_map = {}
    if tools_ref is not None and not tools_ref.empty:
        for _, row in tools_ref.iterrows():
            grp = row.get('copy_group')
            tid = str(row.get('tool_id', ''))
            if tid and pd.notna(grp) and str(grp).strip() not in ('', 'nan', 'None'):
                copy_map[tid] = str(grp)

    C = cr_CG_utils.PASTEL_COLORS

    # ── Sub-tabs ──────────────────────────────────────────────────────────────
    sub_overview, sub_compare, sub_pairings, sub_deepdive = st.tabs([
        "🌐 Overview", "🔄 Press Compare", "💡 Optimal Pairings", "🔬 Part Deep Dive"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — HOLISTIC OVERVIEW
    # ══════════════════════════════════════════════════════════════════════════
    with sub_overview:
        st.subheader("Supply Chain Overview")

        scorecard = cr_CG_utils.compute_supplier_scorecard(fit_df)
        mer_df    = cr_CG_utils.compute_match_efficiency_rate(fit_df, threshold=85.0)

        if scorecard.empty:
            st.warning("No supplier data found.")
        else:
            # ── KPI strip ─────────────────────────────────────────────────────
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Suppliers",        f"{len(scorecard)}")
            k2.metric("Total Tools",      f"{fit_df['tool_id'].nunique()}")
            k3.metric("Total Parts",      f"{fit_df['total_parts'].sum():,.0f}")
            k4.metric("Production Hours", f"{fit_df['production_hrs'].sum():,.0f} h")

            st.markdown("---")

            # ── Metric legend + threshold controls (collapsed) ────────────────
            with st.expander("ℹ️ How to Read These Metrics", expanded=False):
                st.markdown("""
**Tool-Machine Pairing** — A unique combination of one tool and one machine that has been run in production.
Each pairing aggregates all production runs for that combination.

**Match Efficiency Rate** — The % of a supplier's tool-machine pairings that achieved Cap Efficiency ≥ 85%.
An *efficient pairing* is one where the average Cap Efficiency across all its production runs meets or exceeds the 85% threshold.
Colour bands are adjustable below — defaults reflect that hitting ≥ 75% of pairings efficiently is a realistic good benchmark,
and < 50% signals a supplier where the majority of pairings are underperforming.

**Avg Cap Efficiency %** — Average Cap Efficiency across all of a supplier's tool-machine pairings.
Cap Efficiency = Actual Output ÷ Optimal Output (what the machine could have produced running continuously at Approved CT).
Thresholds (95 / 75) are consistent with the rest of the app (Risk Tower uses 95% as the stable threshold).

**RR Time Stability %** — Proportion of total run time spent in active production (not in Run Rate downtime). Same metric as *Run Rate Time Stability* on the Capacity Dashboard.

**MTBF / MTTR** — Mean Time Between Failures / Mean Time To Recover, in minutes. Derived from Run Rate stop events.
                """)

            with st.expander("⚙️ Adjust Colour Thresholds", expanded=False):
                _tc1, _tc2, _tc3, _tc4 = st.columns(4)
                mer_good    = _tc1.number_input("Match Eff — Good ≥ (%)",    0, 100, 75, 5, key=f"mer_good{key_suffix}")
                mer_monitor = _tc2.number_input("Match Eff — Monitor ≥ (%)", 0, 100, 50, 5, key=f"mer_mon{key_suffix}")
                ce_good     = _tc3.number_input("Cap Eff — Good ≥ (%)",      0, 100, 95, 5, key=f"ce_good{key_suffix}")
                ce_monitor  = _tc4.number_input("Cap Eff — Monitor ≥ (%)",   0, 100, 75, 5, key=f"ce_mon{key_suffix}")

            def _html_legend(items):
                """Renders a compact inline colour legend as HTML."""
                parts = [
                    f'<span style="color:{col};font-size:1.1em;">■</span>'
                    f'<span style="font-size:0.82em;margin-left:3px;margin-right:12px;">{lbl}</span>'
                    for lbl, col in items
                ]
                return '<div style="margin-bottom:4px;">' + ''.join(parts) + '</div>'

            c_left, c_right = st.columns(2)
            CHART_H = 300

            # ── Match Efficiency Rate bar ──────────────────────────────────────
            with c_left:
                st.markdown("##### Match Efficiency Rate by Supplier")
                st.caption("% of tool-machine pairings with Cap Efficiency ≥ 85%")
                if not mer_df.empty:
                    mer_colors = [
                        C['green'] if v >= mer_good else (C['orange'] if v >= mer_monitor else C['red'])
                        for v in mer_df['match_efficiency_pct']
                    ]
                    st.markdown(_html_legend([
                        (f'≥ {mer_good}% Good',           C['green']),
                        (f'{mer_monitor}–{mer_good-1}% Monitor', C['orange']),
                        (f'< {mer_monitor}% At Risk',      C['red']),
                    ]), unsafe_allow_html=True)
                    fig_mer = go.Figure(go.Bar(
                        x=mer_df['supplier_id'], y=mer_df['match_efficiency_pct'],
                        marker_color=mer_colors,
                        text=mer_df['match_efficiency_pct'].round(0).astype(int).astype(str)+'%',
                        textposition='outside',
                        customdata=np.stack([mer_df['efficient_sessions'],
                                             mer_df['total_sessions'],
                                             mer_df['machines_used']], axis=-1),
                        hovertemplate=(
                            "<b>%{x}</b><br>"
                            "Match Efficiency: %{y:.0f}%<br>"
                            "Efficient Pairings: %{customdata[0]} / %{customdata[1]}<br>"
                            "Machines: %{customdata[2]}<extra></extra>"
                        ),
                    ))
                    fig_mer.update_layout(
                        yaxis=dict(range=[0, 115], title="Match Efficiency %"),
                        showlegend=False,
                        height=CHART_H, margin=dict(t=10, b=30, l=40, r=10),
                    )
                    st.plotly_chart(fig_mer, use_container_width=True, key=f"ov_mer{key_suffix}")

                    # Table: Supplier | Machines | Tools | Pairings Tested | Efficient Pairings | Match Eff % | Parts | Prod Hrs
                    mer_disp = mer_df[['supplier_id', 'machines_used', 'tools',
                                       'total_sessions', 'efficient_sessions',
                                       'match_efficiency_pct', 'total_parts',
                                       'production_hrs']].rename(columns={
                        'supplier_id':          'Supplier',
                        'machines_used':        'Machines',
                        'tools':                'Tools',
                        'total_sessions':       'Pairings Tested',
                        'efficient_sessions':   'Efficient Pairings',
                        'match_efficiency_pct': 'Match Eff %',
                        'total_parts':          'Parts',
                        'production_hrs':       'Prod Hrs',
                    })
                    def _style_mer(row):
                        styles = [''] * len(row)
                        for i, col in enumerate(mer_disp.columns):
                            if col == 'Match Eff %':
                                v = row[col]
                                styles[i] = (f'color:{C["green"]};font-weight:bold' if v >= mer_good
                                             else (f'color:{C["orange"]}' if v >= mer_monitor else f'color:{C["red"]}'))
                        return styles
                    st.dataframe(
                        mer_disp.style.apply(_style_mer, axis=1)
                                .format({'Match Eff %': '{:.0f}%', 'Parts': '{:,.0f}',
                                         'Prod Hrs': '{:.0f}'}, na_rep='—'),
                        use_container_width=True, hide_index=True,
                    )

            # ── Avg Cap Efficiency bar ─────────────────────────────────────────
            with c_right:
                st.markdown("##### Avg Cap Efficiency by Supplier")
                st.caption("Average across all tool-machine pairings")
                if not scorecard.empty:
                    ce_colors = [
                        C['green'] if v >= ce_good else (C['orange'] if v >= ce_monitor else C['red'])
                        for v in scorecard['avg_cap_eff']
                    ]
                    st.markdown(_html_legend([
                        (f'≥ {ce_good}% Good',             C['green']),
                        (f'{ce_monitor}–{ce_good-1}% Monitor', C['orange']),
                        (f'< {ce_monitor}% At Risk',        C['red']),
                    ]), unsafe_allow_html=True)
                    fig_bar = go.Figure(go.Bar(
                        x=scorecard['supplier_id'], y=scorecard['avg_cap_eff'],
                        marker_color=ce_colors,
                        text=scorecard['avg_cap_eff'].round(0).astype(int).astype(str)+'%',
                        textposition='outside',
                    ))
                    fig_bar.update_layout(
                        yaxis=dict(range=[max(0, scorecard['avg_cap_eff'].min() - 10), 115],
                                   title="Cap Efficiency %"),
                        showlegend=False,
                        height=CHART_H, margin=dict(t=10, b=30, l=40, r=10),
                    )
                    st.plotly_chart(fig_bar, use_container_width=True, key=f"ov_cap{key_suffix}")

                    # Table: # | Supplier | Machines | Tools | Prod Runs | Parts | Prod Hrs | Cap Efficiency % | Stability % | MTBF | MTTR
                    sc_disp = scorecard[['rank', 'supplier_id', 'total_machines', 'total_tools',
                                          'total_runs', 'total_parts', 'production_hrs',
                                          'avg_cap_eff', 'avg_stability',
                                          'avg_mtbf', 'avg_mttr']].rename(columns={
                        'rank':           '#',
                        'supplier_id':    'Supplier',
                        'total_machines': 'Machines',
                        'total_tools':    'Tools',
                        'total_runs':     'Prod Runs',
                        'total_parts':    'Parts',
                        'production_hrs': 'Prod Hrs',
                        'avg_cap_eff':    'Cap Efficiency %',
                        'avg_stability':  'RR Time Stability %',
                        'avg_mtbf':       'MTBF (min)',
                        'avg_mttr':       'MTTR (min)',
                    })
                    def _style_sc(row):
                        styles = [''] * len(row)
                        for i, col in enumerate(sc_disp.columns):
                            if col == 'Cap Efficiency %':
                                v = row[col]
                                styles[i] = (f'color:{C["green"]};font-weight:bold' if v >= 90
                                             else (f'color:{C["orange"]}' if v >= 75 else f'color:{C["red"]}'))
                        return styles
                    st.dataframe(
                        sc_disp.style.apply(_style_sc, axis=1)
                               .format({'Cap Efficiency %': '{:.0f}%', 'RR Time Stability %': '{:.0f}%',
                                        'MTBF (min)': '{:.0f}', 'MTTR (min)': '{:.1f}',
                                        'Parts': '{:,.0f}', 'Prod Hrs': '{:.0f}'}, na_rep='—'),
                        use_container_width=True, hide_index=True,
                    )

            # ── Weekly report download ─────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### 📥 Weekly Report")
            recs_for_report = cr_CG_utils.compute_recommendations(fit_df)
            rankings_for_report = cr_CG_utils.compute_machine_tool_rankings(fit_df)
            report_bytes = cr_CG_utils.generate_weekly_report(
                fit_df=fit_df,
                scorecard=scorecard,
                recs_df=recs_for_report,
                mer_df=mer_df,
                rankings_df=rankings_for_report,
                report_date=pd.Timestamp.now().strftime("%Y-%m-%d"),
            )
            st.download_button(
                label="⬇️ Download Weekly Report (Excel)",
                data=report_bytes,
                file_name=f"machine_fit_report_{pd.Timestamp.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_weekly{key_suffix}",
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — PRESS COMPARE (Tool-driven)
    # ══════════════════════════════════════════════════════════════════════════
    with sub_compare:
        st.subheader("Press Compare — by Part / Tool")
        st.caption(
            "Select a part to compare how it performs across every machine it has run on. "
            "**vs Avg** = % difference from the average across all machines for that KPI. "
            "Green = above average, Red = below average."
        )

        all_tools_pc  = sorted(fit_df['tool_id'].unique())
        all_groups_pc = sorted({v for v in copy_map.values() if v})

        pc_mode = st.radio("Select by", ["Part (Copy Group)", "Individual Tool"],
                           horizontal=True, key=f"pc_mode{key_suffix}")

        if pc_mode == "Part (Copy Group)" and all_groups_pc:
            sel_group = st.selectbox("Part ID", all_groups_pc, key=f"pc_group{key_suffix}")
            sel_tool_ids = [t for t in all_tools_pc if copy_map.get(t) == sel_group]
            label = f"Part {sel_group} — Tools: {', '.join(sel_tool_ids)}"
        else:
            def _tlabel(tid): return f"{tid} [Part: {copy_map[tid]}]" if tid in copy_map else f"{tid} [Single]"
            sel_tool = st.selectbox("Tool ID", all_tools_pc, format_func=_tlabel,
                                    key=f"pc_tool{key_suffix}")
            sel_tool_ids = [sel_tool]
            label = _tlabel(sel_tool)

        recent_days = st.slider("'Recent' window (days)", 7, 90, 30,
                                key=f"pc_recent{key_suffix}")

        st.markdown(f"**{label}**")

        # ── Best machine per tool — shown first ───────────────────────────────
        if len(sel_tool_ids) > 1:
            st.markdown("#### Best Machine Recommendation — Per Tool")
            st.caption(
                "Each copy tool may perform better on a different machine. "
                "Recommended machine shown with its best historical period."
            )
            rec_rows = []
            for tid in sel_tool_ids:
                tool_data = fit_df[fit_df['tool_id'] == tid].sort_values(
                    'cap_efficiency_pct', ascending=False
                ).reset_index(drop=True)
                if tool_data.empty:
                    continue
                best_row   = tool_data.iloc[0]
                worst_row  = tool_data.iloc[-1]
                second_row = tool_data.iloc[1] if len(tool_data) > 1 else None
                pph = (best_row['total_parts'] / best_row['production_hrs']
                       if best_row['production_hrs'] > 0 else 0)

                # Best actual run: find the session with highest cap efficiency
                # for this tool on its best machine from df_processed_global
                best_run_start = best_run_end = best_run_cap_eff = '—'
                if not df_processed_global.empty and 'machine_id' in df_processed_global.columns:
                    pair_shots = df_processed_global[
                        (df_processed_global['tool_id'] == tid) &
                        (df_processed_global['machine_id'] == best_row['machine_id'])
                    ]
                    if not pair_shots.empty and 'run_id' in pair_shots.columns:
                        best_run_eff = -1
                        for run_id, rg in pair_shots.groupby('run_id'):
                            prod = rg[rg['stop_flag'] == 0]
                            dur = (rg['shot_time'].max() - rg['shot_time'].min()).total_seconds()
                            if dur <= 0: continue
                            rct = float(rg['approved_ct_for_run'].iloc[0]) if 'approved_ct_for_run' in rg.columns else float(rg['approved_ct'].iloc[0])
                            rcav = float(rg['working_cavities'].max()) if 'working_cavities' in rg.columns else 1.0
                            opt = (dur / rct) * rcav if rct > 0 else 0
                            act = float(prod['working_cavities'].sum()) if 'working_cavities' in prod.columns else float(len(prod))
                            eff = act / opt * 100 if opt > 0 else 0
                            if eff > best_run_eff:
                                best_run_eff   = eff
                                best_run_start = rg['shot_time'].min().strftime('%d %b %Y %H:%M')
                                best_run_end   = rg['shot_time'].max().strftime('%d %b %Y %H:%M')
                                best_run_cap_eff = eff

                rec_rows.append({
                    'tool_id':           tid,
                    'best_machine':      best_row['machine_id'],
                    'best_cap_eff':      best_row['cap_efficiency_pct'],
                    'best_stability':    best_row['stability_pct'],
                    'best_parts_per_hr': round(pph, 0),
                    'best_fit_score':    best_row['fit_score'],
                    'best_run_start':    best_run_start,
                    'best_run_end':      best_run_end,
                    'best_run_cap_eff':  best_run_cap_eff if isinstance(best_run_cap_eff, float) else 0,
                    'second_machine':    second_row['machine_id'] if second_row is not None else None,
                    'second_cap_eff':    second_row['cap_efficiency_pct'] if second_row is not None else 0,
                    'vs_second_pp':      round((second_row['cap_efficiency_pct'] - best_row['cap_efficiency_pct']), 0) if second_row is not None else 0,
                    'worst_machine':     worst_row['machine_id'],
                    'worst_cap_eff':     worst_row['cap_efficiency_pct'],
                    'machines_tested':   len(tool_data),
                    'vs_worst_pp':       round(best_row['cap_efficiency_pct'] - worst_row['cap_efficiency_pct'], 0),
                })

            if rec_rows:
                card_cols_top = st.columns(min(len(rec_rows), 3))
                for i, r in enumerate(rec_rows):
                    with card_cols_top[i % min(len(rec_rows), 3)]:
                        has_secondary = r['machines_tested'] > 1
                        has_tertiary  = r['machines_tested'] > 2

                        secondary_html = ''
                        if has_secondary and r.get('second_machine'):
                            secondary_html = (
                                f'<br><span style="font-size:0.83em;color:{C["blue"]}">'
                                f'🥈 Next best: <b>{r["second_machine"]}</b> — '
                                f'{r["second_cap_eff"]:.0f}% cap eff '
                                f'({r["vs_second_pp"]:+.0f} pp vs best)</span>'
                            )

                        avoid_html = ''
                        if has_secondary and r.get('worst_machine') != r.get('best_machine'):
                            avoid_html = (
                                f'<span style="color:{C["red"]};font-size:0.82em">'
                                f'⚠️ Avoid: <b>{r["worst_machine"]}</b> '
                                f'({r["worst_cap_eff"]:.0f}% — {r["vs_worst_pp"]:+.0f} pp vs best)</span>'
                            )
                        elif not has_secondary:
                            avoid_html = '<span style="font-size:0.8em;color:#aaa">Only tested on one machine</span>'

                        best_run_html = ''
                        if r.get('best_run_start') and r['best_run_start'] != '—':
                            best_run_html = (
                                f'Best run: <b>{r["best_run_start"]}</b>'
                                f'{" → " + r["best_run_end"] if r.get("best_run_end") and r["best_run_end"] != r["best_run_start"] else ""}'
                                f' ({r["best_run_cap_eff"]:.0f}% cap eff)<br>'
                            )

                        st.markdown(f"""
                        <div style="background:#1a1a2e;border:1px solid {C['green']};
                                    border-radius:8px;padding:14px;margin-bottom:8px">
                            <b style="color:{C['green']};font-size:1.05em">{r['tool_id']}</b>
                            <span style="color:#aaa;font-size:0.8em">
                                &nbsp;— {int(r['machines_tested'])} machine{'s' if r['machines_tested']!=1 else ''} tested
                            </span><br><br>
                            <b>✅ Best: {r['best_machine']}</b><br>
                            <span style="font-size:0.85em">
                                Cap Eff: <b>{r['best_cap_eff']:.0f}%</b> &nbsp;|&nbsp;
                                Stability: {r['best_stability']:.0f}%<br>
                                Parts/hr: {r['best_parts_per_hr']:.0f} &nbsp;|&nbsp;
                                Fit Score: {r['best_fit_score']:.0f}/100<br>
                                {best_run_html}
                            </span>
                            {secondary_html}
                            <br><br>
                            {avoid_html}
                        </div>""", unsafe_allow_html=True)

            st.markdown("---")

        pc = cr_CG_utils.compute_press_compare(
            fit_df, sel_tool_ids, df_processed_global, recent_days
        )

        if not pc or pc['alltime'].empty:
            st.warning("Not enough machine data for this selection.")
        else:
            alltime = pc['alltime']
            delta   = pc['delta']
            labels  = pc['kpi_labels']
            hb      = pc['higher_better']

            # ── All-time KPI table ────────────────────────────────────────────
            st.markdown("#### All-Time Performance by Machine")
            disp_cols_pc = [c for c in labels if c in alltime.columns]
            at_disp = alltime[disp_cols_pc].rename(columns=labels)
            at_disp.index.name = 'Machine'

            def _style_at(row):
                styles = []
                for col, orig in zip(at_disp.columns, disp_cols_pc):
                    v = row[col]
                    d = delta.loc[row.name, orig] if row.name in delta.index else 0
                    if orig in hb:
                        styles.append(f'color:{C["green"]}' if d > 2 else
                                      (f'color:{C["red"]}' if d < -2 else ''))
                    else:
                        styles.append(f'color:{C["green"]}' if d < -2 else
                                      (f'color:{C["red"]}' if d > 2 else ''))
                return styles

            st.dataframe(
                at_disp.style.apply(_style_at, axis=1).format(precision=1, na_rep='—'),
                use_container_width=True
            )

            # ── vs Best Machine table ─────────────────────────────────────────
            st.markdown("#### vs Best Machine")
            st.caption(
                "How each machine compares to this tool's best machine. "
                "Green = outperforms best on that metric. "
                "The best machine row shows 0 pp by definition. "
                "For MTTR and Slow Loss — negative is better."
            )
            # Compute vs-best delta: each machine minus the best machine's value
            kpi_cols = [c for c in labels if c in alltime.columns]
            best_machine_vals = alltime[kpi_cols].loc[alltime['cap_efficiency_pct'].idxmax()] if 'cap_efficiency_pct' in alltime.columns else alltime[kpi_cols].iloc[0]
            vs_best = alltime[kpi_cols].subtract(best_machine_vals).round(1)
            vb_disp = vs_best.rename(columns=labels)
            vb_disp.index.name = 'Machine'

            def _style_vb(row):
                styles = []
                for col, orig in zip(vb_disp.columns, kpi_cols):
                    v = row[col]
                    if orig in hb:
                        styles.append(f'color:{C["green"]}' if v > 1 else
                                      (f'color:{C["red"]}' if v < -1 else ''))
                    else:
                        styles.append(f'color:{C["green"]}' if v < -1 else
                                      (f'color:{C["red"]}' if v > 1 else ''))
                return styles

            fmt_vb = {c: '{:+.1f}' for c in vb_disp.columns}
            st.dataframe(
                vb_disp.style.apply(_style_vb, axis=1).format(fmt_vb, na_rep='—'),
                use_container_width=True
            )

            # ── Recent vs Historical ──────────────────────────────────────────
            recent_df = pc.get('recent', pd.DataFrame())
            hist_df   = pc.get('historical', pd.DataFrame())

            if not recent_df.empty and not hist_df.empty:
                st.markdown(f"#### Recent (last {recent_days}d) vs Historical")
                shared_machines = recent_df.index.intersection(hist_df.index)
                shared_cols = recent_df.columns.intersection(hist_df.columns)
                if len(shared_machines) > 0 and len(shared_cols) > 0:
                    rh_rows = []
                    for m in shared_machines:
                        for col in shared_cols:
                            r_val = recent_df.loc[m, col]
                            h_val = hist_df.loc[m, col]
                            delta_rh = ((r_val - h_val) / h_val * 100) if h_val != 0 else 0
                            rh_rows.append({
                                'Machine': m, 'KPI': labels.get(col, col),
                                'Historical': round(h_val, 1), 'Recent': round(r_val, 1),
                                'Change': round(delta_rh, 1),
                                '_orig': col,
                            })
                    rh_df = pd.DataFrame(rh_rows)

                    def _style_rh(row):
                        styles = ['', '', '', '', '']
                        v = row['Change']
                        orig = row['_orig']
                        good = (v > 0 and orig in hb) or (v < 0 and orig not in hb)
                        styles[4] = f'color:{C["green"]};font-weight:bold' if good and abs(v)>1 else \
                                    (f'color:{C["red"]}' if not good and abs(v)>1 else '')
                        return styles

                    st.dataframe(
                        rh_df.drop(columns=['_orig']).style
                            .apply(_style_rh, axis=1)
                            .format({'Historical':'{:.1f}','Recent':'{:.1f}','Change':'{:+.1f}%'},
                                    na_rep='—'),
                        use_container_width=True, hide_index=True
                    )
            else:
                st.caption("Upload TMD log and ensure sufficient date range for recent vs historical split.")

            # ── Machine Rankings chart for this tool ──────────────────────────
            st.markdown("#### Machine Ranking — Cap Efficiency")
            fig_rank = go.Figure(go.Bar(
                x=alltime.index.tolist(),
                y=alltime['cap_efficiency_pct'].tolist() if 'cap_efficiency_pct' in alltime.columns else [],
                marker_color=[C['green'] if v == alltime['cap_efficiency_pct'].max()
                              else (C['red'] if v == alltime['cap_efficiency_pct'].min()
                              else C['blue']) for v in alltime['cap_efficiency_pct']],
                text=[f"{v:.1f}%" for v in alltime['cap_efficiency_pct']],
                textposition='outside',
            ))
            fig_rank.update_layout(
                yaxis=dict(range=[max(0,alltime['cap_efficiency_pct'].min()-15), 115],
                           title="Cap Efficiency %"),
                xaxis_title="Machine", height=320, margin=dict(t=20,b=40),
            )
            st.plotly_chart(fig_rank, use_container_width=True, key=f"pc_rank{key_suffix}")

    with sub_pairings:
        st.subheader("Optimal Machine-Tool Pairings")
        st.caption(
            "For each machine, the best and worst performing tools are identified from historical data. "
            "Gain = extra parts per hour if the best tool ran instead of the worst."
        )

        recs_df = cr_CG_utils.compute_recommendations(fit_df)

        if recs_df.empty:
            st.warning("Not enough data to generate pairings.")
        else:
            # Compatibility: cap_eff_gain added in latest cr_utils; fall back to cap_eff_spread
            if 'cap_eff_gain' not in recs_df.columns:
                recs_df['cap_eff_gain'] = recs_df['cap_eff_spread']
            if 'worst_parts_per_hr' not in recs_df.columns:
                recs_df['worst_parts_per_hr'] = 0.0

            r1, r2 = st.columns(2)
            r1.metric("Machines with Data", f"{len(recs_df)}")
            r2.metric("Total Cap Eff Gain Potential",
                      f"+{recs_df['cap_eff_gain'].sum():.0f} pp",
                      help="Sum of cap efficiency gain across all machines if each ran its best tool instead of worst")

            st.markdown("---")
            st.markdown("#### Recommended Pairings")
            st.caption(
                "Ranked by cap efficiency spread. "
                "**Cap eff gain** = percentage point improvement switching from worst to best tool on that machine. "
                "Parts/hr shown as context — differs between tools due to cycle time and cavity count."
            )

            for _, row in recs_df.iterrows():
                gain = row['cap_eff_gain']
                best_eff = row['best_cap_eff']
                # Colour indicator based on best tool's cap efficiency
                indicator = "🟢" if best_eff >= 90 else ("🟡" if best_eff >= 75 else "🔴")

                with st.expander(
                    f"{indicator} **{row['machine_id']}** — Best: {row['best_tool']} "
                    f"({row['best_supplier']}) | +{gain:.0f} pp cap eff gain | "
                    f"{int(row['tools_compared'])} tools compared"
                ):
                    ec1, ec2 = st.columns(2)
                    with ec1:
                        st.markdown(f"**✅ Best match: {row['best_tool']}** ({row['best_supplier']})")
                        st.markdown(f"Cap Efficiency: **{row['best_cap_eff']:.0f}%**")
                        st.markdown(f"Parts/hr: {row['best_parts_per_hr']:.0f} *(context — depends on CT & cavities)*")

                        best_sessions = fit_df[
                            (fit_df['tool_id'] == row['best_tool']) &
                            (fit_df['machine_id'] == row['machine_id'])
                        ]
                        if not best_sessions.empty:
                            st.markdown("**Optimal session metrics:**")
                            bs = best_sessions.iloc[0]
                            st.markdown(
                                f"Stability: {bs['stability_pct']:.0f}% &nbsp;|&nbsp; "
                                f"MTBF: {bs['mtbf_min']:.0f} min &nbsp;|&nbsp; "
                                f"MTTR: {bs['mttr_min']:.1f} min  \n"
                                f"Slow Loss: {bs['slow_loss_parts']:.0f} parts &nbsp;|&nbsp; "
                                f"Fast Gain: {bs['fast_gain_parts']:.0f} parts  \n"
                                f"Prod Hrs: {bs['production_hrs']:.0f} &nbsp;|&nbsp; "
                                f"Parts: {bs['total_parts']:.0f}"
                            )
                            btn_key = f"cr_analysis_{row['machine_id']}_{row['best_tool']}"
                            if st.button("📊 Run CR Analysis on this pairing", key=btn_key):
                                st.session_state['cr_dialog_tool']    = row['best_tool']
                                st.session_state['cr_dialog_machine'] = row['machine_id']
                                st.session_state['cr_dialog_df_proc'] = df_processed_global
                                st.session_state['cr_dialog_config']  = config
                                _cr_pairing_dialog()

                    with ec2:
                        st.markdown(f"**⚠️ Worst match: {row['worst_tool']}** ({row['worst_supplier']})")
                        st.markdown(f"Cap Efficiency: **{row['worst_cap_eff']:.0f}%**")
                        st.markdown(f"Parts/hr: {row['worst_parts_per_hr']:.0f} *(context)*")
                        st.markdown(f"Cap eff gap vs best: **+{gain:.0f} pp**")
                        st.caption(
                            "Note: parts/hr difference between tools reflects their cycle time "
                            "and cavity count — not machine performance. Cap efficiency is the "
                            "comparable metric across tools."
                        )

            st.markdown("#### Full Table")
            best_display = recs_df[[
                'machine_id','best_tool','best_supplier','best_cap_eff','best_parts_per_hr',
                'worst_tool','worst_supplier','worst_cap_eff','worst_parts_per_hr',
                'tools_compared','cap_eff_gain',
            ]].rename(columns={
                'machine_id':'Machine','best_tool':'Best Tool','best_supplier':'Best Supplier',
                'best_cap_eff':'Best Cap Eff %','best_parts_per_hr':'Best Parts/hr',
                'worst_tool':'Worst Tool','worst_supplier':'Worst Supplier',
                'worst_cap_eff':'Worst Cap Eff %','worst_parts_per_hr':'Worst Parts/hr',
                'tools_compared':'Tools Compared','cap_eff_gain':'Cap Eff Gain (pp)',
            })

            def _style_recs(row):
                styles = [''] * len(row)
                for i, col in enumerate(best_display.columns):
                    if col == 'Best Cap Eff %':    styles[i] = f'color:{C["green"]};font-weight:bold'
                    elif col == 'Worst Cap Eff %': styles[i] = f'color:{C["red"]}'
                    elif col == 'Cap Eff Gain (pp)':
                        styles[i] = f'color:{C["orange"]}' if row[col] > 5 else ''
                return styles

            st.dataframe(
                best_display.style.apply(_style_recs, axis=1)
                .format({'Best Cap Eff %':'{:.0f}%','Worst Cap Eff %':'{:.0f}%',
                         'Best Parts/hr':'{:.0f}','Worst Parts/hr':'{:.0f}',
                         'Cap Eff Gain (pp)':'{:+.0f} pp'}, na_rep='—'),
                use_container_width=True, hide_index=True
            )

            # ── Heatmap ───────────────────────────────────────────────────────
            st.markdown("#### Cap Efficiency % — All Machines × All Tools")
            st.caption("Green = higher cap efficiency. Blank = not yet tested together.")
            pv = pd.pivot_table(
                fit_df, values='cap_efficiency_pct',
                index='machine_id', columns='tool_id', aggfunc='mean'
            ).round(1)
            st.dataframe(
                pv.style.background_gradient(cmap='RdYlGn', axis=None, vmin=70, vmax=105)
                        .format(precision=1, na_rep=''),
                use_container_width=True
            )
        st.subheader("Tool Rankings by Machine")
        st.caption(
            "Select a machine to see how every tool that has run on it compares. "
            "**vs Best** shows how far each tool is behind the top performer on this machine. "
            "**Parts Gain/hr** is how many more parts per hour this machine would produce "
            "if it ran the best tool instead of this one."
        )

        all_machines_rk = sorted(fit_df['machine_id'].unique())
        sel_machine = st.selectbox("Select Machine", all_machines_rk, key=f"rk_machine_sel{key_suffix}")

        mach_rankings = cr_CG_utils.compute_machine_tool_rankings(fit_df)
        mach_view = mach_rankings[mach_rankings['machine_id'] == sel_machine].copy()

        if mach_view.empty:
            st.warning("No tool data for this machine.")
        else:
            # ── Summary strip ─────────────────────────────────────────────────
            best_r  = mach_view.iloc[0]
            worst_r = mach_view.iloc[-1]
            s1, s2, s3, s4 = st.columns(4)
            s1.metric("Tools Compared",     f"{len(mach_view)}")
            s2.metric("Best Tool",          best_r['tool_id'],
                      f"{best_r['cap_efficiency_pct']:.1f}% Cap Eff")
            s3.metric("Cap Eff Spread",     f"{(best_r['cap_efficiency_pct'] - worst_r['cap_efficiency_pct']):.1f} pp",
                      help="Difference between best and worst tool on this machine")
            s4.metric("Max Parts Gain/hr",  f"{mach_view['parts_gain_potential'].max():,.1f}",
                      help="Parts per hour gained if worst tool replaced by best")

            st.markdown("---")

            mach_view['copy_group'] = mach_view['tool_id'].map(copy_map).fillna('—')
            mach_view['vs_best_label'] = mach_view['vs_best_pct'].apply(
                lambda v: f"—" if v == 0 else f"{v:+.1f} pp"
            )

            disp = mach_view[[
                'rank_on_machine', 'tool_id', 'copy_group', 'supplier_id',
                'runs', 'production_hrs', 'total_parts',
                'cap_efficiency_pct', 'stability_pct', 'fit_score',
                'vs_best_label', 'parts_gain_potential',
                'avg_ct_sec', 'ct_fluctuation_pct', 'mtbf_min', 'mttr_min',
            ]].rename(columns={
                'rank_on_machine': '#', 'tool_id': 'Tool', 'copy_group': 'Copy Group',
                'supplier_id': 'Supplier', 'runs': 'Runs',
                'production_hrs': 'Prod Hrs', 'total_parts': 'Parts',
                'cap_efficiency_pct': 'Cap Eff %', 'stability_pct': 'Stability %',
                'fit_score': 'Fit Score', 'vs_best_label': 'vs Best',
                'parts_gain_potential': 'Parts Gain/hr',
                'avg_ct_sec': 'Avg CT (s)', 'ct_fluctuation_pct': 'CT Fluctuation%',
                'mtbf_min': 'MTBF (min)', 'mttr_min': 'MTTR (min)',
            })

            def _style_mach_rk(row):
                styles = [''] * len(row)
                for i, col in enumerate(disp.columns):
                    if col == 'Cap Eff %':
                        v = row[col]
                        if v >= 90:   styles[i] = f'color:{C["green"]};font-weight:bold'
                        elif v >= 75: styles[i] = f'color:{C["orange"]}'
                        else:         styles[i] = f'color:{C["red"]}'
                    elif col == 'vs Best':
                        styles[i] = '' if row[col] == '—' else f'color:{C["red"]}'
                    elif col == 'Parts Gain/hr':
                        v = row[col]
                        styles[i] = '' if v == 0 else (f'color:{C["orange"]}' if v > 0 else '')
                return styles

            st.dataframe(
                disp.style.apply(_style_mach_rk, axis=1).format(
                    {c: '{:.1f}' for c in ['Cap Eff %','Stability %','Fit Score',
                                            'Parts Gain/hr','Avg CT (s)','CT Fluctuation%',
                                            'MTBF (min)','MTTR (min)']},
                    na_rep='—'
                ),
                use_container_width=True, hide_index=True
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — PART ANALYSIS
    # ══════════════════════════════════════════════════════════════════════════
    with sub_deepdive:
        st.subheader("Part Analysis")

        all_groups_dd = sorted({v for v in copy_map.values() if v})
        all_tools_dd  = sorted(fit_df['tool_id'].unique())

        if all_groups_dd:
            dd_part = st.selectbox("Select Part", all_groups_dd, key=f"dd_part_grp{key_suffix}")
            dd_tool_ids = [t for t in all_tools_dd if copy_map.get(t) == dd_part]
        else:
            dd_part = st.selectbox("Select Tool", all_tools_dd, key=f"dd_part_tool{key_suffix}")
            dd_tool_ids = [dd_part]

        # ── Date range slider ─────────────────────────────────────────────────
        if not df_processed_global.empty and 'shot_time' in df_processed_global.columns:
            part_proc_all = df_processed_global[
                df_processed_global['tool_id'].isin(dd_tool_ids)
            ]
            if not part_proc_all.empty:
                date_min = part_proc_all['shot_time'].min().date()
                date_max = part_proc_all['shot_time'].max().date()
                if date_min < date_max:
                    dd_range = st.slider(
                        "Date Range", min_value=date_min, max_value=date_max,
                        value=(date_min, date_max), key=f"dd_range{key_suffix}",
                        format="DD MMM YYYY"
                    )
                    date_from = pd.Timestamp(dd_range[0])
                    date_to   = pd.Timestamp(dd_range[1]) + pd.Timedelta(days=1)
                    part_proc = df_processed_global[
                        df_processed_global['tool_id'].isin(dd_tool_ids) &
                        (df_processed_global['shot_time'] >= date_from) &
                        (df_processed_global['shot_time'] <  date_to)
                    ].copy()
                    # Filter fit_df to sessions that overlap the date range
                    valid_sessions = part_proc['session_id'].dropna().unique() if 'session_id' in part_proc.columns else []
                    dd_fit = fit_df[fit_df['tool_id'].isin(dd_tool_ids)].copy()
                else:
                    part_proc = part_proc_all.copy()
                    dd_fit    = fit_df[fit_df['tool_id'].isin(dd_tool_ids)].copy()
            else:
                part_proc = pd.DataFrame()
                dd_fit    = fit_df[fit_df['tool_id'].isin(dd_tool_ids)].copy()
        else:
            part_proc = pd.DataFrame()
            dd_fit    = fit_df[fit_df['tool_id'].isin(dd_tool_ids)].copy()

        if not dd_tool_ids:
            st.warning("No data for this part.")
        elif dd_fit.empty:
            st.warning("No machine data found for this part.")
        else:
            SEVERITY_COLOR = {'high': C['red'], 'medium': C['orange'], 'info': C['blue']}
            SEVERITY_ICON  = {'high': '🔴', 'medium': '🟡', 'info': '🔵'}

            # ── Analysis Engine ───────────────────────────────────────────────
            st.markdown("#### 🔍 Automated Insights")
            with st.spinner("Running analysis…"):
                insights = cr_CG_utils.run_part_analysis(
                    fit_df=dd_fit,
                    df_processed=part_proc,
                    tool_ids=dd_tool_ids,
                    part_name=dd_part,
                    copy_map=copy_map,
                )

            if not insights:
                st.info("No significant patterns detected for this part in the selected date range.")
            else:
                for idx, ins in enumerate(insights):
                    color  = SEVERITY_COLOR.get(ins['severity'], C['blue'])
                    icon   = SEVERITY_ICON.get(ins['severity'], '🔵')
                    rule   = ins['rule'].replace('_', ' ').title()
                    ins_tool    = ins.get('tool_id')
                    ins_machine = ins.get('machine_id')

                    st.markdown(f"""
                    <div style="background:#1a1a2e;border-left:4px solid {color};
                                border-radius:6px;padding:12px 16px;margin-bottom:4px">
                        <span style="font-size:0.75em;color:{color};text-transform:uppercase;
                                     letter-spacing:0.05em">{icon} {rule}</span><br>
                        <b style="font-size:0.95em">{ins['title']}</b><br>
                        <span style="font-size:0.85em;color:#ccc">{ins['detail']}</span>
                    </div>""", unsafe_allow_html=True)

                    if ins_tool:
                        btn_label = (
                            f"📊 Analyse {ins_tool}"
                            + (f" on {ins_machine}" if ins_machine else "")
                            + (" · Best Window" if ins.get('date_from') else "")
                            + (f" · {ins.get('shift_filter')}" if ins.get('shift_filter') else "")
                        )
                        btn_key = f"ins_cr_{idx}_{ins['rule']}_{key_suffix}"
                        if st.button(btn_label, key=btn_key):
                            st.session_state['cr_dialog_tool']         = ins_tool
                            st.session_state['cr_dialog_machine']      = ins_machine
                            st.session_state['cr_dialog_df_proc']      = part_proc if not part_proc.empty else df_processed_global
                            st.session_state['cr_dialog_config']       = config
                            st.session_state['cr_dialog_date_from']    = ins.get('date_from')
                            st.session_state['cr_dialog_date_to']      = ins.get('date_to')
                            st.session_state['cr_dialog_shift_filter'] = ins.get('shift_filter')
                            _cr_pairing_dialog()

                    st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

            st.markdown("---")

            # ── Performance Heatmap ───────────────────────────────────────────
            st.markdown("#### Performance Heatmap — Machine × Tool")
            st.caption("Cap efficiency for each tool on each machine. Green = better. Blank = not yet tested.")
            pv_hm = pd.pivot_table(
                dd_fit, values='cap_efficiency_pct',
                index='machine_id', columns='tool_id', aggfunc='mean'
            ).round(0)
            st.dataframe(
                pv_hm.style
                    .background_gradient(cmap='RdYlGn', axis=None, vmin=70, vmax=105)
                    .format('{:.0f}%', na_rep=''),
                use_container_width=True
            )

            st.markdown("---")

            # ── Performance by Shift ──────────────────────────────────────────
            if 'session_period' in df_processed_global.columns and not part_proc.empty:
                shift_cfg = st.session_state.get('shift_config',
                    [("Shift 1",6,14),("Shift 2",14,22),("Shift 3",22,6)])
                shift_label = " · ".join(
                    f"{n} {s:02d}:00–{e:02d}:00" for n,s,e in shift_cfg
                )
                st.markdown("#### Performance by Shift — Machine × Tool")
                st.caption(shift_label)

                if 'machine_id' in part_proc.columns:
                    shift_rows = []
                    for (tid, mid, period), grp in part_proc.groupby(
                        ['tool_id','machine_id','session_period']
                    ):
                        prod = grp[grp['stop_flag'] == 0]
                        dur  = (grp['shot_time'].max() - grp['shot_time'].min()).total_seconds()
                        if dur <= 0: continue
                        rct  = float(grp['approved_ct_for_run'].iloc[0]) if 'approved_ct_for_run' in grp.columns else float(grp['approved_ct'].iloc[0])
                        rcav = float(grp['working_cavities'].max()) if 'working_cavities' in grp.columns else 1.0
                        opt  = (dur / rct) * rcav if rct > 0 else 0
                        act  = float(prod['working_cavities'].sum()) if 'working_cavities' in prod.columns else float(len(prod))
                        shift_rows.append({
                            'pairing':        f"{tid} / {mid}",
                            'session_period': period,
                            'cap_eff':        round(act / opt * 100, 0) if opt > 0 else None,
                            'parts_per_hr':   round(act / (dur / 3600), 0) if dur > 0 else None,
                        })

                    if shift_rows:
                        shift_df = pd.DataFrame(shift_rows)
                        sv1, sv2 = st.tabs(["Cap Efficiency %", "Parts per Hour"])

                        with sv1:
                            pv_eff = pd.pivot_table(
                                shift_df, values='cap_eff',
                                index='pairing', columns='session_period', aggfunc='mean'
                            ).round(0)
                            st.dataframe(
                                pv_eff.style
                                    .background_gradient(cmap='RdYlGn', axis=None, vmin=70, vmax=105)
                                    .format('{:.0f}%', na_rep='—'),
                                use_container_width=True
                            )
                        with sv2:
                            pv_pph = pd.pivot_table(
                                shift_df, values='parts_per_hr',
                                index='pairing', columns='session_period', aggfunc='mean'
                            ).round(0)
                            st.dataframe(
                                pv_pph.style
                                    .background_gradient(cmap='RdYlGn', axis=None)
                                    .format('{:.0f}', na_rep='—'),
                                use_container_width=True
                            )
            elif 'session_period' not in df_processed_global.columns:
                st.caption("Upload TMD log to enable shift breakdown.")

if __name__ == "__main__":
    main()

