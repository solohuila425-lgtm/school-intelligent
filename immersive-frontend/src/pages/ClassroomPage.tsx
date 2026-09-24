import React, { useCallback, useEffect, useRef, useState } from "react";
import { useParams, Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { SocketProvider } from "../context/SocketContext";
import { SceneContainer } from "../canvas-3d/SceneContainer";
import { TeacherDashboard } from "../components/TeacherDashboard";
import { StudentDashboard } from "../components/StudentDashboard";

const CRDT_SERVER_URL = import.meta.env.VITE_CRDT_SERVER_URL ?? "";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
interface SuggestedComponent { component_type: "object3d" | "formula" | "highlight"; payload: Record<string, unknown>; }
interface TeacherResponseData { message?: string; destination?: "chat" | "board"; }
interface AgentResultItem { agent_name: string; ok: boolean; data?: TeacherResponseData; }
interface AgentResult { stream_id?: string; core_pipeline?: { ui_component?: SuggestedComponent | null }; agent_results?: AgentResultItem[]; }
interface SuggestionProposal { id: string; component: SuggestedComponent; }
type PromptStatus = "idle" | "submitting" | "awaiting-result" | "ready" | "failed";

export function ClassroomPage() {
  const { user } = useAuth();
  const { classroomId } = useParams<{ classroomId: string }>();
  const [suggestion, setSuggestion] = useState<SuggestionProposal | null>(null);
  const [chatMessage, setChatMessage] = useState<string | null>(null);
  const [promptStatus, setPromptStatus] = useState<PromptStatus>("idle");
  const handledSuggestionIds = useRef(new Set<string>());
  if (!user) return null;
  if (!classroomId) return <Navigate to="/aulas" replace />;
  const canUseAgents = user.role === "teacher" || user.role === "admin";
  const loadSuggestions = useCallback(async () => {
    if (!canUseAgents) return;
    const response = await fetch(`${API_BASE_URL}/agents/results?session_id=${encodeURIComponent(classroomId)}`, { headers: { Authorization: `Bearer ${user.token}` } });
    if (!response.ok) return;
    const results = await response.json() as AgentResult[];
    const result = results.find((entry) => entry.stream_id && !handledSuggestionIds.current.has(entry.stream_id) && (entry.core_pipeline?.ui_component || entry.agent_results?.some((item) => item.agent_name === "teacher_response_agent" && item.ok && item.data?.destination === "chat")));
    const component = result?.core_pipeline?.ui_component;
    const teacherResponse = result?.agent_results?.find((item) => item.agent_name === "teacher_response_agent" && item.ok)?.data;
    if (result?.stream_id && teacherResponse?.destination === "chat" && teacherResponse.message) {
      handledSuggestionIds.current.add(result.stream_id);
      setChatMessage(teacherResponse.message);
      setPromptStatus("idle");
    } else if (component && result?.stream_id) { setChatMessage(teacherResponse?.message ?? null); setSuggestion({ id: result.stream_id, component }); setPromptStatus("ready"); }
  }, [canUseAgents, classroomId, user.token]);
  useEffect(() => {
    void loadSuggestions();
    const timer = window.setInterval(() => void loadSuggestions(), 3000);
    return () => window.clearInterval(timer);
  }, [loadSuggestions]);
  const requestSuggestion = useCallback(async (rawText: string) => {
    setPromptStatus("submitting");
    try {
      const response = await fetch(`${API_BASE_URL}/agents/events/transcript`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${user.token}` }, body: JSON.stringify({ session_id: classroomId, raw_text: rawText, priority: "high" }) });
      if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail ?? "The agents rejected the request."); }
      setPromptStatus("awaiting-result");
    } catch (error) { setPromptStatus("failed"); throw error; }
  }, [classroomId, user.token]);
  const resolveSuggestion = useCallback((suggestionId: string) => { handledSuggestionIds.current.add(suggestionId); setSuggestion(null); setPromptStatus("idle"); }, []);
  const auditPublication = useCallback(async (component: SuggestedComponent) => {
    const response = await fetch(`${API_BASE_URL}/agents/board-publications`, { method: "POST", headers: { "Content-Type": "application/json", Authorization: `Bearer ${user.token}` }, body: JSON.stringify({ classroom_id: classroomId, component_type: component.component_type, component_payload: component.payload }) });
    if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail ?? "Publication approval could not be recorded."); }
  }, [classroomId, user.token]);
  return <SocketProvider roomId={classroomId} serverUrl={CRDT_SERVER_URL} authToken={user.token}><div style={{ display: "flex", height: "100vh" }}><div style={{ flex: 1 }}><SceneContainer /></div><div style={{ width: 320 }}>{canUseAgents ? <TeacherDashboard suggestion={suggestion} chatMessage={chatMessage} onRequestSuggestion={requestSuggestion} onAuditPublication={auditPublication} onResolveSuggestion={resolveSuggestion} promptStatus={promptStatus} /> : <StudentDashboard apiBaseUrl={API_BASE_URL} authToken={user.token} studentId={user.userId} />}</div></div></SocketProvider>;
}
