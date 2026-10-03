from __future__ import annotations

from datetime import datetime
import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st


def render_header() -> None:
    st.markdown(
        """
        <div class="nexus-header">
          <div class="brand-row">
            <div class="brand-lockup">
              <div class="brand-mark"><span>◇</span></div>
              <div>
                <div class="brand-title">NEXUS</div>
                <div class="brand-subtitle">AI SUPPLY CHAIN CRISIS COMMANDER</div>
              </div>
            </div>
            <div class="system-live">● SYSTEM ONLINE</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _metric_card(label: str, value: str, detail: str, tone: str = "") -> None:
    tone_class = f" metric-{tone}" if tone else ""
    st.markdown(
        f"""
        <div class="metric-card{tone_class}">
          <div class="metric-label">{label}</div>
          <div class="metric-value">{value}</div>
          <div class="metric-detail">{detail}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_metrics(total_shipments: int, incident_count: int, exposed_shipments: int, critical_exposed: int) -> None:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _metric_card("ACTIVE SHIPMENTS", f"{total_shipments:,}", "Synthetic global network")
    with c2:
        _metric_card("ACTIVE INCIDENTS", f"{incident_count:02d}", "Signals under assessment", "warning")
    with c3:
        _metric_card("AT RISK", f"{exposed_shipments:,}", "Deterministic exposure", "risk")
    with c4:
        _metric_card("CRITICAL EXPOSURE", f"{critical_exposed:,}", "Priority shipments", "critical")


def _route_trace(shipment: dict, exposed: bool = False, highlighted: bool = False) -> go.Scattergeo:
    origin = shipment["origin"]
    destination = shipment["destination"]
    if highlighted:
        color, width, opacity = "#6ee7d8", 3.2, 1.0
    elif exposed:
        color, width, opacity = "rgba(255,178,74,0.48)", 1.15, 0.85
    else:
        color, width, opacity = "rgba(127,161,186,0.18)", 0.65, 0.45
    return go.Scattergeo(
        lon=[origin["lon"], destination["lon"]],
        lat=[origin["lat"], destination["lat"]],
        mode="lines",
        line={"width": width, "color": color},
        opacity=opacity,
        hoverinfo="text",
        text=f'{shipment["shipment_id"]}: {origin["code"]} → {destination["code"]}',
        showlegend=False,
    )


def render_network_map(
    shipments: list[dict],
    exposed_ids: set[str],
    incident: dict,
    selected_shipment_id: str | None,
) -> None:
    fig = go.Figure()
    exposed = [s for s in shipments if s["shipment_id"] in exposed_ids]
    regular = [s for s in shipments if s["shipment_id"] not in exposed_ids]

    for shipment in regular[:40]:
        fig.add_trace(_route_trace(shipment))
    for shipment in exposed[:120]:
        fig.add_trace(
            _route_trace(
                shipment,
                exposed=True,
                highlighted=shipment["shipment_id"] == selected_shipment_id,
            )
        )

    hubs: dict[str, dict] = {}
    for shipment in shipments:
        hubs[shipment["origin"]["code"]] = shipment["origin"]
        hubs[shipment["destination"]["code"]] = shipment["destination"]
    hub_list = list(hubs.values())

    fig.add_trace(
        go.Scattergeo(
            lon=[h["lon"] for h in hub_list],
            lat=[h["lat"] for h in hub_list],
            mode="markers+text",
            text=[h["code"] for h in hub_list],
            textposition="top center",
            marker={
                "size": [11 if h["code"] == "MEM" else 7 for h in hub_list],
                "color": ["#ff5f57" if h["code"] == "MEM" else "#91a9ba" for h in hub_list],
                "line": {"width": 1, "color": "#14232d"},
            },
            hovertext=[f'{h["city"]}, {h["country"]}' for h in hub_list],
            hoverinfo="text",
            showlegend=False,
        )
    )
    fig.add_trace(
        go.Scattergeo(
            lon=[incident["lon"]],
            lat=[incident["lat"]],
            mode="markers",
            marker={
                "size": 28,
                "color": "rgba(255,95,87,0.18)",
                "line": {"width": 2, "color": "#ff5f57"},
            },
            hovertext=[incident["title"]],
            hoverinfo="text",
            showlegend=False,
        )
    )
    fig.update_geos(
        projection_type="natural earth",
        showcoastlines=True,
        coastlinecolor="#263946",
        showland=True,
        landcolor="#0c151b",
        showocean=True,
        oceancolor="#081016",
        showlakes=True,
        lakecolor="#081016",
        showcountries=True,
        countrycolor="#243743",
        bgcolor="#081016",
        lataxis_showgrid=True,
        lonaxis_showgrid=True,
        lataxis_gridcolor="rgba(120,150,170,0.08)",
        lonaxis_gridcolor="rgba(120,150,170,0.08)",
    )
    fig.update_layout(
        height=535,
        margin={"l": 0, "r": 0, "t": 10, "b": 0},
        paper_bgcolor="#081016",
        plot_bgcolor="#081016",
        geo_bgcolor="#081016",
        hoverlabel={"bgcolor": "#101c24", "font_color": "#eaf2f6"},
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False, "scrollZoom": True})


def _pct_bar(value: float, label: str) -> str:
    pct = max(0, min(100, round(value * 100)))
    return (
        f'<div class="progress-wrap"><div class="progress-label"><span>{label}</span>'
        f'<strong>{pct}%</strong></div><div class="progress-track">'
        f'<div class="progress-fill" style="width:{pct}%"></div></div></div>'
    )


def render_incident_panel(
    incident: dict,
    analysis: dict,
    ai_ready: bool = False,
    plan_ready: bool = False,
    challenge_ready: bool = False,
    decision_ready: bool = False,
    approved: bool = False,
) -> None:
    detected_raw = incident.get("detected_at", "")
    try:
        detected_text = datetime.fromisoformat(detected_raw.replace("Z", "+00:00")).strftime("%d %b %Y · %H:%M UTC")
    except Exception:
        detected_text = str(detected_raw)
    modes = " · ".join(str(mode).upper() for mode in incident.get("affected_modes", []))
    st.markdown(
        f"""
        <div class="incident-card">
          <div class="section-kicker">INCIDENT INTELLIGENCE</div>
          <div class="incident-id">⚠ {incident.get('incident_id', 'UNKNOWN')}</div>
          <div class="incident-title">{incident.get('title', 'Active incident')}</div>
          <div class="incident-meta">
            <span>{incident.get('incident_type', '').replace('_', ' ').title()}</span>
            <span>{modes}</span>
            <span>{incident.get('expected_duration_hours', 0)}H EXPECTED</span>
          </div>
          {_pct_bar(float(incident.get('severity', 0)), 'SEVERITY')}
          {_pct_bar(float(incident.get('confidence', 0)), 'CONFIDENCE')}
          <div class="incident-facts">
            <div><span>Radius</span><strong>{incident.get('radius_km', 0):,.0f} km</strong></div>
            <div><span>Detected</span><strong>{detected_text}</strong></div>
            <div><span>Source</span><strong>{incident.get('source', 'unknown')}</strong></div>
          </div>
          <div class="impact-summary"><span>IMPACT ENGINE</span><strong>COMPLETE</strong></div>
          <div class="impact-line">✓ {analysis.get('exposed_shipments', 0):,} exposed shipments identified</div>
          <div class="impact-line">✓ {analysis.get('critical_exposed', 0):,} critical shipments prioritized</div>
          <div class="impact-line">✓ Geospatial + mode matching complete</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-kicker response-kicker">NEXUS RESPONSE</div>', unsafe_allow_html=True)
    if approved:
        stages = [
            ("01", "DETECT", "complete", "Incident signal loaded"),
            ("02", "IMPACT", "complete", "Exposure calculated"),
            ("03", "ANALYZE", "complete", "Nemotron incident brief ready"),
            ("04", "PLAN", "complete", "Recovery scenarios simulated"),
            ("05", "CHALLENGE", "complete", "Leader challenged with public evidence"),
            ("06", "DECIDE", "complete", "Human approval recorded"),
        ]
    elif decision_ready:
        stages = [
            ("01", "DETECT", "complete", "Incident signal loaded"),
            ("02", "IMPACT", "complete", "Exposure calculated"),
            ("03", "ANALYZE", "complete", "Nemotron incident brief ready"),
            ("04", "PLAN", "complete", "Recovery scenarios simulated"),
            ("05", "CHALLENGE", "complete", "Leader challenged with public evidence"),
            ("06", "DECIDE", "complete", "Decision generated · human gate applies"),
        ]
    elif challenge_ready:
        stages = [
            ("01", "DETECT", "complete", "Incident signal loaded"),
            ("02", "IMPACT", "complete", "Exposure calculated"),
            ("03", "ANALYZE", "complete", "Nemotron incident brief ready"),
            ("04", "PLAN", "complete", "Recovery scenarios simulated"),
            ("05", "CHALLENGE", "complete", "Leader challenged with public evidence"),
            ("06", "DECIDE", "current", "Generate final decision + human gate"),
        ]
    elif plan_ready:
        stages = [
            ("01", "DETECT", "complete", "Incident signal loaded"),
            ("02", "IMPACT", "complete", "Exposure calculated"),
            ("03", "ANALYZE", "complete", "Nemotron incident brief ready"),
            ("04", "PLAN", "complete", "Recovery scenarios simulated"),
            ("05", "CHALLENGE", "current", "Run Tavily evidence + Nemotron critic"),
            ("06", "DECIDE", "locked", "Evidence-backed action"),
        ]
    else:
        stages = [
            ("01", "DETECT", "complete", "Incident signal loaded"),
            ("02", "IMPACT", "complete", "Exposure calculated"),
            ("03", "ANALYZE", "complete" if ai_ready else "current", "Nemotron incident brief ready" if ai_ready else "Run Nemotron analysis"),
            ("04", "PLAN", "current" if ai_ready else "locked", "Generate + simulate recovery scenarios" if ai_ready else "Recovery strategies"),
            ("05", "CHALLENGE", "locked", "Critic agent"),
            ("06", "DECIDE", "locked", "Evidence-backed action"),
        ]
    rows = []
    for number, name, status, detail in stages:
        icon = "✓" if status == "complete" else "●" if status == "current" else "○"
        badge = "COMPLETE" if status == "complete" else "NEXT" if status == "current" else "LOCKED"
        rows.append(
            f'<div class="agent-row agent-{status}"><div class="agent-number">{number}</div>'
            f'<div class="agent-main"><div class="agent-name">{icon}&nbsp;&nbsp;{name}</div>'
            f'<div class="agent-detail">{detail}</div></div><div class="agent-badge">{badge}</div></div>'
        )
    st.markdown('<div class="agent-list">' + ''.join(rows) + '</div>', unsafe_allow_html=True)


def build_affected_frame(shipments: list[dict], impacts: list[dict]) -> pd.DataFrame:
    by_id = {shipment["shipment_id"]: shipment for shipment in shipments}
    rows = []
    for impact in impacts:
        if not impact.get("exposed"):
            continue
        shipment = by_id.get(impact["shipment_id"])
        if shipment is None:
            continue
        eta_raw = shipment.get("eta_ts", "")
        try:
            eta = datetime.fromisoformat(eta_raw.replace("Z", "+00:00")).strftime("%d %b · %H:%M")
        except Exception:
            eta = eta_raw
        rows.append(
            {
                "Shipment": shipment["shipment_id"],
                "Route": f'{shipment["origin"]["code"]} → {shipment["destination"]["code"]}',
                "Mode": shipment["mode"].upper(),
                "Priority": shipment["priority"].upper(),
                "Status": shipment["status"].replace("_", " ").title(),
                "ETA (UTC)": eta,
                "Risk": round(float(impact["risk_score"]) * 100, 1),
                "Distance km": impact.get("nearest_distance_km"),
                "Reason": impact.get("exposure_reason") or "",
                "Base Cost USD": round(float(shipment["base_cost_usd"]), 2),
            }
        )
    return pd.DataFrame(rows)


def render_shipment_table(frame: pd.DataFrame) -> str | None:
    if frame.empty:
        st.info("No shipments match the current filters.")
        return None
    st.markdown(f'<div class="table-count">{len(frame):,} SHIPMENTS IN CURRENT VIEW</div>', unsafe_allow_html=True)
    selected = st.selectbox(
        "Inspect affected shipment",
        options=frame["Shipment"].tolist(),
        index=0,
        label_visibility="collapsed",
        key="shipment_selector",
    )
    display = frame[["Shipment", "Route", "Mode", "Priority", "Status", "ETA (UTC)", "Risk", "Distance km"]].copy()
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        height=355,
        column_config={
            "Risk": st.column_config.ProgressColumn("Risk", min_value=0, max_value=100, format="%.1f%%"),
            "Distance km": st.column_config.NumberColumn("Distance km", format="%.1f"),
        },
    )
    row = frame[frame["Shipment"] == selected].iloc[0]
    st.markdown(
        f"""
        <div class="shipment-detail">
          <div><span>SELECTED</span><strong>{row['Shipment']} · {row['Route']}</strong></div>
          <div><span>EXPOSURE</span><strong>{row['Reason']}</strong></div>
          <div><span>BASE COST</span><strong>${row['Base Cost USD']:,.2f}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return selected



def render_ai_brief(result: dict) -> None:
    brief = result["brief"]
    confidence = max(0, min(100, round(float(brief.get("confidence", 0)) * 100)))
    actions = brief.get("priority_actions", [])
    watch_items = brief.get("watch_items", [])
    assumptions = brief.get("assumptions", [])
    evidence = brief.get("evidence_used", [])

    def items(rows: list[str], empty: str) -> str:
        if not rows:
            return f'<div class="ai-list-empty">{empty}</div>'
        return "".join(f'<div class="ai-list-item"><span>›</span><div>{row}</div></div>' for row in rows)

    st.markdown(
        f"""
        <div class="ai-brief">
          <div class="ai-brief-header">
            <div>
              <div class="section-kicker">NEMOTRON INCIDENT ANALYSIS</div>
              <div class="ai-title">Operational brief</div>
            </div>
            <div class="ai-provider">NVIDIA NEMOTRON · NEBIUS TOKEN FACTORY</div>
          </div>
          <div class="ai-summary">{brief.get('executive_summary', '')}</div>
          <div class="ai-assessment-label">OPERATIONAL ASSESSMENT</div>
          <div class="ai-assessment">{brief.get('operational_assessment', '')}</div>
          <div class="ai-confidence-row"><span>MODEL CONFIDENCE</span><strong>{confidence}%</strong></div>
          <div class="progress-track"><div class="ai-confidence-fill" style="width:{confidence}%"></div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown('<div class="ai-subpanel"><div class="ai-subtitle">PRIORITY TRIAGE ACTIONS</div>' + items(actions, "No priority actions returned.") + '</div>', unsafe_allow_html=True)
    with c2:
        st.markdown('<div class="ai-subpanel"><div class="ai-subtitle">WATCH ITEMS</div>' + items(watch_items, "No watch items returned.") + '</div>', unsafe_allow_html=True)

    with st.expander("AI assumptions and evidence", expanded=False):
        e1, e2 = st.columns(2)
        with e1:
            st.markdown("**Assumptions / information gaps**")
            for row in assumptions:
                st.markdown(f"- {row}")
            if not assumptions:
                st.caption("None returned.")
        with e2:
            st.markdown("**Evidence cited by the analysis agent**")
            for row in evidence:
                st.markdown(f"- {row}")
            if not evidence:
                st.caption("None returned.")

    st.markdown(
        f"""
        <div class="ai-runtime-meta">
          <span>MODEL <strong>{result.get('model', 'unknown')}</strong></span>
          <span>LATENCY <strong>{result.get('latency_seconds', 0):.2f}s</strong></span>
          <span>TOKENS <strong>{result.get('total_tokens') or 'n/a'}</strong></span>
        </div>
        """,
        unsafe_allow_html=True,
    )



def render_recovery_plan(planner_result: dict, simulation_result: dict) -> None:
    """Render Stage 4 plan + deterministic simulation without calling the model."""
    plan = planner_result["plan"]
    strategies_by_id = {row["strategy_id"]: row for row in plan.get("strategies", [])}
    metrics = simulation_result.get("metrics", [])
    leader_id = simulation_result.get("leader_strategy_id")
    weights = simulation_result.get("weights", {})

    st.markdown(
        f"""
        <div class="recovery-header">
          <div>
            <div class="section-kicker">STAGE 4 · RECOVERY PLANNING</div>
            <div class="recovery-title">Recovery scenarios + deterministic simulation</div>
            <div class="recovery-summary">{html.escape(plan.get("planning_summary", ""))}</div>
          </div>
          <div class="recovery-badge">NEMOTRON PLANNER → PYTHON SIMULATOR</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(3, gap="medium")
    for idx, metric in enumerate(metrics[:3]):
        strategy = strategies_by_id.get(metric["strategy_id"], {})
        is_leader = metric["strategy_id"] == leader_id
        leader_class = " recovery-card-leader" if is_leader else ""
        hub = strategy.get("routing_hub") or "CURRENT PATH"
        cost = float(metric.get("added_cost_usd", 0))
        residual = float(metric.get("residual_risk", 0)) * 100
        score = float(metric.get("composite_score", 0))
        delay = float(metric.get("average_recovery_delay_hours", 0))
        sla = float(metric.get("sla_exposure_pct", 0))
        protected = float(metric.get("critical_protected_pct", 0))
        rerouted = int(metric.get("rerouted_shipments", 0))
        label = metric.get("score_label", "")
        assumptions = strategy.get("assumptions", [])
        priority_counts = metric.get("target_priority_counts", {}) or {}
        critical_targeted = int(priority_counts.get("critical", 0))
        high_targeted = int(priority_counts.get("high", 0))
        standard_targeted = int(priority_counts.get("standard", 0))
        affected = int(metric.get("affected_shipments", 0))

        strategy_type = str(metric.get("strategy_type", ""))
        if strategy_type == "hold_monitor":
            deterministic_scope = (
                f"Keep all {affected:,} exposed shipments on their current paths; "
                "no shipments are rerouted in this scenario."
            )
        elif strategy_type == "reroute_all":
            deterministic_scope = (
                f"Reroute all {rerouted:,} exposed shipments through {hub}. "
                "Target count is calculated from the deterministic impact set."
            )
        elif strategy_type == "protect_priority":
            non_targeted = max(0, affected - rerouted)
            deterministic_scope = (
                f"Reroute {rerouted:,} priority shipments "
                f"({critical_targeted:,} Critical + {high_targeted:,} High) through {hub}; "
                f"{non_targeted:,} non-targeted exposed shipments remain on current paths."
            )
        else:
            deterministic_scope = html.escape(str(strategy.get("description", "")))

        assumptions_html = "".join(
            f'<div class="recovery-assumption">• {html.escape(str(item))}</div>'
            for item in assumptions[:3]
        ) or '<div class="recovery-assumption">• No additional assumptions returned.</div>'

        with cols[idx]:
            st.markdown(
                f"""
                <div class="recovery-card{leader_class}">
                  <div class="recovery-card-top">
                    <span>{html.escape(str(metric.get("strategy_id", "")))}</span>
                    <strong>{html.escape(label)}</strong>
                  </div>
                  <div class="recovery-card-name">{html.escape(str(metric.get("name", "")))}</div>
                  <div class="recovery-route">{html.escape(str(metric.get("strategy_type", "")).replace("_", " ").upper())} · {html.escape(str(hub))}</div>
                  <div class="recovery-description">{html.escape(deterministic_scope)}</div>
                  <div class="recovery-metrics-grid">
                    <div><span>AVG DELAY</span><strong>{delay:.1f}h</strong></div>
                    <div><span>ADDED COST</span><strong>${cost:,.0f}</strong></div>
                    <div><span>RESIDUAL RISK</span><strong>{residual:.1f}%</strong></div>
                    <div><span>SLA EXPOSURE</span><strong>{sla:.1f}%</strong></div>
                    <div><span>CRITICAL PROTECTED</span><strong>{protected:.0f}%</strong></div>
                    <div><span>REROUTED</span><strong>{rerouted:,}</strong></div>
                  </div>
                  <div class="recovery-score-row"><span>COMPOSITE SCORE · LOWER IS BETTER</span><strong>{score:.3f}</strong></div>
                  <div class="recovery-score-track"><div style="width:{max(2.0, min(100.0, score * 100)):.1f}%"></div></div>
                  <div class="recovery-rationale-label">PLANNER RATIONALE</div>
                  <div class="recovery-rationale">{html.escape(str(strategy.get("rationale", "")))}</div>
                  <div class="recovery-rationale-label">ASSUMPTIONS TO VALIDATE</div>
                  {assumptions_html}
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown(
        f"""
        <div class="simulation-strip">
          <div><span>SIMULATION LEADER</span><strong>{html.escape(str(simulation_result.get("leader_name", "")))}</strong></div>
          <div><span>DELAY WEIGHT</span><strong>{float(weights.get("delay", 0))*100:.0f}%</strong></div>
          <div><span>COST WEIGHT</span><strong>{float(weights.get("cost", 0))*100:.0f}%</strong></div>
          <div><span>RISK WEIGHT</span><strong>{float(weights.get("risk", 0))*100:.0f}%</strong></div>
          <div><span>SLA WEIGHT</span><strong>{float(weights.get("sla", 0))*100:.0f}%</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.info(
        simulation_result.get(
            "methodology_note",
            "Stage 4 metrics are deterministic synthetic scenario estimates.",
        ),
        icon="ℹ️",
    )

    with st.expander("Planning assumptions and runtime evidence", expanded=False):
        left, right = st.columns(2)
        with left:
            st.markdown("**Plan-level assumptions**")
            rows = plan.get("planning_assumptions", [])
            if rows:
                for row in rows:
                    st.markdown(f"- {row}")
            else:
                st.caption("None returned.")
        with right:
            st.markdown("**Planner runtime**")
            st.markdown(f"- Model: `{planner_result.get('model', 'unknown')}`")
            st.markdown(f"- Provider: {planner_result.get('provider', 'Nebius Token Factory')}")
            st.markdown(f"- Latency: {float(planner_result.get('latency_seconds', 0)):.2f}s")
            st.markdown(f"- Tokens: {planner_result.get('total_tokens') or 'n/a'}")



def render_critic_review(evidence_result: dict, critic_result: dict) -> None:
    """Render Stage 5 evidence snapshot and Nemotron critic assessment."""
    review = critic_result.get("review", {})
    verdict = str(review.get("verdict", "CAUTION")).upper()
    verdict_class = verdict.lower()
    confidence = max(0, min(100, round(float(review.get("confidence", 0)) * 100)))
    assessments = review.get("assessments", [])
    alternative = review.get("suggested_alternative_strategy_id")

    st.markdown(
        f"""
        <div class="critic-header critic-{html.escape(verdict_class)}">
          <div>
            <div class="section-kicker">STAGE 5 · CRITIC + EVIDENCE VERIFICATION</div>
            <div class="critic-title">Challenge review · {html.escape(str(review.get('strategy_name', 'Simulation leader')))}</div>
            <div class="critic-summary">{html.escape(str(review.get('summary', '')))}</div>
          </div>
          <div class="critic-verdict">{html.escape(verdict)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if review.get("critical_issue"):
        st.markdown(
            f'<div class="critic-critical"><span>CRITICAL ISSUE</span><strong>{html.escape(str(review.get("critical_issue")))}</strong></div>',
            unsafe_allow_html=True,
        )

    cols = st.columns(3, gap="medium")
    for idx, item in enumerate(assessments[:6]):
        status = str(item.get("status", "UNVERIFIED")).upper()
        status_class = status.lower()
        source_ids = item.get("source_ids", []) or []
        source_text = " · ".join(source_ids) if source_ids else "NO DIRECT SOURCE"
        with cols[idx % 3]:
            st.markdown(
                f"""
                <div class="critic-claim critic-claim-{html.escape(status_class)}">
                  <div class="critic-claim-top"><span>{html.escape(status)}</span><strong>{html.escape(source_text)}</strong></div>
                  <div class="critic-claim-title">{html.escape(str(item.get('claim', '')))}</div>
                  <div class="critic-claim-copy">{html.escape(str(item.get('explanation', '')))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    next_action = html.escape(str(review.get("next_action", "")))
    alt_text = f"Inspect {html.escape(str(alternative))} in Stage 6" if alternative else "No alternate strategy nominated"
    st.markdown(
        f"""
        <div class="critic-next">
          <div><span>NEXT ACTION</span><strong>{next_action}</strong></div>
          <div><span>ALTERNATIVE FOR REVIEW</span><strong>{alt_text}</strong></div>
          <div><span>CRITIC CONFIDENCE</span><strong>{confidence}%</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    sources = evidence_result.get("sources", []) or []
    queries = evidence_result.get("queries", []) or []
    limitations = review.get("evidence_limitations", []) or []
    with st.expander("Tavily evidence snapshot + critic limitations", expanded=False):
        st.markdown(
            f"**Evidence snapshot:** {evidence_result.get('search_count', len(queries))} searches · "
            f"{evidence_result.get('source_count', len(sources))} unique sources · "
            f"{float(evidence_result.get('latency_seconds', 0)):.2f}s"
        )
        st.caption(evidence_result.get("synthetic_context_note", ""))
        if sources:
            for source in sources:
                source_id = source.get("source_id", "E?")
                title = source.get("title", "Untitled source")
                url = source.get("url", "")
                query_kind = source.get("query_kind", "evidence")
                st.markdown(f"**{source_id} · {query_kind}** — [{title}]({url})")
                content = str(source.get("content", "")).strip()
                if content:
                    st.caption(content[:600] + ("…" if len(content) > 600 else ""))
        else:
            st.warning("Tavily returned no usable public evidence sources.")

        st.markdown("**Evidence limitations**")
        if limitations:
            for item in limitations:
                st.markdown(f"- {item}")
        else:
            st.caption("No additional limitations returned by the Critic Agent.")

    st.markdown(
        f"""
        <div class="critic-runtime-meta">
          <span>TAVILY <strong>{evidence_result.get('source_count', 0)} SOURCES / {evidence_result.get('search_count', 0)} SEARCHES</strong></span>
          <span>EVIDENCE LATENCY <strong>{float(evidence_result.get('latency_seconds', 0)):.2f}s</strong></span>
          <span>CRITIC MODEL <strong>{html.escape(str(critic_result.get('model', 'unknown')))}</strong></span>
          <span>CRITIC LATENCY <strong>{float(critic_result.get('latency_seconds', 0)):.2f}s</strong></span>
          <span>TOKENS <strong>{critic_result.get('total_tokens') or 'n/a'}</strong></span>
        </div>
        """,
        unsafe_allow_html=True,
    )



def render_final_decision(
    decision_result: dict,
    planner_result: dict,
    simulation_result: dict,
    critic_result: dict,
    evidence_result: dict,
    approval_record: dict | None = None,
) -> str | None:
    """Render Stage 6 final decision and return a human-gate action when clicked."""
    decision = decision_result.get("decision", {})
    gate = decision_result.get("policy_gate", {})
    status = str(decision.get("decision_status", "HOLD_FOR_HUMAN_VALIDATION"))
    ready = status == "READY_FOR_HUMAN_APPROVAL"
    selected_id = decision.get("selected_strategy_id")
    confidence = max(0, min(100, round(float(decision.get("confidence", 0)) * 100)))
    critic_confidence = max(
        0,
        min(
            100,
            round(
                float(
                    critic_result.get("review", {}).get("confidence", 0)
                )
                * 100
            ),
        ),
    )

    strategy_lookup = {
        str(row.get("strategy_id")): row
        for row in planner_result.get("plan", {}).get("strategies", [])
    }
    metric_lookup = {
        str(row.get("strategy_id")): row
        for row in simulation_result.get("metrics", [])
    }

    selected_strategy = strategy_lookup.get(str(selected_id)) if selected_id else None
    selected_metric = metric_lookup.get(str(selected_id)) if selected_id else None

    status_label = "READY FOR HUMAN APPROVAL" if ready else "HOLD FOR HUMAN VALIDATION"
    status_class = "ready" if ready else "hold"
    headline = html.escape(str(decision.get("headline", "Stage 6 decision")))
    summary = html.escape(str(decision.get("summary", "")))

    st.markdown(
        f"""
        <div class="decision-header decision-{status_class}">
          <div>
            <div class="section-kicker">STAGE 6 · FINAL DECISION + HUMAN APPROVAL</div>
            <div class="decision-title">{headline}</div>
            <div class="decision-summary">{summary}</div>
          </div>
          <div class="decision-status">{status_label}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if selected_strategy and selected_metric:
        st.markdown(
            f"""
            <div class="decision-selected">
              <div><span>SELECTED STRATEGY</span><strong>{html.escape(str(selected_strategy.get('name', selected_id)))}</strong></div>
              <div><span>AVG DELAY</span><strong>{float(selected_metric.get('average_recovery_delay_hours', 0)):.1f}h</strong></div>
              <div><span>ADDED COST</span><strong>${float(selected_metric.get('added_cost_usd', 0)):,.0f}</strong></div>
              <div><span>RESIDUAL RISK</span><strong>{float(selected_metric.get('residual_risk', 0))*100:.1f}%</strong></div>
              <div><span>COMPOSITE SCORE</span><strong>{float(selected_metric.get('composite_score', 0)):.3f}</strong></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        leader_name = html.escape(str(simulation_result.get("leader_name", "Simulation leader")))
        st.markdown(
            f"""
            <div class="decision-hold-context">
              <span>CURRENT SIMULATION LEADER</span>
              <strong>{leader_name}</strong>
              <em>Not cleared for execution by the Stage 6 policy gate.</em>
            </div>
            """,
            unsafe_allow_html=True,
        )

    rationale = decision.get("rationale", []) or []
    actions = decision.get("operator_actions", []) or []
    blockers = decision.get("blocking_items", []) or []
    validations = decision.get("human_validation_requirements", []) or []

    def render_rows(rows: list[str], empty: str) -> str:
        if not rows:
            return f'<div class="decision-list-empty">{html.escape(empty)}</div>'
        return "".join(
            f'<div class="decision-list-row"><span>›</span><div>{html.escape(str(row))}</div></div>'
            for row in rows
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown(
            '<div class="decision-panel"><div class="decision-panel-title">DECISION RATIONALE</div>'
            + render_rows(rationale, "No rationale returned.")
            + '</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="decision-panel"><div class="decision-panel-title">OPERATOR NEXT STEPS</div>'
            + render_rows(actions, "No operator actions returned.")
            + '</div>',
            unsafe_allow_html=True,
        )

    if blockers or validations:
        b1, b2 = st.columns(2, gap="large")
        with b1:
            st.markdown(
                '<div class="decision-panel decision-panel-warning"><div class="decision-panel-title">BLOCKING ITEMS</div>'
                + render_rows(blockers, "No blocking items.")
                + '</div>',
                unsafe_allow_html=True,
            )
        with b2:
            st.markdown(
                '<div class="decision-panel decision-panel-warning"><div class="decision-panel-title">HUMAN VALIDATION REQUIRED</div>'
                + render_rows(validations, "No additional human validation required.")
                + '</div>',
                unsafe_allow_html=True,
            )

    evidence_age = gate.get("evidence_age_minutes")
    age_text = "n/a" if evidence_age is None else f"{float(evidence_age):.1f} min"

    if ready:
        confidence_label = "DECISION CONFIDENCE"
        confidence_value = f"{confidence}%"
        gate_label = "POLICY GATE"
        gate_value = "CLEARED"
    else:
        confidence_label = "STRATEGY SELECTION"
        confidence_value = "INSUFFICIENT EVIDENCE"
        gate_label = "POLICY GATE"
        gate_value = "HOLD ENFORCED"

    st.markdown(
        f"""
        <div class="decision-meta-strip">
          <div><span>{confidence_label}</span><strong>{confidence_value}</strong></div>
          <div><span>{gate_label}</span><strong>{gate_value}</strong></div>
          <div><span>CRITIC CONFIDENCE</span><strong>{critic_confidence}%</strong></div>
          <div><span>EVIDENCE AGE</span><strong>{age_text}</strong></div>
          <div><span>TAVILY SEARCHES · STAGE 6</span><strong>{decision_result.get('tavily_searches_this_stage', 0)}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if approval_record:
        approval_status = html.escape(str(approval_record.get("status", "RECORDED")))
        recorded = html.escape(str(approval_record.get("recorded_at_utc", "")))
        note = html.escape(str(approval_record.get("note", "")))
        css_class = "approved" if approval_record.get("status") == "APPROVED" else "review"
        st.markdown(
            f"""
            <div class="human-gate-record human-gate-{css_class}">
              <div><span>HUMAN GATE</span><strong>{approval_status}</strong></div>
              <div>{note}</div>
              <small>{recorded}</small>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return None

    st.markdown('<div class="human-gate-title">HUMAN APPROVAL GATE</div>', unsafe_allow_html=True)
    if ready:
        st.caption(
            "Approval records a decision for this synthetic demo only. NEXUS does not execute real shipment changes."
        )
        approve_col, review_col = st.columns(2)
        with approve_col:
            approve = st.button(
                "Approve Synthetic Recovery Plan",
                type="primary",
                use_container_width=True,
                key="stage6_approve",
            )
        with review_col:
            review = st.button(
                "Return for Review",
                type="secondary",
                use_container_width=True,
                key="stage6_review",
            )
        if approve:
            return "APPROVED"
        if review:
            return "RETURNED_FOR_REVIEW"
    else:
        st.warning(
            "Approval is locked because the deterministic Stage 6 policy gate found unresolved material assumptions. "
            "Validate the blocking items or refresh Stage 5 evidence before reconsidering."
        )
        if st.button(
            "Return for Human Review",
            type="secondary",
            use_container_width=True,
            key="stage6_hold_review",
        ):
            return "RETURNED_FOR_REVIEW"

    return None



def render_decision_replay(replay: dict, selected_step: int) -> None:
    stages = replay.get("stages", [])
    if not stages:
        st.info("Decision Replay is not available yet.")
        return

    # Keep the replay rail as one compact HTML block. Streamlit's Markdown
    # parser can terminate a multiline HTML block when nested markup contains
    # blank/indented lines, which causes subsequent <div> tags to appear as text.
    rail = []
    for stage in stages:
        step = int(stage.get("step", 0))
        active = " replay-step-active" if step == selected_step else ""
        status = html.escape(str(stage.get("status", "PENDING")))
        name = html.escape(str(stage.get("name", "")))
        rail.append(
            f'<div class="replay-step{active}">'
            f'<span>{step:02d}</span>'
            f'<strong>{name}</strong>'
            f'<em>{status}</em>'
            f'</div>'
        )

    replay_rail_html = '<div class="replay-rail">' + ''.join(rail) + '</div>'
    st.markdown(replay_rail_html, unsafe_allow_html=True)

    stage = next((row for row in stages if int(row.get("step", 0)) == selected_step), stages[0])
    facts = stage.get("facts", []) or []
    runtime = stage.get("runtime", []) or []

    facts_html = "".join(
        f'<div class="replay-fact"><span>›</span><div>{html.escape(str(item))}</div></div>'
        for item in facts
    ) or '<div class="replay-empty">No stage facts available.</div>'
    runtime_html = "".join(
        f'<div class="replay-runtime-row">{html.escape(str(item))}</div>'
        for item in runtime
    ) or '<div class="replay-empty">No external runtime call at this stage.</div>'

    st.markdown(
        f"""
        <div class="replay-detail">
          <div class="replay-main">
            <div class="section-kicker">REPLAY STEP {int(stage.get("step", 0)):02d} · {html.escape(str(stage.get("name", "")))}</div>
            <div class="replay-headline">{html.escape(str(stage.get("headline", "")))}</div>
            <div class="replay-summary">{html.escape(str(stage.get("summary", "")))}</div>
            <div class="replay-facts">{facts_html}</div>
          </div>
          <div class="replay-system">
            <span>SYSTEM OF RECORD</span>
            <strong>{html.escape(str(stage.get("system", "")))}</strong>
            <div class="replay-runtime">{runtime_html}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_what_if_result(
    result: dict,
    current_decision: dict | None,
    current_critic: dict | None,
) -> None:
    weights = result.get("weights", {})
    changed = bool(result.get("leader_changed"))
    leader_name = html.escape(str(result.get("what_if_leader_name", "Unknown")))
    original_name = html.escape(str(result.get("original_leader_name", "Unknown")))

    if changed:
        headline = f"What-If leader changed: {original_name} → {leader_name}"
        status = "NEW LEADER · REQUIRES FRESH CHALLENGE"
        status_class = "changed"
    else:
        headline = f"What-If leader remains {leader_name}"
        status = "LEADER UNCHANGED"
        status_class = "same"

    decision_status = (
        (current_decision or {}).get("decision", {}).get("decision_status", "NOT RUN")
    )
    critic_verdict = (
        (current_critic or {}).get("review", {}).get("verdict", "NOT RUN")
    )

    st.markdown(
        f"""
        <div class="whatif-header whatif-{status_class}">
          <div>
            <div class="section-kicker">DETERMINISTIC WHAT-IF RESULT</div>
            <div class="whatif-title">{headline}</div>
            <div class="whatif-copy">
              Re-ranked from the same Stage 4 delay, cost, residual-risk, and SLA outputs.
              No new routes or external facts were generated.
            </div>
          </div>
          <div class="whatif-status">{status}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="whatif-weight-strip">
          <div><span>DELAY</span><strong>{float(weights.get("delay", 0))*100:.0f}%</strong></div>
          <div><span>COST</span><strong>{float(weights.get("cost", 0))*100:.0f}%</strong></div>
          <div><span>RISK</span><strong>{float(weights.get("risk", 0))*100:.0f}%</strong></div>
          <div><span>SLA</span><strong>{float(weights.get("sla", 0))*100:.0f}%</strong></div>
          <div><span>NEMOTRON CALLS</span><strong>{int(result.get("nemotron_calls", 0))}</strong></div>
          <div><span>TAVILY SEARCHES</span><strong>{int(result.get("tavily_searches", 0))}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    cols = st.columns(len(result.get("metrics", [])) or 1, gap="large")
    for col, row in zip(cols, result.get("metrics", [])):
        delta = float(row.get("score_delta", 0))
        if abs(delta) < 0.0005:
            delta = 0.0
        delta_text = "0.000" if delta == 0 else f"{delta:+.3f}"
        with col:
            st.markdown(
                f"""
                <div class="whatif-card {'whatif-card-leader' if int(row.get('rank', 0)) == 1 else ''}">
                  <div class="whatif-card-top">
                    <span>RANK {int(row.get("rank", 0))}</span>
                    <strong>{html.escape(str(row.get("strategy_id", "")))}</strong>
                  </div>
                  <div class="whatif-card-name">{html.escape(str(row.get("name", "")))}</div>
                  <div class="whatif-score"><span>WHAT-IF SCORE</span><strong>{float(row.get("what_if_score", 0)):.3f}</strong></div>
                  <div class="whatif-score"><span>ORIGINAL SCORE</span><strong>{float(row.get("original_score", 0)):.3f}</strong></div>
                  <div class="whatif-delta"><span>SCORE Δ</span><strong>{delta_text}</strong></div>
                  <div class="whatif-mini">Delay {float(row.get("average_recovery_delay_hours", 0)):.1f}h ·
                  Cost ${float(row.get("added_cost_usd", 0)):,.0f} ·
                  Risk {float(row.get("residual_risk", 0))*100:.1f}% ·
                  SLA {float(row.get("sla_exposure_pct", 0)):.1f}%</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if changed:
        st.warning(
            "The What-If leader differs from the strategy challenged in Stage 5. "
            "This result is exploratory only; it needs its own evidence challenge before it can enter the final decision path."
        )
    else:
        st.info(
            f"The leader did not change. Existing critic verdict: {critic_verdict}. "
            f"Existing Stage 6 status: {str(decision_status).replace('_', ' ')}. "
            "What-If Mode never overrides those controls."
        )

    st.caption(str(result.get("note", "")))



def render_stage8_command_center(
    telemetry: dict,
    readiness: dict,
    decision_packet_json: str,
) -> None:
    st.markdown(
        """
        <div class="stage8-header">
          <div>
            <div class="section-kicker">STAGE 8 · DEMO + DEPLOYMENT READINESS</div>
            <div class="stage8-title">Prove the system, not just the recommendation.</div>
            <div class="stage8-copy">
              Runtime telemetry, guardrail status, evidence usage, and a judge-ready walkthrough are derived from the
              completed NEXUS workflow. No additional model or search calls are made here.
            </div>
          </div>
          <div class="stage8-status">FINAL BUILD</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4, c5 = st.columns(5)
    runtime_cards = [
        ("CORE STAGES", f'{int(telemetry.get("core_stages_complete", 0))}/6'),
        ("NEMOTRON CALLS", str(int(telemetry.get("nemotron_calls", 0)))),
        ("TAVILY SEARCHES", str(int(telemetry.get("tavily_searches", 0)))),
        ("TOTAL TOKENS", f'{int(telemetry.get("total_tokens", 0)):,}'),
        ("MODEL LATENCY", f'{float(telemetry.get("total_model_latency_seconds", 0)):.1f}s'),
    ]
    for col, (label, value) in zip([c1, c2, c3, c4, c5], runtime_cards):
        with col:
            st.markdown(
                f"""
                <div class="stage8-kpi">
                  <span>{label}</span>
                  <strong>{value}</strong>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:.6rem'></div>", unsafe_allow_html=True)
    left, right = st.columns([1.05, 1.3], gap="large")

    with left:
        st.markdown(
            f"""
            <div class="readiness-head">
              <div>
                <span>DEPLOYMENT / DEMO READINESS</span>
                <strong>{html.escape(str(readiness.get("overall_status", "UNKNOWN")))}</strong>
              </div>
              <em>{int(readiness.get("ready_count", 0))}/{int(readiness.get("total_count", 0))} checks ready</em>
            </div>
            """,
            unsafe_allow_html=True,
        )
        # Render the readiness list as one compact HTML block. Multiline
        # nested fragments can be interpreted as Markdown text by Streamlit,
        # which exposes raw <div> tags in the deployed app.
        check_html = []
        for check in readiness.get("checks", []):
            state = str(check.get("status", "CHECK"))
            css = "ready" if state == "READY" else "check"
            label = html.escape(str(check.get("label", "")))
            detail = html.escape(str(check.get("detail", "")))
            safe_state = html.escape(state)
            check_html.append(
                f'<div class="readiness-row readiness-{css}">'
                f'<div><strong>{label}</strong><span>{detail}</span></div>'
                f'<em>{safe_state}</em>'
                f'</div>'
            )
        readiness_html = '<div class="readiness-list">' + ''.join(check_html) + '</div>'
        st.markdown(readiness_html, unsafe_allow_html=True)

    with right:
        st.markdown(
            """
            <div class="demo-script">
              <div class="demo-script-title">3-MINUTE JUDGE FLOW</div>
              <div class="demo-step"><span>00:00–00:25</span><strong>Problem + live command center</strong><p>“A severe-weather event hits Memphis. NEXUS instantly identifies the 234 exposed shipments and 18 critical shipments before any LLM reasoning.”</p></div>
              <div class="demo-step"><span>00:25–01:05</span><strong>Analyze + plan</strong><p>Show the Nemotron incident brief, then the three recovery strategies. Emphasize that Python—not the LLM—calculates delay, cost, residual risk, SLA exposure, and ranking.</p></div>
              <div class="demo-step"><span>01:05–01:45</span><strong>Challenge the leader</strong><p>Show Tavily evidence and the Nemotron Critic. Highlight a contradicted or unverified ATL assumption.</p></div>
              <div class="demo-step"><span>01:45–02:20</span><strong>Guardrail + human gate</strong><p>Show that Stage 6 refuses to approve the simulation leader and returns HOLD FOR HUMAN VALIDATION.</p></div>
              <div class="demo-step"><span>02:20–02:50</span><strong>Replay + What-If</strong><p>Replay the six stages, then switch to Cost First to show that business priorities can change the scenario leader without spending more AI/search credits.</p></div>
              <div class="demo-step"><span>02:50–03:00</span><strong>Close</strong><p>“NEXUS does not just recommend. It simulates, challenges, verifies, explains, and knows when to stop for a human.”</p></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="stage8-runtime-strip">
          <div><span>FINAL STATUS</span><strong>{html.escape(str(telemetry.get("decision_status", "NOT RUN")).replace("_", " "))}</strong></div>
          <div><span>CRITIC VERDICT</span><strong>{html.escape(str(telemetry.get("critic_verdict", "NOT RUN")))}</strong></div>
          <div><span>POLICY GATE</span><strong>{html.escape(str(telemetry.get("policy_gate", "NOT RUN")))}</strong></div>
          <div><span>STAGE 7 AI CALLS</span><strong>{int(telemetry.get("stage7_nemotron_calls", 0))}</strong></div>
          <div><span>STAGE 7 SEARCHES</span><strong>{int(telemetry.get("stage7_tavily_searches", 0))}</strong></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.download_button(
        "Export Decision Packet (JSON)",
        data=decision_packet_json,
        file_name="nexus_decision_packet.json",
        mime="application/json",
        use_container_width=True,
        key="stage8_export_packet",
    )
