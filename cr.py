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

def render_forecast_tab(df_tool, config, df_logistics, working_days_per_week, working_hours_per_day):
    """Renders the PO Forecast & Burn-up Tab using dynamically filtered metrics."""
    st.header("Logistics Plan Tracking & Forecast")
    
    # Check if we have PO data mapping in the filtered data
    has_po_in_shots = 'po_number' in df_tool.columns and not df_tool['po_number'].replace("Unknown", pd.NA).isna().all()
    
    if not df_logistics.empty and has_po_in_shots:
        part_pos = df_tool['po_number'].unique()
        avail_pos = df_logistics[df_logistics['po_number'].isin(part_pos)]['po_number'].unique()
        
        if len(avail_pos) == 0:
            st.warning("No matching POs found between Logistics Plan and Production Data for the current filter scope.")
            return
            
        # --- Advanced Tracking Configuration ---
        st.markdown("### ⚙️ Tracking Configuration")
        track_mode = st.radio("Group & Track Progress By:", ["Purchase Order(s)", "Supplier(s)", "Plant(s)"], horizontal=True)
        
        selected_po_list = []
        
        if track_mode == "Purchase Order(s)":
            selected_pos = st.multiselect("Select Purchase Order(s) to Track", avail_pos, default=avail_pos[:1])
            selected_po_list = selected_pos
            
        elif track_mode == "Supplier(s)":
            avail_sups = [s for s in df_tool['supplier_id'].unique() if str(s).lower() not in ['unknown', 'nan']]
            if not avail_sups: st.warning("No identified Supplier data in scope."); return
            selected_sups = st.multiselect("Select Supplier(s) to Track", avail_sups, default=avail_sups)
            linked_pos = df_tool[df_tool['supplier_id'].isin(selected_sups)]['po_number'].unique()
            selected_po_list = [po for po in linked_pos if po in avail_pos]
            
        elif track_mode == "Plant(s)":
            avail_plts = [p for p in df_tool['plant_id'].unique() if str(p).lower() not in ['unknown', 'nan']]
            if not avail_plts: st.warning("No identified Plant data in scope."); return
            selected_plts = st.multiselect("Select Plant(s) to Track", avail_plts, default=avail_plts)
            linked_pos = df_tool[df_tool['plant_id'].isin(selected_plts)]['po_number'].unique()
            selected_po_list = [po for po in linked_pos if po in avail_pos]
            
        if not selected_po_list:
            st.warning(f"No Purchase Orders are associated with your current {track_mode} selection. Please select at least one item.")
            return
            
        # Aggregate the Logistics PO records safely into a composite
        subset_logistics = df_logistics[df_logistics['po_number'].isin(selected_po_list)]
        df_po_shots = df_tool[df_tool['po_number'].isin(selected_po_list)].copy()
        
        total_qty = pd.to_numeric(subset_logistics['total_qty'], errors='coerce').sum()
        min_start = pd.to_datetime(subset_logistics['start_date']).min()
        max_due = pd.to_datetime(subset_logistics['due_date']).max()
        
        po_display_name = ", ".join(selected_po_list) if len(selected_po_list) <= 3 else f"{len(selected_po_list)} POs Selected"
        
        composite_po_record = {
            'po_number': po_display_name,
            'total_qty': total_qty,
            'start_date': min_start,
            'due_date': max_due
        }
        
        # --- PO Summary Box ---
        st.markdown("### 📋 Selected Purchase Orders Summary")
        
        summary_data = []
        for _, row in subset_logistics.iterrows():
            summary_data.append({
                "PO Number": row['po_number'],
                "Project": row['project_id'],
                "Part": row['part_id'],
                "Target Qty": f"{row['total_qty']:,.0f}",
                "Start Date": pd.to_datetime(row['start_date']).strftime('%Y-%m-%d') if pd.notna(row['start_date']) else "N/A",
                "Due Date": pd.to_datetime(row['due_date']).strftime('%Y-%m-%d') if pd.notna(row['due_date']) else "N/A"
            })
            
        st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

        st.markdown("---")
        
        # --- Single PO Deep Dive Graphs ---
        st.markdown("### 📈 Single PO Deep Dive")
        st.info("To maintain accurate timelines and capacity analysis, performance graphs isolate and process one Purchase Order at a time. The bars will automatically stack if multiple toolings are used.")
        
        col_po, col_freq = st.columns([2, 1])
        with col_po:
            selected_graph_po = st.selectbox("Select Purchase Order for Visualization:", selected_po_list)
        with col_freq:
            bar_freq = st.selectbox("Select Frequency Spread", ["Weekly", "Monthly", "Daily"], index=0)
            
        po_record = subset_logistics[subset_logistics['po_number'] == selected_graph_po].iloc[0].to_dict()
        df_single_po_shots = df_po_shots[df_po_shots['po_number'] == selected_graph_po].copy()
        
        # Process the raw data to generate 'stop_flag' and other metrics needed for the chart
        calc_for_chart = cr_CG_utils.CapacityRiskCalculator(df_single_po_shots, **config)
        df_processed_for_chart = calc_for_chart.results.get('processed_df', df_single_po_shots)
        
        agg_po = cr_CG_utils.generate_po_periodic_data(df_single_po_shots, po_record, bar_freq, config, working_days_per_week, working_hours_per_day)
        
        st.markdown(f"#### 1. Periodic Production vs Estimated Demand ({selected_graph_po})")
        
        if not agg_po.empty:
            st.plotly_chart(cr_CG_utils.plot_po_periodic_chart(agg_po, df_processed_for_chart, bar_freq, track_mode), use_container_width=True)
        else:
            st.warning("No periodic data available.")

        st.markdown("---")
        
        # --- GRAPH 2: Burn Up Chart ---
        st.markdown(f"### 2. Global Target Burn-Up ({track_mode})")
        pred_data = cr_CG_utils.generate_po_prediction_data(df_po_shots, composite_po_record, config)
        if pred_data:
            st.plotly_chart(cr_CG_utils.plot_po_burnup(pred_data, subset_logistics), use_container_width=True)
            
            # --- Forecast Analysis Insights ---
            current_cum = pred_data['current_cum']
            target_qty = pred_data['total_qty']
            avg_rate = pred_data['avg_daily_rate']
            opt_rate = pred_data['opt_daily_rate']
            due_date = pred_data['due_date']
            
            if current_cum >= target_qty:
                st.success(f"🎉 **Target Fulfilled!** Current output ({current_cum:,.0f}) has met or exceeded the aggregated quantity ({target_qty:,.0f}).")
            else:
                remaining = target_qty - current_cum
                days_avg = remaining / avg_rate if avg_rate > 0 else 9999
                days_opt = remaining / opt_rate if opt_rate > 0 else 9999
                
                # Protect against series max
                actual_dates = pred_data.get('actual_dates', [])
                if len(actual_dates) > 0:
                    last_act_date = actual_dates.iloc[-1] if hasattr(actual_dates, 'iloc') else actual_dates[-1]
                else:
                    last_act_date = min_start.date()
                
                finish_avg = last_act_date + timedelta(days=int(days_avg))
                finish_opt = last_act_date + timedelta(days=int(days_opt))
                
                status_color = "#ff6961" if finish_avg > due_date else "#77dd77"
                status_text = "LATE - AT RISK" if finish_avg > due_date else "ON TRACK"
                
                analysis_html = f"""
                <div style="background-color: #262730; padding: 15px; border-radius: 5px; border: 1px solid #41424C; margin-bottom: 20px;">
                    <h4 style="margin-top:0;">Forecast Analysis</h4>
                    <ul>
                        <li><strong>Status:</strong> <span style="color:{status_color}; font-weight:bold;">{status_text}</span> to meet demand by {due_date.strftime('%Y-%m-%d')}.</li>
                        <li>To meet demand of <strong>{target_qty:,.0f}</strong>, you need <strong>{remaining:,.0f}</strong> more parts.</li>
                        <li>At your current rate ({avg_rate:,.0f}/day), you are projected to finish on <strong>{finish_avg.strftime('%Y-%m-%d')}</strong>.</li>
                        <li>At optimal rate ({opt_rate:,.0f}/day), you could finish by <strong>{finish_opt.strftime('%Y-%m-%d')}</strong>.</li>
                    </ul>
                </div>
                """
                st.markdown(analysis_html, unsafe_allow_html=True)
        else:
            st.warning("Not enough production data to generate burn-up.")
            
        # --- Breakdown per Tooling Table ---
        st.markdown("### Breakdown per Active Tooling")
        tool_summary = []
        for tool_id, tool_df_iter in df_po_shots.groupby('tool_id'):
            calc = cr_CG_utils.CapacityRiskCalculator(tool_df_iter, **config)
            res = calc.results
            if not res: continue
            
            sup = tool_df_iter['supplier_id'].iloc[0] if 'supplier_id' in tool_df_iter.columns else 'Unknown'
            plt_id = tool_df_iter['plant_id'].iloc[0] if 'plant_id' in tool_df_iter.columns else 'Unknown'
            
            tool_summary.append({
                'Tool ID': tool_id,
                'Supplier Name': sup,
                'Plant': plt_id,
                'Total Shots': res['total_shots'],
                'Actual Output': res['actual_output_parts'],
                'Optimal Output': res['optimal_output_parts'],
                'Downtime Loss': res['capacity_loss_downtime_parts'],
                'Slow Loss': res['capacity_loss_slow_parts'],
                'Efficiency (%)': res['efficiency_rate']
            })
        
        if tool_summary:
            st.dataframe(pd.DataFrame(tool_summary).style.format({
                'Total Shots': '{:,.0f}',
                'Actual Output': '{:,.0f}',
                'Optimal Output': '{:,.0f}',
                'Downtime Loss': '{:,.0f}',
                'Slow Loss': '{:,.0f}',
                'Efficiency (%)': '{:.1f}'
            }), use_container_width=True, hide_index=True)
            
    else:
        # Fallback to Generic Projection if no PO data available
        st.warning("Upload a Logistics Plan and ensure Production Data has PO_NUMBER to enable full tracking. Displaying generic forecast below.")
        
        with st.expander("ℹ️ How Prediction Works (Formulas & Logic)", expanded=False):
            st.markdown("""
            This model projects future capacity based on historical daily performance derived securely via the Core Capacity Engine.
            ### 1. 🔵 Blue Line: Forecast (Average Rate)
            Projects future output using your **Average Daily Rate**.
            ### 2. 🟢 Green Line: Best Case (Peak Rate)
            Projects output using your **Peak Daily Rate** (90th percentile).
            ### 3. 🟠 Orange Line: Required Rate
            Shows the daily output required to hit your Demand Goal by the Target Date.
            """, unsafe_allow_html=True)

        agg_daily = cr_CG_utils.get_aggregated_data(df_tool, 'Daily', config)
        if agg_daily.empty:
            st.warning("Not enough daily data to generate a forecast.")
            return

        c_ctrl, c_chart = st.columns([1, 2])
        with c_ctrl:
            with st.container(border=True):
                st.markdown("#### Forecast Settings")
                data_min = pd.to_datetime(agg_daily['Period']).min().date()
                data_max = pd.to_datetime(agg_daily['Period']).max().date()
                hist_start_date = st.date_input("History From Date", data_min, min_value=data_min, max_value=data_max, key="fc_hist_start")
                tgt_date = st.date_input("Target Date", data_max + timedelta(days=30), min_value=data_max, key="fc_date")
                dem_goal = st.number_input("Demand Goal (Total Parts)", 0, step=1000, key="fc_goal")
                
        agg_filtered = agg_daily[pd.to_datetime(agg_daily['Period']).dt.date >= hist_start_date]
        if agg_filtered.empty:
            st.warning("No data available for the selected history range.")
            return

        with c_chart:
            pred = cr_CG_utils.generate_prediction_data(agg_filtered, data_max, tgt_date, dem_goal)
            fig = cr_CG_utils.plot_prediction_chart(pred, dem_goal)
            fig.update_layout(title="Future Capacity Projection")
            st.plotly_chart(fig, use_container_width=True, key="fc_chart")
            
            if dem_goal > 0 and pred:
                current_cum = pred['historic_cum'].iloc[-1]
                remaining = dem_goal - current_cum
                avg_rate = pred['rates']['avg']
                days_needed = remaining / avg_rate if avg_rate > 0 else 9999
                finish_date = data_max + timedelta(days=int(days_needed))
                is_late = finish_date > tgt_date
                status_color = "#ff6961" if is_late else "#77dd77"
                status_text = "LATE - AT RISK" if is_late else "ON TRACK"
                
                st.markdown(f"""
                <div style="background-color: #262730; padding: 15px; border-radius: 5px; border: 1px solid #41424C;">
                    <h4 style="margin-top:0;">Forecast Analysis</h4>
                    <ul>
                        <li><strong>Status:</strong> <span style="color:{status_color}; font-weight:bold;">{status_text}</span> to meet demand by {tgt_date}.</li>
                        <li>To meet demand of <strong>{dem_goal:,.0f}</strong>, you need <strong>{remaining:,.0f}</strong> more parts.</li>
                        <li>At your current rate ({avg_rate:,.0f}/day), you are projected to finish on <strong>{finish_date}</strong>.</li>
                    </ul>
                </div>
                """, unsafe_allow_html=True)


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

APP_VERSION = "v4.0"

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
    # Logistics Plan upload commented out — PO module disabled
    # logistics_file = st.sidebar.file_uploader(
    #     "Upload Logistics Plan (Excel/CSV) [Optional]",
    #     accept_multiple_files=False, type=['xlsx', 'csv', 'xls']
    # )

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

    if not files:
        st.info("👈 Upload one or more production data files to begin.")
        st.stop()

    df_all = cr_CG_utils.load_all_data_cr(files)
    if df_all.empty:
        st.error("No valid production data found. Check file format.")
        st.stop()

    # df_logistics = cr_CG_utils.load_logistics_plan(logistics_file) if logistics_file else pd.DataFrame()
    df_logistics = pd.DataFrame()

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
            df_all = cr_CG_utils.assign_machine_from_tmd(df_all, df_tmd)
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

    # Logistics config commented out — PO module disabled
    # with st.sidebar.expander("Logistics & Schedule Config"):
    #     working_days_per_week = st.slider("Working Days per Week", 1, 7, 5)
    #     working_hours_per_day = st.slider("Working Hours per Day", 1, 24, 24)
    working_days_per_week = 5
    working_hours_per_day = 24

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
    # Forecast tab commented out — PO module disabled
    # t_risk, t_opt, t_tgt, t_trend, t_fc = st.tabs([...,"Forecast (PO Tracking)"])

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

    # Forecast tab commented out — PO module disabled
    # with t_fc:
    #     render_forecast_tab(df_tool_scope, config, df_logistics,
    #                         working_days_per_week, working_hours_per_day)

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
    sub_overview, sub_rankings, sub_recs, sub_deepdive = st.tabs([
        "🌐 Overview", "📊 Machine Rankings", "💡 Recommendations", "🔬 Deep Dive"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — HOLISTIC OVERVIEW
    # ══════════════════════════════════════════════════════════════════════════
    with sub_overview:
        st.subheader("Supply Chain Overview — Machine Performance Scorecard")
        st.caption("Aggregated across all tools that have run on each machine. "
                   "Ranks machines within plant and globally by composite fit score.")

        scorecard = cr_CG_utils.compute_supplier_scorecard(fit_df)

        if scorecard.empty:
            st.warning("No supplier data found. Ensure SUPPLIER_ID is in your production data.")
        else:
            # ── Top-level KPI strip ───────────────────────────────────────────
            k1, k2, k3, k4, k5 = st.columns(5)
            k1.metric("Suppliers Tracked",   f"{scorecard['supplier_id'].nunique()}")
            k2.metric("Total Tools",         f"{fit_df['tool_id'].nunique()}")
            k3.metric("Total Parts Produced",f"{scorecard['total_parts'].sum():,.0f}")
            k4.metric("Total Production Hrs",f"{scorecard['production_hrs'].sum():,.0f} h")
            k5.metric("Avg Fleet Fit Score", f"{scorecard['avg_fit_score'].mean():.0f} / 100")

            st.markdown("---")

            # ── Best / Worst supplier cards ───────────────────────────────────
            if len(scorecard) >= 2:
                best  = scorecard.iloc[0]
                worst = scorecard.iloc[-1]
                cb, cw = st.columns(2)
                for col, m, color, label in [
                    (cb, best,  C['green'], "✅ Top Supplier"),
                    (cw, worst, C['red'],   "⚠️ Lowest Supplier"),
                ]:
                    with col:
                        st.markdown(f"""
                        <div style="background:#1a1a2e;border:1px solid {color};border-radius:8px;padding:14px;margin-bottom:10px">
                            <h4 style="color:{color};margin-top:0">{label}: {m['supplier_id']}</h4>
                            <table style="width:100%;font-size:0.83em;border-collapse:collapse">
                            <tr><td style="padding:2px 5px">Fit Score</td>      <td><b>{m['avg_fit_score']:.0f}/100</b></td></tr>
                            <tr><td style="padding:2px 5px">Tools</td>          <td>{int(m['total_tools'])}</td></tr>
                            <tr><td style="padding:2px 5px">Machines Used</td>  <td>{int(m['total_machines'])}</td></tr>
                            <tr><td style="padding:2px 5px">Total Runs</td>     <td>{int(m['total_runs'])}</td></tr>
                            <tr><td style="padding:2px 5px">Total Parts</td>    <td>{m['total_parts']:,.0f}</td></tr>
                            <tr><td style="padding:2px 5px">Prod Hours</td>     <td>{m['production_hrs']:,.0f} h</td></tr>
                            <tr><td style="padding:2px 5px">Cap Efficiency</td> <td>{m['avg_cap_eff']:.1f}%</td></tr>
                            <tr><td style="padding:2px 5px">Stability</td>      <td>{m['avg_stability']:.1f}%</td></tr>
                            <tr><td style="padding:2px 5px">MTBF</td>           <td>{m['avg_mtbf']:.0f} min</td></tr>
                            <tr><td style="padding:2px 5px">MTTR</td>           <td>{m['avg_mttr']:.1f} min</td></tr>
                            <tr><td style="padding:2px 5px">Best Machine</td>   <td>{m['best_machine']}</td></tr>
                            <tr><td style="padding:2px 5px">Worst Machine</td>  <td>{m['worst_machine']}</td></tr>
                            </table>
                        </div>""", unsafe_allow_html=True)

            st.markdown("#### Supplier Scorecard")

            sc_display = scorecard.rename(columns={
                'rank': '#', 'supplier_id': 'Supplier',
                'total_tools': 'Tools', 'total_machines': 'Machines',
                'total_runs': 'Runs', 'total_parts': 'Parts',
                'production_hrs': 'Prod Hrs', 'avg_fit_score': 'Fit Score',
                'avg_cap_eff': 'Cap Eff %', 'avg_stability': 'Stability %',
                'avg_efficiency': 'Efficiency %',
                'avg_mtbf': 'MTBF (min)', 'avg_mttr': 'MTTR (min)',
                'total_slow_loss': 'Slow Loss', 'total_fast_gain': 'Fast Gain',
                'best_machine': 'Best Machine', 'worst_machine': 'Worst Machine',
            })

            def _style_sc(row):
                styles = [''] * len(row)
                for i, col in enumerate(sc_display.columns):
                    if col == 'Fit Score':
                        v = row[col]
                        if v >= 70:   styles[i] = f'color:{C["green"]};font-weight:bold'
                        elif v >= 45: styles[i] = f'color:{C["orange"]}'
                        else:         styles[i] = f'color:{C["red"]}'
                    elif col in ('Cap Eff %', 'Stability %', 'Efficiency %'):
                        v = row[col]
                        if v >= 90:   styles[i] = f'color:{C["green"]}'
                        elif v >= 75: styles[i] = f'color:{C["orange"]}'
                        else:         styles[i] = f'color:{C["red"]}'
                return styles

            st.dataframe(
                sc_display.style.apply(_style_sc, axis=1).format(precision=1, na_rep='—'),
                use_container_width=True, hide_index=True
            )

            # ── Pivot: Supplier × Machine ─────────────────────────────────────
            st.markdown("#### Pivot: Supplier × Machine")
            st.caption("Average fit score for each supplier's tools on each machine.")
            pv_sup = pd.pivot_table(
                fit_df, values='fit_score',
                index='supplier_id', columns='machine_id', aggfunc='mean'
            ).round(1)
            st.dataframe(pv_sup, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — MACHINE-CENTRIC RANKINGS
    # ══════════════════════════════════════════════════════════════════════════
    with sub_rankings:
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

            # ── Pivot: All machines × all tools ───────────────────────────────
            st.markdown("#### Pivot: All Machines × All Tools (Cap Efficiency %)")
            st.caption("Blank = that tool has not run on that machine.")
            pv = pd.pivot_table(
                fit_df, values='cap_efficiency_pct',
                index='machine_id', columns='tool_id', aggfunc='mean'
            ).round(1)
            st.dataframe(pv, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — RECOMMENDATIONS
    # ══════════════════════════════════════════════════════════════════════════
    with sub_recs:
        st.subheader("Best Match Recommendations")
        st.caption(
            "For each machine, the best-performing tool is identified. "
            "Where a tool from a different supplier outperforms the current supplier's tool, "
            "a **cross-supplier swap** is flagged with the quantified parts-per-hour gain."
        )

        recs_df = cr_CG_utils.compute_recommendations(fit_df)

        if recs_df.empty:
            st.warning("Not enough cross-supplier data to generate recommendations.")
        else:
            # ── KPI strip ─────────────────────────────────────────────────────
            swap_count = recs_df['swap_recommended'].sum()
            total_gain = recs_df['parts_gain_best_vs_worst'].sum()
            swap_gain  = recs_df[recs_df['swap_recommended']]['swap_parts_per_hr_gain'].sum()
            r1, r2, r3 = st.columns(3)
            r1.metric("Machines Analysed",        f"{len(recs_df)}")
            r2.metric("Swap Opportunities Found",  f"{int(swap_count)}")
            r3.metric("Total Swap Gain Potential", f"{swap_gain:,.1f} parts/hr",
                      help="Sum of parts/hr gained if all recommended swaps were actioned")

            st.markdown("---")

            # ── Swap opportunities ─────────────────────────────────────────────
            swaps = recs_df[recs_df['swap_recommended']].copy()
            if swaps.empty:
                st.info("No cross-supplier swap opportunities identified with current data.")
            else:
                st.markdown("#### 🔄 Cross-Supplier Swap Opportunities")
                st.caption(
                    "These machines have a tool from a different supplier that outperforms "
                    "the current supplier's tool. Routing the better-matched tool to this machine "
                    "would yield the stated parts-per-hour gain."
                )
                for _, row in swaps.iterrows():
                    gain_color = C['green'] if row['swap_parts_per_hr_gain'] > 0 else C['orange']
                    st.markdown(f"""
                    <div style="background:#1a1a2e;border-left:4px solid {gain_color};
                                border-radius:6px;padding:14px;margin-bottom:10px">
                        <b style="font-size:1.05em">Machine: {row['machine_id']}</b>
                        &nbsp;&nbsp;
                        <span style="color:{gain_color};font-weight:bold">
                            +{row['swap_parts_per_hr_gain']:.1f} parts/hr gain
                        </span>
                        &nbsp;|&nbsp;
                        <span style="color:{C['blue']}">
                            +{row['swap_cap_eff_gain']:.1f} pp cap efficiency
                        </span>
                        <br><br>
                        <table style="width:100%;font-size:0.85em;border-collapse:collapse">
                        <tr style="color:#aaa">
                            <td style="padding:3px 10px"><b>Current best</b></td>
                            <td style="padding:3px 10px"><b>Recommended swap</b></td>
                        </tr>
                        <tr>
                            <td style="padding:3px 10px">
                                Tool: <b>{row['best_tool']}</b> ({row['best_supplier']})<br>
                                Cap Eff: {row['best_cap_eff']:.1f}%<br>
                                Parts/hr: {row['best_parts_per_hr']:.1f}
                            </td>
                            <td style="padding:3px 10px">
                                Move tool: <b>{row['swap_tool']}</b>
                                from <b>{row['swap_from_supplier']}</b>
                                → run on this machine<br>
                                Supplier: <b>{row['swap_to_supplier']}</b><br>
                                Cap Eff gain: <b style="color:{gain_color}">
                                    +{row['swap_cap_eff_gain']:.1f} pp</b>
                            </td>
                        </tr>
                        </table>
                    </div>""", unsafe_allow_html=True)

            st.markdown("#### All Machine Best Matches")
            best_display = recs_df[[
                'machine_id', 'best_tool', 'best_supplier', 'best_cap_eff',
                'best_parts_per_hr', 'worst_tool', 'worst_supplier', 'worst_cap_eff',
                'tools_compared', 'cap_eff_spread', 'parts_gain_best_vs_worst',
                'swap_recommended', 'swap_tool', 'swap_to_supplier',
                'swap_cap_eff_gain', 'swap_parts_per_hr_gain',
            ]].rename(columns={
                'machine_id': 'Machine', 'best_tool': 'Best Tool',
                'best_supplier': 'Best Supplier', 'best_cap_eff': 'Best Cap Eff %',
                'best_parts_per_hr': 'Best Parts/hr',
                'worst_tool': 'Worst Tool', 'worst_supplier': 'Worst Supplier',
                'worst_cap_eff': 'Worst Cap Eff %', 'tools_compared': 'Tools Compared',
                'cap_eff_spread': 'Spread (pp)', 'parts_gain_best_vs_worst': 'Gain Potential (parts/hr)',
                'swap_recommended': 'Swap?', 'swap_tool': 'Swap Tool',
                'swap_to_supplier': 'From Supplier',
                'swap_cap_eff_gain': 'Swap Cap Gain (pp)',
                'swap_parts_per_hr_gain': 'Swap Parts Gain/hr',
            })

            def _style_recs(row):
                styles = [''] * len(row)
                for i, col in enumerate(best_display.columns):
                    if col == 'Swap?':
                        styles[i] = f'color:{C["green"]};font-weight:bold' if row[col] else ''
                    elif col in ('Spread (pp)', 'Gain Potential (parts/hr)'):
                        v = row[col]
                        styles[i] = f'color:{C["orange"]}' if v > 5 else ''
                    elif col in ('Swap Cap Gain (pp)', 'Swap Parts Gain/hr'):
                        v = row[col]
                        styles[i] = f'color:{C["green"]}' if v > 0 else ''
                return styles

            st.dataframe(
                best_display.style.apply(_style_recs, axis=1).format(precision=1, na_rep='—'),
                use_container_width=True, hide_index=True
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — DEEP DIVE
    # ══════════════════════════════════════════════════════════════════════════
    with sub_deepdive:
        st.subheader("Deep Dive — Single Tool")

        all_tools_dd = sorted(fit_df['tool_id'].unique())

        def _tool_label_dd(tid):
            grp = copy_map.get(tid)
            return f"{tid}  [Copy: {grp}]" if grp else tid

        dd_tool = st.selectbox("Select Tool", all_tools_dd, format_func=_tool_label_dd,
                                key=f"dd_tool{key_suffix}")

        grp_name = copy_map.get(dd_tool)
        siblings = [t for t in all_tools_dd if copy_map.get(t) == grp_name and t != dd_tool] if grp_name else []

        if grp_name:
            st.info(f"📋 **Copy Group: {grp_name}** — Siblings in data: {', '.join(siblings) if siblings else 'none'}")
        else:
            st.caption("🔹 Single tool — no copy group")

        tool_fit = fit_df[fit_df['tool_id'] == dd_tool].copy()
        tool_fit = tool_fit.sort_values('fit_score', ascending=False).reset_index(drop=True)

        if machine_master is not None and not machine_master.empty:
            id_col = next((c for c in machine_master.columns
                           if c.strip().lower() in ('machine id','machine_id','machinecode')), None)
            if id_col:
                mm = machine_master.rename(columns={id_col: 'machine_id'})
                meta_cols = ['machine_id'] + [c for c in
                    ['Machine Maker','Machine Type','Machine Model',
                     'Machine Tonnage (ton)','Plant ID','Line'] if c in mm.columns]
                tool_fit = tool_fit.merge(mm[meta_cols], on='machine_id', how='left')

        n_mach = len(tool_fit)
        if n_mach < 1:
            st.warning("No data for this tool.")
        else:
            # ── Metric cards per machine ──────────────────────────────────────
            st.markdown("#### Machine Comparison Cards")
            card_cols = st.columns(min(n_mach, 4))
            for i, (_, row) in enumerate(tool_fit.iterrows()):
                col = card_cols[i % min(n_mach, 4)]
                score = row['fit_score']
                bcolor = C['green'] if score >= 70 else (C['orange'] if score >= 45 else C['red'])
                imp = row.get('improvement_rate', np.nan)
                imp_str = f"{imp:+.1f} pp" if pd.notna(imp) else "n/a"
                imp_color = C['green'] if (pd.notna(imp) and imp > 0) else (C['red'] if (pd.notna(imp) and imp < 0) else '#aaa')
                with col:
                    st.markdown(f"""
                    <div style="background:#1a1a2e;border:1px solid {bcolor};border-radius:8px;padding:12px;margin-bottom:8px;text-align:center">
                        <b style="color:{bcolor};font-size:1.05em">{row['machine_id']}</b><br>
                        <span style="font-size:1.6em;font-weight:bold">{score:.0f}</span>
                        <span style="font-size:0.75em;color:#aaa">/100</span><br>
                        <span style="font-size:0.78em">Cap Eff: {row['cap_efficiency_pct']:.1f}%</span><br>
                        <span style="font-size:0.78em">Stability: {row['stability_pct']:.1f}%</span><br>
                        <span style="font-size:0.78em">Prod Hrs: {row['production_hrs']:,.0f}</span><br>
                        <span style="font-size:0.78em">Parts: {row['total_parts']:,.0f}</span><br>
                        <span style="font-size:0.78em;color:{imp_color}" title="Performance trend: cap efficiency of recent runs vs early runs on this machine. Positive = improving over time.">Trend: {imp_str}</span>
                    </div>""", unsafe_allow_html=True)

            # ── Heatmap ───────────────────────────────────────────────────────
            st.markdown("#### Performance Heatmap")
            fig_hm = cr_CG_utils.plot_machine_fit_heatmap(tool_fit)
            st.plotly_chart(fig_hm, use_container_width=True, key=f"dd_heatmap{key_suffix}")

            # ── Detail table ──────────────────────────────────────────────────
            st.markdown("#### Full Detail Table")
            base_cols = ['machine_id', 'fit_score', 'runs', 'production_hrs', 'total_parts',
                         'cap_efficiency_pct', 'stability_pct', 'efficiency_pct',
                         'improvement_rate', 'avg_ct_sec', 'ct_fluctuation_pct',
                         'slow_loss_parts', 'fast_gain_parts', 'mtbf_min', 'mttr_min',
                         'stop_count', 'downtime_hrs']
            meta_present = [c for c in ['Machine Maker','Machine Tonnage (ton)','Plant ID','Line']
                            if c in tool_fit.columns]
            dd_display = tool_fit[['machine_id'] + meta_present +
                                  [c for c in base_cols if c != 'machine_id' and c in tool_fit.columns]
                                 ].rename(columns={
                'machine_id':'Machine','fit_score':'Fit Score','runs':'Runs',
                'production_hrs':'Prod Hrs','total_parts':'Parts',
                'cap_efficiency_pct':'Cap Eff %','stability_pct':'Stability %',
                'efficiency_pct':'Efficiency %','improvement_rate':'Perf Trend (pp)',
                'avg_ct_sec':'Avg CT (s)','ct_fluctuation_pct':'CT Fluctuation%',
                'slow_loss_parts':'Slow Loss','fast_gain_parts':'Fast Gain',
                'mtbf_min':'MTBF (min)','mttr_min':'MTTR (min)',
                'stop_count':'Stops','downtime_hrs':'Downtime (h)',
                'Machine Tonnage (ton)':'Tonnage',
            })
            st.dataframe(dd_display, use_container_width=True, hide_index=True)

            # ── Copy group bar compare ────────────────────────────────────────
            if grp_name and siblings:
                st.markdown(f"#### Copy Group Compare — {grp_name}")
                all_in_group = [dd_tool] + siblings
                group_fit = fit_df[fit_df['tool_id'].isin(all_in_group)].copy()
                palette = [C['blue'], C['green'], C['orange']]
                fig_cmp = go.Figure()
                for i, tid in enumerate(all_in_group):
                    tdf = group_fit[group_fit['tool_id'] == tid].sort_values('machine_id')
                    if tdf.empty: continue
                    fig_cmp.add_trace(go.Bar(
                        name=tid, x=tdf['machine_id'], y=tdf['fit_score'],
                        marker_color=palette[i % len(palette)], opacity=0.85,
                        text=tdf['fit_score'].round(0).astype(int), textposition='outside',
                    ))
                fig_cmp.update_layout(
                    barmode='group', title=f"Fit Score by Machine — {grp_name}",
                    xaxis_title="Machine", yaxis_title="Fit Score (0–100)",
                    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
                )
                st.plotly_chart(fig_cmp, use_container_width=True, key=f"dd_cmp{key_suffix}")


if __name__ == "__main__":
    main()

