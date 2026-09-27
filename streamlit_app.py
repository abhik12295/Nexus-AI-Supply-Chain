from __future__ import annotations

from pathlib import Path
import json

import streamlit as st
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

from services.critic_service import CriticService  # noqa: E402
from services.decision_service import DecisionService  # noqa: E402
from services.decision_packet_service import DecisionPacketService  # noqa: E402
from services.nemotron_service import (  # noqa: E402
    NemotronConfigurationError,
    NemotronResponseError,
    NemotronService,
)
from services.nexus_api import NexusAPI, NexusAPIError  # noqa: E402
from services.recovery_planner import RecoveryPlanner  # noqa: E402
from services.replay_service import DecisionReplayService  # noqa: E402
from services.telemetry_service import TelemetryService  # noqa: E402
from services.simulation_service import RecoverySimulationService  # noqa: E402
from services.what_if_service import WhatIfService  # noqa: E402
from services.tavily_service import (  # noqa: E402
    TavilyConfigurationError,
    TavilyEvidenceService,
    TavilySearchError,
)
from ui.dashboard import (  # noqa: E402
    build_affected_frame,
    render_ai_brief,
    render_critic_review,
    render_final_decision,
    render_header,
    render_incident_panel,
    render_metrics,
    render_network_map,
    render_recovery_plan,
    render_decision_replay,
    render_what_if_result,
    render_stage8_command_center,
    render_shipment_table,
)

st.set_page_config(
    page_title="NEXUS · AI Supply Chain Crisis Commander",
    page_icon="◇",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(
    f"<style>{(ROOT / 'ui' / 'styles' / 'nexus.css').read_text(encoding='utf-8')}</style>",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=30, show_spinner=False)
def load_nexus_data(api_url: str):
    api = NexusAPI(api_url)
    health = api.health()
    shipments = api.shipments(1200)
    incidents = api.incidents()
    if not incidents:
        raise NexusAPIError("NEXUS API returned no incidents.")
    incident = incidents[0]
    analysis = api.incident_analysis(incident["incident_id"])
    return health, shipments, incidents, incident, analysis


def clear_ai_state() -> None:
    for key in (
        "nemotron_result",
        "recovery_planner_result",
        "recovery_simulation_result",
        "critic_evidence_result",
        "critic_review_result",
        "final_decision_result",
        "human_approval_record",
    ):
        st.session_state.pop(key, None)


def clear_challenge_state() -> None:
    for key in (
        "critic_evidence_result",
        "critic_review_result",
        "final_decision_result",
        "human_approval_record",
    ):
        st.session_state.pop(key, None)


def clear_decision_state() -> None:
    for key in ("final_decision_result", "human_approval_record"):
        st.session_state.pop(key, None)


def main() -> None:
    render_header()
    st.markdown(
        """
        <div class="page-intro">
          <div class="page-kicker">GLOBAL OPERATIONS · COMMAND CENTER</div>
          <div class="page-title">Operational picture</div>
          <div class="page-copy">NEXUS now closes the loop with runtime telemetry, deployment checks, a judge-ready demo path, and an exportable evidence-backed decision packet.</div>
        </div>
        <div class="stage-banner">
          <div class="left">BUILD STAGE 08 · FINAL POLISH + DEMO READINESS</div>
          <div class="right">CORE LOOP ✓ &nbsp;&nbsp; REPLAY ✓ &nbsp;&nbsp; WHAT-IF ✓ &nbsp;&nbsp; DEMO READY</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    api_url = st.sidebar.text_input("NEXUS API URL", value="http://127.0.0.1:8000")
    nemotron = NemotronService()
    planner = RecoveryPlanner(nemotron)
    simulator = RecoverySimulationService()
    tavily = TavilyEvidenceService()
    critic = CriticService(nemotron)
    decision_agent = DecisionService(nemotron)
    replay_service = DecisionReplayService()
    what_if_service = WhatIfService()
    telemetry_service = TelemetryService()
    packet_service = DecisionPacketService()

    st.sidebar.markdown("---")
    st.sidebar.caption("AI RUNTIME")
    st.sidebar.write(f"**Model:** `{nemotron.model}`")
    st.sidebar.write(f"**Nebius key:** {'configured ✓' if nemotron.configured else 'missing'}")
    st.sidebar.markdown("---")
    st.sidebar.caption("EVIDENCE RUNTIME")
    st.sidebar.write(f"**Tavily key:** {'configured ✓' if tavily.configured else 'missing'}")
    st.sidebar.caption(
        "Stage 5 uses a small set of live public searches to challenge assumptions. "
        "The core shipment incident remains synthetic."
    )
    st.sidebar.markdown("---")
    st.sidebar.caption("DECISION RUNTIME")
    st.sidebar.caption("Stage 6 reuses the Stage 5 Tavily snapshot by default: 0 additional searches.")
    st.sidebar.markdown("---")
    st.sidebar.caption("EXPLAINABILITY LAB")
    st.sidebar.caption("Stage 7 Replay + What-If uses 0 Nemotron calls and 0 Tavily searches.")

    if st.sidebar.button("Refresh operational data", use_container_width=True):
        st.cache_data.clear()
        clear_ai_state()
        st.rerun()

    try:
        _, shipments, incidents, incident, analysis = load_nexus_data(api_url)
    except NexusAPIError as exc:
        st.error(str(exc))
        st.code("source .venv/bin/activate\npython -m uvicorn app.main:app --reload", language="bash")
        st.stop()

    render_metrics(
        analysis["total_shipments"],
        len(incidents),
        analysis["exposed_shipments"],
        analysis["critical_exposed"],
    )

    current_ai = st.session_state.get("nemotron_result")
    current_plan = st.session_state.get("recovery_planner_result")
    current_simulation = st.session_state.get("recovery_simulation_result")
    current_evidence = st.session_state.get("critic_evidence_result")
    current_critic = st.session_state.get("critic_review_result")
    current_decision = st.session_state.get("final_decision_result")
    current_approval = st.session_state.get("human_approval_record")

    st.markdown("<div style='height:.65rem'></div>", unsafe_allow_html=True)
    status_col, analyze_col, plan_col, critic_col, decide_col = st.columns(
        [2.0, 0.82, 1.0, 0.92, 0.88],
        vertical_alignment="center",
    )

    with status_col:
        if current_approval:
            approval_status = current_approval.get("status", "RECORDED")
            st.success(f"Human gate recorded · {approval_status}")
        elif current_decision:
            decision_status = current_decision.get("decision", {}).get("decision_status", "HOLD_FOR_HUMAN_VALIDATION")
            if decision_status == "READY_FOR_HUMAN_APPROVAL":
                st.success("Stage 6 decision ready · awaiting explicit human approval")
            else:
                st.warning("Stage 6 decision: HOLD FOR HUMAN VALIDATION · approval remains locked")
        elif current_critic:
            verdict = current_critic.get("review", {}).get("verdict", "CAUTION")
            st.info(f"Stage 5 complete · critic verdict: {verdict} · generate the Stage 6 decision")
        elif current_plan and current_simulation:
            if tavily.configured:
                st.info(
                    f"Simulation leader: {current_simulation['leader_name']}. "
                    "Challenge it with Tavily evidence before final decision."
                )
            else:
                st.warning("Stage 4 is complete. Add TAVILY_API_KEY to .env to unlock the Stage 5 Critic Agent.")
        elif current_ai:
            st.info("Incident analysis is ready. Generate recovery scenarios and deterministic simulation first.")
        elif nemotron.configured:
            st.info("Run Nemotron analysis first; later stages unlock sequentially.")
        else:
            st.warning("Add NEBIUS_API_KEY to .env before running the AI workflow.")

    with analyze_col:
        run_ai = st.button(
            "Run Analysis" if not current_ai else "Refresh Analysis",
            type="secondary" if current_ai else "primary",
            use_container_width=True,
            disabled=not nemotron.configured,
        )

    with plan_col:
        run_plan = st.button(
            "Generate Recovery Plan",
            type="primary" if current_ai and not current_plan else "secondary",
            use_container_width=True,
            disabled=not bool(current_ai) or not nemotron.configured,
        )

    with critic_col:
        run_critic = st.button(
            "Challenge Leader" if not current_critic else "Refresh Challenge",
            type="primary" if current_plan and current_simulation and not current_critic else "secondary",
            use_container_width=True,
            disabled=not bool(current_plan and current_simulation) or not nemotron.configured or not tavily.configured,
        )

    with decide_col:
        run_decision = st.button(
            "Final Decision" if not current_decision else "Refresh Decision",
            type="primary" if current_critic and not current_decision else "secondary",
            use_container_width=True,
            disabled=not bool(current_critic and current_evidence) or not nemotron.configured,
        )

    if run_ai:
        try:
            with st.spinner("Nemotron is analyzing deterministic incident evidence..."):
                result = nemotron.analyze_incident(incident, analysis, shipments)
            st.session_state["nemotron_result"] = result.model_dump()
            st.session_state.pop("recovery_planner_result", None)
            st.session_state.pop("recovery_simulation_result", None)
            clear_challenge_state()
            st.rerun()
        except (NemotronConfigurationError, NemotronResponseError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Nebius/Nemotron analysis call failed: {type(exc).__name__}: {exc}")

    if run_plan and current_ai:
        try:
            with st.spinner("Nemotron is generating bounded recovery scenarios..."):
                planner_result = planner.plan(
                    incident=incident,
                    analysis=analysis,
                    shipments=shipments,
                    incident_brief=current_ai["brief"],
                )
            with st.spinner("Python is simulating delay, cost, risk and SLA trade-offs..."):
                simulation_result = simulator.simulate(
                    plan=planner_result.plan,
                    incident=incident,
                    analysis=analysis,
                    shipments=shipments,
                )
            st.session_state["recovery_planner_result"] = planner_result.model_dump()
            st.session_state["recovery_simulation_result"] = simulation_result.model_dump()
            clear_challenge_state()
            st.rerun()
        except (NemotronConfigurationError, NemotronResponseError, ValueError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Stage 4 planning/simulation failed: {type(exc).__name__}: {exc}")

    if run_critic and current_ai and current_plan and current_simulation:
        try:
            leader_id = current_simulation["leader_strategy_id"]
            leader_strategy = next(
                row for row in current_plan["plan"]["strategies"] if row["strategy_id"] == leader_id
            )
            with st.spinner("Tavily is collecting a live public evidence snapshot for the simulation leader..."):
                evidence_result = tavily.collect_for_strategy(
                    strategy=leader_strategy,
                    incident=incident,
                    shipments=shipments,
                )
            with st.spinner("Nemotron Critic is challenging assumptions against the evidence..."):
                critic_result = critic.review(
                    plan=current_plan["plan"],
                    simulation=current_simulation,
                    incident=incident,
                    incident_brief=current_ai["brief"],
                    evidence_bundle=evidence_result.model_dump(),
                )
            st.session_state["critic_evidence_result"] = evidence_result.model_dump()
            st.session_state["critic_review_result"] = critic_result.model_dump()
            clear_decision_state()
            st.rerun()
        except StopIteration:
            st.error("Could not resolve the Stage 4 simulation leader strategy.")
        except (
            TavilyConfigurationError,
            TavilySearchError,
            NemotronConfigurationError,
            NemotronResponseError,
            ValueError,
        ) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Stage 5 critic workflow failed: {type(exc).__name__}: {exc}")


    if run_decision and current_ai and current_plan and current_simulation and current_evidence and current_critic:
        try:
            with st.spinner("Nemotron is synthesizing simulation, critic findings, and the existing evidence snapshot..."):
                decision_result = decision_agent.decide(
                    plan=current_plan["plan"],
                    simulation=current_simulation,
                    critic_result=current_critic,
                    evidence_bundle=current_evidence,
                    incident_brief=current_ai["brief"],
                )
            st.session_state["final_decision_result"] = decision_result.model_dump()
            st.session_state.pop("human_approval_record", None)
            st.rerun()
        except (NemotronConfigurationError, NemotronResponseError, ValueError) as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error(f"Stage 6 final-decision workflow failed: {type(exc).__name__}: {exc}")

    affected_frame = build_affected_frame(shipments, analysis["impacts"])
    st.markdown("<div style='height:.75rem'></div>", unsafe_allow_html=True)

    f1, f2, f3 = st.columns([1, 1, 2])
    with f1:
        mode_filter = st.selectbox(
            "Mode",
            ["All modes", "AIR", "ROAD", "OCEAN", "RAIL"],
            label_visibility="collapsed",
        )
    with f2:
        priority_filter = st.selectbox(
            "Priority",
            ["All priorities", "CRITICAL", "HIGH", "STANDARD"],
            label_visibility="collapsed",
        )
    with f3:
        st.markdown(
            '<div class="filter-note">FILTERS APPLY TO THE AFFECTED-SHIPMENT VIEW</div>',
            unsafe_allow_html=True,
        )

    filtered = affected_frame.copy()
    if mode_filter != "All modes":
        filtered = filtered[filtered["Mode"] == mode_filter]
    if priority_filter != "All priorities":
        filtered = filtered[filtered["Priority"] == priority_filter]

    selected_id = st.session_state.get("shipment_selector") or st.session_state.get("selected_shipment_id")
    exposed_ids = set(filtered["Shipment"].tolist())

    map_col, incident_col = st.columns([2.15, 0.85], gap="large")
    with map_col:
        st.markdown(
            '<div class="panel-title"><strong>OPERATIONAL NETWORK</strong><span>EXPOSED ROUTES · SELECT A SHIPMENT BELOW</span></div>',
            unsafe_allow_html=True,
        )
        render_network_map(shipments, exposed_ids, incident, selected_id)
    with incident_col:
        render_incident_panel(
            incident,
            analysis,
            ai_ready=bool(current_ai),
            plan_ready=bool(current_plan and current_simulation),
            challenge_ready=bool(current_critic),
            decision_ready=bool(current_decision),
            approved=bool(current_approval and current_approval.get("status") == "APPROVED"),
        )

    if current_ai:
        st.markdown("<div style='height:.9rem'></div>", unsafe_allow_html=True)
        render_ai_brief(current_ai)

    if current_plan and current_simulation:
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        render_recovery_plan(current_plan, current_simulation)
    elif current_ai:
        st.markdown("<div style='height:.85rem'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="plan-placeholder">
              <div class="section-kicker">RECOVERY PLANNING UNLOCKED</div>
              <strong>Generate three recovery scenarios</strong>
              <span>Nemotron proposes bounded scenarios; the simulator calculates every numeric outcome.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if current_evidence and current_critic:
        st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
        render_critic_review(current_evidence, current_critic)

        if current_decision:
            st.markdown("<div style='height:1rem'></div>", unsafe_allow_html=True)
            approval_action = render_final_decision(
                decision_result=current_decision,
                planner_result=current_plan,
                simulation_result=current_simulation,
                critic_result=current_critic,
                evidence_result=current_evidence,
                approval_record=current_approval,
            )
            if approval_action:
                from datetime import datetime, timezone
                st.session_state["human_approval_record"] = {
                    "status": approval_action,
                    "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
                    "note": (
                        "Human operator approved the synthetic recovery plan for demo/review."
                        if approval_action == "APPROVED"
                        else "Human operator returned the synthetic recovery plan for review."
                    ),
                }
                st.rerun()
        else:
            st.markdown("<div style='height:.85rem'></div>", unsafe_allow_html=True)
            st.markdown(
                """
                <div class="plan-placeholder">
                  <div class="section-kicker">FINAL DECISION UNLOCKED</div>
                  <strong>Generate the evidence-backed Stage 6 decision</strong>
                  <span>Stage 6 reuses the Stage 5 evidence snapshot and performs zero additional Tavily searches by default.</span>
                </div>
                """,
                unsafe_allow_html=True,
            )
    elif current_plan and current_simulation:
        st.markdown("<div style='height:.85rem'></div>", unsafe_allow_html=True)
        message = (
            "Tavily is configured. Challenge the Stage 4 simulation leader before moving to final decision."
            if tavily.configured
            else "Add TAVILY_API_KEY to .env to unlock evidence-backed challenge review."
        )
        st.markdown(
            f"""
            <div class="plan-placeholder">
              <div class="section-kicker">CRITIC REVIEW UNLOCKED</div>
              <strong>Challenge the simulation leader</strong>
              <span>{message}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


    if current_decision:
        st.markdown("<div style='height:1.1rem'></div>", unsafe_allow_html=True)
        st.markdown(
            """
            <div class="stage7-header">
              <div>
                <div class="section-kicker">STAGE 7 · DECISION REPLAY + WHAT-IF LAB</div>
                <div class="stage7-title">Inspect the decision. Then stress-test the priorities.</div>
                <div class="stage7-copy">
                  Replay shows how each NEXUS component contributed to the final gate. What-If Mode re-ranks the same
                  deterministic Stage 4 outcomes under alternate business priorities without calling Nemotron or Tavily.
                </div>
              </div>
              <div class="stage7-zero">0 NEW AI CALLS · 0 NEW SEARCHES</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        replay = replay_service.build(
            incident=incident,
            analysis=analysis,
            ai_result=current_ai,
            planner_result=current_plan,
            simulation_result=current_simulation,
            evidence_result=current_evidence,
            critic_result=current_critic,
            decision_result=current_decision,
            approval_record=current_approval,
        ).model_dump()

        replay_tab, whatif_tab = st.tabs(["Decision Replay", "What-If Lab"])

        with replay_tab:
            selected_replay_step = st.slider(
                "Replay step",
                min_value=1,
                max_value=6,
                value=6,
                step=1,
                key="stage7_replay_step",
            )
            render_decision_replay(replay, selected_replay_step)

        with whatif_tab:
            preset = st.selectbox(
                "Decision priority preset",
                list(what_if_service.PRESETS.keys()) + ["Custom"],
                index=0,
                key="stage7_whatif_preset",
            )

            if preset == "Custom":
                wc1, wc2, wc3, wc4 = st.columns(4)
                with wc1:
                    delay_weight = st.slider("Delay", 0, 100, 35, key="whatif_delay")
                with wc2:
                    cost_weight = st.slider("Cost", 0, 100, 20, key="whatif_cost")
                with wc3:
                    risk_weight = st.slider("Risk", 0, 100, 30, key="whatif_risk")
                with wc4:
                    sla_weight = st.slider("SLA", 0, 100, 15, key="whatif_sla")
                requested_weights = {
                    "delay": delay_weight,
                    "cost": cost_weight,
                    "risk": risk_weight,
                    "sla": sla_weight,
                }
                st.caption("Custom values are normalized automatically to 100%.")
            else:
                requested_weights = what_if_service.PRESETS[preset]

            what_if_result = what_if_service.rescore(
                simulation=current_simulation,
                weights=requested_weights,
            ).model_dump()
            render_what_if_result(
                result=what_if_result,
                current_decision=current_decision,
                current_critic=current_critic,
            )


    if current_decision:
        telemetry = telemetry_service.summarize(
            ai_result=current_ai,
            planner_result=current_plan,
            evidence_result=current_evidence,
            critic_result=current_critic,
            decision_result=current_decision,
        )
        readiness = telemetry_service.readiness(
            backend_health=health,
            nemotron_configured=nemotron.configured,
            tavily_configured=tavily.configured,
            telemetry=telemetry,
            decision_result=current_decision,
        )
        packet = packet_service.build(
            incident=incident,
            analysis=analysis,
            ai_result=current_ai,
            planner_result=current_plan,
            simulation_result=current_simulation,
            evidence_result=current_evidence,
            critic_result=current_critic,
            decision_result=current_decision,
            approval_record=current_approval,
            telemetry=telemetry.model_dump(),
        )

        st.markdown("<div style='height:1.15rem'></div>", unsafe_allow_html=True)
        render_stage8_command_center(
            telemetry=telemetry.model_dump(),
            readiness=readiness.model_dump(),
            decision_packet_json=json.dumps(packet, indent=2, default=str),
        )

    st.markdown("<div style='height:.85rem'></div>", unsafe_allow_html=True)
    st.markdown(
        '<div class="panel-title"><strong>AFFECTED SHIPMENTS</strong><span>DETERMINISTIC IMPACT ENGINE OUTPUT</span></div>',
        unsafe_allow_html=True,
    )
    selected = render_shipment_table(filtered)
    if selected:
        st.session_state["selected_shipment_id"] = selected

    st.caption(
        "Stage 8 is a zero-call productization layer. Telemetry, readiness checks, the judge flow, and the exported "
        "decision packet are derived from existing workflow state. They do not invoke Nemotron, spend Tavily credits, "
        "change the Stage 6 decision, or execute logistics actions."
    )


if __name__ == "__main__":
    main()
